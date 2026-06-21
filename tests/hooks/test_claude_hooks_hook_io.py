import pytest
from scripts.claude_hooks.hook_io import read_stdin_json


@pytest.mark.contract_case('HOOK-HARNESS-005')
def test_read_bash_command():
    ctx = read_stdin_json('pre-bash', '{"tool_name":"Bash","tool_input":{"command":"git status"}}')
    assert ctx.tool_name == 'Bash'
    assert ctx.command == 'git status'


@pytest.mark.contract_case('HOOK-HARNESS-005')
def test_read_candidate_paths():
    ctx = read_stdin_json(
        'post-write', '{"tool_name":"Edit","tool_input":{"file_path":"src/a.py"}}'
    )
    assert ctx.candidate_paths == ['src/a.py']


@pytest.mark.contract_case('HOOK-HARNESS-005')
def test_bad_json_does_not_crash():
    ctx = read_stdin_json('x', 'not-json')
    assert ctx.parse_error
