from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.agent_runtime import hook_entry as hook_main
from scripts.agent_runtime.context import read_stdin_json
from scripts.agent_runtime.events.adapter import UNVERIFIED, build_bootstrap_request
from scripts.agent_runtime.events.policy.file import pre_write_payload_block_reason
from scripts.harness.sessionctl import Registry

REPO_ROOT = Path(__file__).resolve().parents[1]


PLATFORM_BOOTSTRAP_FIXTURES = (
    (
        'codex-app',
        'codex-cli',
        'session-start',
        {'sessionId': 'codex-app-s', 'cwd': '/tmp/codex app'},
        'codex',
        'SessionStart',
    ),
    (
        'codex-cli',
        'codex-cli',
        'pre-write',
        {
            'session_id': 'codex-cli-s',
            'cwd': '/tmp/codex-cli',
        },
        'codex',
        'PreToolUse',
    ),
    (
        'claude-code-cli',
        'claude-code-cli',
        'cwd-changed',
        {
            'session_id': 'claude-s',
            'cwd': '/tmp/claude-worktree',
        },
        'claude',
        'CwdChanged',
    ),
    (
        'qoder-cli',
        'qoder-cli',
        'cwd-changed',
        {
            'sessionId': 'qoder-cli-s',
            'workingDirectory': '/tmp/qoder-cli',
        },
        'qoder',
        'CwdChanged',
    ),
    (
        'qoder-client',
        'qoder-client',
        'user-prompt-submit',
        {
            'sessionId': 'qoder-client-s',
            'cwd': '/tmp/qoder-client',
        },
        'qoder',
        'UserPromptSubmit',
    ),
)


