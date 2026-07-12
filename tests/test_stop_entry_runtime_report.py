from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.harness.primary_session import resolve_checkout_identity, resolve_runtime_root
from scripts.harness.sessionctl import Registry, acquire_writer_lease
from scripts.harness.stop_entry import FileLock, collect_git_evidence, run_stop
from scripts.harness.stop_entry_checks.reentry import (
    matching_reentry_failure,
    recovery_scope,
    update_reentry,
)
from scripts.harness.stop_helpers import GitEvidenceError
from scripts.quality.check_agent_runtime_report import validate_runtime_report


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_stop_quality_keeps_atomic_gate_command_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.harness.stop_entry_checks import quality as stop_quality

    captured: list[tuple[list[str], dict[str, str]]] = []
    monkeypatch.setattr(stop_quality, 'QUALITY_TARGETS', {'hook-runtime': ['settingsJson']})
    monkeypatch.setattr(stop_quality, 'GATE_PATTERNS', {})
    monkeypatch.setattr(stop_quality, 'target_parallel_meta', lambda _target: {})
    monkeypatch.setattr(
        stop_quality,
        '_gate_command',
        lambda _gate, _root, _target: ['python', '-c', 'print("ok")'],
    )

    def capture(
        _name: str,
        cmd: list[str],
        _repo_root: Path,
        env: dict[str, str],
        timeout: int = 1800,
    ) -> bool:
        del timeout
        captured.append((cmd, env))
        return True

    monkeypatch.setattr(stop_quality, 'run_cmd', capture)

    passed, failures, results = stop_quality.run_quality_checks(
        'change-a', ['.claude/settings.json'], tmp_path, ['hook-runtime']
    )

    assert passed is True
    assert failures == []
    assert results == [{'name': 'settingsJson', 'status': 'PASS'}]
    assert captured[0][0] == ['python', '-c', 'print("ok")']
    assert captured[0][1]['QUALITY_CHANGED_FILES'] == '[".claude/settings.json"]'


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
    (repo / 'harness' / 'agent-runtime.manifest.yaml').write_text('protected_roots:\n  - scripts/\n  - openspec/\n', encoding='utf-8')
    (repo / '.gitignore').write_text('tmp/\n', encoding='utf-8')
    _run(['git', 'add', 'harness/agent-runtime.manifest.yaml', '.gitignore'], repo)
    _run(['git', 'commit', '-m', 'manifest'], repo)
    return repo


def _record(repo: Path, run_id: str, session: str, change: str = 'adopt-client-checkout-runtime') -> dict:
    head = subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True
    ).strip()
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
    (root / 'index.json').write_text(json.dumps({'schemaVersion': 2, 'runs': [r['runId'] for r in records]}), encoding='utf-8')


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


