"""进程生命周期、heartbeat、STALL 与显式中断清理 contract。"""

import inspect
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from scripts.gates.execution import process_supervisor
from scripts.gates.execution.outcome_classifier import ExecutionStatus, classify_owner_outcome
from scripts.gates.planning.plan_compiler import CommandInvocation


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class CompletingProcess:
    def __init__(self, clock: FakeClock, finish_at: float = 125.0) -> None:
        self.clock = clock
        self.finish_at = finish_at
        self.returncode = None
        self.pid = 31415

    def poll(self):
        if self.clock.value >= self.finish_at:
            self.returncode = 0
        return self.returncode

    def wait(self):
        self.returncode = 0
        return self.returncode


def _invocation() -> CommandInvocation:
    return CommandInvocation('gate:step:run', 'command', ('tool',), (), 'gate', 'step')


def test_supervisor_reports_fake_clock_heartbeat_and_stall(tmp_path: Path, monkeypatch) -> None:
    clock = FakeClock()
    process = CompletingProcess(clock)
    monkeypatch.setattr(process_supervisor.subprocess, 'Popen', lambda *_args, **_kwargs: process)
    events = []
    observation = process_supervisor.supervise_process(
        _invocation(),
        cwd=tmp_path,
        log_path=tmp_path / 'process.log',
        event_sink=events.append,
        heartbeat_seconds=30,
        stall_seconds=120,
        poll_interval=30,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert observation.return_code == 0
    assert observation.stalled
    assert [event.kind for event in events] == [
        'START',
        'HEARTBEAT',
        'HEARTBEAT',
        'HEARTBEAT',
        'HEARTBEAT',
        'STALL',
    ]
    assert events[-1].elapsed_seconds == 120


@pytest.mark.parametrize('capture_events', [True, False])
@pytest.mark.parametrize(
    ('growth_times', 'finish_at', 'stall_count'),
    [
        ((), 180, 1),
        ((150,), 180, 1),
        ((150,), 330, 2),
        ((30, 60, 90, 120, 150), 180, 0),
    ],
)
def test_stall_fact_survives_recovery_and_does_not_depend_on_event_sink(
    tmp_path: Path, monkeypatch, capture_events, growth_times, finish_at, stall_count
) -> None:
    clock = FakeClock()
    process = CompletingProcess(clock, finish_at=finish_at)
    monkeypatch.setattr(process_supervisor.subprocess, 'Popen', lambda *_args, **_kwargs: process)
    signals = []
    monkeypatch.setattr(process_supervisor.os, 'killpg', lambda *args: signals.append(args))
    log = tmp_path / 'progress.log'
    events = []

    def sleep_and_write(seconds: float) -> None:
        clock.sleep(seconds)
        if clock.value in growth_times:
            with log.open('ab') as output:
                output.write(b'progress\n')

    observation = process_supervisor.supervise_process(
        _invocation(),
        cwd=tmp_path,
        log_path=log,
        event_sink=events.append if capture_events else None,
        clock=clock,
        sleeper=sleep_and_write,
        poll_interval=30,
    )
    assert observation.stalled is bool(stall_count)
    assert observation.as_dict()['stalled'] is bool(stall_count)
    assert observation.return_code == 0
    assert observation.exit_reason == 'EXITED'
    assert clock.value == finish_at
    assert signals == []
    if capture_events:
        assert sum(event.kind == 'STALL' for event in events) == stall_count
        assert any(event.kind == 'HEARTBEAT' for event in events)
    if growth_times:
        assert 'progress' in observation.output_tail
    result = classify_owner_outcome(_invocation(), observation)
    expected = (
        (ExecutionStatus.FAIL, 'process-stalled') if stall_count else (ExecutionStatus.PASS, '')
    )
    assert (result.status, result.reason) == expected


def test_supervisor_has_no_execution_timeout_parameter() -> None:
    assert 'timeout' not in inspect.signature(process_supervisor.supervise_process).parameters


def test_keyboard_interrupt_cleans_process_group(tmp_path: Path, monkeypatch) -> None:
    clock = FakeClock()
    process = CompletingProcess(clock, finish_at=999)
    cleaned = []

    def interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    def terminate(selected) -> None:
        cleaned.append(selected.pid)
        selected.returncode = -15

    monkeypatch.setattr(process_supervisor.subprocess, 'Popen', lambda *_args, **_kwargs: process)
    monkeypatch.setattr(process_supervisor, '_terminate_process_group', terminate)
    observation = process_supervisor.supervise_process(
        _invocation(),
        cwd=tmp_path,
        log_path=tmp_path / 'interrupted.log',
        clock=clock,
        sleeper=interrupt,
    )
    assert cleaned == [31415]
    assert observation.exit_reason == 'INTERRUPTED'
    assert observation.return_code == -15


def test_spawn_error_is_observable_runtime_fact(tmp_path: Path, monkeypatch) -> None:
    def missing(*_args, **_kwargs):
        raise FileNotFoundError('missing tool')

    monkeypatch.setattr(process_supervisor.subprocess, 'Popen', missing)
    observation = process_supervisor.supervise_process(
        _invocation(), cwd=tmp_path, log_path=tmp_path / 'missing.log'
    )
    assert observation.return_code is None
    assert observation.exit_reason == 'SPAWN_ERROR'
    assert 'missing tool' in observation.output_tail


def test_child_environment_is_provider_clean_and_run_isolated(tmp_path: Path, monkeypatch) -> None:
    clock = FakeClock()
    process = CompletingProcess(clock, finish_at=0)
    captured = {}

    def spawn(*_args, **kwargs):
        captured.update(kwargs['env'])
        return process

    monkeypatch.setenv('CODEX_PRIVATE', 'secret')
    monkeypatch.setattr(process_supervisor.subprocess, 'Popen', spawn)
    process_supervisor.supervise_process(
        _invocation(),
        cwd=tmp_path,
        log_path=tmp_path / 'logs' / 'isolated.log',
        clock=clock,
        sleeper=clock.sleep,
    )
    assert 'CODEX_PRIVATE' not in captured
    assert Path(captured['TMPDIR']).is_dir()
    assert Path(captured['XDG_CACHE_HOME']).is_dir()
    assert Path(captured['FEIPI_FIXTURE_DATA_DIR']).is_dir()
    assert Path(captured['FEIPI_QUALITY_ARTIFACT_DIR']).is_relative_to(tmp_path / 'tmp' / 'quality')
    assert captured['GIT_CEILING_DIRECTORIES'] == captured['TMPDIR']


def test_supervisor_waits_for_natural_completion_without_signalling(
    tmp_path: Path, monkeypatch
) -> None:
    signals = []
    monkeypatch.setattr(
        process_supervisor.os,
        'killpg',
        lambda pid, signum: signals.append((pid, signum)),
    )
    invocation = CommandInvocation(
        'natural',
        'command',
        (sys.executable, '-c', "import time; time.sleep(0.1); print('complete')"),
        (),
        'gate',
        'step',
    )
    started = time.monotonic()
    observation = process_supervisor.supervise_process(
        invocation,
        cwd=tmp_path,
        log_path=tmp_path / 'natural.log',
        poll_interval=0.02,
    )
    assert time.monotonic() - started >= 0.08
    assert observation.return_code == 0
    assert observation.output_tail.strip() == 'complete'
    assert signals == []


def test_cleanup_kills_descendant_after_group_leader_exits(tmp_path: Path, monkeypatch) -> None:
    descendant_pid_path = tmp_path / 'descendant.pid'
    descendant_code = (
        'import os, signal, time\n'
        'from pathlib import Path\n'
        'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
        'Path(__import__("sys").argv[1]).write_text(str(os.getpid()))\n'
        'time.sleep(30)\n'
    )
    leader_code = (
        'import subprocess, sys, time\n'
        'subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2]])\n'
        'time.sleep(30)\n'
    )
    leader = subprocess.Popen(
        [sys.executable, '-c', leader_code, descendant_code, str(descendant_pid_path)],
        start_new_session=True,
    )
    real_killpg = os.killpg
    leader_exited_before_kill = []

    def record_killpg(process_group_id: int, signal_number: int) -> None:
        if signal_number == signal.SIGKILL:
            leader_exited_before_kill.append(leader.poll() is not None)
        real_killpg(process_group_id, signal_number)

    monkeypatch.setattr(process_supervisor.os, 'killpg', record_killpg)
    try:
        deadline = time.monotonic() + 3
        descendant_pid = 0
        while time.monotonic() < deadline:
            try:
                descendant_pid = int(descendant_pid_path.read_text())
            except (FileNotFoundError, ValueError):
                time.sleep(0.02)
                continue
            break
        if not descendant_pid:
            pytest.fail('descendant did not become ready')

        process_supervisor._terminate_process_group(leader)

        assert leader.poll() is not None
        assert leader_exited_before_kill == [True]
        deadline = time.monotonic() + 3
        while process_supervisor._process_group_exists(leader.pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not process_supervisor._process_group_exists(leader.pid)
        with pytest.raises(ProcessLookupError):
            os.kill(descendant_pid, 0)
    finally:
        try:
            os.killpg(leader.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        leader.wait()
