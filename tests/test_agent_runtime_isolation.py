import json
from pathlib import Path

from scripts.claude_hooks.paths import (
    agent_log_dir,
    build_paths,
    identity_from_values,
    quality_dir,
)
from scripts.harness.agent_stop_check import (
    _read_active_change_id,
    collect_stop_changed_files,
)
from scripts.quality.changed_files import read_recorded_changed_files_from_paths


def _write_changed_file(repo_root: Path, client: str, session: str, agent: str, file: str) -> Path:
    identity = identity_from_values(client, session, agent)
    path = agent_log_dir(repo_root, identity) / 'changed-files.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'schemaVersion': 1,
        'sessionId': session,
        'agentId': agent,
        'file': file,
    }
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
    return path


def _write_active_change(path: Path, change_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'change_id': change_id}) + '\n', encoding='utf-8')


def test_changed_files_are_isolated_by_client_with_same_session_id(tmp_path):
    claude_path = _write_changed_file(
        tmp_path, 'claude', 'same-session', '', '.claude/agents/qwen-main-default.md'
    )
    qoder_path = _write_changed_file(tmp_path, 'qoder', 'same-session', '', '.qoder/AGENTS.md')

    claude_files = read_recorded_changed_files_from_paths([claude_path], 'same-session')
    qoder_files = read_recorded_changed_files_from_paths([qoder_path], 'same-session')

    assert claude_path == tmp_path / 'tmp/agent_logs/claude/same-session/main/changed-files.jsonl'
    assert qoder_path == tmp_path / 'tmp/agent_logs/qoder/same-session/main/changed-files.jsonl'
    assert claude_files == ['.claude/agents/qwen-main-default.md']
    assert qoder_files == ['.qoder/AGENTS.md']
    assert '.qoder/AGENTS.md' not in claude_files


def test_changed_files_are_isolated_by_session_for_same_client(tmp_path):
    _write_changed_file(tmp_path, 'qoder', 'session-a', '', 'scripts/quality/check_a.py')
    _write_changed_file(tmp_path, 'qoder', 'session-b', '', 'scripts/quality/check_b.py')

    identity = identity_from_values('qoder', 'session-a', '')
    changed, mode = collect_stop_changed_files(identity, 'session-a', repo_root=tmp_path)

    assert mode == 'identity-session'
    assert changed == ['scripts/quality/check_a.py']
    assert 'scripts/quality/check_b.py' not in changed


def test_main_stop_collects_main_and_subagents_within_same_session(tmp_path):
    _write_changed_file(tmp_path, 'claude', 'session-a', '', '.claude/agents/qwen-main-default.md')
    _write_changed_file(tmp_path, 'claude', 'session-a', 'worker-1', 'scripts/quality/check_x.py')
    _write_changed_file(tmp_path, 'claude', 'session-b', 'worker-2', 'AGENTS.md')

    identity = identity_from_values('claude', 'session-a', '')
    changed, mode = collect_stop_changed_files(identity, 'session-a', repo_root=tmp_path)

    assert mode == 'identity-session'
    assert changed == ['.claude/agents/qwen-main-default.md', 'scripts/quality/check_x.py']
    assert 'AGENTS.md' not in changed


def test_subagent_stop_collects_only_own_agent_files(tmp_path):
    _write_changed_file(tmp_path, 'claude', 'session-a', '', '.claude/agents/qwen-main-default.md')
    _write_changed_file(tmp_path, 'claude', 'session-a', 'worker-1', 'scripts/quality/check_x.py')
    _write_changed_file(tmp_path, 'claude', 'session-a', 'worker-2', 'AGENTS.md')

    identity = identity_from_values('claude', 'session-a', 'worker-1')
    changed, mode = collect_stop_changed_files(
        identity, 'session-a', agent_id='worker-1', repo_root=tmp_path
    )

    assert mode == 'identity-agent'
    assert changed == ['scripts/quality/check_x.py']
    assert '.claude/agents/qwen-main-default.md' not in changed
    assert 'AGENTS.md' not in changed


def test_main_stop_does_not_collect_other_session_agents(tmp_path):
    _write_changed_file(tmp_path, 'claude', 'session-a', '', '.claude/agents/qwen-main-default.md')
    _write_changed_file(tmp_path, 'claude', 'session-a', 'worker-1', 'scripts/quality/check_x.py')
    _write_changed_file(tmp_path, 'claude', 'session-b', 'worker-2', 'AGENTS.md')

    identity = identity_from_values('claude', 'session-a', '')
    changed, _mode = collect_stop_changed_files(identity, 'session-a', repo_root=tmp_path)

    assert changed == ['.claude/agents/qwen-main-default.md', 'scripts/quality/check_x.py']
    assert 'AGENTS.md' not in changed


def test_quality_output_dir_isolated_by_client_session_and_agent(tmp_path):
    claude_main = quality_dir(tmp_path, identity_from_values('claude', 'same-session', ''))
    qoder_main = quality_dir(tmp_path, identity_from_values('qoder', 'same-session', ''))
    qoder_other_session = quality_dir(tmp_path, identity_from_values('qoder', 'other-session', ''))
    qoder_agent = quality_dir(tmp_path, identity_from_values('qoder', 'same-session', 'worker-1'))

    assert len({claude_main, qoder_main, qoder_other_session, qoder_agent}) == 4
    assert claude_main == tmp_path / 'tmp/quality/claude/same-session/main'
    assert qoder_main == tmp_path / 'tmp/quality/qoder/same-session/main'
    assert qoder_other_session == tmp_path / 'tmp/quality/qoder/other-session/main'
    assert qoder_agent == tmp_path / 'tmp/quality/qoder/same-session/agents/worker-1'


def test_active_change_candidates_prefer_agent_then_session(tmp_path):
    identity = identity_from_values('qoder', 'session-a', 'worker-1')
    paths = build_paths(tmp_path, identity=identity)

    assert paths.active_change_candidates == [
        tmp_path / 'tmp/agent_logs/qoder/session-a/agents/worker-1/active_change.json',
        tmp_path / 'tmp/agent_logs/qoder/session-a/main/active_change.json',
    ]

    _write_active_change(paths.active_change_candidates[1], 'session-change')
    assert _read_active_change_id(identity, repo_root=tmp_path) == 'session-change'

    _write_active_change(paths.active_change_candidates[0], 'agent-change')
    assert _read_active_change_id(identity, repo_root=tmp_path) == 'agent-change'


def test_legacy_active_change_only_used_without_session_identity(tmp_path):
    legacy = tmp_path / 'tmp/active_change.json'
    _write_active_change(legacy, 'legacy-change')

    session_identity = identity_from_values('qoder', 'session-a', '')
    legacy_identity = identity_from_values('qoder', '', '')

    assert build_paths(tmp_path, identity=session_identity).active_change_candidates == [
        tmp_path / 'tmp/agent_logs/qoder/session-a/main/active_change.json'
    ]
    assert _read_active_change_id(session_identity, repo_root=tmp_path) is None
    assert build_paths(tmp_path, identity=legacy_identity).active_change_candidates == [legacy]
    assert _read_active_change_id(legacy_identity, repo_root=tmp_path) == 'legacy-change'
