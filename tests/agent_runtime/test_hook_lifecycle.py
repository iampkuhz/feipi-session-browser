"""Hook lifecycle 的稳定输入、策略、证据与三平台入口 contract。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from scripts.agent_runtime.context import read_stdin_json
from scripts.agent_runtime.events.evidence import (
    acquire_bash_mutation_lock,
    post_bash_isolation_failure,
    read_changed_files,
    record_changed_file,
    record_post_bash,
    record_pre_bash_snapshot,
    release_bash_mutation_lock,
)
from scripts.agent_runtime.events.policy.bash import (
    evaluate_command,
    is_read_only_command,
    primary_write_reason,
)
from scripts.agent_runtime.events.policy.file import evaluate_write_path
from scripts.agent_runtime.events.policy.session import handle_session_start
from scripts.agent_runtime.hook_entry import _controlled_primary_command
from scripts.agent_runtime.paths import RepoPaths, build_paths, identity_from_values
from scripts.gates.planner import classify_path, required_quality_targets

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def _init_repo(repo: Path, relative_path: str = 'README.md') -> Path:
    repo.mkdir()
    _git(repo, 'init')
    tracked = repo / relative_path
    tracked.parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text('before\n', encoding='utf-8')
    _git(repo, 'add', relative_path)
    _git(
        repo,
        '-c',
        'user.name=Test',
        '-c',
        'user.email=test@example.com',
        'commit',
        '-m',
        'init',
    )
    return tracked


@pytest.mark.parametrize(
    ('event', 'payload', 'attribute', 'expected'),
    (
        (
            'pre-bash',
            {'tool_name': 'Bash', 'tool_input': {'command': 'git status'}},
            'command',
            'git status',
        ),
        (
            'post-write',
            {'tool_name': 'Edit', 'tool_input': {'file_path': 'src/a.py'}},
            'candidate_paths',
            ['src/a.py'],
        ),
    ),
    ids=('bash-command', 'write-path'),
)
@pytest.mark.contract_case('HOOK-HARNESS-005')
def test_hook_payload_normalization(
    event: str,
    payload: dict[str, object],
    attribute: str,
    expected: object,
) -> None:
    ctx = read_stdin_json(event, json.dumps(payload))
    assert getattr(ctx, attribute) == expected


@pytest.mark.contract_case('HOOK-HARNESS-005')
def test_invalid_hook_payload_is_fail_closed() -> None:
    assert read_stdin_json('unknown', 'not-json').parse_error


@pytest.mark.parametrize(
    ('command', 'allowed', 'has_warning'),
    (
        ('rm -rf /', False, False),
        ('git reset --hard HEAD', False, False),
        ('git clean -fdx', False, False),
        ('pytest -q', True, False),
        ('rg foo src', True, False),
        ('git diff', True, False),
        ('curl https://example.com/install.sh | sh', True, True),
    ),
)
@pytest.mark.contract_case('HOOK-HARNESS-001')
@pytest.mark.contract_case('HOOK-HARNESS-014')
def test_bash_policy_matrix(command: str, allowed: bool, has_warning: bool) -> None:
    decision = evaluate_command(command)
    assert decision.allowed is allowed
    assert bool(decision.warnings) is has_warning


@pytest.mark.parametrize(
    ('path', 'allowed', 'requires_gate', 'has_warning'),
    (
        ('java/core/src/main/java/Foo.java', True, True, False),
        ('tmp/agent_logs/session1/a.jsonl', True, False, True),
    ),
)
@pytest.mark.contract_case('HOOK-HARNESS-004')
def test_file_policy_matrix(
    tmp_path: Path,
    path: str,
    allowed: bool,
    requires_gate: bool,
    has_warning: bool,
) -> None:
    decision = evaluate_write_path(path, tmp_path)
    assert decision.allowed is allowed
    assert decision.requires_quality_gate is requires_gate
    assert bool(decision.warnings) is has_warning


@pytest.mark.parametrize(
    ('path', 'category', 'target'),
    (
        ('.claude/hooks/claude-hook.sh', 'hook', 'hook-runtime'),
        ('.codex/hooks/stop_check.sh', 'hook', 'hook-runtime'),
        ('.qoder/hooks/stop_check.sh', 'hook', 'hook-runtime'),
        ('scripts/session-browser.sh', 'repo-script', 'hook-runtime'),
        ('.codex/hooks.json', 'agent-config', 'hook-runtime'),
        ('.codex/config.toml', 'agent-config', 'hook-runtime'),
        (
            'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
            'agent-config',
            'hook-runtime',
        ),
        (
            '.agents/skills/feipi-openspec-orchestrate-change/SKILL.md',
            'agent-config',
            'hook-runtime',
        ),
        (
            '.codex/skills/feipi-openspec-orchestrate-change/SKILL.md',
            'agent-config',
            'hook-runtime',
        ),
        (
            '.claude/skills/feipi-openspec-orchestrate-change/SKILL.md',
            'agent-config',
            'hook-runtime',
        ),
        ('AGENTS.md', 'agent-config', 'hook-runtime'),
        ('CLAUDE.md', 'agent-config', 'hook-runtime'),
        ('config/api-snapshots/java-public-api.txt', 'java-build', 'java-build'),
        (
            'java/web/src/main/resources/static/css/session-detail.css',
            'session-detail-ui',
            'session-detail',
        ),
        (
            'java/web/src/main/resources/static/js/session-detail/init.js',
            'session-detail-ui',
            'session-detail',
        ),
        ('pyproject.toml', 'python-tooling-config', 'hook-runtime'),
        ('requirements-dev.txt', 'python-tooling-config', 'hook-runtime'),
        ('requirements-dev.lock', 'python-tooling-config', 'hook-runtime'),
        ('uv.lock', 'python-tooling-config', 'hook-runtime'),
        ('.pre-commit-config.yaml', 'python-tooling-config', 'hook-runtime'),
        ('.github/workflows/quality.yml', 'python-tooling-config', 'hook-runtime'),
        (
            'docs/acceptance-contracts/features/DATA_PRESENTERS.md',
            'acceptance-contract',
            'acceptance-contracts',
        ),
        ('tests/backend/test_round_signals.py', 'test', 'acceptance-contracts'),
    ),
)
@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_changed_path_classification(path: str, category: str, target: str) -> None:
    classified = classify_path(path)
    assert classified.category == category
    assert classified.quality_target == target
    assert classified.requires_quality_gate


@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_quality_targets_are_deduplicated() -> None:
    assert required_quality_targets(
        ['java/core/src/main/java/Foo.java', 'java/core/src/main/java/Bar.java']
    ) == ['java-src']
    assert required_quality_targets(
        [
            'docs/acceptance-contracts/features/DATA_PRESENTERS.md',
            'tests/backend/test_round_signals.py',
        ]
    ) == ['acceptance-contracts']


@pytest.mark.contract_case('HOOK-HARNESS-003')
def test_changed_file_evidence_is_jsonl(tmp_path: Path) -> None:
    target = tmp_path / 'java/core/src/main/java/Foo.java'
    target.parent.mkdir(parents=True)
    target.write_text('class Foo {}\n')
    paths = RepoPaths(repo_root=tmp_path, agent_log_dir=tmp_path / 'tmp/agent_logs/session1')
    ctx = read_stdin_json(
        'post-write',
        '{"tool_name":"Edit","tool_input":{"file_path":"java/core/src/main/java/Foo.java"}}',
    )

    record = record_changed_file(paths, ctx, 'java/core/src/main/java/Foo.java')

    assert record['category'] == 'java-src'
    assert read_changed_files(paths) == [record]


def test_missing_bash_snapshot_records_fail_closed_marker(tmp_path: Path) -> None:
    repo = tmp_path / 'repo'
    repo.mkdir()
    paths = build_paths(repo, identity_from_values(agent_client='claude', session_id='session-a'))
    ctx = read_stdin_json(
        'post-bash',
        json.dumps(
            {
                'session_id': 'session-a',
                'tool_name': 'Bash',
                'tool_use_id': 'tool-missing',
                'tool_input': {'command': 'python scripts/mutate.py'},
            }
        ),
    )

    assert record_post_bash(paths, ctx) == []
    events = [json.loads(line) for line in paths.hook_events.read_text().splitlines()]
    assert len(events) == 1
    assert {
        key: events[0][key]
        for key in (
            'status',
            'bashSnapshotRequired',
            'bashMutationTracking',
            'mutationSource',
        )
    } == {
        'status': 'BASH_SNAPSHOT_MISSING',
        'bashSnapshotRequired': True,
        'bashMutationTracking': True,
        'mutationSource': 'bash',
    }


def test_bash_mutation_records_session_changed_file(tmp_path: Path) -> None:
    repo = tmp_path / 'repo'
    tracked = _init_repo(repo, 'scripts/tool.py')
    paths = RepoPaths(
        repo_root=repo,
        agent_log_dir=repo / 'tmp/agent_logs/claude/session-a/main',
    )
    ctx = read_stdin_json(
        'pre-bash',
        json.dumps(
            {
                'session_id': 'session-a',
                'tool_name': 'Bash',
                'tool_use_id': 'tool-1',
                'tool_input': {'command': 'python scripts/tool.py'},
            }
        ),
    )

    assert record_pre_bash_snapshot(paths, ctx)
    tracked.write_text('after\n', encoding='utf-8')
    records = record_post_bash(paths, ctx)

    assert [record['file'] for record in records] == ['scripts/tool.py']
    changed_record = json.loads(paths.changed_files.read_text().splitlines()[0])
    assert (changed_record['sessionId'], changed_record['toolUseId'], changed_record['file']) == (
        'session-a',
        'tool-1',
        'scripts/tool.py',
    )


@pytest.mark.parametrize(
    'template',
    [
        'cp source.txt "{primary}/copy.txt"',
        'mv source.txt "{primary}/moved.txt"',
        'mv "{primary}/source.txt" moved.txt',
        'cp -t "{primary}" source.txt',
        'rsync source.txt "{primary}/sync.txt"',
        'install source.txt "{primary}/installed.txt"',
        'sed -i s/a/b/ "{primary}/tracked.txt"',
        'git -C "{primary}" checkout -- tracked.txt',
        'printf x > "{primary}/redirected.txt"',
        'ln -s source.txt "{alias}/linked.txt"',
    ],
)
def test_linked_worktree_primary_write_corpus_is_blocked(tmp_path: Path, template: str) -> None:
    """常见路径写法和 symlink 绕过必须统一命中 primary 隔离。"""
    primary = tmp_path / 'primary checkout'
    linked = tmp_path / 'linked checkout'
    primary.mkdir()
    linked.mkdir()
    alias = tmp_path / 'primary-alias'
    alias.symlink_to(primary, target_is_directory=True)

    reason = primary_write_reason(
        template.format(primary=primary, alias=alias),
        cwd=linked,
        checkout_root=linked,
        primary_root=primary,
    )

    assert reason


def test_primary_read_only_git_and_linked_write_are_allowed(tmp_path: Path) -> None:
    """primary 只读 Git 查询与当前 linked checkout 内写入不应被误阻断。"""
    primary = tmp_path / 'primary'
    linked = tmp_path / 'linked'
    primary.mkdir()
    linked.mkdir()
    query = f'git -C "{primary}" status --short'
    assert is_read_only_command(query)
    assert not primary_write_reason(
        query,
        cwd=linked,
        checkout_root=linked,
        primary_root=primary,
    )
    assert not primary_write_reason(
        f'cp source.txt "{linked}/copy.txt"',
        cwd=linked,
        checkout_root=linked,
        primary_root=primary,
    )


def test_primary_fingerprint_blocks_unparsed_bash_bypass(tmp_path: Path) -> None:
    """预解析未知命令仍必须由 primary 内容指纹在 post-Bash 关闭失败。"""
    linked = tmp_path / 'linked'
    primary = tmp_path / 'primary'
    _init_repo(linked)
    tracked = _init_repo(primary, 'tracked.txt')
    paths = build_paths(
        linked,
        identity_from_values(agent_client='claude', session_id='session-a'),
    )
    ctx = read_stdin_json(
        'pre-bash',
        '{"session_id":"session-a","tool_name":"Bash","tool_use_id":"bypass",'
        '"tool_input":{"command":"opaque-writer"}}',
    )
    assert acquire_bash_mutation_lock(paths, ctx)
    assert record_pre_bash_snapshot(paths, ctx, primary_root=primary)
    tracked.write_text('bypassed\n', encoding='utf-8')
    post_ctx = read_stdin_json(
        'post-bash',
        '{"session_id":"session-a","tool_name":"Bash","tool_use_id":"bypass",'
        '"tool_input":{"command":"opaque-writer"}}',
    )
    record_post_bash(paths, post_ctx)
    assert 'primary fingerprint audit BLOCK' in post_bash_isolation_failure(paths, post_ctx)


def test_controlled_finalize_requires_current_fresh_validated_receipt() -> None:
    """直接 finalize 仅接受当前 run 的 fresh VALIDATED Stop receipt。"""
    ctx = read_stdin_json(
        'pre-bash',
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3 scripts/harness/sessionctl.py finalize --run-id run-a"}}',
    )
    record = {
        'runId': 'run-a',
        'status': 'VALIDATED',
        'stopExitCode': 0,
        'stopValidation': {'status': 'PASS', 'fresh': True},
    }
    assert _controlled_primary_command(ctx, record)
    assert not _controlled_primary_command(
        ctx,
        {**record, 'stopValidation': {'status': 'PASS', 'fresh': False}},
    )
    other = read_stdin_json(
        'pre-bash',
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3 scripts/harness/sessionctl.py finalize --run-id run-b"}}',
    )
    assert not _controlled_primary_command(other, record)


@pytest.mark.contract_case('HOOK-HARNESS-019')
def test_bash_snapshots_are_identity_scoped(tmp_path: Path) -> None:
    repo = tmp_path / 'repo'
    _init_repo(repo)
    ctx_a = read_stdin_json(
        'pre-bash',
        '{"session_id":"session-a","tool_name":"Bash","tool_use_id":"same-tool",'
        '"tool_input":{"command":"python scripts/tool.py"}}',
    )
    ctx_b = read_stdin_json(
        'pre-bash',
        '{"session_id":"session-b","tool_name":"Bash","tool_use_id":"same-tool",'
        '"tool_input":{"command":"python scripts/tool.py"}}',
    )
    paths_a = RepoPaths(repo_root=repo, agent_log_dir=repo / 'tmp/agent_logs/claude/session-a/main')
    paths_b = RepoPaths(repo_root=repo, agent_log_dir=repo / 'tmp/agent_logs/claude/session-b/main')

    assert record_pre_bash_snapshot(paths_a, ctx_a)
    assert record_pre_bash_snapshot(paths_b, ctx_b)
    snapshots_a = list((paths_a.agent_log_dir / 'bash-snapshots').glob('*.json'))
    snapshots_b = list((paths_b.agent_log_dir / 'bash-snapshots').glob('*.json'))
    assert len(snapshots_a) == len(snapshots_b) == 1
    assert snapshots_a[0] != snapshots_b[0]


def test_bash_mutation_lock_owner_is_identity_scoped(tmp_path: Path) -> None:
    repo = tmp_path / 'repo'
    repo.mkdir()
    paths_a = build_paths(repo, identity_from_values(agent_client='claude', session_id='session-a'))
    paths_b = build_paths(repo, identity_from_values(agent_client='claude', session_id='session-b'))
    ctx_a = read_stdin_json(
        'pre-bash',
        '{"session_id":"session-a","tool_name":"Bash","tool_use_id":"same-tool",'
        '"tool_input":{"command":"python scripts/tool.py"}}',
    )
    ctx_b = read_stdin_json(
        'post-bash',
        '{"session_id":"session-b","tool_name":"Bash","tool_use_id":"same-tool",'
        '"tool_input":{"command":"python scripts/tool.py"}}',
    )

    assert acquire_bash_mutation_lock(paths_a, ctx_a)
    lock_path = repo / 'tmp/agent_logs/bash-mutation.lock'
    release_bash_mutation_lock(paths_b, ctx_b)
    assert lock_path.exists()
    release_bash_mutation_lock(paths_a, ctx_a)
    assert not lock_path.exists()


def test_main_and_subagent_session_start_use_separate_runtime_dirs(tmp_path: Path) -> None:
    repo = tmp_path / 'repo'
    _init_repo(repo)
    main_paths = build_paths(
        repo,
        identity_from_values(agent_client='claude', session_id='session-a'),
    )
    agent_paths = build_paths(
        repo,
        identity_from_values(agent_client='claude', session_id='session-a', agent_id='agent-1'),
    )

    handle_session_start(
        main_paths,
        read_stdin_json('session-start', '{"session_id":"session-a"}'),
        'session-start',
    )
    handle_session_start(
        agent_paths,
        read_stdin_json(
            'subagent-start',
            '{"session_id":"session-a","agent_id":"agent-1"}',
        ),
        'subagent-start',
    )

    assert main_paths.session_id_file.read_text().strip() == 'session-a'
    assert agent_paths.session_id_file.read_text().strip() == 'session-a'
    assert main_paths.base_commit != agent_paths.base_commit
    assert main_paths.base_commit.read_text() == agent_paths.base_commit.read_text()


def _commands_for_event(path: Path) -> dict[tuple[str, str], list[str]]:
    data = json.loads(path.read_text(encoding='utf-8'))
    return {
        (event, entry.get('matcher') or ''): [hook['command'] for hook in entry['hooks']]
        for event, entries in data['hooks'].items()
        for entry in entries
    }


PLATFORM_HOOK_CONFIGS = (
    (
        'claude',
        '.claude/settings.json',
        {
            ('SessionStart', ''): '.claude/hooks/session-start.sh',
            ('CwdChanged', ''): '.claude/hooks/cwd-changed.sh',
            ('SubagentStart', ''): '.claude/hooks/subagent-start.sh',
            ('PreToolUse', 'Bash'): '.claude/hooks/pre-bash.sh',
            (
                'PreToolUse',
                'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch',
            ): '.claude/hooks/pre-write.sh',
            ('PostToolUse', 'Bash'): '.claude/hooks/post-bash.sh',
            (
                'PostToolUse',
                'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch',
            ): '.claude/hooks/post-write.sh',
            ('PostToolUseFailure', ''): '.claude/hooks/tool-failure.sh',
            ('Stop', ''): '.claude/hooks/stop.sh',
            ('SubagentStop', ''): '.claude/hooks/subagent-stop.sh',
            ('ConfigChange', ''): '.claude/hooks/config-change.sh',
            ('SessionEnd', ''): '.claude/hooks/session-end.sh',
        },
        False,
    ),
    (
        'codex',
        '.codex/hooks.json',
        {
            ('SessionStart', ''): '.codex/hooks/session-start.sh',
            ('PreToolUse', ''): '.codex/hooks/pre_tool_bootstrap.sh',
            ('PreToolUse', 'Bash'): '.codex/hooks/pre_tool_guard.sh',
            (
                'PreToolUse',
                'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch',
            ): '.codex/hooks/pre_write_guard.sh',
            ('PostToolUse', 'Bash'): '.codex/hooks/post_bash_guard.sh',
            (
                'PostToolUse',
                'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch',
            ): '.codex/hooks/post_tool_guard.sh',
            ('PostToolUseFailure', ''): '.codex/hooks/tool_failure.sh',
            ('Stop', ''): '.codex/hooks/stop_check.sh',
            ('StopFailure', ''): '.codex/hooks/stop_failure.sh',
            ('SessionEnd', ''): '.codex/hooks/session_end.sh',
        },
        True,
    ),
    (
        'qoder',
        '.qoder/settings.json',
        {
            ('SessionStart', ''): '.qoder/hooks/session-start.sh',
            ('CwdChanged', ''): '.qoder/hooks/cwd-changed.sh',
            ('UserPromptSubmit', ''): '.qoder/hooks/user-prompt-submit.sh',
            ('PreToolUse', ''): '.qoder/hooks/pre_tool_bootstrap.sh',
            ('PreToolUse', 'Bash'): '.qoder/hooks/pre_tool_guard.sh',
            (
                'PreToolUse',
                'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch',
            ): '.qoder/hooks/pre_write_guard.sh',
            ('PostToolUse', 'Bash'): '.qoder/hooks/post_bash_guard.sh',
            (
                'PostToolUse',
                'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch',
            ): '.qoder/hooks/post_tool_guard.sh',
            ('PostToolUseFailure', ''): '.qoder/hooks/tool_failure.sh',
            ('Stop', ''): '.qoder/hooks/stop_check.sh',
            ('StopFailure', ''): '.qoder/hooks/stop_failure.sh',
            ('SessionEnd', ''): '.qoder/hooks/session_end.sh',
        },
        True,
    ),
)


@pytest.mark.parametrize(
    ('client', 'config_path', 'expected', 'resolves_git_root'),
    PLATFORM_HOOK_CONFIGS,
    ids=[case[0] for case in PLATFORM_HOOK_CONFIGS],
)
@pytest.mark.contract_case('HOOK-HARNESS-023')
def test_platform_hook_configuration_matrix(
    client: str,
    config_path: str,
    expected: dict[tuple[str, str], str],
    resolves_git_root: bool,
) -> None:
    path = REPO_ROOT / config_path
    commands = _commands_for_event(path)
    assert set(commands) == set(expected)
    for key, wrapper in expected.items():
        assert len(commands[key]) == 1
        command = commands[key][0]
        if resolves_git_root:
            assert 'git rev-parse --show-toplevel' in command
            assert wrapper in command
            assert '/feipi-session-browser' not in command
        else:
            assert command == wrapper
    if resolves_git_root:
        stop_hook = json.loads(path.read_text())['hooks']['Stop'][0]['hooks'][0]
        assert stop_hook['timeout'] >= 1230, client


@pytest.mark.parametrize(
    ('client', 'wrapper', 'payload'),
    (
        ('claude', '.claude/hooks/pre-write.sh', {'tool_name': 'Write', 'tool_input': {}}),
        (
            'codex',
            '.codex/hooks/pre_write_guard.sh',
            {'client': 'codex', 'toolName': 'Write', 'toolInput': {}},
        ),
        (
            'qoder',
            '.qoder/hooks/pre_write_guard.sh',
            {'client': 'qoder', 'toolName': 'Write', 'toolInput': {}},
        ),
    ),
    ids=('claude', 'codex', 'qoder'),
)
@pytest.mark.contract_case('HOOK-HARNESS-023')
def test_platform_pre_write_entrypoints_fail_closed(
    tmp_path: Path,
    client: str,
    wrapper: str,
    payload: dict[str, object],
) -> None:
    env = os.environ.copy()
    for name in ('FEIPI_AGENT_CLIENT', 'FEIPI_RUN_ID', 'FEIPI_SESSION_ID'):
        env.pop(name, None)
    env['PYTHONPATH'] = str(REPO_ROOT)
    env['FEIPI_AGENT_RUNTIME_ROOT'] = str(tmp_path / 'runtime')
    proc = subprocess.run(
        ['bash', wrapper],
        cwd=REPO_ROOT,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 2, (client, proc.stdout, proc.stderr)
    assert 'BLOCK' in proc.stderr
