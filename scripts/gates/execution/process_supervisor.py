"""负责监管一个 CommandInvocation 的进程组、日志与进度事件；不负责业务分类。

由 Execution 运行编排器逐个调用。"""

from __future__ import annotations

import hashlib
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

from scripts.gates.execution.command_adapter import sanitized_environment

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from scripts.gates.planning.plan_compiler import CommandInvocation

PROCESS_TAIL_BYTES = 4096
PROCESS_TERM_GRACE_SECONDS = 0.4
DEFAULT_HEARTBEAT_SECONDS = 30.0
DEFAULT_STALL_SECONDS = 120.0


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """Execution 提交给 Presentation 的稳定事件。"""

    kind: str
    gate_name: str = ''
    recipe_step_name: str = ''
    invocation_id: str = ''
    elapsed_seconds: float = 0.0
    log_path: str = ''
    status: str = ''
    reason: str = ''
    process_count: int = 0


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    """一次 OS 进程的技术事实；不解释 Gate 业务状态。"""

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
        """返回可序列化的进程观察事实，不补充业务状态。"""
        return asdict(self)


class ProcessInterrupted(KeyboardInterrupt):
    """表示显式中断；受管进程组已在返回前清理。"""

    def __init__(self, signal_number: int | None = None) -> None:
        super().__init__(f'received signal {signal_number}' if signal_number else 'interrupted')
        self.signal_number = signal_number


def _raise_process_interruption(signal_number: int, _frame: object) -> None:
    raise ProcessInterrupted(signal_number)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _isolated_child_environment(
    invocation: CommandInvocation,
    *,
    repo_root: Path,
    log_path: Path,
    overrides: Mapping[str, str | None] | None,
) -> dict[str, str]:
    """为每次 run/step 隔离缓存、fixture 和 owner artifact。"""

    scope = _fingerprint(str(log_path.parent))[:12]
    safe_id = ''.join(
        character if character.isalnum() or character in '._-' else '-'
        for character in invocation.invocation_id
    )[:96]
    quality_root = repo_root / 'tmp' / 'quality'
    runtime_root = quality_root / 'runtime' / scope / (safe_id or 'command')
    paths = {
        'TMPDIR': runtime_root / 'tmp',
        'XDG_CACHE_HOME': runtime_root / 'cache',
        'FEIPI_FIXTURE_DATA_DIR': runtime_root / 'fixture-data',
        'FEIPI_QUALITY_ARTIFACT_DIR': quality_root
        / 'owner-artifacts'
        / scope
        / (safe_id or 'command'),
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = sanitized_environment(
        overrides,
        base=sanitized_environment(dict(invocation.environment)),
    )
    environment.update({name: str(path) for name, path in paths.items()})
    environment['GIT_CEILING_DIRECTORIES'] = str(paths['TMPDIR'])
    if invocation.kind == 'playwright' and environment.get('FORCE_COLOR'):
        environment.pop('NO_COLOR', None)
    return environment


def _tail(path: Path, limit: int = PROCESS_TAIL_BYTES) -> str:
    try:
        with path.open('rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read(limit).decode('utf-8', errors='replace')
    except OSError:
        return ''


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


def _emit(
    sink: Callable[[ExecutionEvent], None] | None,
    kind: str,
    invocation: CommandInvocation,
    *,
    elapsed: float,
    log_path: Path,
) -> None:
    if sink is not None:
        sink(
            ExecutionEvent(
                kind,
                gate_name=invocation.gate_name,
                recipe_step_name=invocation.recipe_step_name,
                invocation_id=invocation.invocation_id,
                elapsed_seconds=round(elapsed, 3),
                log_path=str(log_path),
            )
        )


def supervise_process(
    invocation: CommandInvocation,
    *,
    cwd: Path | str,
    log_path: Path | str,
    environment_overrides: Mapping[str, str | None] | None = None,
    event_sink: Callable[[ExecutionEvent], None] | None = None,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    stall_seconds: float = DEFAULT_STALL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    poll_interval: float = 0.2,
) -> ProcessObservation:
    """自然等待一个进程；定期报告心跳和停滞，但不因时间目标 kill。"""

    if heartbeat_seconds <= 0 or stall_seconds <= 0 or poll_interval <= 0:
        raise ValueError('progress intervals must be positive')
    command = tuple(invocation.argv)
    selected_log = Path(log_path).expanduser().absolute()
    selected_log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = Path(cwd).resolve()
    child_environment = _isolated_child_environment(
        invocation,
        repo_root=root,
        log_path=selected_log,
        overrides=environment_overrides,
    )
    started_at = _utc_now()
    started = clock()
    process: subprocess.Popen[bytes] | None = None
    return_code: int | None = None
    exit_reason = 'SPAWN_ERROR'
    previous_sigterm_handler: signal.Handlers | None = None
    handles_sigterm = threading.current_thread() is threading.main_thread()
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(selected_log, flags, 0o600)
    with os.fdopen(descriptor, 'wb') as log:
        try:
            if not command or any(not value or '\0' in value for value in command):
                raise OSError('command unavailable')
            if handles_sigterm:
                previous_sigterm_handler = signal.getsignal(signal.SIGTERM)
                signal.signal(signal.SIGTERM, _raise_process_interruption)
            process = subprocess.Popen(
                command,
                cwd=root,
                env=child_environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                shell=False,
            )
            _emit(event_sink, 'START', invocation, elapsed=0.0, log_path=selected_log)
            last_size = 0
            last_growth = started
            next_heartbeat = started + heartbeat_seconds
            stall_reported = False
            while process.poll() is None:
                now = clock()
                try:
                    current_size = os.fstat(log.fileno()).st_size
                except OSError:
                    current_size = last_size
                if current_size > last_size:
                    last_size = current_size
                    last_growth = now
                    stall_reported = False
                if now >= next_heartbeat:
                    _emit(
                        event_sink,
                        'HEARTBEAT',
                        invocation,
                        elapsed=now - started,
                        log_path=selected_log,
                    )
                    while next_heartbeat <= now:
                        next_heartbeat += heartbeat_seconds
                if not stall_reported and now - last_growth >= stall_seconds:
                    _emit(
                        event_sink,
                        'STALL',
                        invocation,
                        elapsed=now - started,
                        log_path=selected_log,
                    )
                    stall_reported = True
                sleeper(poll_interval)
            return_code = process.returncode
            exit_reason = 'SIGNAL' if return_code is not None and return_code < 0 else 'EXITED'
        except OSError as exc:
            log.write(f'{type(exc).__name__}: {exc}\n'.encode(errors='replace'))
        except (KeyboardInterrupt, ProcessInterrupted):
            if process is not None:
                _terminate_process_group(process)
            return_code = process.returncode if process else None
            exit_reason = 'INTERRUPTED'
        except BaseException:
            if process is not None:
                _terminate_process_group(process)
            raise
        finally:
            if handles_sigterm and previous_sigterm_handler is not None:
                signal.signal(signal.SIGTERM, previous_sigterm_handler)
            log.flush()
            os.fsync(log.fileno())
    finished = clock()
    return ProcessObservation(
        return_code=return_code,
        exit_reason=exit_reason,
        command_fingerprint=_fingerprint(command),
        environment_fingerprint=_fingerprint(sorted(child_environment.items())),
        started_at=started_at,
        finished_at=_utc_now(),
        duration_seconds=round(finished - started, 6),
        child_pid=process.pid if process else None,
        log_path=str(selected_log),
        output_tail=_tail(selected_log),
    )