def test_runtime_report_requires_explicit_run_context_and_changed_files_match(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    _save(repo, _record(repo, 'run-a', 'session-a'))
    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a'}) == 0
    report = repo / 'tmp/quality/codex/session-a/runs/run-a/main/adopt-client-checkout-runtime/runtime-report.json'

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

    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a', 'stop_hook_active': True}) == 0

    summary = json.loads((repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json').read_text())
    assert summary['status'] == 'PASS'
    assert any('stop_hook_active reentry observed' in item for item in summary['warnings'])


def test_stop_without_authoritative_run_fails_without_legacy_state(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    payload = {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'missing-run', 'stop_hook_active': True}

    assert run_stop('codex', payload) == 2
    assert not (repo / 'tmp/agent_logs/legacy').exists()
    assert not (repo / 'tmp/agent_logs/codex/session-a/runs/missing-run').exists()
    assert not (resolve_runtime_root(repo) / 'runs/missing-run').exists()


def test_repeated_failure_circuit_and_audit_are_isolated_by_run(tmp_path: Path, monkeypatch):
    from scripts.harness.stop_entry_checks import quality as stop_quality

    repo = _repo(tmp_path, monkeypatch)
    _save(repo, _record(repo, 'run-a', 'session-a'), _record(repo, 'run-b', 'session-b'))
    monkeypatch.setattr(
        stop_quality.check_agent_runtime_report,
        'validate_runtime_report',
        lambda **_kwargs: ['forced stable report failure'],
    )
    payload = {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a', 'stop_hook_active': True}

    assert run_stop('codex', payload) == 2
    assert run_stop('codex', payload) == 2
    assert run_stop('codex', payload) == 0

    summary = json.loads((repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json').read_text())
    assert summary['continuationCount'] > 2
    assert summary['circuitState'] == 'OPEN'
    assert summary['status'] == 'BLOCKED'
    assert summary['runStatus'] == 'READ_ONLY_READY'
    assert any('continuation limit' in item for item in summary['blockingFailures'])
    runtime = resolve_runtime_root(repo)
    state_a = json.loads((runtime / 'runs/run-a/stop-reentry.json').read_text())
    assert state_a['scope']['runId'] == 'run-a'
    assert state_a['scope']['sessionId'] == 'session-a'
    assert state_a['scope']['worktreeId'] == _record(repo, 'run-a', 'session-a')['worktreeId']
    assert state_a['circuitBreaker']['state'] == 'OPEN'
    assert not (runtime / 'runs/run-b/stop-reentry.json').exists()
    audit = [json.loads(path.read_text()) for path in (runtime / 'audit').glob('*.json')]
    assert audit
    assert {item['runId'] for item in audit} == {'run-a'}
    assert run_stop('codex', payload, adapter_mode='cli') == 2


def test_retryable_stop_failure_preserves_active_writer(tmp_path: Path, monkeypatch):
    from scripts.harness.stop_entry_checks import quality as stop_quality

    repo = _repo(tmp_path, monkeypatch)
    record = _record(repo, 'run-a', 'session-a')
    _save(repo, record)
    writable, lease = acquire_writer_lease(Registry(repo), record)
    assert writable['status'] == 'LOCAL_WRITER'
    assert lease['state'] == 'ACTIVE'
    monkeypatch.setattr(
        stop_quality.check_agent_runtime_report,
        'validate_runtime_report',
        lambda **_kwargs: ['forced retryable report failure'],
    )

    payload = {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a'}
    assert run_stop('codex', payload) == 2

    latest = Registry(repo).load_run('run-a')
    assert latest['status'] == 'LOCAL_WRITER'
    assert latest['writerLease']['leaseId'] == lease['leaseId']
    summary = json.loads(
        (repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json').read_text()
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


def _mutate_and_pass(repo: Path) -> tuple[bool, list[str], list[dict[str, str]]]:
    """模拟 check 执行期间文件被修改，但 check 本身通过。"""
    (repo / 'README.md').write_text('during-gate\n', encoding='utf-8')
    return True, [], [{'name': 'fake-gate', 'status': 'PASS'}]


def test_stop_blocks_when_same_changed_path_mutates_during_required_gates(
    tmp_path: Path, monkeypatch
):
    from scripts.harness.stop_entry_checks import quality as stop_quality
    from scripts.harness.stop_entry_checks import git_evidence as stop_git_evidence

    repo = _repo(tmp_path, monkeypatch)
    record = _record(repo, 'run-a', 'session-a')
    _save(repo, record)
    (repo / 'README.md').write_text('before-gate\n', encoding='utf-8')

    monkeypatch.setattr(stop_quality.stop_helpers, 'required_targets', lambda _files: ['harness'])
    monkeypatch.setattr(
        stop_quality.stop_helpers,
        'changed_files_require_openspec',
        lambda _files: False,
    )
    monkeypatch.setattr(
        stop_quality.check_agent_runtime_report,
        'validate_runtime_report',
        lambda **_kwargs: [],
    )
    # 模拟 check 执行期间文件被修改
    monkeypatch.setattr(
        stop_quality,
        'run_quality_checks',
        lambda _cid, _cf, _root, _targets: _mutate_and_pass(repo),
    )
    # 让 collect_git_evidence 返回带 fingerprint 的证据，以触发 post-gate 一致性复核
    _real_collect = stop_git_evidence.collect_git_evidence
    _call_count = [0]

    def _fingerprinted_collect(repo_root, rec):
        result = _real_collect(repo_root, rec)
        _call_count[0] += 1
        # 每次调用都根据当前文件内容计算不同 fingerprint
        readme = (repo_root / 'README.md').read_text(encoding='utf-8')
        result['checkoutFingerprint'] = f'fp-{_call_count[0]}-{readme}'
        return result

    monkeypatch.setattr(stop_git_evidence, 'collect_git_evidence', _fingerprinted_collect)
    # stop_entry.py 里也从 git_evidence 子模块导入了 collect_git_evidence
    monkeypatch.setattr(
        'scripts.harness.stop_entry.collect_git_evidence',
        _fingerprinted_collect,
    )
    assert run_stop(
        'codex',
        {
            'cwd': str(repo),
            'session_id': 'session-a',
            'run_id': 'run-a',
            'handoff_on_failure': True,
        },
        adapter_mode='cli',
    ) == 2
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
    from scripts.harness import stop_helpers

    with pytest.raises(GitEvidenceError):
        stop_helpers._hash_untracked_contents(tmp_path, raw_paths)


def test_untracked_content_snapshot_rejects_intermediate_symlink_escape(tmp_path: Path):
    from scripts.harness import stop_helpers

    repo = tmp_path / 'repo'
    outside = tmp_path / 'outside'
    repo.mkdir()
    outside.mkdir()
    (outside / 'secret.txt').write_text('secret\n', encoding='utf-8')
    (repo / 'escape').symlink_to(outside, target_is_directory=True)

    with pytest.raises(GitEvidenceError):
        stop_helpers._hash_untracked_contents(repo, b'escape/secret.txt\0')


def test_file_lock_release_and_dead_owner_reclaim_are_exact(tmp_path: Path):
    path = tmp_path / 'locks' / 'run.lock'
    owner = {'runId': 'run-a', 'sessionId': 'session-a', 'worktreeId': 'checkout-a'}
    lock = FileLock(path, owner)
    try:
        assert lock.acquire()
    finally:
        assert lock.release()
    assert not path.exists()

    path.write_text(json.dumps({
        **owner,
        'pid': 999_999_999,
        'processStartTime': 'dead-process',
        'fencingToken': 'old-token',
    }), encoding='utf-8')
    lock = FileLock(path, owner)
    assert lock.acquire()
    assert lock.reclaimed_owner['runId'] == 'run-a'
    assert lock.release()

    path.write_text(json.dumps({
        **dict(owner, runId='run-b'),
        'pid': 999_999_999,
        'processStartTime': 'dead-process',
        'fencingToken': 'other-token',
    }), encoding='utf-8')
    assert not FileLock(path, owner).acquire()
    assert path.exists()
