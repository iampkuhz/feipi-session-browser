"""Named cross-process resource locks for primary-session runtime isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from scripts.harness.primary_session import resolve_runtime_root

DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_STALE_SECONDS = 3600.0
_POLL_SECONDS = 0.1


class ResourceLockTimeout(TimeoutError):
    """Raised when a named resource lock cannot be acquired before timeout."""

    # 维护 __init__ 函数行为。
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
    }
    if extra:
        data.update(extra)
    return data


@dataclass
class LockAcquireResult:
    resource: str
    status: str
    path: str
    waitedSeconds: float
    owner: dict[str, Any] | None = None


@dataclass
class NamedResourceLock:
    repo_root: Path
    resource: str
    owner: dict[str, Any]
    stale_seconds: float = DEFAULT_STALE_SECONDS
    acquired: bool = False
    path: Path = field(init=False)

    # 维护 __post_init__ 函数行为。
    def __post_init__(self) -> None:
        self.path = lock_root(self.repo_root) / f"{_safe_name(self.resource)}.lock"

    # 维护 read owner 函数行为。
    def read_owner(self) -> dict[str, Any] | None:
        """参数：
            当前函数不接收参数。

        返回：
            当前 lock owner metadata，无法读取时返回 None。
        """
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    # 维护 stale 判断。
    def _is_stale(self, data: dict[str, Any] | None) -> bool:
        """参数：
            data: 资源锁持有者元数据。

        返回：
            lock 可安全回收时返回 true。
        """
        if not data:
            return True
        pid = data.get("pid")
        start_time = str(data.get("processStartTime") or "")
        if isinstance(pid, int) and process_is_alive(pid, start_time):
            return False
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return True
        return age >= 0 or age > self.stale_seconds

    # 维护 stale lock 回收。
    def _remove_stale(self) -> bool:
        """参数：
            当前函数不接收参数。

        返回：
            stale lock 已不存在或已删除时返回 true。
        """
        data = self.read_owner()
        if not self._is_stale(data):
            return False
        try:
            self.path.unlink()
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self.owner)
        payload.update(
            {
                "resource": self.resource,
                "pid": os.getpid(),
                "processStartTime": _pid_start_time(os.getpid()),
                "acquiredAt": _utc_now(),
                "heartbeatAt": _utc_now(),
                "hostMarker": _host_marker(),
            }
        )
        self._remove_stale()
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        self.acquired = True
        return True

    # 维护 acquire 函数行为。
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

    # 维护 heartbeat 函数行为。
    def heartbeat(self) -> None:
        """参数：
            当前函数不接收参数。

        返回：
            无；仅刷新当前进程持有 lock 的 heartbeat timestamp。
        """
        if not self.acquired:
            return
        data = self.read_owner() or {}
        if data.get("pid") != os.getpid():
            return
        data["heartbeatAt"] = _utc_now()
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    # 维护 release 函数行为。
    def release(self) -> None:
        """参数：
            当前函数不接收参数。

        返回：
            无；仅释放当前进程持有的 lock 文件。
        """
        if not self.acquired:
            return
        try:
            data = self.read_owner() or {}
            if data.get("pid") in (None, os.getpid()):
                self.path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False


class ResourceLockSet:
    """Acquire multiple resources in stable sorted order and release in reverse order."""

    # 维护 __init__ 函数行为。
    def __init__(self, repo_root: Path, resources: Iterable[str], owner: dict[str, Any], *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
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

    # 维护 acquire 函数行为。
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

    # 维护 release 函数行为。
    def release(self) -> None:
        """参数：
            当前函数不接收参数。

        返回：
            无；按获取逆序释放已经持有的资源锁。
        """
        for lock in reversed(self.locks):
            lock.release()

    # 维护 __enter__ 函数行为。
    def __enter__(self) -> "ResourceLockSet":
        """参数：
            当前函数不接收参数。

        返回：
            已获取全部资源的当前资源锁集合。
        """
        self.acquire()
        return self

    # 维护 __exit__ 函数行为。
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """参数：
            exc_type: context manager 异常类型。
            exc: context manager 异常实例。
            tb: 上下文管理器 traceback。

        返回：
            无；确保 finally 风格释放。
        """
        self.release()


# 维护 status 函数行为。
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
        alive = isinstance(pid, int) and process_is_alive(pid, str(owner.get("processStartTime") or ""))
        result.append({"resource": path.stem, "path": str(path), "alive": alive, "owner": owner})
    return result


# 维护 doctor 函数行为。
def doctor(repo_root: Path) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        lock metadata contract 诊断错误列表。
    """
    errors: list[str] = []
    for item in status(repo_root):
        owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
        for field_name in ("runId", "client", "sessionId", "worktreeId", "target", "pid", "acquiredAt", "hostMarker"):
            if field_name not in owner:
                errors.append(f"{item['resource']}: missing owner field {field_name}")
    return errors


# 维护 main 函数行为。
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
