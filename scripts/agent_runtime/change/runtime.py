"""负责 Change controller 共用的 bounded process、环境、锁与持久化原语。

本模块不负责判定 Git candidate、Gate 或 integration 业务。所有 controller 子进程和
metadata 竞争都应经这里执行，避免平台 adapter 各自实现超时与恢复语义。
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from scripts.agent_runtime.locks import (
    _atomic_publish_lock,
    _fsync_directory,
    _pid_start_time,
    _read_lock_snapshot,
    _same_lock_epoch,
)
from scripts.agent_runtime.storage import utc_now, write_json_atomic

DEFAULT_LOCK_TIMEOUT_SECONDS = 1.8
LOCK_POLL_SECONDS = 0.05
PROCESS_TAIL_BYTES = 4096
PROCESS_TERM_GRACE_SECONDS = 0.4
MAX_JSONL_EVENT_BYTES = 64 * 1024
PROVIDER_ENV_PREFIXES = ('CODEX_', 'QODER_', 'CLAUDE_')


class ChangeRuntimeError(RuntimeError):
    """Change runtime 的结构化基础错误；``code`` 可直接映射 controller 协议。"""

    code = 'INTERNAL_ERROR'


class LockBusyError(ChangeRuntimeError):
    """活 owner 持有锁时的可重试结果，不允许污染持久 Change 状态。"""

    code = 'BUSY_RETRYABLE'

    def __init__(
        self,
        path: Path,
        *,
        owner: Mapping[str, Any],
        waited_seconds: float,
        held_seconds: float,
    ) -> None:
        super().__init__(f'bounded metadata lock busy: {path}')
        self.path = path
        self.owner = dict(owner)
        self.waited_seconds = waited_seconds
        self.held_seconds = held_seconds


class LockInvariantError(ChangeRuntimeError):
    """锁 metadata 损坏或身份不可证明时关闭失败，禁止猜测或自动覆盖。"""

    code = 'TERMINAL_BLOCKED'

    def __init__(self, path: Path, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.path = path
        self.reason_code = reason_code


class StaleLockEpochError(LockInvariantError):
    """旧 epoch 不得等待、回收或覆盖更新 epoch 的 owner。"""

    def __init__(self, path: Path, *, expected: int, observed: int) -> None:
        super().__init__(
            path,
            'STALE_LOCK_EPOCH',
            f'stale lock epoch: expected={expected}, observed={observed}',
        )
        self.expected = expected
        self.observed = observed


class ManagedProcessError(ChangeRuntimeError):
    """managed child 缺失 capability 或身份无法安全处理时的结构化错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class BoundedRunResult:
    """一次 bounded child 的紧凑结果；完整 stdout/stderr 仅保存在 ``log_path``。"""

    return_code: int | None
    exit_reason: str
    timed_out: bool
    command_fingerprint: str
    environment_fingerprint: str
    started_at: str
    finished_at: str
    duration_seconds: float
    child_pid: int | None
    log_path: str
    output_tail: str

    @property
    def passed(self) -> bool:
        """判定 child 正常零退出；不把 timeout 或 signal 视为通过。"""
        return self.return_code == 0 and self.exit_reason == 'EXITED'

    def as_dict(self) -> dict[str, Any]:
        """返回可 JSON 序列化的稳定字段，不展开完整子进程日志。"""
        return asdict(self)


@dataclass(slots=True)
class ManagedProcess:
    """后台 managed child 的进程句柄和可持久化身份。"""

    process: subprocess.Popen[bytes]
    pid: int
    process_start_time: str
    process_group_id: int
    command_fingerprint: str
    environment_fingerprint: str
    started_at: str
    log_path: str


