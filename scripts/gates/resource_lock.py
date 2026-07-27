"""提供 Gate 命令组的跨进程资源锁与 fencing 释放。"""

from __future__ import annotations

import errno
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

from scripts.gates.support import ensure_private_directory, resolve_runtime_root, stable_hash, utc_now

if TYPE_CHECKING:
    from collections.abc import Iterable
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_STALE_SECONDS = 3600.0
_POLL_SECONDS = 0.1


@dataclass(frozen=True)
class _LockSnapshot:
    """保存一次 no-follow 锁读取的 inode、属主与解析状态，供 fencing 复核使用。"""

    state: str
    data: dict[str, Any] | None
    device: int
    inode: int
    uid: int
    mtime: float


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
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
    """通过同目录临时文件和 hard link 无覆盖发布锁；已有 owner 时绝不替换目标。"""
    temp = path.with_name(f'.{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    descriptor = os.open(
        temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600
    )
    published = False
    try:
        metadata = os.fstat(descriptor)
        complete = {
            **payload,
            'schemaVersion': 2,
            'ownerUid': metadata.st_uid,
            'lockDevice': metadata.st_dev,
            'lockInode': metadata.st_ino,
        }
        encoded = (json.dumps(complete, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
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
        return (published, complete)
    finally:
        os.close(descriptor)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _read_lock_snapshot(path: Path) -> _LockSnapshot | None:
    """以 no-follow 方式读取锁及其 inode；符号链接、异主文件和坏 JSON 均标记为不安全。"""
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        return _LockSnapshot(
            'unsafe', None, before.st_dev, before.st_ino, before.st_uid, before.st_mtime
        )
    current_uid = getattr(os, 'geteuid', os.getuid)()
    if before.st_uid != current_uid:
        return _LockSnapshot(
            'foreign-uid', None, before.st_dev, before.st_ino, before.st_uid, before.st_mtime
        )
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
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
        state, data = ('empty', None)
    elif len(raw) > 64 * 1024:
        state, data = ('corrupt', None)
    else:
        try:
            decoded = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            state, data = ('corrupt', None)
        else:
            data = decoded if isinstance(decoded, dict) else None
            state = 'valid' if data is not None else 'corrupt'
    if data is not None:
        required = {
            'fencingToken',
            'ownerUid',
            'lockDevice',
            'lockInode',
            'pid',
            'processStartTime',
        }
        if int(data.get('schemaVersion') or 0) < 2 or not required.issubset(data):
            state = 'legacy'
        elif (
            data.get('ownerUid') != before.st_uid
            or data.get('lockDevice') != before.st_dev
            or data.get('lockInode') != before.st_ino
        ):
            state = 'fencing-mismatch'
    return _LockSnapshot(state, data, before.st_dev, before.st_ino, before.st_uid, before.st_mtime)


def _same_lock_epoch(path: Path, snapshot: _LockSnapshot, token: str = '') -> bool:
    """复核锁路径仍指向同一 inode 与 fencing token，避免旧 owner 删除新锁。"""
    current = _read_lock_snapshot(path)
    if current is None or current.device != snapshot.device or current.inode != snapshot.inode:
        return False
    if current.uid != snapshot.uid or current.state in {'unsafe', 'foreign-uid'}:
        return False
    return not token or bool(current.data and current.data.get('fencingToken') == token)


def read_lock_owner(path: Path) -> dict[str, Any] | None:
    """不跟随符号链接读取当前锁 owner；损坏或外部 UID 锁均不返回可操作数据。"""
    snapshot = _read_lock_snapshot(path)
    return dict(snapshot.data) if snapshot and snapshot.state == 'valid' else None


def release_owned_lock(path: Path, expected: dict[str, Any]) -> bool:
    """复核 owner、inode 与 fencing token 后释放跨进程持有的锁。"""
    snapshot = _read_lock_snapshot(path)
    if snapshot is None or snapshot.state != 'valid' or not snapshot.data:
        return False
    if any(snapshot.data.get(name) != value for name, value in expected.items()):
        return False
    token = str(snapshot.data.get('fencingToken') or '')
    if not token or not _same_lock_epoch(path, snapshot, token):
        return False
    try:
        path.unlink()
        _fsync_directory(path.parent)
        return True
    except OSError:
        return False


class ResourceLockTimeoutError(TimeoutError):
    """表示资源锁在期限内未获取，并保留当前 owner 证据供 Gate 报告。"""

    def __init__(self, resource: str, owner: dict[str, Any] | None, waited_seconds: float):
        super().__init__(f'resource lock busy: {resource}')
        self.resource = resource
        self.owner = owner or {}
        self.waited_seconds = waited_seconds


def _host_marker() -> str:
    raw = f"{socket.gethostname()}:{os.getuid()}"
    return stable_hash(raw)[:16]


def _pid_start_time(pid: int) -> str:
    stat = Path(f'/proc/{pid}/stat')
    if stat.exists():
        try:
            return stat.read_text(encoding='utf-8').split()[21]
        except Exception:
            return ''
    try:
        return str(Path(f'/proc/{pid}').stat().st_ctime_ns)
    except Exception:
        pass
    try:
        return subprocess.check_output(
            ['ps', '-o', 'lstart=', '-p', str(pid)], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return ''


def process_is_alive(pid: int, expected_start_time: str = '') -> bool:
    """同时校验 PID 存活与进程启动时间，防止 PID 复用被误判为原 owner。"""
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


def lock_root(repo_root: Path) -> Path:
    """解析仓库隔离的运行时资源锁目录，并强制属主私有权限。"""
    return resolve_runtime_root(repo_root) / 'locks'


def _safe_name(resource: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in '._-' else '-' for ch in resource) or 'resource'


def owner_metadata(
    *,
    run_id: str = '',
    client: str = '',
    session_id: str = '',
    worktree_id: str = '',
    target: str = '',
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造携带 run、Session、worktree 和进程启动时间的锁 owner 证据。"""
    data: dict[str, Any] = {
        'schemaVersion': 1,
        'runId': run_id,
        'client': client,
        'sessionId': session_id,
        'worktreeId': worktree_id,
        'target': target,
        'pid': os.getpid(),
        'processStartTime': _pid_start_time(os.getpid()),
        'acquiredAt': utc_now(),
        'heartbeatAt': utc_now(),
        'hostMarker': _host_marker(),
        'ownerUid': getattr(os, 'geteuid', os.getuid)(),
    }
    if extra:
        data.update(extra)
    return data


@dataclass
class LockAcquireResult:
    """保存资源锁获取状态、等待时间和冲突 owner，供 executor 写入运行报告。"""

    resource: str
    status: str
    path: str
    waited_seconds: float
    owner: dict[str, Any] | None = None


@dataclass
class FencedFileLock:
    """使用 hard-link no-clobber 发布的排他锁。

    锁发布后，heartbeat/release/reclaim 都必须复核 inode、当前 UID 与
    ``fencingToken``；``strict_scope`` 还阻止 Stop 回收其他 run 的锁。
    """

    path: Path
    owner: dict[str, Any]
    stale_seconds: float = DEFAULT_STALE_SECONDS
    strict_scope: bool = False
    reclaim_event: str = 'RESOURCE_LOCK_RECLAIMED'
    acquired: bool = False
    fencing_token: str = ''
    lock_device: int = 0
    lock_inode: int = 0
    reclaimed_owner: dict[str, Any] = field(default_factory=dict)
    reclaim_audit: dict[str, Any] = field(default_factory=dict)

    def read_owner(self) -> dict[str, Any] | None:
        """读取当前锁 owner；不把不安全或无法解析的文件当作可信 owner。"""
        snapshot = _read_lock_snapshot(self.path)
        return dict(snapshot.data) if snapshot and snapshot.data is not None else None

    def _scope_matches(self, data: dict[str, Any]) -> bool:
        if not self.strict_scope:
            return True
        for name in ('runId', 'sessionId', 'worktreeId'):
            expected, actual = str(self.owner.get(name) or ''), str(data.get(name) or '')
            if actual and (not expected or actual != expected):
                return False
        return True

    def _remove_stale(self) -> bool:
        snapshot = _read_lock_snapshot(self.path)
        if snapshot is None:
            return True
        if snapshot.state in {'unsafe', 'foreign-uid'}:
            return False
        if time.time() - snapshot.mtime < max(0.0, self.stale_seconds):
            return False
        data = snapshot.data or {}
        if not self._scope_matches(data):
            return False
        pid = data.get('pid')
        if (
            isinstance(pid, int)
            and pid > 0
            and process_is_alive(pid, str(data.get('processStartTime') or ''))
        ):
            return False
        if self.strict_scope and snapshot.state == 'valid':
            if any(
                not str(self.owner.get(name) or '') for name in ('runId', 'sessionId', 'worktreeId')
            ):
                return False
        if not _same_lock_epoch(self.path, snapshot):
            return False
        try:
            self.path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        self.reclaimed_owner = dict(data or {'lockState': snapshot.state})
        self.reclaim_audit = {
            'event': self.reclaim_event,
            'previousState': snapshot.state,
            'previousDevice': snapshot.device,
            'previousInode': snapshot.inode,
            'previousUid': snapshot.uid,
            'reclaimedAt': utc_now(),
        }
        _fsync_directory(self.path.parent)
        return True

    def try_acquire(self) -> bool:
        """先按存活与宽限期回收陈旧锁，再以新 fencing token 无覆盖获取。"""
        ensure_private_directory(self.path.parent)
        self._remove_stale()
        self.fencing_token = uuid.uuid4().hex
        payload = {
            **self.owner,
            'pid': os.getpid(),
            'processStartTime': _pid_start_time(os.getpid()),
            'fencingToken': self.fencing_token,
            'acquiredAt': utc_now(),
            'heartbeatAt': utc_now(),
            'graceSeconds': max(0.0, self.stale_seconds),
            'reclaimAudit': dict(self.reclaim_audit),
        }
        try:
            published, complete = _atomic_publish_lock(self.path, payload)
        except OSError:
            return False
        if not published:
            return False
        self.lock_device = int(complete['lockDevice'])
        self.lock_inode = int(complete['lockInode'])
        self.acquired = True
        return True

    def _owned_snapshot(self) -> _LockSnapshot | None:
        snapshot = _read_lock_snapshot(self.path)
        if (
            snapshot is None
            or snapshot.device != self.lock_device
            or snapshot.inode != self.lock_inode
            or not snapshot.data
            or snapshot.data.get('fencingToken') != self.fencing_token
            or not self._scope_matches(snapshot.data)
        ):
            return None
        return snapshot

    def heartbeat(self) -> bool:
        """仅在 inode、作用域与 fencing token 仍归当前实例时刷新锁时间。"""
        if not self.acquired or self._owned_snapshot() is None:
            return False
        os.utime(self.path, None, follow_symlinks=False)
        return True

    def release(self) -> bool:
        """仅删除当前实例持有的同一锁 epoch；被替换或 fenced 时返回失败。"""
        if not self.acquired:
            return False
        released = False
        try:
            if self._owned_snapshot() is not None:
                self.path.unlink()
                _fsync_directory(self.path.parent)
                released = True
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False
            self.fencing_token = ''
            self.lock_device = self.lock_inode = 0
        return released


class NamedResourceLock(FencedFileLock):
    """按 runtime resource 名称获取共享跨 run 锁。"""

    def __init__(
        self,
        repo_root: Path,
        resource: str,
        owner: dict[str, Any],
        stale_seconds: float = DEFAULT_STALE_SECONDS,
    ) -> None:
        self.repo_root, self.resource = repo_root, resource
        super().__init__(
            lock_root(repo_root) / f'{_safe_name(resource)}.lock',
            {**owner, 'resource': resource, 'hostMarker': _host_marker()},
            stale_seconds,
        )

    def acquire(self, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> LockAcquireResult:
        """轮询获取单个命名资源锁；超时抛出含 owner 证据的异常。"""
        started = time.monotonic()
        while True:
            if self.try_acquire():
                return LockAcquireResult(
                    self.resource, 'acquired', str(self.path), time.monotonic() - started
                )
            waited = time.monotonic() - started
            if waited >= timeout_seconds:
                raise ResourceLockTimeoutError(self.resource, self.read_owner(), waited)
            time.sleep(_POLL_SECONDS)


class ResourceLockSet:
    """按稳定顺序管理一组资源锁，部分获取失败时逆序释放已持有锁。"""

    def __init__(
        self,
        repo_root: Path,
        resources: Iterable[str],
        owner: dict[str, Any],
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.repo_root = repo_root
        self.resources = sorted({resource for resource in resources if resource})
        self.owner = owner
        self.timeout_seconds = timeout_seconds
        self.locks = [NamedResourceLock(repo_root, resource, owner) for resource in self.resources]
        self.results: list[LockAcquireResult] = []

    def acquire(self) -> list[LockAcquireResult]:
        """在共享期限内顺序获取全部资源，任一失败都回滚已获取锁。"""
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
        """按获取顺序的逆序释放资源锁，保持多资源锁定的一致边界。"""
        for lock in reversed(self.locks):
            lock.release()

    def __enter__(self) -> ResourceLockSet:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb
        self.release()
