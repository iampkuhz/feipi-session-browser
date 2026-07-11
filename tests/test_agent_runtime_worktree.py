import json
import subprocess
from pathlib import Path

from scripts.claude_hooks import main as hook_main
from scripts.claude_hooks.hook_io import HookContext, read_stdin_json
from scripts.claude_hooks.paths import build_paths
from scripts.claude_hooks.policy.bash_policy import is_read_only_command
from scripts.agent_runtime.worktree import (
    assignment_marker_path,
    check_session_worktree,
    expected_worktree_path,
    read_assignment_marker,
)
from scripts.claude_hooks.paths import identity_from_values


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _git_repo(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    _run(['git', 'init'], repo)
    _run(['git', 'config', 'user.email', 'agent-runtime@example.invalid'], repo)
    _run(['git', 'config', 'user.name', 'Agent Runtime Test'], repo)
    (repo / 'README.md').write_text('# synthetic repo\n', encoding='utf-8')
    _run(['git', 'add', 'README.md'], repo)
    _run(['git', 'commit', '-m', 'initial'], repo)
    return repo


def test_expected_worktree_paths_cover_all_three_clients(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.setenv('FEIPI_AGENT_WORKTREE_ROOT', str(tmp_path / 'worktrees'))
    identities = [identity_from_values(client, 'same-session', '') for client in ('claude', 'codex', 'qoder')]
    paths = [expected_worktree_path(repo, identity) for identity in identities]
    assert len(set(paths)) == 3
    assert all(path.parent.parent == tmp_path / 'worktrees' for path in paths)
    assert all(not path.resolve().is_relative_to(repo.resolve()) for path in paths)


def test_different_main_sessions_get_distinct_worktrees(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.setenv('FEIPI_AGENT_WORKTREE_ROOT', str(tmp_path / 'worktrees'))
    first = expected_worktree_path(repo, identity_from_values('codex', 'session-a', ''))
    second = expected_worktree_path(repo, identity_from_values('codex', 'session-b', ''))
    assert first != second
    assert first.parent == second.parent == tmp_path / 'worktrees' / 'codex'


def test_main_session_creation_blocks_shared_checkout_until_retried_from_worktree(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.setenv('FEIPI_AGENT_WORKTREE_ROOT', str(tmp_path / 'worktrees'))
    identity = identity_from_values('claude', 'session-a', '')
    decision = check_session_worktree(repo, identity, create=True)
    assert decision.required is True
    assert decision.allowed is False
    assert decision.assigned is True
    assert decision.created is True
    assert 'WORKTREE_REQUIRED' in decision.reason
    target = Path(decision.expected_root)
    assert target.is_dir()
    assert read_assignment_marker(repo, identity)['worktreePath'] == str(target)
    retry = check_session_worktree(target, identity, create=False)
    assert retry.allowed is True
    assert retry.assigned is True


def test_existing_assignment_blocks_wrong_checkout_but_not_read_only_legacy(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.setenv('FEIPI_AGENT_WORKTREE_ROOT', str(tmp_path / 'worktrees'))
    identity = identity_from_values('qoder', 'session-a', '')
    legacy = check_session_worktree(repo, identity, create=False)
    assert legacy.allowed is True
    assert legacy.assigned is False
    created = check_session_worktree(repo, identity, create=True)
    assert created.allowed is False
    blocked = check_session_worktree(repo, identity, create=False)
    assert blocked.allowed is False
    assert Path(blocked.marker_path).is_file()
    assert blocked.expected_root == created.expected_root


def test_subagent_inherits_main_session_assignment(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.setenv('FEIPI_AGENT_WORKTREE_ROOT', str(tmp_path / 'worktrees'))
    main = identity_from_values('codex', 'session-a', '')
    subagent = identity_from_values('codex', 'session-a', 'worker-1')
    created = check_session_worktree(repo, main, create=True)
    target = Path(created.expected_root)
    subagent_wrong_checkout = check_session_worktree(repo, subagent, create=True)
    assert subagent_wrong_checkout.allowed is False
    assert subagent_wrong_checkout.expected_root == created.expected_root
    assert assignment_marker_path(repo, subagent) == assignment_marker_path(repo, main)
    subagent_retry = check_session_worktree(target, subagent, create=False)
    assert subagent_retry.allowed is True
    assert subagent_retry.expected_root == created.expected_root


def test_missing_session_identity_does_not_allocate_worktree(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.setenv('FEIPI_AGENT_WORKTREE_ROOT', str(tmp_path / 'worktrees'))
    identity = identity_from_values('claude', '', '')
    decision = check_session_worktree(repo, identity, create=True)
    assert decision.required is False
    assert decision.allowed is True
    assert not (tmp_path / 'worktrees').exists()


def test_marker_is_shared_from_linked_worktree(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.setenv('FEIPI_AGENT_WORKTREE_ROOT', str(tmp_path / 'worktrees'))
    identity = identity_from_values('qoder', 'session-b', '')
    decision = check_session_worktree(repo, identity, create=True)
    target = Path(decision.expected_root)
    marker_from_repo = assignment_marker_path(repo, identity)
    marker_from_worktree = assignment_marker_path(target, identity)
    assert marker_from_repo == marker_from_worktree
    data = json.loads(marker_from_worktree.read_text(encoding='utf-8'))
    assert data['client'] == 'qoder'
    assert data['sessionId'] == 'session-b'
    assert data['worktreePath'] == str(target)


def test_hook_context_cwd_falls_back_to_wrapper_env(monkeypatch):
    monkeypatch.setenv('FEIPI_HOOK_CWD', '/tmp/assigned-worktree')
    ctx = read_stdin_json('pre-bash', '{"tool_name":"Bash","tool_input":{"command":"git status"}}')
    assert ctx.cwd == '/tmp/assigned-worktree'


def test_read_only_detection_allows_simple_cd_and_rejects_shell_expansion():
    assert is_read_only_command('cd /tmp && git status --short')
    assert not is_read_only_command("git status $(python3 -c 'print(1)')")


def test_pre_bash_honors_leading_cd_to_assigned_worktree(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.setenv('FEIPI_AGENT_WORKTREE_ROOT', str(tmp_path / 'worktrees'))
    identity = identity_from_values('codex', 'session-cd', '')
    created = check_session_worktree(repo, identity, create=True)
    target = Path(created.expected_root)
    paths = build_paths(repo, identity=identity)
    command = f"cd {target} && python3 -c 'open(\"README.md\",\"w\").write(\"changed\")'"
    ctx = HookContext(
        event_name='pre-bash',
        raw={
            'hook_event_name': 'pre-bash',
            'tool_name': 'Bash',
            'tool_use_id': 'tool-cd',
            'session_id': 'session-cd',
            'agent_client': 'codex',
            'cwd': str(repo),
            'tool_input': {'command': command},
        },
    )

    result = hook_main.handle_pre_bash(paths, ctx)

    assert result.status == 'PASS'
    assert (target / 'tmp' / 'agent_logs' / 'bash-mutation.lock').exists()



def test_shell_hook_exec_root_prefers_linked_worktree(tmp_path):
    repo = _git_repo(tmp_path)
    helper_target = repo / 'scripts' / 'harness'
    helper_target.mkdir(parents=True)
    (helper_target / 'agent_stop_check.py').write_text('# synthetic stop runner\n', encoding='utf-8')
    _run(['git', 'add', 'scripts/harness/agent_stop_check.py'], repo)
    _run(['git', 'commit', '-m', 'add hook runner'], repo)
    worktree = tmp_path / 'linked-worktree'
    _run(['git', 'worktree', 'add', '--detach', str(worktree), 'HEAD'], repo)
    common = Path(__file__).resolve().parents[1] / '.codex' / 'hooks' / 'lib' / 'common.sh'
    script = f'source "{common}"; FEIPI_HOOK_CWD="{worktree}"; hook_exec_root "{repo}"'

    resolved = subprocess.check_output(['bash', '-c', script], text=True).strip()

    assert resolved == str(worktree)
