"""Hook lifecycle 的稳定输入、策略、证据与三平台入口 contract。"""

from __future__ import annotations

import copy
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from scripts.agent_runtime import hook_entry as hook_runtime
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
from scripts.agent_runtime.hook_entry import _bootstrap_hook_session, _controlled_primary_command
from scripts.agent_runtime.paths import RepoPaths, build_paths, identity_from_values
from scripts.checks.check_agent_runtime_manifest import codex_hook_errors
from scripts.gates.planner import classify_path, required_quality_targets
from scripts.harness import hook_dispatch
from scripts.harness.hook_dispatch import dispatch

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


@pytest.mark.parametrize('subcommand', ('on-stop', 'resume', 'adopt-current'))
def test_controlled_primary_accepts_only_canonical_change_command_for_current_run(
    subcommand: str,
) -> None:
    record = {'runId': 'run-a'}
    current = read_stdin_json(
        'pre-bash',
        json.dumps(
            {
                'tool_name': 'Bash',
                'tool_input': {
                    'command': 'python3 scripts/harness/change.py '
                    f'{subcommand} --run-id run-a --message "complete task"'
                },
            }
        ),
    )
    other_run = read_stdin_json(
        'pre-bash',
        json.dumps(
            {
                'tool_name': 'Bash',
                'tool_input': {
                    'command': 'python3 scripts/harness/change.py '
                    f'{subcommand} --run-id run-b --message "complete task"'
                },
            }
        ),
    )
    retired = read_stdin_json(
        'pre-bash',
        json.dumps(
            {
                'tool_name': 'Bash',
                'tool_input': {
                    'command': 'python3 scripts/harness/sessionctl.py finalize --run-id run-a'
                },
            }
        ),
    )

    assert _controlled_primary_command(current, record)
    assert not _controlled_primary_command(other_run, record)
    assert not _controlled_primary_command(retired, record)


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
    paths_a = build_paths(
        repo,
        identity_from_values(agent_client='claude', session_id='session-a', run_id=''),
    )
    paths_b = build_paths(
        repo,
        identity_from_values(agent_client='claude', session_id='session-b', run_id=''),
    )
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


