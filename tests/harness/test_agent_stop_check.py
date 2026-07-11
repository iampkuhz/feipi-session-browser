import json
import sys
from types import SimpleNamespace

from scripts.harness import agent_stop_check
from scripts.harness.agent_stop_check import parse_git_status_paths, required_targets
from scripts.quality import changed_files
from scripts.claude_hooks import paths as runtime_paths


def test_parse_git_status_paths_includes_deleted_contract_file():
    output = ' D docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
    assert parse_git_status_paths(output) == [
        'docs/acceptance-contracts/features/DATA_PRESENTERS.md'
    ]


def test_deleted_contract_file_requires_acceptance_contract_gate():
    output = ' D docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
    paths = parse_git_status_paths(output)
    assert required_targets(paths) == ['acceptance-contracts']


def test_parse_git_status_paths_includes_renames():
    output = 'R  docs/old.md -> docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
    assert parse_git_status_paths(output) == [
        'docs/old.md',
        'docs/acceptance-contracts/features/DATA_PRESENTERS.md',
    ]


# 01. Windows 路径规范化测试
def test_windows_path_normalization_java():
    """Windows 反斜杠路径必须正确规范化为 java-src target。"""
    from scripts.claude_hooks.classify import classify_file

    c = classify_file('java\\core-domain\\src\\main\\java\\com\\feipi\\Foo.java')
    assert c.quality_target == 'java-src'
    assert c.file == 'java/core-domain/src/main/java/com/feipi/Foo.java'


def test_windows_path_normalization_build():
    """Windows 路径下的 Gradle 文件必须规范化为 java-build target。"""
    from scripts.claude_hooks.classify import classify_file

    c = classify_file('.\\build.gradle.kts')
    assert c.quality_target == 'java-build'


# 02. 多 target Stop 阻断测试
def test_multiple_targets_java_and_hook():
    """Java + hook 文件同时变更时触发两个 target。"""
    targets = required_targets(
        [
            'java/core-domain/src/main/java/com/feipi/Foo.java',
            '.claude/hooks/stop.sh',
        ]
    )
    assert 'java-src' in targets
    assert 'hook-runtime' in targets


def test_stop_blocks_on_java_change():
    """Java 文件变更必须触发 java-src target（不可被 Stop 绕过）。"""
    targets = required_targets(
        [
            'java/core-domain/src/main/java/com/feipi/Foo.java',
        ]
    )
    assert 'java-src' in targets
    assert len(targets) >= 1


def test_shared_changed_files_excludes_preexisting_git_dirty(monkeypatch, tmp_path):
    """Pre-existing dirty files must NOT enter gate routing; only session-scoped sources count."""

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=(
                ' M scripts/quality/run_required_quality_gates.py\n'
                ' D docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
                '?? .codex/hooks.json\n'
            ),
        )

    monkeypatch.setattr(changed_files.subprocess, 'run', fake_run)

    paths = changed_files.collect_changed_files(
        None,
        repo_root=tmp_path,
        changed_files_path=tmp_path / 'missing.jsonl',
    )

    assert paths == []


def test_shared_changed_files_includes_committed_changes_since_base(monkeypatch, tmp_path):
    """Commits made since the base commit must enter gate routing."""
    base_file = tmp_path / 'base-commit.txt'
    base_file.write_text('base123\n', encoding='utf-8')

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=(
                'scripts/quality/run_required_quality_gates.py\n'
                'docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
            ),
        )

    monkeypatch.setattr(changed_files.subprocess, 'run', fake_run)

    paths = changed_files.collect_changed_files(
        None,
        repo_root=tmp_path,
        changed_files_path=tmp_path / 'missing.jsonl',
        base_commit_file=base_file,
    )

    assert paths == [
        'scripts/quality/run_required_quality_gates.py',
        'docs/acceptance-contracts/features/DATA_PRESENTERS.md',
    ]
    targets = required_targets(paths)
    assert 'hook-runtime' in targets
    assert 'acceptance-contracts' in targets


