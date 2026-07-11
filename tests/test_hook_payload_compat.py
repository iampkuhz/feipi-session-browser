from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.claude_hooks.hook_io import read_stdin_json
from scripts.claude_hooks.policy.file_policy import pre_write_payload_block_reason

REPO_ROOT = Path(__file__).resolve().parents[1]


def _payload(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False)


def test_hook_context_supports_snake_and_camel_case():
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
    assert snake.session_id == 's1'
    assert snake.agent_id == 'a1'
    assert snake.agent_client == 'claude'
    assert snake.candidate_paths == ['README.md']
    assert camel.session_id == 's2'
    assert camel.agent_id == 'a2'
    assert camel.agent_client == 'codex'
    assert camel.candidate_paths == ['README.md']


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
        _payload({'tool_name': 'Write', 'tool_input': {'file_path': 'scripts/claude_hooks/main.py'}}),
    )
    reason = pre_write_payload_block_reason(ctx, REPO_ROOT)
    assert 'session id' in reason


def test_invalid_json_for_pre_write_blocks():
    ctx = read_stdin_json('pre-write', '{not-json')
    reason = pre_write_payload_block_reason(ctx, REPO_ROOT)
    assert ctx.parse_error
    assert reason


def test_qoder_payload_minimal_fields_are_supported_or_blocked_safely():
    supported = read_stdin_json(
        'pre-write',
        _payload({'client': 'qoder', 'toolName': 'Write', 'toolInput': {'path': 'README.md'}}),
    )
    assert supported.agent_client == 'qoder'
    assert supported.candidate_paths == ['README.md']
    assert not pre_write_payload_block_reason(supported, REPO_ROOT)

    blocked = read_stdin_json(
        'pre-write',
        _payload({'client': 'qoder', 'toolName': 'Write', 'toolInput': {}}),
    )
    assert pre_write_payload_block_reason(blocked, REPO_ROOT)


def test_check_hook_payload_compat_passes():
    proc = subprocess.run(
        [sys.executable, 'scripts/quality/check_hook_payload_compat.py'],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert '[hookPayloadCompat] PASS' in proc.stdout
