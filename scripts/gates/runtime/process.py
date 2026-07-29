"""本模块负责执行带超时、进程组清理和有界日志尾部的子进程。

不负责把进程结果归约为 Gate 状态；由 executor 的命令执行边界调用。
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from scripts.gates.runtime.environment import sanitized_environment

PROCESS_TAIL_BYTES = 4096
PROCESS_TERM_GRACE_SECONDS = 0.4


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _stable_hash(value: str | bytes) -> str:
    payload = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class BoundedRunResult:
    """保存一次受控子进程的技术执行结果，不解释业务状态。"""

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

    def as_dict(self) -> dict[str, Any]:
        """返回可序列化的技术执行记录。"""
        return asdict(self)


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        process.wait(timeout=2)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + PROCESS_TERM_GRACE_SECONDS
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    process.wait(timeout=2)


def _log_tail(path: Path, limit: int = PROCESS_TAIL_BYTES) -> str:
    try:
        with path.open('rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
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
    """运行无 shell 子进程；超时清理整个进程组并返回有界技术结果。"""
    if (
        isinstance(argv, (str, bytes))
        or not argv
        or any(not isinstance(value, str) or not value or '\0' in value for value in argv)
    ):
        raise ValueError('argv must contain non-empty strings without NUL')
    if timeout <= 0:
        raise ValueError('timeout must be positive')
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
    timed_out = False
    with os.fdopen(descriptor, 'wb') as log:
        try:
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
            try:
                return_code = process.wait(timeout=timeout)
                exit_reason = 'SIGNAL' if return_code < 0 else 'EXITED'
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_reason = 'TIMEOUT'
                _terminate_process_group(process)
                return_code = process.returncode
        except OSError as exc:
            log.write(f'{type(exc).__name__}: {exc}\n'.encode(errors='replace'))
        except BaseException:
            if process is not None:
                _terminate_process_group(process)
            raise
        finally:
            log.flush()
            os.fsync(log.fileno())
    return BoundedRunResult(
        return_code,
        exit_reason,
        timed_out,
        _stable_hash(json.dumps(command)),
        _stable_hash(json.dumps(sorted(child_env.items()))),
        started_at,
        _utc_now(),
        round(time.monotonic() - started, 6),
        process.pid if process else None,
        str(selected_log),
        _log_tail(selected_log),
    )
