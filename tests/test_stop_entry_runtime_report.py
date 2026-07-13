from __future__ import annotations

import json
import os
import subprocess
import time
from typing import TYPE_CHECKING

import pytest
from scripts.agent_runtime.session.contract import resolve_checkout_identity, resolve_runtime_root
from scripts.agent_runtime.session.lease import acquire_writer_lease
from scripts.agent_runtime.session.registry import Registry
from scripts.agent_runtime.stop.evidence import (
    GitEvidenceError,
    collect_git_evidence,
    filter_baseline_dirty,
)
from scripts.agent_runtime.stop.pipeline import run_stop
from scripts.agent_runtime.stop.recovery import (
    FileLock,
    matching_reentry_failure,
    recovery_scope,
    update_reentry,
)
from scripts.checks.check_agent_runtime_report import validate_runtime_report

if TYPE_CHECKING:
    from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def test_stop_quality_calls_unified_gate_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from scripts.agent_runtime.stop import pipeline as stop_pipeline
    from scripts.agent_runtime.stop.model import StopContext

    captured: dict[str, object] = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            passed=True,
            reused=False,
            details=(SimpleNamespace(name='settingsJson', status='PASS'),),
        )

    monkeypatch.setattr(stop_pipeline, 'run_service', fake_service)
    context = StopContext('codex', {})
    context.repo_root = tmp_path
    context.report_path = tmp_path / 'quality' / 'runtime-report.json'
    context.changed_files = ['.claude/settings.json']
    context.targets = ['hook-runtime']
    context.change_id = 'change-a'
    context.read_only = False

    stop_pipeline._gate(context)

    assert context.gates_ok is True
    assert context.failures == []
    assert context.gate_results == [{'name': 'settingsJson', 'status': 'EXECUTED'}]
    assert captured['tier'] == 'required'
    assert captured['changed_files'] == ['.claude/settings.json']


def test_baseline_dirty_filter_uses_content_state() -> None:
    baseline = {
        'exists': True,
        'size': 3,
        'sha256': 'baseline-hash',
    }
    evidence = {
        'initialDirtySnapshot': {
            'tracked': ['same.txt', 'modified-again.txt'],
            'untracked': [],
            'pathStates': {
                'same.txt': baseline,
                'modified-again.txt': baseline,
            },
        },
        'currentDirtyPathStates': {
            'same.txt': baseline,
            'modified-again.txt': {
                'exists': True,
                'size': 4,
                'sha256': 'new-hash',
            },
        },
    }

    changed, baseline_paths = filter_baseline_dirty(
        ['same.txt', 'modified-again.txt', 'new.txt'], evidence
    )

    assert changed == ['modified-again.txt', 'new.txt']
    assert baseline_paths == {'same.txt', 'modified-again.txt'}


def test_legacy_baseline_dirty_without_hash_keeps_path_exclusion() -> None:
    changed, baseline_paths = filter_baseline_dirty(
        ['legacy.txt', 'new.txt'],
        {
            'initialDirtySnapshot': {
                'tracked': ['legacy.txt'],
                'untracked': [],
            }
        },
    )

    assert changed == ['new.txt']
    assert baseline_paths == {'legacy.txt'}


def _repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / 'repo'
    repo.mkdir()
    _run(['git', 'init', '-b', 'main'], repo)
    _run(['git', 'config', 'user.email', 'stop@example.invalid'], repo)
    _run(['git', 'config', 'user.name', 'Stop Test'], repo)
    (repo / 'README.md').write_text('x\n', encoding='utf-8')
    _run(['git', 'add', 'README.md'], repo)
    _run(['git', 'commit', '-m', 'init'], repo)
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    (repo / 'harness').mkdir()
    (repo / 'harness' / 'agent-runtime.manifest.yaml').write_text(
        'protected_roots:\n  - scripts/\n  - openspec/\n', encoding='utf-8'
    )
    (repo / '.gitignore').write_text('tmp/\n', encoding='utf-8')
    _run(['git', 'add', 'harness/agent-runtime.manifest.yaml', '.gitignore'], repo)
    _run(['git', 'commit', '-m', 'manifest'], repo)
    return repo


