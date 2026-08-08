"""本模块负责执行受控子进程、进程组清理和有界日志尾部。

不负责把进程结果归约为 Gate 状态；由 executor 的命令执行边界调用。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from scripts.gates.runtime.environment import sanitized_environment
from scripts.gates.support import stable_hash

PROCESS_TAIL_BYTES = 4096
PROCESS_TERM_GRACE_SECONDS = 0.4


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


@dataclass(frozen=True, slots=True)
class ManagedRunResult:
    """保存一次受控子进程的技术执行结果，不解释业务状态。"""

    return_code: int | None
    exit_reason: str
    command_fingerprint: str
    environment_fingerprint: str
    started_at: str
    finished_at: str
    duration_seconds: float
    child_pid: int | None
    log_path: str
    output_tail: str

    def as_dict(self) -> dict[str, Any]:
        """返回可序列化的技术执行记录。"""
        return asdict(self)


class ManagedRunInterrupted(KeyboardInterrupt):
    """表示受控运行收到应清理子进程组的显式终止信号。"""

    def __init__(self, signal_number: int) -> None:
        super().__init__(f'received signal {signal_number}')
        self.signal_number = signal_number


def _raise_on_termination(signal_number: int, _frame: object) -> None:
    raise ManagedRunInterrupted(signal_number)


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + PROCESS_TERM_GRACE_SECONDS
    while _process_group_exists(process.pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    if _process_group_exists(process.pid):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    process.wait()


def _log_tail(path: Path, limit: int = PROCESS_TAIL_BYTES) -> str:
    try:
        with path.open('rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read(limit).decode('utf-8', errors='replace')
    except OSError:
        return ''


def run_managed(
    argv: Sequence[str],
    *,
    cwd: Path | str,
    env: Mapping[str, str | None] | None,
    log_path: Path | str,
) -> ManagedRunResult:
    """运行无 shell 子进程；自然等待完成，异常或显式中断时清理进程组。"""
    if (
        isinstance(argv, (str, bytes))
        or not argv
        or any(not isinstance(value, str) or not value or '\0' in value for value in argv)
    ):
        raise ValueError('argv must contain non-empty strings without NUL')
    command = tuple(argv)
    selected_log = Path(os.path.abspath(Path(log_path).expanduser()))
    selected_log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(selected_log, flags, 0o600)
    child_env = sanitized_environment(env)
    started_at = _utc_now()
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    return_code: int | None = None
    exit_reason = 'SPAWN_ERROR'
    previous_sigterm_handler: signal.Handlers | None = None
    handles_sigterm = threading.current_thread() is threading.main_thread()
    with os.fdopen(descriptor, 'wb') as log:
        try:
            if handles_sigterm:
                previous_sigterm_handler = signal.getsignal(signal.SIGTERM)
                signal.signal(signal.SIGTERM, _raise_on_termination)
            process = subprocess.Popen(
                command,
                cwd=Path(cwd).resolve(),
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                shell=False,
            )
            return_code = process.wait()
            exit_reason = 'SIGNAL' if return_code < 0 else 'EXITED'
        except OSError as exc:
            if process is not None:
                _terminate_process_group(process)
                raise
            log.write(f'{type(exc).__name__}: {exc}\n'.encode(errors='replace'))
        except BaseException:
            if process is not None:
                _terminate_process_group(process)
            raise
        finally:
            if handles_sigterm and previous_sigterm_handler is not None:
                signal.signal(signal.SIGTERM, previous_sigterm_handler)
            log.flush()
            os.fsync(log.fileno())
    return ManagedRunResult(
        return_code=return_code,
        exit_reason=exit_reason,
        command_fingerprint=stable_hash(json.dumps(command)),
        environment_fingerprint=stable_hash(json.dumps(sorted(child_env.items()))),
        started_at=started_at,
        finished_at=_utc_now(),
        duration_seconds=round(time.monotonic() - started, 6),
        child_pid=process.pid if process else None,
        log_path=str(selected_log),
        output_tail=_log_tail(selected_log),
    )
