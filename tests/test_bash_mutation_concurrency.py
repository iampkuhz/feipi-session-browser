import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.claude_hooks import evidence, main as hook_main
from scripts.claude_hooks.hook_io import HookContext
from scripts.claude_hooks.paths import build_paths, identity_from_values
from scripts.harness import agent_stop_check as stop_check


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _run(['git', 'init'], tmp_path)
    _run(['git', 'config', 'user.email', 'test@example.com'], tmp_path)
    _run(['git', 'config', 'user.name', 'Test User'], tmp_path)
    (tmp_path / '.gitignore').write_text('tmp/\n', encoding='utf-8')
    (tmp_path / 'README.md').write_text('base\n', encoding='utf-8')
    manifest = tmp_path / 'harness' / 'agent-runtime.manifest.yaml'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        'protected_roots:\n'
        '  - .claude/\n'
        '  - .codex/\n'
        '  - .qoder/\n'
        '  - .agents/\n'
        '  - skills/\n'
        '  - harness/\n'
        '  - scripts/\n'
        '  - openspec/\n'
        '  - src/session_browser/\n'
        '  - tests/\n'
        '  - AGENTS.md\n'
        '  - CLAUDE.md\n',
        encoding='utf-8',
    )
    _run(['git', 'add', '.gitignore', 'README.md', 'harness/agent-runtime.manifest.yaml'], tmp_path)
    _run(['git', 'commit', '-m', 'base'], tmp_path)
    return tmp_path


def _ctx(
    event: str,
    *,
    session: str = 'session-a',
    agent: str = 'agent-a',
    tool_use: str = 'tool-a',
    command: str = 'printf x >> README.md',
) -> HookContext:
    return HookContext(
        event_name=event,
        raw={
            'hook_event_name': event,
            'tool_name': 'Bash',
            'tool_use_id': tool_use,
            'session_id': session,
            'agent_id': agent,
            'agent_client': 'claude',
            'tool_input': {'command': command},
        },
    )


def _paths(repo: Path, *, session: str = 'session-a', agent: str = 'agent-a'):
    return build_paths(repo, identity=identity_from_values('claude', session, agent))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def test_second_mutating_bash_blocks_when_lock_busy(tmp_path):
    repo = tmp_path
    _run(['git', 'init'], repo)
    paths_a = _paths(repo, session='s1', agent='agent-a')
    paths_b = _paths(repo, session='s2', agent='agent-b')

    first = hook_main.handle_pre_bash(paths_a, _ctx('pre-bash', session='s1', agent='agent-a'))
    second = hook_main.handle_pre_bash(paths_b, _ctx('pre-bash', session='s2', agent='agent-b'))

    assert first.status == 'PASS'
    assert second.status == 'BLOCK'
    assert second.exit_code != 0
    events = _jsonl(paths_b.hook_events)
    busy = events[-1]['bashMutationLock']
    assert events[-1]['status'] == 'BLOCK'
    assert busy['state'] == 'busy'
    assert busy['owner']
    assert busy['sessionId'] == 's1'
    assert busy['agentId'] == 'agent-a'
    assert isinstance(busy['age_seconds'], (int, float))
    assert not paths_b.changed_files.exists()


def test_read_only_bash_does_not_acquire_mutation_lock(tmp_path):
    repo = tmp_path
    _run(['git', 'init'], repo)
    paths = _paths(repo)

    result = hook_main.handle_pre_bash(
        paths, _ctx('pre-bash', command='git status --short && rg -n base README.md')
    )

    assert result.status == 'PASS'
    assert not (repo / 'tmp' / 'agent_logs' / 'bash-mutation.lock').exists()
    events = _jsonl(paths.hook_events)
    assert events[-1]['bashMutationTracking'] is False
    assert events[-1]['bashSnapshot'] is False


def test_read_only_post_bash_does_not_create_snapshot_gap(tmp_path):
    repo = tmp_path
    _run(['git', 'init'], repo)
    paths = _paths(repo)
    ctx = _ctx(
        'pre-bash',
        tool_use='read-only',
        command='git status --short && rg -n base README.md',
    )

    assert hook_main.handle_pre_bash(paths, ctx).status == 'PASS'
    records = evidence.record_post_bash(
        paths,
        _ctx('post-bash', tool_use='read-only', command=ctx.command),
    )

    assert records == []
    events = _jsonl(paths.hook_events)
    assert events[-1]['status'] == 'OBSERVED'
    assert not any(event['status'] == 'BASH_SNAPSHOT_MISSING' for event in events)


def test_blocked_pre_bash_post_does_not_create_snapshot_gap(tmp_path):
    repo = tmp_path
    _run(['git', 'init'], repo)
    paths_a = _paths(repo, session='s1', agent='agent-a')
    paths_b = _paths(repo, session='s2', agent='agent-b')

    assert hook_main.handle_pre_bash(
        paths_a,
        _ctx('pre-bash', session='s1', agent='agent-a', tool_use='owner'),
    ).status == 'PASS'
    assert hook_main.handle_pre_bash(
        paths_b,
        _ctx('pre-bash', session='s2', agent='agent-b', tool_use='blocked'),
    ).status == 'BLOCK'
    records = evidence.record_post_bash(
        paths_b,
        _ctx('post-bash', session='s2', agent='agent-b', tool_use='blocked'),
    )

    assert records == []
    events = _jsonl(paths_b.hook_events)
    assert events[-1]['status'] == 'OBSERVED'
    assert not any(event['status'] == 'BASH_SNAPSHOT_MISSING' for event in events)