def _record(
    repo: Path, run_id: str, session: str, change: str = 'adopt-client-checkout-runtime'
) -> dict:
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    facts = resolve_checkout_identity(repo, checkout_creator='unknown', base_commit=head)
    return {
        'schemaVersion': 2,
        'runId': run_id,
        'repoKey': facts['repoKey'],
        'client': 'codex',
        'taskId': f'task-{run_id}',
        'sessionId': session,
        'worktreeId': facts['worktreeId'],
        'checkoutRoot': facts['checkoutRoot'],
        'checkoutKind': facts['checkoutKind'],
        'checkoutCreator': facts['checkoutCreator'],
        'gitCommonDir': facts['gitCommonDir'],
        'branch': facts['branch'],
        'detached': facts['detached'],
        'targetBranch': facts['branch'],
        'primaryRepoRoot': facts['primaryRepoRoot'],
        'baseCommit': head,
        'headCommit': head,
        'initialDirtySnapshot': {
            'dirty': False,
            'tracked': [],
            'untracked': [],
            'capturedAt': '2026-01-01T00:00:00Z',
        },
        'changeAttribution': {
            'baseline': 'initialDirtySnapshot',
            'preexistingChangesAttributedToRun': False,
            'requiresHandoffIfIndistinguishable': False,
        },
        'changeId': change,
        'status': 'READ_ONLY_READY',
        'allowedPaths': ['scripts', 'openspec'],
        'forbiddenPaths': ['.env', '.mcp.json'],
        'writerLease': {},
        'hookActivation': {'confirmed': True, 'client': 'codex'},
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:01Z',
    }


def _save(repo: Path, *records: dict) -> None:
    root = resolve_runtime_root(repo) / 'runs'
    root.mkdir(parents=True, exist_ok=True)
    for record in records:
        (root / f"{record['runId']}.json").write_text(json.dumps(record), encoding='utf-8')
    (root / 'index.json').write_text(
        json.dumps({'schemaVersion': 2, 'runs': [r['runId'] for r in records]}), encoding='utf-8'
    )


def test_two_run_stop_summaries_do_not_overwrite(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    _save(repo, _record(repo, 'run-a', 'session-a'), _record(repo, 'run-b', 'session-b'))

    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a'}) == 0
    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'session-b', 'run_id': 'run-b'}) == 0

    first = repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json'
    second = repo / 'tmp/agent_logs/codex/session-b/runs/run-b/main/stop-check-summary.json'
    assert first.exists() and second.exists()
    first_summary = json.loads(first.read_text())
    assert first_summary['runId'] == 'run-a'
    assert first_summary['checkoutKind'] == 'primary-checkout'
    assert first_summary['checkoutCreator'] == 'unknown'
    assert first_summary['detached'] is False
    assert first_summary['baseCommitExists'] is True
    assert first_summary['baseIsAncestorOfHead'] is True
    assert first_summary['committedFiles'] == []
    assert first_summary['uncommittedFiles'] == []
    assert first_summary['untrackedFiles'] == []
    assert first_summary['targetStatus']['state'] == 'AT_RESULT'
    assert first_summary['primaryStatus']['clean'] is True
    assert first_summary['runStatus'] == 'VALIDATED'
    assert json.loads(second.read_text())['runId'] == 'run-b'
    runtime = resolve_runtime_root(repo)
    assert (runtime / 'runs/run-a/stop-reentry.json').is_file()
    assert (runtime / 'runs/run-b/stop-reentry.json').is_file()
    assert not (repo / 'tmp/agent_logs/codex/session-a/runs/run-a/stop-reentry.json').exists()


def test_runtime_report_requires_explicit_run_context_and_changed_files_match(
    tmp_path: Path, monkeypatch
):
    repo = _repo(tmp_path, monkeypatch)
    _save(repo, _record(repo, 'run-a', 'session-a'))
    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a'}) == 0
    report = (
        repo
        / 'tmp/quality/codex/session-a/runs/run-a/main/adopt-client-checkout-runtime/runtime-report.json'
    )

    ok = validate_runtime_report(
        run_id='run-a',
        client='codex',
        session_id='session-a',
        change_id='adopt-client-checkout-runtime',
        worktree_root=repo,
        changed_files=[],
        report_path=report,
    )
    assert ok == []
    mismatch = validate_runtime_report(
        run_id='run-a',
        client='codex',
        session_id='session-a',
        change_id='adopt-client-checkout-runtime',
        worktree_root=repo,
        changed_files=['scripts/other.py'],
        report_path=report,
    )
    assert any('changed_files' in item for item in mismatch)
    report_data = json.loads(report.read_text(encoding='utf-8'))
    assert report_data['committedFiles'] == []
    assert report_data['targetStatus']['state'] == 'AT_RESULT'
    assert report_data['primary']['clean'] is True


