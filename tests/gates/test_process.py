from __future__ import annotations

import inspect
import os
import signal
import subprocess
import sys
import time
from dataclasses import fields
from typing import TYPE_CHECKING

import pytest
from scripts.gates.runtime import process as process_runtime

if TYPE_CHECKING:
    from pathlib import Path


def test_managed_api_has_no_timeout_or_timed_out_result() -> None:
    signature = inspect.signature(process_runtime.run_managed)

    assert 'timeout' not in signature.parameters
    assert {field.name for field in fields(process_runtime.ManagedRunResult)}.isdisjoint(
        {'timeout', 'timed_out'}
    )
    assert not hasattr(process_runtime, 'run_bounded')
    assert not hasattr(process_runtime, 'BoundedRunResult')


def test_run_managed_waits_for_natural_completion_without_signalling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(
        process_runtime.os,
        'killpg',
        lambda pid, signum: signals.append((pid, signum)),
    )
    started = time.monotonic()

    result = process_runtime.run_managed(
        [
            sys.executable,
            '-c',
            "import time; time.sleep(0.15); print('naturally complete')",
        ],
        cwd=tmp_path,
        env=None,
        log_path=tmp_path / 'managed.log',
    )

    assert time.monotonic() - started >= 0.12
    assert result.return_code == 0
    assert result.exit_reason == 'EXITED'
    assert result.output_tail.strip() == 'naturally complete'
    assert signals == []


@pytest.mark.parametrize(
    'raised',
    [RuntimeError('parent failed'), process_runtime.ManagedRunInterrupted(signal.SIGTERM)],
)
def test_parent_exception_or_explicit_termination_cleans_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raised: BaseException,
) -> None:
    class FakeProcess:
        pid = 731

        def wait(self) -> int:
            raise raised

    cleaned: list[FakeProcess] = []
    monkeypatch.setattr(process_runtime.subprocess, 'Popen', lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        process_runtime,
        '_terminate_process_group',
        cleaned.append,
    )

    with pytest.raises(type(raised)):
        process_runtime.run_managed(
            ['fake-command'],
            cwd=tmp_path,
            env=None,
            log_path=tmp_path / 'interrupted.log',
        )

    assert len(cleaned) == 1
    assert cleaned[0].pid == 731


def test_cleanup_kills_descendant_after_process_group_leader_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    leader_exited_before_kill: list[bool] = []

    def record_killpg(process_group_id: int, signal_number: int) -> None:
        if signal_number == signal.SIGKILL:
            leader_exited_before_kill.append(leader.poll() is not None)
        real_killpg(process_group_id, signal_number)

    monkeypatch.setattr(process_runtime.os, 'killpg', record_killpg)
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

        process_runtime._terminate_process_group(leader)

        assert leader.poll() is not None
        assert leader_exited_before_kill == [True]
        deadline = time.monotonic() + 3
        while process_runtime._process_group_exists(leader.pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not process_runtime._process_group_exists(leader.pid)
        with pytest.raises(ProcessLookupError):
            os.kill(descendant_pid, 0)
    finally:
        try:
            os.killpg(leader.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        leader.wait()


def test_sigterm_handler_is_installed_and_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        pid = 941

        def wait(self) -> int:
            return 0

    previous_handler = object()
    handler_changes: list[object] = []
    monkeypatch.setattr(process_runtime.subprocess, 'Popen', lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(process_runtime.signal, 'getsignal', lambda signum: previous_handler)
    monkeypatch.setattr(
        process_runtime.signal,
        'signal',
        lambda signum, handler: handler_changes.append(handler),
    )

    process_runtime.run_managed(
        ['fake-command'],
        cwd=tmp_path,
        env=None,
        log_path=tmp_path / 'signal-handler.log',
    )

    assert handler_changes == [process_runtime._raise_on_termination, previous_handler]


def test_sigterm_handler_raises_explicit_interruption() -> None:
    with pytest.raises(process_runtime.ManagedRunInterrupted) as caught:
        process_runtime._raise_on_termination(signal.SIGTERM, None)

    assert caught.value.signal_number == signal.SIGTERM