def test_shared_changed_files_includes_worktree_deletions_since_base(monkeypatch, tmp_path):
    """Bash 删除等未提交变更在有 base commit 时必须进入 Stop target 路由。"""
    base_file = tmp_path / 'base-commit.txt'
    base_file.write_text('base123\n', encoding='utf-8')
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        commands.append(cmd)
        if cmd[:3] == ['git', 'diff', '--name-only']:
            return SimpleNamespace(
                returncode=0,
                stdout='docs/acceptance-contracts/features/DATA_PRESENTERS.md\n',
            )
        if cmd[:3] == ['git', 'ls-files', '--others']:
            return SimpleNamespace(returncode=0, stdout='')
        return SimpleNamespace(returncode=0, stdout='')

    monkeypatch.setattr(changed_files.subprocess, 'run', fake_run)

    paths = changed_files.collect_changed_files(
        None,
        repo_root=tmp_path,
        changed_files_path=tmp_path / 'missing.jsonl',
        base_commit_file=base_file,
    )

    assert paths == ['docs/acceptance-contracts/features/DATA_PRESENTERS.md']
    assert required_targets(paths) == ['acceptance-contracts']
    assert ['git', 'diff', '--name-only', '--diff-filter=ACMRD', 'base123'] in commands


def test_stop_changed_files_are_scoped_to_explicit_session(monkeypatch, tmp_path):
    """只读 session 不得被其他 session 的 changed-file evidence 牵连。"""
    monkeypatch.setattr(agent_stop_check, 'REPO_ROOT', tmp_path)
    changed_file = (
        tmp_path
        / 'tmp'
        / 'agent_logs'
        / 'claude'
        / 'writer-session'
        / 'main'
        / 'changed-files.jsonl'
    )
    changed_file.parent.mkdir(parents=True)
    changed_file.write_text(
        json.dumps(
            {
                'sessionId': 'writer-session',
                'agentId': '',
                'file': 'scripts/quality/run_required_quality_gates.py',
            }
        )
        + '\n',
        encoding='utf-8',
    )
    identity = runtime_paths.identity_from_values(
        agent_client='claude',
        session_id='reader-session',
    )

    paths, mode = agent_stop_check.collect_stop_changed_files(
        identity,
        'fallback-session',
    )

    assert mode == 'identity-session'
    assert paths == []


def test_stop_changed_files_filter_agent_id(monkeypatch, tmp_path):
    """SubagentStop 有 agent_id 时只归因当前 agent 的写入。"""
    monkeypatch.setattr(agent_stop_check, 'REPO_ROOT', tmp_path)
    root = tmp_path / 'tmp' / 'agent_logs' / 'claude' / 'shared-session' / 'agents'
    changed_file_a = root / 'writer-a' / 'changed-files.jsonl'
    changed_file_b = root / 'writer-b' / 'changed-files.jsonl'
    changed_file_a.parent.mkdir(parents=True)
    changed_file_b.parent.mkdir(parents=True)
    records = [
        {'sessionId': 'shared-session', 'agentId': 'writer-a', 'file': 'java/Foo.java'},
        {'sessionId': 'shared-session', 'agentId': 'writer-b', 'file': 'java/Bar.java'},
    ]
    changed_file_a.write_text(json.dumps(records[0]) + '\n', encoding='utf-8')
    changed_file_b.write_text(json.dumps(records[1]) + '\n', encoding='utf-8')
    identity = runtime_paths.identity_from_values(
        agent_client='claude',
        session_id='shared-session',
        agent_id='writer-b',
    )

    paths, mode = agent_stop_check.collect_stop_changed_files(
        identity,
        'fallback-session',
        agent_id='writer-b',
    )

    assert mode == 'identity-agent'
    assert paths == ['java/Bar.java']


def test_stop_session_without_agent_id_aggregates_subagents(monkeypatch, tmp_path):
    """Session Stop 不带 agent_id 时汇总 main 和所有 subagent evidence。"""
    monkeypatch.setattr(agent_stop_check, 'REPO_ROOT', tmp_path)
    base = tmp_path / 'tmp' / 'agent_logs' / 'claude' / 'shared-session'
    main_file = base / 'main' / 'changed-files.jsonl'
    agent_file = base / 'agents' / 'writer-a' / 'changed-files.jsonl'
    main_file.parent.mkdir(parents=True)
    agent_file.parent.mkdir(parents=True)
    main_file.write_text(
        json.dumps({'sessionId': 'shared-session', 'agentId': '', 'file': 'README.md'}) + '\n',
        encoding='utf-8',
    )
    agent_file.write_text(
        json.dumps({'sessionId': 'shared-session', 'agentId': 'writer-a', 'file': 'java/Foo.java'})
        + '\n',
        encoding='utf-8',
    )
    identity = runtime_paths.identity_from_values(
        agent_client='claude',
        session_id='shared-session',
    )

    paths, mode = agent_stop_check.collect_stop_changed_files(identity, 'fallback-session')

    assert mode == 'identity-session'
    assert paths == ['README.md', 'java/Foo.java']