def test_stop_hook_active_does_not_block_by_itself(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    _save(repo, _record(repo, 'run-a', 'session-a'))

    assert (
        run_stop(
            'codex',
            {
                'cwd': str(repo),
                'session_id': 'session-a',
                'run_id': 'run-a',
                'stop_hook_active': True,
            },
        )
        == 0
    )

    summary = json.loads(
        (
            repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json'
        ).read_text()
    )
    assert summary['status'] == 'PASS'
    assert any('stop_hook_active reentry observed' in item for item in summary['warnings'])


def test_stop_without_authoritative_run_fails_without_legacy_state(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    payload = {
        'cwd': str(repo),
        'session_id': 'session-a',
        'run_id': 'missing-run',
        'stop_hook_active': True,
    }

    assert run_stop('codex', payload) == 2
    assert not (repo / 'tmp/agent_logs/legacy').exists()
    assert not (repo / 'tmp/agent_logs/codex/session-a/runs/missing-run').exists()
    assert not (resolve_runtime_root(repo) / 'runs/missing-run').exists()


def test_repeated_failure_circuit_and_audit_are_isolated_by_run(
    tmp_path: Path, monkeypatch, capsys
):
    from scripts.agent_runtime.stop import report as stop_report

    repo = _repo(tmp_path, monkeypatch)
    _save(repo, _record(repo, 'run-a', 'session-a'), _record(repo, 'run-b', 'session-b'))
    monkeypatch.setattr(
        stop_report.check_agent_runtime_report,
        'validate_runtime_report',
        lambda **_kwargs: ['forced stable report failure'],
    )
    payload = {
        'cwd': str(repo),
        'session_id': 'session-a',
        'run_id': 'run-a',
        'stop_hook_active': True,
    }

    assert run_stop('codex', payload) == 2
    assert run_stop('codex', payload) == 2
    assert run_stop('codex', payload) == 2
    assert 'HANDOFF_BLOCKED circuit OPEN' in capsys.readouterr().err

    summary = json.loads(
        (
            repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json'
        ).read_text()
    )
    assert summary['continuationCount'] > 2
    assert summary['circuitState'] == 'OPEN'
    assert summary['status'] == 'BLOCKED'
    assert summary['runStatus'] == 'BLOCKED'
    assert any('continuation limit' in item for item in summary['blockingFailures'])
    runtime = resolve_runtime_root(repo)
    state_a = json.loads((runtime / 'runs/run-a/stop-reentry.json').read_text())
    assert state_a['scope']['runId'] == 'run-a'
    assert state_a['scope']['sessionId'] == 'session-a'
    assert state_a['scope']['worktreeId'] == _record(repo, 'run-a', 'session-a')['worktreeId']
    assert state_a['circuitBreaker']['state'] == 'OPEN'
    assert not (runtime / 'runs/run-b/stop-reentry.json').exists()
    registry_record = Registry(repo).load_run('run-a')
    assert registry_record['status'] == 'BLOCKED'
    assert registry_record['stopExitCode'] == 2
    assert registry_record['stopValidation']['status'] == 'FAIL'
    runtime_report = json.loads(
        (
            repo / 'tmp/quality/codex/session-a/runs/run-a/main/'
            'adopt-client-checkout-runtime/runtime-report.json'
        ).read_text()
    )
    assert runtime_report['status'] == 'BLOCKED'
    audit = [json.loads(path.read_text()) for path in (runtime / 'audit').glob('*.json')]
    assert audit
    assert {item['runId'] for item in audit} == {'run-a'}
    assert run_stop('codex', payload, adapter_mode='cli') == 2


def test_retryable_stop_failure_preserves_active_writer(tmp_path: Path, monkeypatch):
    from scripts.agent_runtime.stop import report as stop_report

    repo = _repo(tmp_path, monkeypatch)
    record = _record(repo, 'run-a', 'session-a')
    _save(repo, record)
    writable, lease = acquire_writer_lease(Registry(repo), record)
    assert writable['status'] == 'LOCAL_WRITER'
    assert lease['state'] == 'ACTIVE'
    monkeypatch.setattr(
        stop_report.check_agent_runtime_report,
        'validate_runtime_report',
        lambda **_kwargs: ['forced retryable report failure'],
    )

    payload = {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a'}
    assert run_stop('codex', payload) == 2

    latest = Registry(repo).load_run('run-a')
    assert latest['status'] == 'LOCAL_WRITER'
    assert latest['writerLease']['leaseId'] == lease['leaseId']
    summary = json.loads(
        (
            repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json'
        ).read_text()
    )
    assert summary['status'] == 'BLOCKED'
    assert summary['runStatus'] == 'LOCAL_WRITER'


def test_change_id_update_invalidates_reentry_failure(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    record = _record(repo, 'run-a', 'session-a', change='')
    runtime = resolve_runtime_root(repo)
    reentry = runtime / 'runs/run-a/stop-reentry.json'
    audit = runtime / 'audit'
    scope = recovery_scope(record)
    failures = ['active change is missing for protected changes']

    update_reentry(
        reentry,
        repo,
        failures,
        scope=scope,
        audit_dir=audit,
        change_id='unknown',
    )
    assert matching_reentry_failure(
        reentry,
        repo,
        scope,
        change_id='unknown',
    )[0]
    assert not matching_reentry_failure(
        reentry,
        repo,
        scope,
        change_id='fixed-change',
    )[0]


def test_dependency_installation_invalidates_reentry_failure(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    record = _record(repo, 'run-a', 'session-a', change='change-a')
    reentry = resolve_runtime_root(repo) / 'runs/run-a/stop-reentry.json'
    scope = recovery_scope(record)
    update_reentry(
        reentry,
        repo,
        ['browserLayout=BLOCKED'],
        scope=scope,
        audit_dir=resolve_runtime_root(repo) / 'audit',
        change_id='change-a',
    )
    assert matching_reentry_failure(reentry, repo, scope, change_id='change-a')[0]

    (repo / 'node_modules' / '.bin').mkdir(parents=True)
    (repo / 'node_modules' / '.bin' / 'playwright').touch()

    assert not matching_reentry_failure(reentry, repo, scope, change_id='change-a')[0]


@pytest.mark.contract_case('HOOK-HARNESS-006')
def test_git_evidence_separates_committed_staged_working_and_untracked(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    (repo / 'working.txt').write_text('base\n', encoding='utf-8')
    _run(['git', 'add', 'working.txt'], repo)
    _run(['git', 'commit', '-m', 'working baseline'], repo)
    record = _record(repo, 'run-a', 'session-a')

    (repo / 'committed.txt').write_text('committed\n', encoding='utf-8')
    _run(['git', 'add', 'committed.txt'], repo)
    _run(['git', 'commit', '-m', 'run commit'], repo)
    (repo / 'staged.txt').write_text('staged\n', encoding='utf-8')
    _run(['git', 'add', 'staged.txt'], repo)
    (repo / 'working.txt').write_text('changed\n', encoding='utf-8')
    (repo / 'untracked.txt').write_text('untracked\n', encoding='utf-8')

    facts = collect_git_evidence(repo, record)
    assert facts['committedFiles'] == ['committed.txt']
    assert facts['uncommittedFiles'] == ['staged.txt', 'working.txt']
    assert facts['untrackedFiles'] == ['untracked.txt']
    assert facts['changedFiles'] == ['committed.txt', 'staged.txt', 'working.txt', 'untracked.txt']
    assert len(facts['commits']) == 1
    assert facts['checkoutStatus']['clean'] is False
    assert facts['initialDirtyBaseline']['dirty'] is False

    invalid = dict(record, baseCommit='not-a-commit')
    with pytest.raises(GitEvidenceError):
        collect_git_evidence(repo, invalid)


def test_stop_blocks_when_same_changed_path_mutates_during_required_gates(
    tmp_path: Path, monkeypatch
):
    from types import SimpleNamespace

    from scripts.agent_runtime.stop import evidence as stop_evidence
    from scripts.agent_runtime.stop import pipeline as stop_pipeline
    from scripts.agent_runtime.stop import report as stop_report

    repo = _repo(tmp_path, monkeypatch)
    record = _record(repo, 'run-a', 'session-a')
    _save(repo, record)
    (repo / 'README.md').write_text('before-gate\n', encoding='utf-8')

    monkeypatch.setattr(stop_evidence, 'required_targets', lambda _files: ['harness'])
    monkeypatch.setattr(stop_evidence, 'validate_openspec_evidence', lambda *_args: [])
    monkeypatch.setattr(
        stop_report.check_agent_runtime_report,
        'validate_runtime_report',
        lambda **_kwargs: [],
    )

    def fake_service(**_kwargs):
        (repo / 'README.md').write_text('during-gate\n', encoding='utf-8')
        return SimpleNamespace(
            passed=True,
            reused=False,
            details=(SimpleNamespace(name='fake-gate', status='PASS'),),
        )

    monkeypatch.setattr(stop_pipeline, 'run_service', fake_service)
    real_collect = stop_evidence.collect_git_evidence
    call_count = [0]

    def fingerprinted_collect(repo_root, rec):
        result = real_collect(repo_root, rec)
        call_count[0] += 1
        readme = (repo_root / 'README.md').read_text(encoding='utf-8')
        result['checkoutFingerprint'] = f'fp-{call_count[0]}-{readme}'
        return result

    monkeypatch.setattr(stop_evidence, 'collect_git_evidence', fingerprinted_collect)
    assert (
        run_stop(
            'codex',
            {
                'cwd': str(repo),
                'session_id': 'session-a',
                'run_id': 'run-a',
                'handoff_on_failure': True,
            },
            adapter_mode='cli',
        )
        == 2
    )
    summary_path = repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert summary['status'] == 'BLOCKED'
    assert summary['runStatus'] == 'BLOCKED'
    assert 'checkout Git snapshot changed during Stop validation' in summary['blockingFailures']
    latest = json.loads(
        (resolve_runtime_root(repo) / 'runs/run-a.json').read_text(encoding='utf-8')
    )
    assert latest['status'] == 'BLOCKED'
    assert latest['stopValidation']['fresh'] is False


@pytest.mark.parametrize(
    'raw_paths',
    [b'/absolute\0', b'parent/../escape\0', b'parent/./file\0', b'parent//file\0', b'\0'],
)
def test_untracked_content_snapshot_rejects_unsafe_path_components(
    tmp_path: Path, raw_paths: bytes
):
    from scripts.agent_runtime import git_state

    with pytest.raises(GitEvidenceError):
        git_state.hash_untracked_contents(tmp_path, raw_paths)


def test_untracked_content_snapshot_rejects_intermediate_symlink_escape(tmp_path: Path):
    from scripts.agent_runtime import git_state

    repo = tmp_path / 'repo'
    outside = tmp_path / 'outside'
    repo.mkdir()
    outside.mkdir()
    (outside / 'secret.txt').write_text('secret\n', encoding='utf-8')
    (repo / 'escape').symlink_to(outside, target_is_directory=True)

    with pytest.raises(GitEvidenceError):
        git_state.hash_untracked_contents(repo, b'escape/secret.txt\0')


def test_file_lock_release_and_dead_owner_reclaim_are_exact(tmp_path: Path):
    path = tmp_path / 'locks' / 'run.lock'
    owner = {'runId': 'run-a', 'sessionId': 'session-a', 'worktreeId': 'checkout-a'}
    lock = FileLock(path, owner)
    try:
        assert lock.acquire()
    finally:
        assert lock.release()
    assert not path.exists()

    path.write_text(
        json.dumps(
            {
                **owner,
                'pid': 999_999_999,
                'processStartTime': 'dead-process',
                'fencingToken': 'old-token',
            }
        ),
        encoding='utf-8',
    )
    old = time.time() - 10
    os.utime(path, (old, old))
    lock = FileLock(path, owner, grace_seconds=1)
    assert lock.acquire()
    assert lock.reclaimed_owner['runId'] == 'run-a'
    assert lock.release()

    path.write_text(
        json.dumps(
            {
                **dict(owner, runId='run-b'),
                'pid': 999_999_999,
                'processStartTime': 'dead-process',
                'fencingToken': 'other-token',
            }
        ),
        encoding='utf-8',
    )
    os.utime(path, (old, old))
    assert not FileLock(path, owner, grace_seconds=1).acquire()
    assert path.exists()
