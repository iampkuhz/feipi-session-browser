import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.agent_runtime.change import entry
from scripts.agent_runtime.session.contract import resolve_checkout_identity
from scripts.agent_runtime.stop.evidence import GitEvidenceError, collect_git_evidence


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, text=True)


def _evidence_repo(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    repo = tmp_path / 'repo'
    repo.mkdir()
    _run_git(repo, 'init', '-b', 'main')
    _run_git(repo, 'config', 'user.email', 'stop@example.invalid')
    _run_git(repo, 'config', 'user.name', 'Stop Test')
    (repo / 'working.txt').write_text('base\n', encoding='utf-8')
    _run_git(repo, 'add', 'working.txt')
    _run_git(repo, 'commit', '-m', 'baseline')
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    facts = resolve_checkout_identity(repo, checkout_creator='unknown', base_commit=head)
    record = {
        'schemaVersion': 2,
        'runId': 'run-evidence',
        'repoKey': facts['repoKey'],
        'client': 'codex',
        'sessionId': 'session-evidence',
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
        'initialDirtySnapshot': {'dirty': False, 'tracked': [], 'untracked': []},
        'changeAttribution': {'preexistingChangesAttributedToRun': False},
    }
    return repo, record


def test_change_entry_reads_platform_json_once_and_emits_one_compact_object(monkeypatch, capsys):
    payload = {'cwd': '/tmp/repo', 'session_id': 'session-1'}
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(
        entry,
        'run_stop_payload',
        lambda agent, value: (
            0,
            {
                'status': 'PASS',
                'state': 'INTEGRATED',
                'code': 'CHANGE_INTEGRATED',
                'agent': agent,
                'payload': value,
            },
        ),
    )

    assert entry.main(['--agent', 'codex']) == 0
    output = capsys.readouterr().out
    decoded = json.loads(output)
    assert decoded['status'] == 'PASS'
    assert decoded['payload'] == payload
    assert len(output.encode()) <= 4096
    assert output.count('\n') == 1


@pytest.mark.contract_case('HOOK-HARNESS-006')
def test_git_evidence_separates_committed_staged_working_and_untracked(tmp_path, monkeypatch):
    repo, record = _evidence_repo(tmp_path, monkeypatch)
    (repo / 'committed.txt').write_text('committed\n', encoding='utf-8')
    _run_git(repo, 'add', 'committed.txt')
    _run_git(repo, 'commit', '-m', 'run commit')
    (repo / 'staged.txt').write_text('staged\n', encoding='utf-8')
    _run_git(repo, 'add', 'staged.txt')
    (repo / 'working.txt').write_text('changed\n', encoding='utf-8')
    (repo / 'untracked.txt').write_text('untracked\n', encoding='utf-8')

    facts = collect_git_evidence(repo, record)

    assert facts['committedFiles'] == ['committed.txt']
    assert facts['uncommittedFiles'] == ['staged.txt', 'working.txt']
    assert facts['untrackedFiles'] == ['untracked.txt']
    assert facts['changedFiles'] == [
        'committed.txt',
        'staged.txt',
        'working.txt',
        'untracked.txt',
    ]
    assert len(facts['commits']) == 1
    assert facts['checkoutStatus']['clean'] is False
    with pytest.raises(GitEvidenceError):
        collect_git_evidence(repo, dict(record, baseCommit='not-a-commit'))


@pytest.mark.parametrize('agent', ['codex', 'claude', 'qoder'])
def test_stop_without_start_self_heals_through_same_controller(agent, tmp_path, monkeypatch):
    record = {
        'runId': f'run-{agent}',
        'sessionId': f'session-{agent}',
        'worktreeId': f'worktree-{agent}',
    }
    calls = []
    monkeypatch.setattr(entry, 'bootstrap_session', lambda **_kwargs: dict(record))

    def attest_start(_cwd, run_id, **kwargs):
        calls.append((run_id, kwargs['activation_source'], kwargs['capability']))
        return {**record, 'changeBegin': {'status': 'ATTESTED'}}

    class FakeController:
        def __init__(self, cwd, selected):
            assert cwd == tmp_path.resolve()
            assert selected['changeBegin']['status'] == 'ATTESTED'

        def on_stop(self, *, message):
            assert message.startswith('chore(agent): complete')
            return {'status': 'PASS', 'state': 'WORKING', 'code': 'NO_CHANGES'}

    monkeypatch.setattr(entry, 'attest_run_start', attest_start)
    monkeypatch.setattr(entry, 'LifecycleController', FakeController)

    exit_code, result = entry.run_stop_payload(
        agent,
        {'cwd': str(tmp_path), 'session_id': record['sessionId'], 'task_id': 'task-1'},
    )

    assert exit_code == 0
    assert result['code'] == 'NO_CHANGES'
    assert calls == [(record['runId'], f'hook:{agent}:Stop-self-heal', 'START_ENFORCED')]
