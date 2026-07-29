from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from scripts.gates import executor
from scripts.gates.planner import plan
from scripts.gates.report import PASS, GateDetail
from scripts.gates.resource_lock import (
    NamedResourceLock,
    ResourceLockSet,
    ResourceLockTimeoutError,
    owner_metadata,
)
from scripts.gates.support import reserve_port


def test_multi_resource_lock_uses_stable_order_and_finally_release(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    owner = owner_metadata(
        run_id='run-a',
        client='codex',
        session_id='s-a',
        worktree_id='checkout-a',
        target='java-src',
    )
    locks = ResourceLockSet(
        tmp_path,
        ['playwright-browser', 'gradle-daemon', 'fixture-server'],
        owner,
        timeout_seconds=1,
    )
    try:
        results = locks.acquire()
        assert [item.resource for item in results] == [
            'fixture-server',
            'gradle-daemon',
            'playwright-browser',
        ]
        for item in results:
            data = json.loads(Path(item.path).read_text(encoding='utf-8'))
            assert data['runId'] == 'run-a'
            assert data['pid'] == os.getpid()
            assert data['hostMarker']
    finally:
        locks.release()
    assert list((tmp_path / 'runtime' / 'locks').glob('*.lock')) == []


def test_resource_lock_timeout_reports_owner(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    first = NamedResourceLock(
        tmp_path,
        'gradle-daemon',
        owner_metadata(
            run_id='run-a',
            client='codex',
            session_id='s-a',
            worktree_id='checkout-a',
            target='java-build',
        ),
    )
    assert first.try_acquire()
    try:
        second = NamedResourceLock(
            tmp_path,
            'gradle-daemon',
            owner_metadata(
                run_id='run-b',
                client='qoder',
                session_id='s-b',
                worktree_id='checkout-b',
                target='java-build',
            ),
        )
        try:
            second.acquire(timeout_seconds=0.01)
        except ResourceLockTimeoutError as exc:
            assert exc.resource == 'gradle-daemon'
            assert exc.owner['runId'] == 'run-a'
        else:
            raise AssertionError('expected lock timeout')
    finally:
        first.release()


def test_stale_lock_reclaimed_when_pid_is_dead(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    lock_path = tmp_path / 'runtime' / 'locks' / 'fixture-server.lock'
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps({'pid': 99999999, 'runId': 'dead-run', 'processStartTime': 'dead'}) + '\n'
    )
    old = time.time() - 10
    os.utime(lock_path, (old, old))
    lock = NamedResourceLock(
        tmp_path,
        'fixture-server',
        owner_metadata(
            run_id='run-live',
            client='codex',
            session_id='s-live',
            worktree_id='checkout-live',
            target='session-detail',
        ),
        stale_seconds=1,
    )
    assert lock.try_acquire()
    try:
        assert json.loads(lock_path.read_text(encoding='utf-8'))['runId'] == 'run-live'
    finally:
        lock.release()


@pytest.mark.parametrize('raw', ['', '{broken', '[]'])
def test_invalid_resource_lock_reclaimed_only_after_grace(
    tmp_path: Path, monkeypatch, raw: str
) -> None:
    """empty/corrupt lock 只有在 UID、inode 和 grace 复核后才可回收。"""
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    path = tmp_path / 'runtime/locks/shared.lock'
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding='utf-8')
    lock = NamedResourceLock(tmp_path, 'shared', owner_metadata(run_id='new'), stale_seconds=60)
    assert not lock.try_acquire()
    old = time.time() - 120
    os.utime(path, (old, old))
    assert lock.try_acquire()
    assert lock.reclaim_audit['previousState'] in {'empty', 'corrupt'}
    lock.release()


def _write_fenced_owner(path: Path, *, start_time: str) -> None:
    """写入与当前 inode 一致的 v2 owner fixture。"""
    path.write_text('{}\n', encoding='utf-8')
    metadata = path.stat()
    path.write_text(
        json.dumps(
            {
                'schemaVersion': 2,
                'pid': os.getpid(),
                'processStartTime': start_time,
                'fencingToken': 'old-epoch',
                'ownerUid': metadata.st_uid,
                'lockDevice': metadata.st_dev,
                'lockInode': metadata.st_ino,
            }
        )
        + '\n',
        encoding='utf-8',
    )


def test_live_owner_never_reclaimed_and_pid_reuse_is_reclaimed_after_grace(
    tmp_path: Path, monkeypatch
) -> None:
    """live owner 即使过旧也保留；相同 PID 的 start-time 漂移按 PID reuse 回收。"""
    from scripts.gates.resource_lock import _pid_start_time

    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    path = tmp_path / 'runtime/locks/shared.lock'
    path.parent.mkdir(parents=True)
    _write_fenced_owner(path, start_time=_pid_start_time(os.getpid()))
    old = time.time() - 120
    os.utime(path, (old, old))
    contender = NamedResourceLock(tmp_path, 'shared', owner_metadata(run_id='new'), stale_seconds=1)
    assert not contender.try_acquire()
    assert json.loads(path.read_text())['fencingToken'] == 'old-epoch'

    _write_fenced_owner(path, start_time='reused-process-start')
    os.utime(path, (old, old))
    assert contender.try_acquire()
    assert contender.reclaimed_owner['fencingToken'] == 'old-epoch'
    contender.release()


def test_resource_lock_release_and_heartbeat_are_fenced(tmp_path: Path, monkeypatch) -> None:
    """旧 epoch 修改 token 后不得 heartbeat 或删除新 owner。"""
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    lock = NamedResourceLock(tmp_path, 'shared', owner_metadata(run_id='run-a'))
    assert lock.try_acquire()
    data = json.loads(lock.path.read_text())
    data['fencingToken'] = 'new-epoch'
    lock.path.write_text(json.dumps(data) + '\n', encoding='utf-8')
    before = lock.path.stat().st_mtime_ns
    lock.heartbeat()
    assert lock.path.stat().st_mtime_ns == before
    lock.release()
    assert lock.path.exists()


def test_two_fixture_ports_are_distinct_and_records_are_run_scoped(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    monkeypatch.setenv('FEIPI_RUN_ID', 'run-a')
    first = reserve_port(tmp_path, 'fixture-server', hold_socket=True)
    monkeypatch.setenv('FEIPI_RUN_ID', 'run-b')
    second = reserve_port(tmp_path, 'fixture-server', hold_socket=True)
    try:
        assert first.port != second.port
        assert first.path.name.startswith('run-a-')
        assert second.path.name.startswith('run-b-')
    finally:
        first.close()
        second.close()


def test_executor_acquires_target_resources(monkeypatch, tmp_path: Path):
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    identity = executor.gate_support.identity_from_values(
        agent_client='test', session_id='session', run_id='run', worktree_id='worktree'
    )
    monkeypatch.setattr(executor.gate_support, 'identity_from_values', lambda: identity)
    active: list[list[str]] = []

    def fake_run(name, cmd, cwd, **kwargs):
        active.append(sorted(path.stem for path in (tmp_path / 'runtime/locks').glob('*.lock')))
        return GateDetail(name=name, status=PASS)

    monkeypatch.setattr(executor, 'run_cmd', fake_run)
    monkeypatch.setattr(executor, 'command_for_gate', lambda *_args: ['/bin/true'])
    gate_plan = plan(['java/app-cli/src/main/java/App.java'], ['java-src'], tier='required')
    details = executor.execute_plan(executor.build_execution_plan(gate_plan, tmp_path), tmp_path)
    assert details
    resource_runs = [item for item in active if item]
    assert resource_runs and all(
        item == ['gradle-daemon', 'java-build-tree'] for item in resource_runs
    )
    assert list((tmp_path / 'runtime/locks').glob('*.lock')) == []
