from pathlib import Path

from scripts.agent_runtime.identity import (
    agent_log_dir,
    identity_from_values,
    identity_requires_fail_closed,
    quality_dir,
    session_main_log_dir,
    session_root_dir,
)


def test_identity_sanitizes_client_session_agent_segments():
    identity = identity_from_values('claude/client', 'session/../alpha', 'agent one')

    assert '/' not in identity.client
    assert '/' not in identity.session_id
    assert '/' not in identity.agent_id
    assert identity.client.startswith('claude-client')
    assert identity.session_id.startswith('session-..-alpha')
    assert identity.agent_id.startswith('agent-one')
    assert identity.raw_session_id == 'session/../alpha'
    assert identity.raw_agent_id == 'agent one'


def test_quality_dir_isolated_by_client(tmp_path: Path):
    claude = identity_from_values('claude', 'same-session', '')
    codex = identity_from_values('codex', 'same-session', '')
    qoder = identity_from_values('qoder', 'same-session', '')

    dirs = {quality_dir(tmp_path, claude), quality_dir(tmp_path, codex), quality_dir(tmp_path, qoder)}

    assert len(dirs) == 3
    assert quality_dir(tmp_path, claude) == tmp_path / 'tmp' / 'quality' / 'claude' / 'same-session' / 'main'
    assert quality_dir(tmp_path, qoder) == tmp_path / 'tmp' / 'quality' / 'qoder' / 'same-session' / 'main'


def test_log_dir_isolated_by_session(tmp_path: Path):
    first = identity_from_values('claude', 'session-a', '')
    second = identity_from_values('claude', 'session-b', '')

    assert session_root_dir(tmp_path, first) != session_root_dir(tmp_path, second)
    assert session_main_log_dir(tmp_path, first) == tmp_path / 'tmp' / 'agent_logs' / 'claude' / 'session-a' / 'main'
    assert agent_log_dir(tmp_path, second) == tmp_path / 'tmp' / 'agent_logs' / 'claude' / 'session-b' / 'main'


def test_agent_log_dir_isolated_by_agent_id(tmp_path: Path):
    first = identity_from_values('codex', 'session-a', 'agent-a')
    second = identity_from_values('codex', 'session-a', 'agent-b')

    assert agent_log_dir(tmp_path, first) != agent_log_dir(tmp_path, second)
    assert agent_log_dir(tmp_path, first) == tmp_path / 'tmp' / 'agent_logs' / 'codex' / 'session-a' / 'agents' / 'agent-a'
    assert quality_dir(tmp_path, second) == tmp_path / 'tmp' / 'quality' / 'codex' / 'session-a' / 'agents' / 'agent-b'


def test_main_and_subagent_dirs_are_distinct(tmp_path: Path):
    main = identity_from_values('qoder', 'session-a', '')
    subagent = identity_from_values('qoder', 'session-a', 'worker-1')

    assert agent_log_dir(tmp_path, main) != agent_log_dir(tmp_path, subagent)
    assert quality_dir(tmp_path, main) != quality_dir(tmp_path, subagent)
    assert agent_log_dir(tmp_path, main) == tmp_path / 'tmp' / 'agent_logs' / 'qoder' / 'session-a' / 'main'
    assert agent_log_dir(tmp_path, subagent) == tmp_path / 'tmp' / 'agent_logs' / 'qoder' / 'session-a' / 'agents' / 'worker-1'


def test_missing_session_id_fails_closed_for_protected_write():
    identity = identity_from_values('claude', '', '')

    assert identity_requires_fail_closed(
        identity,
        operation='Write',
        protected=True,
        mutating=False,
    ) is True


def test_explicit_empty_session_does_not_fall_back_to_environment(monkeypatch):
    monkeypatch.setenv('FEIPI_SESSION_ID', 'ambient-session')
    monkeypatch.setenv('FEIPI_AGENT_ID', 'ambient-agent')

    identity = identity_from_values('qoder', '', '')

    assert identity.raw_session_id == ''
    assert identity.raw_agent_id == ''
    assert identity.has_session is False
    assert identity.is_agent is False


def test_missing_session_id_fails_closed_for_mutating_bash():
    identity = identity_from_values('codex', '', '')

    assert identity_requires_fail_closed(
        identity,
        operation='Bash',
        protected=False,
        mutating=True,
    ) is True


def test_missing_session_id_allows_read_only_operation():
    identity = identity_from_values('qoder', '', '')

    assert identity_requires_fail_closed(
        identity,
        operation='Read',
        protected=False,
        mutating=False,
    ) is False


def test_present_session_does_not_fail_closed_for_protected_or_mutating_operations():
    identity = identity_from_values('qoder', 'session-a', '')

    assert identity_requires_fail_closed(
        identity,
        operation='Write',
        protected=True,
        mutating=True,
    ) is False