def test_post_bash_releases_lock_for_owner(repo: Path):
    paths = _paths(repo)
    pre_ctx = _ctx('pre-bash', tool_use='owned')
    post_ctx = _ctx('post-bash', tool_use='owned')

    assert hook_main.handle_pre_bash(paths, pre_ctx).status == 'PASS'
    assert (repo / 'tmp' / 'agent_logs' / 'bash-mutation.lock').exists()
    (repo / 'README.md').write_text('mutated\n', encoding='utf-8')
    records = evidence.record_post_bash(paths, post_ctx)

    assert [record['file'] for record in records] == ['README.md']
    assert not (repo / 'tmp' / 'agent_logs' / 'bash-mutation.lock').exists()


def test_non_owner_post_bash_does_not_release_lock(repo: Path):
    owner_paths = _paths(repo, session='owner-session', agent='owner-agent')
    other_paths = _paths(repo, session='other-session', agent='other-agent')

    assert hook_main.handle_pre_bash(
        owner_paths, _ctx('pre-bash', session='owner-session', agent='owner-agent', tool_use='owner')
    ).status == 'PASS'
    evidence.record_post_bash(
        other_paths, _ctx('post-bash', session='other-session', agent='other-agent', tool_use='other')
    )

    lock_info = evidence.read_bash_mutation_lock_info(owner_paths)
    assert lock_info is not None
    assert lock_info['sessionId'] == 'owner-session'
    assert lock_info['agentId'] == 'owner-agent'


def test_stale_bash_mutation_lock_is_removed(tmp_path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path
    _run(['git', 'init'], repo)
    stale_paths = _paths(repo, session='stale-session', agent='stale-agent')
    fresh_paths = _paths(repo, session='fresh-session', agent='fresh-agent')
    monkeypatch.setattr(evidence, 'BASH_MUTATION_LOCK_STALE_SECONDS', 1)

    assert evidence.acquire_bash_mutation_lock(stale_paths, _ctx('pre-bash', session='stale-session', agent='stale-agent'))
    lock_path = repo / 'tmp' / 'agent_logs' / 'bash-mutation.lock'
    old = time.time() - 10
    os.utime(lock_path, (old, old))

    assert evidence.acquire_bash_mutation_lock(fresh_paths, _ctx('pre-bash', session='fresh-session', agent='fresh-agent'))
    lock_info = evidence.read_bash_mutation_lock_info(fresh_paths)
    assert lock_info is not None
    assert lock_info['sessionId'] == 'fresh-session'
    assert lock_info['agentId'] == 'fresh-agent'


def test_dead_owner_bash_mutation_lock_is_removed(tmp_path):
    repo = tmp_path
    _run(['git', 'init'], repo)
    paths = _paths(repo, session='fresh-session', agent='fresh-agent')
    lock_path = repo / 'tmp' / 'agent_logs' / 'bash-mutation.lock'
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps({'schemaVersion': 1, 'owner': 'dead-owner', 'pid': 999999}),
        encoding='utf-8',
    )

    assert evidence.acquire_bash_mutation_lock(
        paths,
        _ctx('pre-bash', session='fresh-session', agent='fresh-agent'),
    )
    lock_info = evidence.read_bash_mutation_lock_info(paths)
    assert lock_info is not None
    assert lock_info['sessionId'] == 'fresh-session'


def test_missing_snapshot_records_attribution_gap(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    paths = _paths(repo, session='gap-session', agent='gap-agent')
    (repo / 'README.md').write_text('dirty without snapshot\n', encoding='utf-8')

    records = evidence.record_post_bash(
        paths, _ctx('post-bash', session='gap-session', agent='gap-agent', tool_use='missing-snapshot')
    )
    assert records == []
    events = _jsonl(paths.hook_events)
    assert events[-1]['status'] == 'BASH_SNAPSHOT_MISSING'

    monkeypatch.setattr(stop_check, 'REPO_ROOT', repo)
    monkeypatch.setattr(stop_check, 'AGENT_LOG_BASE', repo / 'tmp' / 'agent_logs')
    monkeypatch.setattr(stop_check, 'STOP_LOCK', repo / 'tmp' / 'agent_logs' / 'stop-check' / 'legacy.lock')
    monkeypatch.setenv('ACTIVE_CHANGE_ID', 'harden-agent-runtime-full-v3')
    monkeypatch.setattr(sys, 'argv', ['agent_stop_check.py', '--agent', 'claude', '--agent-id', 'gap-agent'])
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({'session_id': 'gap-session'})))

    code = stop_check.main()
    captured = capsys.readouterr()
    summary_path = repo / 'tmp' / 'agent_logs' / 'claude' / 'gap-session' / 'agents' / 'gap-agent' / 'stop-check-summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))

    assert code != 0
    assert summary['status'] == 'BLOCKED'
    assert any('BASH_SNAPSHOT_MISSING' in item for item in summary['blockingFailures'])
    assert 'BASH_SNAPSHOT_MISSING' in captured.err