def test_stop_attribution_gap_ignores_legacy_unmarked_missing_snapshot(tmp_path):
    """修复前无法补齐的 legacy missing-snapshot 记录不得永久阻断 Stop。"""
    identity = runtime_paths.identity_from_values(
        agent_client='claude',
        session_id='shared-session',
    )
    events_path = runtime_paths.agent_log_dir(tmp_path, identity) / 'hook-events.jsonl'
    events_path.parent.mkdir(parents=True)
    events = [
        {
            'sessionId': 'shared-session',
            'agentId': '',
            'event': 'pre-bash',
            'toolUseId': 'instrumented',
            'status': 'LAZY_BIND',
        },
        {
            'sessionId': 'shared-session',
            'agentId': '',
            'event': 'post-bash',
            'toolUseId': 'instrumented',
            'status': 'BASH_SNAPSHOT_MISSING',
        },
        {
            'sessionId': 'shared-session',
            'agentId': '',
            'event': 'pre-bash',
            'toolUseId': 'legacy-pass',
            'status': 'PASS',
        },
        {
            'sessionId': 'shared-session',
            'agentId': '',
            'event': 'post-bash',
            'toolUseId': 'legacy-pass',
            'status': 'BASH_SNAPSHOT_MISSING',
        },
        {
            'sessionId': 'shared-session',
            'agentId': '',
            'event': 'post-bash',
            'toolUseId': 'legacy-no-pre',
            'status': 'BASH_SNAPSHOT_MISSING',
        },
    ]
    events_path.write_text(
        ''.join(json.dumps(event) + '\n' for event in events),
        encoding='utf-8',
    )

    failures = agent_stop_check.identity_attribution_gap_failures(
        identity,
        repo_root=tmp_path,
    )

    assert failures == []


def test_stop_attribution_gap_blocks_future_missing_snapshot(tmp_path):
    """未来真实 missing snapshot 必须仍然 fail-closed。"""
    identity = runtime_paths.identity_from_values(
        agent_client='claude',
        session_id='shared-session',
    )
    events_path = runtime_paths.agent_log_dir(tmp_path, identity) / 'hook-events.jsonl'
    events_path.parent.mkdir(parents=True)
    events = [
        {
            'sessionId': 'shared-session',
            'agentId': '',
            'event': 'post-bash',
            'toolUseId': 'future-post-marker',
            'status': 'BASH_SNAPSHOT_MISSING',
            'bashSnapshotRequired': True,
            'bashMutationTracking': True,
        },
        {
            'sessionId': 'shared-session',
            'agentId': '',
            'event': 'pre-bash',
            'toolUseId': 'future-pre-marker',
            'status': 'PASS',
            'bashMutationTracking': True,
        },
        {
            'sessionId': 'shared-session',
            'agentId': '',
            'event': 'post-bash',
            'toolUseId': 'future-pre-marker',
            'status': 'BASH_SNAPSHOT_MISSING',
        },
    ]
    events_path.write_text(
        ''.join(json.dumps(event) + '\n' for event in events),
        encoding='utf-8',
    )

    failures = agent_stop_check.identity_attribution_gap_failures(
        identity,
        repo_root=tmp_path,
    )

    assert failures == [
        'BASH_SNAPSHOT_MISSING attribution gap for toolUseId=future-post-marker',
        'BASH_SNAPSHOT_MISSING attribution gap for toolUseId=future-pre-marker',
    ]


def test_resolve_change_id_is_identity_scoped(monkeypatch, tmp_path):
    """同一 worktree 中不同 session 的 active_change 不得互相覆盖。"""
    monkeypatch.delenv('ACTIVE_CHANGE_ID', raising=False)
    monkeypatch.setattr(agent_stop_check, 'REPO_ROOT', tmp_path)
    first = runtime_paths.identity_from_values(agent_client='claude', session_id='session-a')
    second = runtime_paths.identity_from_values(agent_client='claude', session_id='session-b')
    first_active = runtime_paths.agent_log_dir(tmp_path, first) / 'active_change.json'
    second_active = runtime_paths.agent_log_dir(tmp_path, second) / 'active_change.json'
    first_active.parent.mkdir(parents=True)
    second_active.parent.mkdir(parents=True)
    first_active.write_text(json.dumps({'change_id': 'change-a'}), encoding='utf-8')
    second_active.write_text(json.dumps({'change_id': 'change-b'}), encoding='utf-8')
    (tmp_path / 'tmp').mkdir(exist_ok=True)
    (tmp_path / 'tmp' / 'active_change.json').write_text(
        json.dumps({'change_id': 'legacy-change'}),
        encoding='utf-8',
    )

    assert agent_stop_check.resolve_change_id(first) == 'change-a'
    assert agent_stop_check.resolve_change_id(second) == 'change-b'


