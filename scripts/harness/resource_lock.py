"""本模块负责执行 `resource_lock` 对应的确定性仓库检查。

不负责产品业务处理；由 harness 命令行或受控收口流程调用。"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import socket
import stat
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.harness.primary_session import ensure_private_directory, resolve_runtime_root

if TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_STALE_SECONDS = 3600.0
_POLL_SECONDS = 0.1


@dataclass(frozen=True)
class _LockSnapshot:
    """保存一次不跟随符号链接的 lock 文件读取结果。"""

    state: str
    data: dict[str, Any] | None
    device: int
    inode: int
    uid: int
    mtime: float


def _fsync_directory(path: Path) -> None:
    """同步目录项；不支持目录 fsync 的平台保持保守但不破坏已发布锁。"""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
            raise
    finally:
        os.close(descriptor)


def _atomic_publish_lock(path: Path, payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """先完整写入并 fsync 临时文件，再用 hard-link 原子 no-clobber 发布。"""
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temp,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    published = False
    try:
        metadata = os.fstat(descriptor)
        complete = {
            **payload,
            "schemaVersion": 2,
            "ownerUid": metadata.st_uid,
            "lockDevice": metadata.st_dev,
            "lockInode": metadata.st_ino,
        }
        encoded = (json.dumps(complete, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        offset = 0
        while offset < len(encoded):
            offset += os.write(descriptor, encoded[offset:])
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        try:
            os.link(temp, path, follow_symlinks=False)
            published = True
            _fsync_directory(path.parent)
        except FileExistsError:
            published = False
        return published, complete
    finally:
        os.close(descriptor)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _read_lock_snapshot(path: Path) -> _LockSnapshot | None:
    """读取并复核 lock inode、UID 与 fencing metadata，区分损坏和旧格式。"""
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        return _LockSnapshot(
            "unsafe", None, before.st_dev, before.st_ino, before.st_uid, before.st_mtime
        )
    current_uid = getattr(os, "geteuid", os.getuid)()
    if before.st_uid != current_uid:
        return _LockSnapshot(
            "foreign-uid", None, before.st_dev, before.st_ino, before.st_uid, before.st_mtime
        )
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        opened = os.fstat(descriptor)
        if opened.st_dev != before.st_dev or opened.st_ino != before.st_ino:
            return None
        raw = bytearray()
        while len(raw) <= 64 * 1024:
            chunk = os.read(descriptor, min(8192, 64 * 1024 + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        finished = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if finished.st_dev != before.st_dev or finished.st_ino != before.st_ino:
        return None
    if not raw:
        state, data = "empty", None
    elif len(raw) > 64 * 1024:
        state, data = "corrupt", None
    else:
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            state, data = "corrupt", None
        else:
            data = decoded if isinstance(decoded, dict) else None
            state = "valid" if data is not None else "corrupt"
    if data is not None:
        required = {
            "fencingToken",
            "ownerUid",
            "lockDevice",
            "lockInode",
            "pid",
            "processStartTime",
        }
        if int(data.get("schemaVersion") or 0) < 2 or not required.issubset(data):
            state = "legacy"
        elif (
            data.get("ownerUid") != before.st_uid
            or data.get("lockDevice") != before.st_dev
            or data.get("lockInode") != before.st_ino
        ):
            state = "fencing-mismatch"
    return _LockSnapshot(state, data, before.st_dev, before.st_ino, before.st_uid, before.st_mtime)


def _same_lock_epoch(path: Path, snapshot: _LockSnapshot, token: str = "") -> bool:
    """复核路径仍指向同一 inode；提供 token 时同时复核 fencing epoch。"""
    current = _read_lock_snapshot(path)
    if current is None or current.device != snapshot.device or current.inode != snapshot.inode:
        return False
    if current.uid != snapshot.uid or current.state in {"unsafe", "foreign-uid"}:
        return False
    return not token or bool(current.data and current.data.get("fencingToken") == token)


class ResourceLockTimeout(TimeoutError):  # noqa: N818
    """命名资源锁在超时前无法取得时抛出。"""

    def __init__(self, resource: str, owner: dict[str, Any] | None, waited_seconds: float):
        """参数：
            resource: 被占用的资源名称。
            owner: 当前 lock 文件中的 owner metadata。
            waited_seconds: 已等待秒数。

        返回：
            初始化后的 timeout 异常。
        """
        super().__init__(f"resource lock busy: {resource}")
        self.resource = resource
        self.owner = owner or {}
        self.waited_seconds = waited_seconds


# 维护 utc now 函数行为。
def _utc_now() -> str:
    """参数：
        当前函数不接收参数。

    返回：
        UTC 时间字符串。
    """
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# 维护 host marker 函数行为。
def _host_marker() -> str:
    """参数：
        当前函数不接收参数。

    返回：
        脱敏后的 host marker。
    """
    raw = f"{socket.gethostname()}:{os.getuid()}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:16]


# 维护 pid start time 函数行为。
def _pid_start_time(pid: int) -> str:
    """参数：
        pid: 进程编号。

    返回：
        进程启动时间标记，无法读取时返回空字符串。
    """
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        try:
            return stat.read_text(encoding="utf-8").split()[21]
        except Exception:
            return ""
    try:
        return str(Path(f"/proc/{pid}").stat().st_ctime_ns)
    except Exception:
        pass
    try:
        # macOS 没有 /proc；使用进程启动时间而不是可复用的 PID 作为身份补充。
        return subprocess.check_output(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return ""


# 维护 process alive 判断。
def process_is_alive(pid: int, expected_start_time: str = "") -> bool:
    """参数：
        pid: 待检查进程编号。
        expected_start_time: 可选进程启动时间标记。

    返回：
        进程仍然活跃且启动时间匹配时返回 true。
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    if expected_start_time:
        current = _pid_start_time(pid)
        return not current or current == expected_start_time
    return True