def sanitized_environment(
    overrides: Mapping[str, str | None] | None = None,
    *,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """构造真正传给 child 的环境，并移除所有 provider 私有命名空间。

    ``PATH``、``HOME``、Java、Node 和 Python 等普通 capability 环境会保留；显式
    override 可新增或删除普通变量，但不能重新注入 provider 私有目录。
    """
    source = os.environ if base is None else base
    result = {str(key): str(value) for key, value in source.items()}
    for key, value in (overrides or {}).items():
        if value is None:
            result.pop(str(key), None)
        else:
            result[str(key)] = str(value)
    for key in tuple(result):
        if key.startswith(PROVIDER_ENV_PREFIXES):
            result.pop(key, None)
    return result


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _absolute_without_symlink_resolution(path: Path | str) -> Path:
    """转为绝对路径但保留末端 symlink，交由 no-follow open 关闭失败。"""
    expanded = Path(path).expanduser()
    return Path(os.path.abspath(expanded))


def _validate_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if isinstance(argv, (str, bytes)):
        raise TypeError('run_bounded argv must be a sequence, never a shell string')
    command = tuple(argv)
    if not command or any(
        not isinstance(item, str) or not item or '\0' in item for item in command
    ):
        raise ValueError('run_bounded argv must contain non-empty strings without NUL')
    return command


def _open_process_log(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags, 0o600)
    metadata = os.fstat(descriptor)
    current_uid = getattr(os, 'geteuid', os.getuid)()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != current_uid:
        os.close(descriptor)
        raise ChangeRuntimeError(f'unsafe process log path: {path}')
    os.fchmod(descriptor, 0o600)
    return os.fdopen(descriptor, 'wb')


def _process_group_alive(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """timeout/取消时清理整个 process group，并始终等待直接 child 被回收。"""
    if process.poll() is not None:
        process.wait(timeout=2)
        return
    process_group = process.pid
    if _process_group_alive(process_group):
        try:
            os.killpg(process_group, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.monotonic() + PROCESS_TERM_GRACE_SECONDS
    while _process_group_alive(process_group) and time.monotonic() < deadline:
        time.sleep(0.02)
    if _process_group_alive(process_group):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def log_tail(path: Path | str, limit: int = PROCESS_TAIL_BYTES) -> str:
    """读取日志的有界尾部；日志缺失时返回空字符串而不伪造事实。"""
    selected = Path(path)
    try:
        with selected.open('rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit), os.SEEK_SET)
            return handle.read(limit).decode('utf-8', errors='replace')
    except OSError:
        return ''


def run_bounded(
    argv: Sequence[str],
    *,
    cwd: Path | str,
    timeout: float,
    env: Mapping[str, str | None] | None,
    log_path: Path | str,
) -> BoundedRunResult:
    """无 shell 执行 child。

    timeout/取消会清理进程树，响应只携带有限日志尾部。
    """
    command = _validate_argv(argv)
    if timeout <= 0:
        raise ValueError('run_bounded timeout must be positive')
    selected_cwd = Path(cwd).resolve()
    selected_log = _absolute_without_symlink_resolution(log_path)
    child_env = sanitized_environment(env)
    command_fingerprint = _fingerprint(command)
    environment_fingerprint = _fingerprint(sorted(child_env.items()))
    started_at = utc_now()
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    exit_reason = 'SPAWN_ERROR'
    timed_out = False
    return_code: int | None = None
    with _open_process_log(selected_log) as log:
        try:
            process = subprocess.Popen(
                command,
                cwd=selected_cwd,
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                shell=False,
            )
            try:
                return_code = process.wait(timeout=timeout)
                exit_reason = 'SIGNAL' if return_code < 0 else 'EXITED'
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_reason = 'TIMEOUT'
                _terminate_process_group(process)
                return_code = process.returncode
        except OSError as exc:
            log.write(f'{type(exc).__name__}: {exc}\n'.encode('utf-8', errors='replace'))
            log.flush()
            os.fsync(log.fileno())
        except BaseException:
            # 调用端取消也不能留下 fixture、Gradle 或测试孙进程。
            if process is not None:
                _terminate_process_group(process)
            raise
        finally:
            log.flush()
            os.fsync(log.fileno())
    return BoundedRunResult(
        return_code=return_code,
        exit_reason=exit_reason,
        timed_out=timed_out,
        command_fingerprint=command_fingerprint,
        environment_fingerprint=environment_fingerprint,
        started_at=started_at,
        finished_at=utc_now(),
        duration_seconds=round(time.monotonic() - started, 6),
        child_pid=process.pid if process is not None else None,
        log_path=str(selected_log),
        output_tail=log_tail(selected_log),
    )


def spawn_managed(
    argv: Sequence[str],
    *,
    cwd: Path | str,
    env: Mapping[str, str | None] | None,
    log_path: Path | str,
) -> ManagedProcess:
    """通过唯一 runtime 原语启动后台 child，并把 stdout/stderr 写入真实日志。"""
    command = _validate_argv(argv)
    selected_cwd = Path(cwd).resolve()
    selected_log = _absolute_without_symlink_resolution(log_path)
    child_env = sanitized_environment(env)
    log = _open_process_log(selected_log)
    try:
        process = subprocess.Popen(
            command,
            cwd=selected_cwd,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            shell=False,
        )
    except OSError as exc:
        log.write(f'{type(exc).__name__}: {exc}\n'.encode('utf-8', errors='replace'))
        log.flush()
        os.fsync(log.fileno())
        raise ManagedProcessError(
            'CAPABILITY_RETRYABLE', f'managed process unavailable: {exc}'
        ) from exc
    finally:
        log.close()
    start_identity = _pid_start_time(process.pid)
    if not start_identity:
        if process.poll() is not None:
            start_identity = f'exited-before-identity-observation:{process.pid}'
        else:
            _terminate_process_group(process)
            raise ManagedProcessError(
                'TERMINAL_BLOCKED', 'cannot prove managed process start identity'
            )
    try:
        process_group = os.getpgid(process.pid)
    except ProcessLookupError as exc:
        if process.poll() is not None:
            # start_new_session=True 已定义 PGID=PID；极速退出时内核已回收查询入口。
            process_group = process.pid
        else:
            _terminate_process_group(process)
            raise ManagedProcessError(
                'TERMINAL_BLOCKED', f'cannot prove managed process group: {exc}'
            ) from exc
    if process_group != process.pid:
        _terminate_process_group(process)
        raise ManagedProcessError(
            'TERMINAL_BLOCKED', 'managed process did not create an isolated process group'
        )
    return ManagedProcess(
        process=process,
        pid=process.pid,
        process_start_time=start_identity,
        process_group_id=process_group,
        command_fingerprint=_fingerprint(command),
        environment_fingerprint=_fingerprint(sorted(child_env.items())),
        started_at=utc_now(),
        log_path=str(selected_log),
    )


def process_identity_status(pid: int, expected_start_time: str) -> str:
    """返回 ``MATCH``、``DEAD``、``PID_REUSED`` 或 ``UNKNOWN``，禁止模糊存活。"""
    if pid <= 0 or not expected_start_time:
        return 'UNKNOWN'
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return 'DEAD'
    except PermissionError:
        return 'UNKNOWN'
    except OSError:
        return 'DEAD'
    observed = _pid_start_time(pid)
    if not observed:
        return 'UNKNOWN'
    return 'MATCH' if observed == expected_start_time else 'PID_REUSED'


def terminate_managed_group(
    *,
    pid: int,
    process_start_time: str,
    process_group_id: int,
    process: subprocess.Popen[bytes] | None = None,
) -> bool:
    """复核 PID identity 后清理完整 managed process group。

    group leader 已死亡时仍会回收同一 PGID 的 orphan；PID reuse/未知身份绝不发送
    signal。传入直接 child 句柄时还会确定性 ``wait``，避免 controller 制造 zombie。
    """
    if process_group_id <= 0 or process_group_id != pid:
        raise ManagedProcessError('TERMINAL_BLOCKED', 'managed process group identity is invalid')
    identity = process_identity_status(pid, process_start_time)
    if identity == 'PID_REUSED':
        raise ManagedProcessError('TERMINAL_BLOCKED', 'managed process PID was reused')
    if identity == 'UNKNOWN':
        raise ManagedProcessError('TERMINAL_BLOCKED', 'managed process identity is unknown')
    if _process_group_alive(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            raise ManagedProcessError(
                'TERMINAL_BLOCKED', 'managed process group is not signal-safe'
            ) from exc
    if process is not None:
        try:
            process.wait(timeout=PROCESS_TERM_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
    deadline = time.monotonic() + PROCESS_TERM_GRACE_SECONDS
    while _process_group_alive(process_group_id) and time.monotonic() < deadline:
        time.sleep(0.02)
    if _process_group_alive(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            raise ManagedProcessError(
                'TERMINAL_BLOCKED', 'managed process group cannot be force-cleaned'
            ) from exc
    if process is not None:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    return not _process_group_alive(process_group_id)


def _owner_liveness(owner: Mapping[str, Any]) -> bool | None:
    """同时验证 PID 与启动身份。

    启动时间不可读时返回 unknown 并关闭失败。
    """
    pid = owner.get('pid')
    expected = str(owner.get('processStartTime') or '')
    if not isinstance(pid, int) or pid <= 0 or not expected:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    except OSError:
        return False
    observed = _pid_start_time(pid)
    if not observed:
        return None
    return observed == expected


def _validate_lock_owner(path: Path, owner: Mapping[str, Any]) -> None:
    """验证锁 owner 的 fencing 身份；字段缺失时不得回收或覆盖。"""
    required = {
        'pid',
        'processStartTime',
        'sessionId',
        'changeId',
        'epoch',
        'acquiredAt',
        'fencingToken',
        'ownerUid',
        'lockDevice',
        'lockInode',
    }
    if not required.issubset(owner):
        raise LockInvariantError(path, 'LOCK_METADATA_CORRUPT', 'lock owner fields are incomplete')
    try:
        epoch = int(owner['epoch'])
    except (TypeError, ValueError) as exc:
        raise LockInvariantError(
            path, 'LOCK_METADATA_CORRUPT', 'lock epoch is not an integer'
        ) from exc
    if epoch <= 0 or not all(
        str(owner.get(name) or '') for name in ('processStartTime', 'sessionId', 'changeId')
    ):
        raise LockInvariantError(path, 'LOCK_METADATA_CORRUPT', 'lock identity is incomplete')


class BoundedMetadataLock:
    """带 PID identity、change epoch 和 fencing token 的 2 秒 metadata 锁。

    活 owner 只返回 ``BUSY_RETRYABLE``；死亡或 PID reuse owner 可原地回收；坏
    metadata、未知存活状态和旧 epoch 一律 fail closed。释放时须再次匹配 inode、
    epoch 与 token，旧进程绝不能删除新 owner 的锁。
    """

    def __init__(
        self,
        path: Path | str,
        *,
        session_id: str,
        change_id: str,
        epoch: int,
        timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> None:
        if not session_id or not change_id or epoch <= 0 or timeout_seconds < 0:
            raise ValueError('lock requires session_id, change_id, positive epoch and timeout')
        self.path = _absolute_without_symlink_resolution(path)
        self.session_id = session_id
        self.change_id = change_id
        self.epoch = epoch
        self.timeout_seconds = timeout_seconds
        self.acquired = False
        self.fencing_token = ''
        self.lock_device = 0
        self.lock_inode = 0
        self.metadata: dict[str, Any] = {}
        self.reclaimed_owner: dict[str, Any] = {}

    def _snapshot(self) -> Any:
        snapshot = _read_lock_snapshot(self.path)
        if snapshot is not None and snapshot.state != 'valid':
            raise LockInvariantError(
                self.path,
                'LOCK_METADATA_CORRUPT',
                f'lock metadata is not safely readable: {snapshot.state}',
            )
        if snapshot is not None:
            _validate_lock_owner(self.path, snapshot.data or {})
        return snapshot

    def _publish(self) -> bool:
        self.fencing_token = uuid.uuid4().hex
        payload = {
            'pid': os.getpid(),
            'processStartTime': _pid_start_time(os.getpid()),
            'sessionId': self.session_id,
            'changeId': self.change_id,
            'epoch': self.epoch,
            'fencingToken': self.fencing_token,
            'acquiredAt': utc_now(),
        }
        if not payload['processStartTime']:
            raise LockInvariantError(
                self.path,
                'PROCESS_IDENTITY_UNAVAILABLE',
                'cannot prove current process start identity',
            )
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        published, complete = _atomic_publish_lock(self.path, payload)
        if published:
            self.acquired = True
            self.lock_device = int(complete['lockDevice'])
            self.lock_inode = int(complete['lockInode'])
            self.metadata = dict(complete)
        return published

    def acquire(self) -> BoundedMetadataLock:
        """在期限内获取锁；活 owner、死 owner 和损坏 metadata 有不同结果。"""
        if self.acquired:
            return self
        started = time.monotonic()
        while True:
            snapshot = self._snapshot()
            if snapshot is None:
                if self._publish():
                    return self
                continue
            owner = dict(snapshot.data or {})
            observed_epoch = int(owner['epoch'])
            if observed_epoch > self.epoch:
                raise StaleLockEpochError(self.path, expected=self.epoch, observed=observed_epoch)
            liveness = _owner_liveness(owner)
            if liveness is None:
                raise LockInvariantError(
                    self.path,
                    'LOCK_OWNER_IDENTITY_UNPROVEN',
                    'cannot prove lock owner process identity',
                )
            if not liveness:
                token = str(owner.get('fencingToken') or '')
                if not token or not _same_lock_epoch(self.path, snapshot, token):
                    continue
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise LockInvariantError(
                        self.path, 'LOCK_RECLAIM_FAILED', f'cannot reclaim dead owner: {exc}'
                    ) from exc
                _fsync_directory(self.path.parent)
                self.reclaimed_owner = owner
                continue
            waited = time.monotonic() - started
            if waited >= self.timeout_seconds:
                raise LockBusyError(
                    self.path,
                    owner=owner,
                    waited_seconds=waited,
                    held_seconds=max(0.0, time.time() - snapshot.mtime),
                )
            time.sleep(min(LOCK_POLL_SECONDS, self.timeout_seconds - waited))

    def _owned_snapshot(self) -> Any:
        snapshot = self._snapshot()
        if (
            snapshot is None
            or snapshot.device != self.lock_device
            or snapshot.inode != self.lock_inode
            or not snapshot.data
            or snapshot.data.get('fencingToken') != self.fencing_token
            or int(snapshot.data.get('epoch') or 0) != self.epoch
            or snapshot.data.get('sessionId') != self.session_id
            or snapshot.data.get('changeId') != self.change_id
        ):
            return None
        return snapshot

    def heartbeat(self) -> bool:
        """只有当前 inode/token/epoch owner 能刷新锁；被 fenced 时不触碰新锁。"""
        if not self.acquired or self._owned_snapshot() is None:
            return False
        os.utime(self.path, None, follow_symlinks=False)
        return True

    def release(self) -> bool:
        """精确释放当前 lease；旧 attempt 或旧进程调用只能得到 ``False``。"""
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

    def __enter__(self) -> BoundedMetadataLock:
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb
        self.release()


def write_atomic_json(path: Path | str, payload: Mapping[str, Any]) -> None:
    """复用 Runtime 原子 replace 写 JSON snapshot，写入失败时保留旧事实。"""
    write_json_atomic(Path(path), dict(payload))


def _ensure_append_target(path: Path) -> tuple[int, bool]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    before = None
    try:
        before = path.lstat()
    except FileNotFoundError:
        pass
    if before and (stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode)):
        raise ChangeRuntimeError(f'unsafe append-only path: {path}')
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags, 0o600)
    opened = os.fstat(descriptor)
    current_uid = getattr(os, 'geteuid', os.getuid)()
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != current_uid
        or (before and (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino))
    ):
        os.close(descriptor)
        raise ChangeRuntimeError(f'append-only path changed or has unsafe owner: {path}')
    os.fchmod(descriptor, 0o600)
    return descriptor, before is None


def append_jsonl(path: Path | str, event: Mapping[str, Any]) -> None:
    """以单次 ``O_APPEND`` syscall 追加紧凑事件并 fsync，绝不重写历史行。"""
    selected = Path(path)
    payload = (json.dumps(dict(event), ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
    if len(payload) > MAX_JSONL_EVENT_BYTES:
        raise ValueError('append-only JSONL event exceeds 64 KiB')
    descriptor, created = _ensure_append_target(selected)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise ChangeRuntimeError('append-only JSONL write was incomplete')
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if created:
        _fsync_directory(selected.parent)


def append_event(directory: Path | str, event: Mapping[str, Any]) -> Path:
    """为审计事实创建唯一原子 JSON 文件；既有 event 永不覆盖。"""
    event_id = f'{time.time_ns()}-{uuid.uuid4().hex[:12]}'
    payload = dict(event)
    payload.setdefault('schemaVersion', 1)
    payload.setdefault('eventId', event_id)
    path = Path(directory) / f'{event_id}.json'
    write_atomic_json(path, payload)
    return path