def _commands_for_event(path: Path) -> dict[tuple[str, str], dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    return {
        (event, entry.get('matcher') or ''): entry['hooks'][0]
        for event, entries in data['hooks'].items()
        for entry in entries
    }


def test_codex_hook_schema_contract_rejects_unknown_fields_and_events() -> None:
    config = json.loads((REPO_ROOT / '.codex/hooks.json').read_text(encoding='utf-8'))

    assert codex_hook_errors(config) == []
    assert set(config) == {'hooks'}
    assert set(config['hooks']) == {
        'SessionStart',
        'UserPromptSubmit',
        'PreToolUse',
        'PostToolUse',
        'Stop',
    }
    assert len(config['hooks']['PreToolUse']) == 1
    assert len(config['hooks']['PostToolUse']) == 1

    unknown_top = copy.deepcopy(config)
    unknown_top['schemaNote'] = 'invalid'
    assert any('未知顶层字段' in item for item in codex_hook_errors(unknown_top))
    for event in ('PostToolUseFailure', 'StopFailure', 'SessionEnd'):
        unsupported = copy.deepcopy(config)
        unsupported['hooks'][event] = copy.deepcopy(config['hooks']['Stop'])
        assert any('不支持事件' in item for item in codex_hook_errors(unsupported))
    overlapping = copy.deepcopy(config)
    overlapping['hooks']['PreToolUse'].append(copy.deepcopy(config['hooks']['PreToolUse'][0]))
    assert any('只能有一个 matcher group' in item for item in codex_hook_errors(overlapping))
    for groups in config['hooks'].values():
        command = groups[0]['hooks'][0]['command']
        assert 'scripts/harness/hook_dispatch.py' in command


@pytest.mark.parametrize(
    ('runtime_event', 'tool_name', 'expected_handler'),
    (
        ('pre-tool', 'Bash', 'pre-bash'),
        ('pre-tool', 'apply_patch', 'pre-write'),
        ('post-tool', 'Bash', 'post-bash'),
        ('post-tool', 'Write', 'post-write'),
    ),
)
def test_unified_tool_event_calls_exactly_one_shared_handler(
    monkeypatch: pytest.MonkeyPatch,
    runtime_event: str,
    tool_name: str,
    expected_handler: str,
) -> None:
    calls: list[str] = []

    def fake(label: str):
        def invoke(_paths, _ctx):
            calls.append(label)
            return label

        return invoke

    monkeypatch.setattr(hook_runtime, 'handle_pre_bash', fake('pre-bash'))
    monkeypatch.setattr(hook_runtime, 'handle_pre_write', fake('pre-write'))
    monkeypatch.setattr(hook_runtime, 'handle_post_bash', fake('post-bash'))
    monkeypatch.setattr(hook_runtime, 'handle_post_write', fake('post-write'))
    ctx = read_stdin_json(runtime_event, json.dumps({'tool_name': tool_name}))

    if runtime_event == 'pre-tool':
        result = hook_runtime.handle_pre_tool(object(), ctx)
    else:
        result = hook_runtime.handle_post_tool(object(), ctx)

    assert result == expected_handler
    assert calls == [expected_handler]


@pytest.mark.parametrize(
    ('client', 'config_path'),
    (
        ('claude', '.claude/settings.json'),
        ('codex', '.codex/hooks.json'),
        ('qoder', '.qoder/settings.json'),
    ),
)
@pytest.mark.contract_case('HOOK-HARNESS-023')
def test_platform_hook_configuration_uses_manifest_dispatcher(
    client: str,
    config_path: str,
) -> None:
    manifest = yaml.safe_load(
        (REPO_ROOT / 'harness/agent-runtime.manifest.yaml').read_text(encoding='utf-8')
    )
    dispatch = manifest['platforms'][client]['hook_dispatch']
    commands = _commands_for_event(REPO_ROOT / config_path)
    expected = {(item['event'], item.get('matcher') or ''): item for item in dispatch['bindings']}
    assert set(commands) == set(expected)
    for key, binding in expected.items():
        hook = commands[key]
        command = hook['command']
        assert 'git rev-parse --show-toplevel' in command
        assert 'scripts/harness/hook_dispatch.py' in command
        assert f'--client {client}' in command
        assert f'--event {binding["dispatch_event"]}' in command
        assert '/hooks/' not in command
        assert hook['timeout'] == binding['timeout']
        if binding['dispatch_event'] == 'stop':
            assert hook['timeout'] >= 1230


@pytest.mark.parametrize('client', ('claude', 'codex', 'qoder'))
@pytest.mark.contract_case('HOOK-HARNESS-023')
def test_platform_pre_write_dispatcher_is_fail_closed(
    tmp_path: Path,
    client: str,
) -> None:
    env = os.environ.copy()
    for name in ('FEIPI_AGENT_CLIENT', 'FEIPI_RUN_ID', 'FEIPI_SESSION_ID'):
        env.pop(name, None)
    env['PYTHONPATH'] = str(REPO_ROOT)
    env['FEIPI_AGENT_RUNTIME_ROOT'] = str(tmp_path / 'runtime')
    proc = subprocess.run(
        [
            sys.executable,
            'scripts/harness/hook_dispatch.py',
            '--client',
            client,
            '--event',
            'pre-write',
        ],
        cwd=REPO_ROOT,
        input=json.dumps({'tool_name': 'Write', 'tool_input': {}}),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 2, (client, proc.stdout, proc.stderr)
    assert 'BLOCK' in proc.stderr


def test_same_payload_has_same_fail_closed_result_for_all_platforms(tmp_path: Path) -> None:
    payload = json.dumps({'tool_name': 'Write', 'tool_input': {}})
    observed = []
    for client in ('claude', 'codex', 'qoder'):
        env = os.environ.copy()
        env['FEIPI_AGENT_RUNTIME_ROOT'] = str(tmp_path / client)
        proc = subprocess.run(
            [
                sys.executable,
                'scripts/harness/hook_dispatch.py',
                '--client',
                client,
                '--event',
                'pre-write',
            ],
            cwd=REPO_ROOT,
            input=payload,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        observed.append((proc.returncode, 'BLOCK' in proc.stderr))
    assert observed == [(2, True)] * 3


def test_missing_dependency_python_fails_fast_without_traceback(
    tmp_path: Path,
) -> None:
    wrapper = tmp_path / 'python-without-site'
    wrapper.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" -I -S "$@"\n',
        encoding='utf-8',
    )
    wrapper.chmod(0o755)
    env = os.environ.copy()
    env['SESSION_BROWSER_PYTHON'] = str(wrapper)
    env['FEIPI_AGENT_RUNTIME_ROOT'] = str(tmp_path / 'runtime')
    env['CODEX_THREAD_ID'] = 'private-session-id'
    started = time.monotonic()

    proc = subprocess.run(
        [
            sys.executable,
            'scripts/harness/hook_dispatch.py',
            '--client',
            'codex',
            '--event',
            'pre-tool',
        ],
        cwd=REPO_ROOT,
        input='{}',
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    duration = time.monotonic() - started

    assert proc.returncode == 2
    assert duration < 2
    assert proc.stderr.splitlines()[0] == 'BLOCKED_PROJECT_PYTHON_NOT_READY'
    assert 'remediation: ./scripts/session-browser.sh deps --dev' in proc.stderr
    assert 'Traceback' not in proc.stderr
    trace = json.loads(next((tmp_path / 'runtime/hook-bootstrap').glob('*.json')).read_text())
    assert [item['phase'] for item in trace['phases']][-2:] == [
        'ENTERED',
        'PYTHON_NOT_READY',
    ]
    assert 'private-session-id' not in json.dumps(trace)


def test_bootstrap_trace_is_atomic_private_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / 'runtime'
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(runtime))
    monkeypatch.setenv('CODEX_THREAD_ID', 'private-session')
    monkeypatch.setattr(hook_dispatch, 'TRACE_FILE_LIMIT', 2)
    common = tmp_path / '.git'
    for phase in ('ENTERED', 'PYTHON_NOT_READY', 'DISPATCHED', 'FAILED'):
        hook_dispatch._record_bootstrap_trace(
            common,
            client='codex',
            event='pre-tool',
            phase=phase,
            error_type='SyntheticError' if phase in {'PYTHON_NOT_READY', 'FAILED'} else '',
        )
    for index in range(10):
        hook_dispatch._record_bootstrap_trace(
            common,
            client='codex',
            event='pre-tool',
            phase='ENTERED',
        )
    first = next((runtime / 'hook-bootstrap').glob('*.json'))
    payload = json.loads(first.read_text(encoding='utf-8'))

    assert len(payload['phases']) == hook_dispatch.TRACE_PHASE_LIMIT
    assert first.stat().st_mode & 0o777 == 0o600
    assert (runtime / 'hook-bootstrap').stat().st_mode & 0o777 == 0o700
    assert 'private-session' not in first.read_text(encoding='utf-8')
    assert list((runtime / 'hook-bootstrap').glob('*.tmp')) == []

    for index in range(3):
        monkeypatch.setenv('CODEX_THREAD_ID', f'session-{index}')
        hook_dispatch._record_bootstrap_trace(
            common,
            client='codex',
            event='post-tool',
            phase='ENTERED',
        )
    assert len(list((runtime / 'hook-bootstrap').glob('*.json'))) == 2


def test_ready_lightweight_dispatch_completes_within_one_second(
    tmp_path: Path,
) -> None:
    primary = tmp_path / 'dispatcher-primary'
    _init_repo(primary)
    _git(primary, 'branch', '-M', 'main_java')
    linked = tmp_path / 'dispatcher-linked'
    _git(primary, 'worktree', 'add', '--detach', str(linked), 'HEAD')
    env = os.environ.copy()
    for name in ('FEIPI_RUN_ID', 'FEIPI_SESSION_ID', 'FEIPI_WORKTREE_ID'):
        env.pop(name, None)
    env['FEIPI_AGENT_RUNTIME_ROOT'] = str(tmp_path / 'runtime')
    env['CODEX_THREAD_ID'] = 'performance-ready-pretool'
    payload = json.dumps(
        {
            'session_id': 'performance-ready-pretool',
            'turn_id': 'turn-a',
            'cwd': str(linked),
            'client_surface': 'codex-app',
            'tool_name': 'Read',
            'tool_input': {},
        }
    )
    command = [
        sys.executable,
        'scripts/harness/hook_dispatch.py',
        '--client',
        'codex',
        '--event',
        'pre-tool',
    ]
    cold = subprocess.run(
        command,
        cwd=REPO_ROOT,
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    started = time.monotonic()
    warm = subprocess.run(
        command,
        cwd=REPO_ROOT,
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    duration = time.monotonic() - started

    assert cold.returncode == 0, cold.stderr
    assert warm.returncode == 0, warm.stderr
    assert duration < 1
    trace = json.loads(next((tmp_path / 'runtime/hook-bootstrap').glob('*.json')).read_text())
    assert trace['phases'][-1]['phase'] == 'DISPATCHED'


def test_project_python_path_comparison_does_not_collapse_venv_symlink(tmp_path: Path) -> None:
    linked_python = tmp_path / 'venv-python'
    linked_python.symlink_to(sys.executable)

    assert hook_dispatch._executable_path(str(linked_python)) == linked_python.absolute()
    assert hook_dispatch._executable_path(str(linked_python)) != Path(sys.executable).resolve()


def test_dispatch_import_failure_is_structured_without_module_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = tmp_path / 'runtime'
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(runtime))
    monkeypatch.setenv('CODEX_THREAD_ID', 'private-failed-session')
    monkeypatch.setattr(hook_dispatch, 'trusted_checkout', lambda: (REPO_ROOT, tmp_path / '.git'))
    monkeypatch.setattr(hook_dispatch, 'ensure_project_python', lambda _argv: None)
    monkeypatch.setattr(hook_dispatch.sys, 'stdin', io.StringIO('{}'))

    def fail_dispatch(*_args, **_kwargs):
        raise ModuleNotFoundError('sensitive-module-name')

    monkeypatch.setattr(hook_dispatch, 'dispatch', fail_dispatch)

    assert hook_dispatch.main(['--client', 'codex', '--event', 'pre-tool']) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'BLOCKED_HOOK_DISPATCH_FAILED' in captured.err
    assert 'errorType: ModuleNotFoundError' in captured.err
    assert 'Traceback' not in captured.err
    assert 'sensitive-module-name' not in captured.err
    trace = json.loads(next((runtime / 'hook-bootstrap').glob('*.json')).read_text())
    assert [item['phase'] for item in trace['phases']] == ['ENTERED', 'FAILED']
    assert 'private-failed-session' not in json.dumps(trace)
    assert 'sensitive-module-name' not in json.dumps(trace)


@pytest.mark.parametrize('client', ('claude', 'codex', 'qoder'))
def test_stop_dispatch_preserves_payload_output_and_exit_code(
    client: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.agent_runtime import hook_entry

    seen: dict[str, object] = {}

    def fake_hook_main(argv: list[str]) -> int:
        seen['argv'] = argv
        seen['payload'] = sys.stdin.read()
        print('hook-stdout')
        print('hook-stderr', file=sys.stderr)
        return 7

    monkeypatch.setattr(hook_entry, 'main', fake_hook_main)
    assert dispatch(client, 'stop', '{"payload":"unchanged"}') == 7
    assert seen == {
        'argv': ['stop'],
        'payload': '{"payload":"unchanged"}',
    }
    captured = capsys.readouterr()
    assert captured.out == 'hook-stdout\n'
    assert captured.err == 'hook-stderr\n'


def test_codex_app_enforces_start_in_detached_managed_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / 'codex-app-primary'
    _init_repo(repo)
    _git(repo, 'branch', '-M', 'main_java')
    linked = tmp_path / 'codex-app-managed-worktree'
    _git(repo, 'worktree', 'add', '--detach', str(linked), 'HEAD')
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    ctx = read_stdin_json(
        'session-start',
        json.dumps(
            {
                'session_id': 'codex-app-session',
                'cwd': str(linked),
                'client_surface': 'codex-app',
                'hook_event_name': 'SessionStart',
            }
        ),
    )

    record = _bootstrap_hook_session(ctx, wrapper_client='codex')

    assert record is not None
    assert record['checkoutKind'] == 'linked-worktree'
    assert record['detached'] is True
    assert record['changeBegin']['status'] == 'ATTESTED'
    assert record['changeBegin']['capability'] == 'START_ENFORCED'
    assert ctx.runtime_record == record
