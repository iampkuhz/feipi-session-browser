from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.harness.port_allocator import reserve_port
from scripts.harness.resource_lock import NamedResourceLock, ResourceLockSet, ResourceLockTimeout, owner_metadata
from scripts.quality import run_required_quality_gates


def test_multi_resource_lock_uses_stable_order_and_finally_release(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    owner = owner_metadata(run_id='run-a', client='codex', session_id='s-a', worktree_id='checkout-a', target='java-src')
    locks = ResourceLockSet(tmp_path, ['playwright-browser', 'gradle-daemon', 'fixture-server'], owner, timeout_seconds=1)
    try:
        results = locks.acquire()
        assert [item.resource for item in results] == ['fixture-server', 'gradle-daemon', 'playwright-browser']
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
        owner_metadata(run_id='run-a', client='codex', session_id='s-a', worktree_id='checkout-a', target='java-build'),
    )
    assert first.try_acquire()
    try:
        second = NamedResourceLock(
            tmp_path,
            'gradle-daemon',
            owner_metadata(run_id='run-b', client='qoder', session_id='s-b', worktree_id='checkout-b', target='java-build'),
        )
        try:
            second.acquire(timeout_seconds=0.01)
        except ResourceLockTimeout as exc:
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
    lock_path.write_text(json.dumps({'pid': 99999999, 'runId': 'dead-run', 'processStartTime': 'dead'}) + '\n')
    lock = NamedResourceLock(
        tmp_path,
        'fixture-server',
        owner_metadata(run_id='run-live', client='codex', session_id='s-live', worktree_id='checkout-live', target='session-detail'),
    )
    assert lock.try_acquire()
    try:
        assert json.loads(lock_path.read_text(encoding='utf-8'))['runId'] == 'run-live'
    finally:
        lock.release()


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


def test_required_runner_acquires_target_resources(monkeypatch, tmp_path: Path):
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    monkeypatch.setattr(run_required_quality_gates, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(run_required_quality_gates, 'get_changed_files', lambda explicit_json=None: ['java/app-cli/src/main/java/App.java'])
    monkeypatch.setattr(run_required_quality_gates, '_run_global_preflight', lambda repo_root, dry_run: True)
    monkeypatch.setattr(run_required_quality_gates, 'compute_tier_required_targets', lambda tier, changed: ['java-src'])
    monkeypatch.setattr(run_required_quality_gates, 'effective_targets', lambda targets: targets)
    calls: list[list[str]] = []

    def fake_run_gate(
        target,
        change_id,
        quality_dir=None,
        changed_files=None,
        *,
        full_baseline=False,
    ):
        active = sorted(path.stem for path in (tmp_path / 'runtime' / 'locks').glob('*.lock'))
        calls.append(active)
        assert changed_files == ['java/app-cli/src/main/java/App.java']
        assert full_baseline is False
        return True, str(tmp_path / 'summary.json')

    monkeypatch.setattr(run_required_quality_gates, 'run_gate', fake_run_gate)
    monkeypatch.setattr(
        run_required_quality_gates.sys,
        'argv',
        ['run_required_quality_gates.py', '--change-id', 'adopt-client-checkout-runtime'],
    )
    assert run_required_quality_gates.main() == 0
    assert calls == [['gradle-daemon', 'java-build-tree']]
    assert list((tmp_path / 'runtime' / 'locks').glob('*.lock')) == []