# 维护 lock root 路径。
def lock_root(repo_root: Path) -> Path:
    """参数：
        repo_root: 仓库根目录。

    返回：
        shared runtime root 下的 locks 目录。
    """
    return resolve_runtime_root(repo_root) / "locks"


# 维护资源安全名称。
def _safe_name(resource: str) -> str:
    """参数：
        resource: 原始资源名称。

    返回：
        可用于 lock 文件名的资源名称。
    """
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in resource) or "resource"


# 构建 owner metadata。
def owner_metadata(
    *,
    run_id: str = "",
    client: str = "",
    session_id: str = "",
    worktree_id: str = "",
    target: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """参数：
        run_id: 主运行编号。
        client: 客户端名称。
        session_id: 会话编号。
        worktree_id: 工作树编号。
        target: 当前质量目标。
        extra: 额外 metadata。

    返回：
        可写入 lock 文件的 owner metadata。
    """
    data: dict[str, Any] = {
        "schemaVersion": 1,
        "runId": run_id,
        "client": client,
        "sessionId": session_id,
        "worktreeId": worktree_id,
        "target": target,
        "pid": os.getpid(),
        "processStartTime": _pid_start_time(os.getpid()),
        "acquiredAt": _utc_now(),
        "heartbeatAt": _utc_now(),
        "hostMarker": _host_marker(),
        "ownerUid": getattr(os, "geteuid", os.getuid)(),
    }
    if extra:
        data.update(extra)
    return data


@dataclass
class LockAcquireResult:
    """保存 `LockAcquireResult` 的结构化契约数据；字段由所属运行阶段构造并由后续报告读取。"""

    resource: str
    status: str
    path: str
    waitedSeconds: float  # noqa: N815
    owner: dict[str, Any] | None = None


@dataclass
class NamedResourceLock:
    """保存 `NamedResourceLock` 的结构化契约数据；字段由所属运行阶段构造并由后续报告读取。"""

    repo_root: Path
    resource: str
    owner: dict[str, Any]
    stale_seconds: float = DEFAULT_STALE_SECONDS
    acquired: bool = False
    path: Path = field(init=False)
    fencing_token: str = ""
    lock_device: int = 0
    lock_inode: int = 0
    reclaimed_owner: dict[str, Any] = field(default_factory=dict)
    reclaim_audit: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path = lock_root(self.repo_root) / f"{_safe_name(self.resource)}.lock"

    # 维护 read owner 函数行为。
    def read_owner(self) -> dict[str, Any] | None:
        """参数：
            当前函数不接收参数。

        返回：
            当前 lock owner metadata，无法读取时返回 None。
        """
        snapshot = _read_lock_snapshot(self.path)
        return dict(snapshot.data) if snapshot and snapshot.data is not None else None

    # 维护 stale 判断。
    def _is_stale(self, data: dict[str, Any] | None) -> bool:
        """参数：
            data: 资源锁持有者元数据。

        返回：
            lock 可安全回收时返回 true。
        """
        snapshot = _read_lock_snapshot(self.path)
        if snapshot is None or snapshot.state in {"unsafe", "foreign-uid"}:
            return False
        if time.time() - snapshot.mtime < max(0.0, self.stale_seconds):
            return False
        if snapshot.data:
            pid = snapshot.data.get("pid")
            start_time = str(snapshot.data.get("processStartTime") or "")
            if isinstance(pid, int) and pid > 0 and process_is_alive(pid, start_time):
                return False
        if snapshot.state != "valid":
            return True
        data = snapshot.data
        if not data:
            return False
        return True

    # 维护 stale lock 回收。
    def _remove_stale(self) -> bool:
        """参数：
            当前函数不接收参数。

        返回：
            stale lock 已不存在或已删除时返回 true。
        """
        snapshot = _read_lock_snapshot(self.path)
        if snapshot is None:
            return True
        data = snapshot.data
        if not self._is_stale(data):
            return False
        if not _same_lock_epoch(self.path, snapshot):
            return False
        try:
            self.path.unlink()
            self.reclaimed_owner = dict(data or {"lockState": snapshot.state})
            self.reclaim_audit = {
                "event": "RESOURCE_LOCK_RECLAIMED",
                "resource": self.resource,
                "previousState": snapshot.state,
                "previousDevice": snapshot.device,
                "previousInode": snapshot.inode,
                "previousUid": snapshot.uid,
                "reclaimedAt": _utc_now(),
            }
            _fsync_directory(self.path.parent)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False

    # 维护 try acquire 函数行为。
    def try_acquire(self) -> bool:
        """参数：
            当前函数不接收参数。

        返回：
            获取成功时返回 true。
        """
        runtime_root = ensure_private_directory(resolve_runtime_root(self.repo_root))
        ensure_private_directory(self.path.parent, root=runtime_root)
        self._remove_stale()
        payload = dict(self.owner)
        self.fencing_token = uuid.uuid4().hex
        payload.update(
            {
                "resource": self.resource,
                "pid": os.getpid(),
                "processStartTime": _pid_start_time(os.getpid()),
                "acquiredAt": _utc_now(),
                "heartbeatAt": _utc_now(),
                "hostMarker": _host_marker(),
                "fencingToken": self.fencing_token,
                "graceSeconds": max(0.0, self.stale_seconds),
                "reclaimAudit": dict(self.reclaim_audit),
            }
        )
        try:
            published, complete = _atomic_publish_lock(self.path, payload)
        except OSError:
            return False
        if not published:
            return False
        self.lock_device = int(complete["lockDevice"])
        self.lock_inode = int(complete["lockInode"])
        self.acquired = True
        return True

    def acquire(self, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> LockAcquireResult:
        """参数：
            timeout_seconds: 最大等待秒数。

        返回：
            获取成功的 lock 结果。
        """
        started = time.monotonic()
        last_owner: dict[str, Any] | None = None
        while True:
            if self.try_acquire():
                waited = time.monotonic() - started
                return LockAcquireResult(self.resource, "acquired", str(self.path), waited)
            last_owner = self.read_owner()
            waited = time.monotonic() - started
            if waited >= timeout_seconds:
                raise ResourceLockTimeout(self.resource, last_owner, waited)
            time.sleep(_POLL_SECONDS)

    def heartbeat(self) -> None:
        """参数：
            当前函数不接收参数。

        返回：
            无；仅刷新当前进程持有 lock 的 heartbeat timestamp。
        """
        if not self.acquired:
            return
        snapshot = _read_lock_snapshot(self.path)
        if (
            snapshot is None
            or snapshot.device != self.lock_device
            or snapshot.inode != self.lock_inode
        ):
            return
        data = snapshot.data or {}
        if data.get("fencingToken") != self.fencing_token or data.get("pid") != os.getpid():
            return
        # mtime 是无需替换 inode 的 heartbeat；payload 保留首次 heartbeat 供审计。
        os.utime(self.path, None, follow_symlinks=False)

    def release(self) -> None:
        """参数：
            当前函数不接收参数。

        返回：
            无；仅释放当前进程持有的 lock 文件。
        """
        if not self.acquired:
            return
        try:
            snapshot = _read_lock_snapshot(self.path)
            if (
                snapshot is not None
                and snapshot.device == self.lock_device
                and snapshot.inode == self.lock_inode
                and snapshot.data
                and snapshot.data.get("fencingToken") == self.fencing_token
                and snapshot.data.get("pid") == os.getpid()
            ):
                self.path.unlink()
                _fsync_directory(self.path.parent)
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False
            self.fencing_token = ""
            self.lock_device = 0
            self.lock_inode = 0


class ResourceLockSet:
    """按稳定顺序获取多项资源，并按相反顺序释放，避免锁顺序死锁。"""

    def __init__(
        self,
        repo_root: Path,
        resources: Iterable[str],
        owner: dict[str, Any],
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        """参数：
            repo_root: 仓库根目录。
            resources: 待获取的 named resources。
            owner: 写入 lock 文件的 owner metadata。
            timeout_seconds: 整组资源获取的最大等待时间。

        返回：
            初始化后的 ResourceLockSet。
        """
        self.repo_root = repo_root
        self.resources = sorted({resource for resource in resources if resource})
        self.owner = owner
        self.timeout_seconds = timeout_seconds
        self.locks = [NamedResourceLock(repo_root, resource, owner) for resource in self.resources]
        self.results: list[LockAcquireResult] = []

    def acquire(self) -> list[LockAcquireResult]:
        """参数：
            当前函数不接收参数。

        返回：
            按稳定顺序获取到的 lock 结果列表。
        """
        started = time.monotonic()
        try:
            for lock in self.locks:
                remaining = max(0.0, self.timeout_seconds - (time.monotonic() - started))
                self.results.append(lock.acquire(timeout_seconds=remaining))
            return self.results
        except BaseException:
            self.release()
            raise

    def release(self) -> None:
        """参数：
            当前函数不接收参数。

        返回：
            无；按获取逆序释放已经持有的资源锁。
        """
        for lock in reversed(self.locks):
            lock.release()

    def __enter__(self) -> ResourceLockSet:
        """参数：
            当前函数不接收参数。

        返回：
            已获取全部资源的当前资源锁集合。
        """
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """参数：
            exc_type: context manager 异常类型。
            exc: context manager 异常实例。
            tb: 上下文管理器 traceback。

        返回：
            无；确保 finally 风格释放。
        """
        del exc_type, exc, tb
        self.release()


def status(repo_root: Path) -> list[dict[str, Any]]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        当前 lock root 下所有 lock 的 owner 和活跃性摘要。
    """
    root = lock_root(repo_root)
    result: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.lock")):
        try:
            owner = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            owner = {}
        pid = owner.get("pid") if isinstance(owner, dict) else None
        alive = isinstance(pid, int) and process_is_alive(
            pid, str(owner.get("processStartTime") or "")
        )
        result.append({"resource": path.stem, "path": str(path), "alive": alive, "owner": owner})
    return result


def doctor(repo_root: Path) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        lock metadata contract 诊断错误列表。
    """
    errors: list[str] = []
    for item in status(repo_root):
        owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
        for field_name in (
            "runId",
            "client",
            "sessionId",
            "worktreeId",
            "target",
            "pid",
            "acquiredAt",
            "hostMarker",
        ):
            if field_name not in owner:
                errors.append(f"{item['resource']}: missing owner field {field_name}")
    return errors


def main() -> int:
    """参数：
        无；读取命令行参数。

    返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description="Inspect named resource locks")
    parser.add_argument("command", choices=["status", "doctor"])
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    args = parser.parse_args()
    repo_root = Path(args.repo_root)
    if args.command == "status":
        print(json.dumps(status(repo_root), indent=2, ensure_ascii=False))
        return 0
    errors = doctor(repo_root)
    if errors:
        for error in errors:
            print(f"[resource-locks] FAIL {error}")
        return 1
    print("[resource-locks] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
