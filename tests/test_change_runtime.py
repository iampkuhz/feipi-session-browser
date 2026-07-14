from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from scripts.agent_runtime.change.runtime import (
    BoundedMetadataLock,
    LockBusyError,
    LockInvariantError,
    StaleLockEpochError,
    append_event,
    append_jsonl,
    run_bounded,
    sanitized_environment,
    write_atomic_json,
)

ROOT = Path(__file__).resolve().parents[1]


def _process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    status = subprocess.run(
        ['ps', '-o', 'stat=', '-p', str(pid)],
        text=True,
        capture_output=True,
        check=False,
        timeout=1,
    ).stdout.strip()
    return bool(status and not status.startswith('Z'))


def test_sanitized_environment_and_runner_hide_provider_data(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_DATA_DIR', '/private/codex')
    monkeypatch.setenv('QODER_DATA_DIR', '/private/qoder')
    monkeypatch.setenv('CLAUDE_DATA_DIR', '/private/claude')
    monkeypatch.setenv('CODEX_TRANSCRIPT_PATH', '/private/transcript')
    monkeypatch.setenv('VISIBLE_VALUE', 'base')

    selected = sanitized_environment({'VISIBLE_VALUE': 'override', 'EXPLICIT_VALUE': 'yes'})
    assert not any(key.startswith(('CODEX_', 'QODER_', 'CLAUDE_')) for key in selected)
    assert selected['VISIBLE_VALUE'] == 'override'
    assert selected['EXPLICIT_VALUE'] == 'yes'
    assert selected['PATH'] and selected['HOME']

    code = (
        'import json, os; '
        'print(json.dumps({"provider": os.getenv("CODEX_DATA_DIR"), '
        '"visible": os.getenv("VISIBLE_VALUE"), "explicit": os.getenv("EXPLICIT_VALUE")}))'
    )
    result = run_bounded(
        [sys.executable, '-c', code],
        cwd=tmp_path,
        timeout=2,
        env={'VISIBLE_VALUE': 'override', 'EXPLICIT_VALUE': 'yes'},
        log_path=tmp_path / 'run.log',
    )
    assert result.passed
    assert json.loads(result.output_tail.strip()) == {
        'provider': None,
        'visible': 'override',
        'explicit': 'yes',
    }


def test_runner_timeout_reaps_process_group_and_returns_limited_tail(tmp_path):
    pid_path = tmp_path / 'child.pid'
    code = (
        'import pathlib, subprocess, sys, time; '
        'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
        f'pathlib.Path({str(pid_path)!r}).write_text(str(child.pid)); '
        'print("x"*6000, flush=True); time.sleep(30)'
    )

    result = run_bounded(
        [sys.executable, '-c', code],
        cwd=tmp_path,
        timeout=0.6,
        env={},
        log_path=tmp_path / 'timeout.log',
    )

    assert result.exit_reason == 'TIMEOUT'
    assert result.timed_out is True
    assert result.duration_seconds < 3
    assert len(result.output_tail.encode()) <= 4096
    child_pid = int(pid_path.read_text())
    deadline = time.monotonic() + 2
    while _process_running(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _process_running(child_pid)


def test_runner_rejects_shell_string(tmp_path):
    with pytest.raises(TypeError, match='never a shell string'):
        run_bounded(  # type: ignore[arg-type]
            'echo unsafe', cwd=tmp_path, timeout=1, env={}, log_path=tmp_path / 'unsafe.log'
        )


def test_missing_executable_returns_structured_spawn_error(tmp_path):
    result = run_bounded(
        ['/definitely/missing/change-runtime-command'],
        cwd=tmp_path,
        timeout=1,
        env={},
        log_path=tmp_path / 'missing.log',
    )

    assert result.exit_reason == 'SPAWN_ERROR'
    assert result.return_code is None
    assert result.duration_seconds < 1
    assert 'FileNotFoundError' in result.output_tail


def test_live_lock_returns_busy_with_owner_within_default_budget(tmp_path):
    path = tmp_path / 'controller.lock'
    first = BoundedMetadataLock(path, session_id='session-a', change_id='change-a', epoch=1)
    first.acquire()
    started = time.monotonic()
    try:
        with pytest.raises(LockBusyError) as captured:
            BoundedMetadataLock(
                path, session_id='session-b', change_id='change-b', epoch=1
            ).acquire()
        elapsed = time.monotonic() - started
        assert 1.65 <= elapsed < 2.0
        assert captured.value.code == 'BUSY_RETRYABLE'
        assert captured.value.owner['pid'] == os.getpid()
        assert captured.value.owner['sessionId'] == 'session-a'
    finally:
        assert first.release()


def test_dead_owner_is_reclaimed_without_a_recovery_worktree(tmp_path):
    path = tmp_path / 'dead-owner.lock'
    code = (
        'import os, sys; '
        'from scripts.agent_runtime.change.runtime import BoundedMetadataLock; '
        'lock=BoundedMetadataLock(sys.argv[1],session_id="session-a",'
        'change_id="change-a",epoch=1); lock.acquire(); os._exit(0)'
    )
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    subprocess.run(
        [sys.executable, '-c', code, str(path)],
        cwd=ROOT,
        env=env,
        check=True,
        timeout=5,
    )

    replacement = BoundedMetadataLock(
        path, session_id='session-a', change_id='change-a', epoch=1
    ).acquire()
    try:
        assert replacement.reclaimed_owner['changeId'] == 'change-a'
        assert replacement.metadata['pid'] == os.getpid()
    finally:
        assert replacement.release()


def test_pid_reuse_and_epoch_fencing_cannot_release_new_owner(tmp_path):
    path = tmp_path / 'fenced.lock'
    old = BoundedMetadataLock(path, session_id='session-a', change_id='change-a', epoch=1)
    old.acquire()
    metadata = json.loads(path.read_text())
    metadata['processStartTime'] = 'definitely-not-current-start-time'
    with path.open('w', encoding='utf-8') as handle:
        json.dump(metadata, handle)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())

    replacement = BoundedMetadataLock(
        path, session_id='session-a', change_id='change-a', epoch=2
    ).acquire()
    try:
        assert replacement.reclaimed_owner['epoch'] == 1
        assert old.release() is False
        assert path.exists()
        with pytest.raises(StaleLockEpochError):
            BoundedMetadataLock(
                path,
                session_id='session-stale',
                change_id='change-stale',
                epoch=1,
                timeout_seconds=0,
            ).acquire()
    finally:
        assert replacement.release()


def test_corrupt_lock_metadata_fails_closed(tmp_path):
    path = tmp_path / 'corrupt.lock'
    path.write_text('{not-json', encoding='utf-8')

    with pytest.raises(LockInvariantError) as captured:
        BoundedMetadataLock(path, session_id='session-a', change_id='change-a', epoch=1).acquire()

    assert captured.value.code == 'TERMINAL_BLOCKED'
    assert captured.value.reason_code == 'LOCK_METADATA_CORRUPT'
    assert path.read_text() == '{not-json'


def test_atomic_json_failure_preserves_previous_snapshot(tmp_path, monkeypatch):
    from scripts.agent_runtime import storage

    path = tmp_path / 'snapshot.json'
    write_atomic_json(path, {'version': 1})

    def fail_replace(_source, _target):
        raise OSError('injected replace failure')

    monkeypatch.setattr(storage.os, 'replace', fail_replace)
    with pytest.raises(OSError, match='injected'):
        write_atomic_json(path, {'version': 2})

    assert json.loads(path.read_text()) == {'version': 1}
    assert not list(tmp_path.glob('.*.tmp'))


def test_append_only_jsonl_and_event_artifacts(tmp_path):
    journal = tmp_path / 'attempts.jsonl'
    append_jsonl(journal, {'attemptId': 'attempt-1', 'status': 'FAIL'})
    append_jsonl(journal, {'attemptId': 'attempt-2', 'status': 'PASS'})
    assert [json.loads(line)['attemptId'] for line in journal.read_text().splitlines()] == [
        'attempt-1',
        'attempt-2',
    ]

    first = append_event(tmp_path / 'audit', {'event': 'ATTEMPT_STARTED'})
    second = append_event(tmp_path / 'audit', {'event': 'ATTEMPT_FINISHED'})
    assert first != second
    assert json.loads(first.read_text())['event'] == 'ATTEMPT_STARTED'
    assert json.loads(second.read_text())['event'] == 'ATTEMPT_FINISHED'
