from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.harness.primary_session import resolve_runtime_root
from scripts.harness.stop_entry import FileLock, run_stop
from scripts.quality.check_agent_runtime_report import validate_runtime_report


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


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
    _run(['git', 'add', 'harness/agent-runtime.manifest.yaml'], repo)
    _run(['git', 'commit', '-m', 'manifest'], repo)
    return repo


def _record(repo: Path, run_id: str, session: str, change: str = 'support-parallel-primary-sessions') -> dict:
    return {
        'schemaVersion': 1,
        'runId': run_id,
        'client': 'codex',
        'taskId': f'task-{run_id}',
        'sessionId': session,
        'worktreeId': f'wt-{run_id}',
        'worktreeRoot': str(repo.resolve()),
        'branch': 'main',
        'targetBranch': 'main',
        'primaryRepoRoot': str(repo.resolve()),
        'baseCommit': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
        'headCommit': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
        'changeId': change,
        'mode': 'writable',
        'status': 'RUNNING',
        'allowedPaths': ['scripts', 'openspec'],
        'forbiddenPaths': ['.env', '.mcp.json'],
        'resourceAllocations': {'ports': [], 'paths': []},
        'writerLease': {'leaseId': f'lease-{run_id}', 'holderRunId': run_id},
        'hookActivation': {'confirmed': True, 'client': 'codex'},
        'processes': [],
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:01Z',
    }


def _save(repo: Path, *records: dict) -> None:
    root = resolve_runtime_root(repo) / 'runs'
    root.mkdir(parents=True, exist_ok=True)
    for record in records:
        (root / f"{record['runId']}.json").write_text(json.dumps(record), encoding='utf-8')
    (root / 'index.json').write_text(json.dumps({'schemaVersion': 1, 'runs': [r['runId'] for r in records]}), encoding='utf-8')


def test_two_run_stop_summaries_do_not_overwrite(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    _save(repo, _record(repo, 'run-a', 'session-a'), _record(repo, 'run-b', 'session-b'))

    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a'}) == 0
    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'session-b', 'run_id': 'run-b'}) == 0

    first = repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json'
    second = repo / 'tmp/agent_logs/codex/session-b/runs/run-b/main/stop-check-summary.json'
    assert first.exists() and second.exists()
    assert json.loads(first.read_text())['runId'] == 'run-a'
    assert json.loads(second.read_text())['runId'] == 'run-b'


def test_runtime_report_requires_explicit_run_context_and_changed_files_match(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    _save(repo, _record(repo, 'run-a', 'session-a'))
    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a'}) == 0
    report = repo / 'tmp/quality/codex/session-a/runs/run-a/main/support-parallel-primary-sessions/runtime-report.json'

    ok = validate_runtime_report(
        run_id='run-a',
        client='codex',
        session_id='session-a',
        change_id='support-parallel-primary-sessions',
        worktree_root=repo,
        changed_files=[],
        report_path=report,
    )
    assert ok == []
    mismatch = validate_runtime_report(
        run_id='run-a',
        client='codex',
        session_id='session-a',
        change_id='support-parallel-primary-sessions',
        worktree_root=repo,
        changed_files=['scripts/other.py'],
        report_path=report,
    )
    assert any('changed_files' in item for item in mismatch)


def test_legacy_session_stop_collects_changed_files_without_run_context(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)

    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'legacy-session'}) == 0

    summary = repo / 'tmp/agent_logs/codex/legacy-session/main/stop-check-summary.json'
    assert summary.exists()
    data = json.loads(summary.read_text(encoding='utf-8'))
    assert data['status'] == 'PASS'
    assert data['evidenceMode'] == 'unbound-session-fail-closed'
    assert data['changedFiles'] == []


def test_stop_repo_root_prefers_current_exec_root_over_original_hook_cwd(tmp_path: Path, monkeypatch):
    original_root = tmp_path / 'original'
    assigned_root = tmp_path / 'assigned'
    original_root.mkdir()
    assigned_root.mkdir()
    original = _repo(original_root, monkeypatch)
    assigned = _repo(assigned_root, monkeypatch)

    monkeypatch.chdir(assigned)
    monkeypatch.setenv('FEIPI_HOOK_CWD', str(original))
    monkeypatch.setenv('FEIPI_HOOK_EXEC_ROOT', str(assigned))

    from scripts.harness import stop_entry

    assert stop_entry._repo_root({}) == assigned.resolve()
    assert stop_entry._repo_root({'cwd': str(original)}) == assigned.resolve()


def test_changed_file_dedupe_preserves_hidden_path_prefixes():
    from scripts.harness.stop_entry import _dedupe

    assert _dedupe(['./.codex/hooks.json', '.qoder/settings.json', './.gitignore']) == [
        '.codex/hooks.json',
        '.qoder/settings.json',
        '.gitignore',
    ]


def test_stop_hook_active_does_not_block_by_itself(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    _save(repo, _record(repo, 'run-a', 'session-a'))

    assert run_stop('codex', {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'run-a', 'stop_hook_active': True}) == 0

    summary = json.loads((repo / 'tmp/agent_logs/codex/session-a/runs/run-a/main/stop-check-summary.json').read_text())
    assert summary['status'] == 'PASS'
    assert any('stop_hook_active reentry observed' in item for item in summary['warnings'])


def test_repeated_same_failure_stops_at_continuation_limit(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    payload = {'cwd': str(repo), 'session_id': 'session-a', 'run_id': 'missing-run', 'stop_hook_active': True}

    assert run_stop('codex', payload) == 2
    assert run_stop('codex', payload) == 2
    assert run_stop('codex', payload) == 2

    summary = json.loads((repo / 'tmp/agent_logs/codex/session-a/runs/missing-run/main/stop-check-summary.json').read_text())
    assert summary['continuationCount'] > 2
    assert any('continuation limit' in item for item in summary['blockingFailures'])
    assert any('run record not found' in item for item in summary['blockingFailures'])


def test_file_lock_releases_after_exception_style_finally(tmp_path: Path):
    path = tmp_path / 'locks' / 'gradle-daemon.lock'
    lock = FileLock(path, {'resource': 'gradle-daemon', 'runId': 'run-a'})
    try:
        assert lock.acquire()
    finally:
        lock.release()
    assert not path.exists()