def _payload(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ['git', '-C', str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _git_checkout(tmp_path: Path, checkout_kind: str) -> tuple[Path, Path]:
    primary = tmp_path / 'primary checkout'
    primary.mkdir()
    _git(primary, 'init', '-b', 'main')
    _git(primary, 'config', 'user.name', 'Hook Adapter Test')
    _git(primary, 'config', 'user.email', 'hook-adapter@example.invalid')
    (primary / 'README.md').write_text('fixture\n', encoding='utf-8')
    _git(primary, 'add', 'README.md')
    _git(primary, 'commit', '-m', 'fixture')
    if checkout_kind == 'primary-checkout':
        return primary, primary
    linked = tmp_path / 'linked worktree'
    _git(primary, 'worktree', 'add', '--detach', str(linked), 'HEAD')
    return primary, linked


@pytest.mark.parametrize(
    ('platform_label', 'expected_adapter', 'event_name', 'payload', 'client', 'hook_event'),
    PLATFORM_BOOTSTRAP_FIXTURES,
    ids=[case[0] for case in PLATFORM_BOOTSTRAP_FIXTURES],
)
@pytest.mark.parametrize(
    'checkout_kind',
    ('primary-checkout', 'linked-worktree'),
    ids=('local', 'linked'),
)
def test_five_platform_payloads_repeat_bootstrap_on_real_git_checkouts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    platform_label: str,
    expected_adapter: str,
    event_name: str,
    payload: dict[str, object],
    client: str,
    hook_event: str,
    checkout_kind: str,
):
    primary, checkout = _git_checkout(tmp_path, checkout_kind)
    runtime_temp = tmp_path / 'runtime temp'
    runtime_temp.mkdir()
    monkeypatch.setenv('TMPDIR', str(runtime_temp))
    for name in (
        'FEIPI_AGENT_RUNTIME_ROOT',
        'FEIPI_RUN_ID',
        'FEIPI_SESSION_ID',
        'FEIPI_AGENT_CLIENT',
    ):
        monkeypatch.delenv(name, raising=False)

    real_payload = dict(payload)
    cwd_keys = {'cwd', 'workingDirectory'}
    replaced = [key for key in cwd_keys if key in real_payload]
    assert len(replaced) == 1
    real_payload[replaced[0]] = str(checkout)
    ctx = read_stdin_json(event_name, _payload(real_payload))
    request = build_bootstrap_request(ctx, wrapper_client=client)
    assert request is not None
    assert (platform_label, request.adapter.surface) == (platform_label, expected_adapter)
    assert request.adapter.verification == UNVERIFIED
    assert request.client == client
    assert request.session_id == ctx.session_id
    assert request.cwd == ctx.cwd
    assert request.hook_event == hook_event
    assert request.checkout_creator == client
    worktrees_before = _git(primary, 'worktree', 'list', '--porcelain')

    first = hook_main._bootstrap_hook_session(ctx, wrapper_client=client)
    second = hook_main._bootstrap_hook_session(ctx, wrapper_client=client)

    assert first is not None and second is not None
    assert first['runId'] == second['runId']
    assert first['checkoutRoot'] == str(checkout.resolve())
    assert first['checkoutKind'] == checkout_kind
    assert first['checkoutCreator'] == client
    assert first['bootstrap']['firstHookEvent'] == hook_event
    assert _git(primary, 'worktree', 'list', '--porcelain') == worktrees_before
    records = Registry(checkout).all_runs()
    assert len(records) == 1
    assert records[0]['runId'] == first['runId']


def test_wrapper_event_is_authoritative_over_conflicting_payload_event():
    ctx = read_stdin_json(
        'post-write',
        _payload(
            {
                'sessionId': 's-conflict',
                'cwd': '/checkout/conflict',
                'hook_event_name': 'SessionStart',
            }
        ),
    )

    assert build_bootstrap_request(ctx, wrapper_client='codex') is None


def test_hook_context_supports_snake_camel_and_client_aliases():
    snake = read_stdin_json(
        'pre-write',
        _payload(
            {
                'session_id': 's1',
                'agent_id': 'a1',
                'agent_client': 'claude',
                'tool_name': 'Write',
                'tool_input': {'file_path': 'README.md'},
            }
        ),
    )
    camel = read_stdin_json(
        'pre-write',
        _payload(
            {
                'sessionId': 's2',
                'agentId': 'a2',
                'agentClient': 'codex',
                'toolName': 'Edit',
                'toolInput': {'path': 'README.md'},
            }
        ),
    )
    qoder = read_stdin_json(
        'pre-write',
        _payload(
            {
                'client': 'qoder',
                'toolName': 'Write',
                'toolInput': {'path': 'README.md'},
            }
        ),
    )
    assert snake.session_id == 's1'
    assert snake.agent_id == 'a1'
    assert snake.agent_client == 'claude'
    assert snake.candidate_paths == ['README.md']
    assert camel.session_id == 's2'
    assert camel.agent_id == 'a2'
    assert camel.agent_client == 'codex'
    assert camel.candidate_paths == ['README.md']
    assert qoder.agent_client == 'qoder'
    assert qoder.candidate_paths == ['README.md']


def test_multiedit_extracts_all_candidate_paths():
    ctx = read_stdin_json(
        'pre-write',
        _payload(
            {
                'tool_name': 'MultiEdit',
                'tool_input': {
                    'edits': [
                        {'file_path': 'a.txt'},
                        {'path': 'b.txt'},
                        {'notebook_path': 'c.ipynb'},
                        {'file_path': 'a.txt'},
                    ]
                },
            }
        ),
    )
    assert ctx.candidate_paths == ['a.txt', 'b.txt', 'c.ipynb']


def test_notebook_edit_extracts_notebook_path():
    ctx = read_stdin_json(
        'pre-write',
        _payload({'tool_name': 'NotebookEdit', 'tool_input': {'notebook_path': 'analysis.ipynb'}}),
    )
    assert ctx.candidate_paths == ['analysis.ipynb']


def test_missing_path_for_write_blocks():
    ctx = read_stdin_json('pre-write', _payload({'tool_name': 'Write', 'tool_input': {}}))
    assert pre_write_payload_block_reason(ctx, REPO_ROOT)


def test_missing_session_for_protected_write_blocks():
    ctx = read_stdin_json(
        'pre-write',
        _payload(
            {
                'tool_name': 'Write',
                'tool_input': {'file_path': 'scripts/agent_runtime/hook_entry.py'},
            }
        ),
    )
    reason = pre_write_payload_block_reason(ctx, REPO_ROOT)
    assert 'session id' in reason


def test_invalid_json_for_pre_write_blocks():
    ctx = read_stdin_json('pre-write', '{not-json')
    reason = pre_write_payload_block_reason(ctx, REPO_ROOT)
    assert ctx.parse_error
    assert reason


def test_check_hook_payload_compat_passes():
    proc = subprocess.run(
        [sys.executable, 'scripts/checks/check_hook_payload_compat.py'],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert '[hookPayloadCompat] PASS' in proc.stdout