def test_stop_quality_artifact_path_is_identity_scoped(monkeypatch, tmp_path):
    """Stop 触发的 quality artifact 必须写入当前 agent 的隔离目录。"""
    monkeypatch.setattr(agent_stop_check, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(
        agent_stop_check,
        '_read_json_stdin',
        lambda: {'session_id': 'session-a', 'agent_id': 'agent-1'},
    )
    monkeypatch.setattr(
        agent_stop_check,
        'collect_stop_changed_files',
        lambda identity, fallback_session_id, agent_id=None: (
            ['tests/harness/test_agent_stop_check.py'],
            'identity-agent',
        ),
    )
    monkeypatch.setattr(agent_stop_check, 'required_targets', lambda files: ['harness'])
    monkeypatch.setattr(agent_stop_check, 'changed_files_require_openspec', lambda files: False)
    monkeypatch.setattr(agent_stop_check, 'resolve_change_id', lambda identity=None: 'change-a')
    captured: list[tuple[str, list[str], dict[str, str] | None]] = []

    def fake_run_step(
        name: str,
        cmd: list[str],
        env_overrides: dict[str, str] | None = None,
    ) -> bool:
        captured.append((name, cmd, env_overrides))
        return True

    monkeypatch.setattr(agent_stop_check, 'run_step', fake_run_step)
    monkeypatch.setattr(sys, 'argv', ['agent_stop_check.py', '--agent', 'claude'])

    assert agent_stop_check.main() == 0

    quality_call = next(item for item in captured if item[0] == 'required-quality-gates')
    cmd = quality_call[1]
    out_index = cmd.index('--out') + 1
    assert cmd[out_index] == 'tmp/quality/claude/session-a/agents/agent-1'
    assert quality_call[2] == {
        'FEIPI_AGENT_CLIENT': 'claude',
        'FEIPI_SESSION_ID': 'session-a',
        'FEIPI_AGENT_ID': 'agent-1',
    }
    summary = (
        tmp_path
        / 'tmp'
        / 'agent_logs'
        / 'claude'
        / 'session-a'
        / 'agents'
        / 'agent-1'
        / 'stop-check-summary.json'
    )
    assert summary.exists()


def test_stop_changed_files_fail_closed_without_explicit_session(monkeypatch):
    """缺少 Stop stdin session id 时继续使用旧的 fail-closed 采集。"""
    identity = runtime_paths.identity_from_values(agent_client='claude')
    monkeypatch.setattr(agent_stop_check, 'read_git_dirty_files', lambda: [])
    monkeypatch.setattr(
        agent_stop_check,
        'collect_changed_files',
        lambda session_id, agent_id=None: ['scripts/harness/agent_stop_check.py'],
    )

    paths, mode = agent_stop_check.collect_stop_changed_files(identity, 'fallback-session')

    assert mode == 'fail-closed-legacy'
    assert paths == ['scripts/harness/agent_stop_check.py']


def test_codex_stop_without_session_uses_dirty_java_fail_closed(monkeypatch):
    """Codex Stop 缺少 session id 时，dirty Java 文件必须触发 java-src。"""
    identity = runtime_paths.identity_from_values(agent_client='codex')
    monkeypatch.setattr(
        agent_stop_check,
        'read_git_dirty_files',
        lambda: ['java/index-sqlite/src/main/java/com/feipi/Foo.java'],
    )

    paths, mode = agent_stop_check.collect_stop_changed_files(identity, None)

    assert mode == 'fail-closed-git'
    assert paths == ['java/index-sqlite/src/main/java/com/feipi/Foo.java']
    assert 'java-src' in required_targets(paths)


def test_stop_check_lock_is_exclusive(tmp_path):
    lock_path = tmp_path / 'stop-check.lock'
    first = agent_stop_check.StopCheckLock(lock_path, 'claude', 's1')
    second = agent_stop_check.StopCheckLock(lock_path, 'claude', 's2')

    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()
