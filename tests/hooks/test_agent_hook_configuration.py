import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _commands_for_event(path: Path) -> dict[tuple[str, str], list[str]]:
    """Return hook commands keyed by (event, matcher)."""
    data = json.loads(path.read_text(encoding='utf-8'))
    result: dict[tuple[str, str], list[str]] = {}
    for event, entries in data['hooks'].items():
        for entry in entries:
            matcher = entry.get('matcher') or ''
            result[(event, matcher)] = [hook['command'] for hook in entry['hooks']]
    return result


PLATFORM_HOOK_CONFIGS = (
    (
        'claude',
        '.claude/settings.json',
        {
            ('SessionStart', ''): '.claude/hooks/session-start.sh',
            ('CwdChanged', ''): '.claude/hooks/cwd-changed.sh',
            ('SubagentStart', ''): '.claude/hooks/subagent-start.sh',
            ('PreToolUse', 'Bash'): '.claude/hooks/pre-bash.sh',
            ('PreToolUse', 'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch'): '.claude/hooks/pre-write.sh',
            ('PostToolUse', 'Bash'): '.claude/hooks/post-bash.sh',
            ('PostToolUse', 'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch'): '.claude/hooks/post-write.sh',
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
            ('PreToolUse', 'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch'): '.codex/hooks/pre_write_guard.sh',
            ('PostToolUse', 'Bash'): '.codex/hooks/post_bash_guard.sh',
            ('PostToolUse', 'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch'): '.codex/hooks/post_tool_guard.sh',
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
            ('PreToolUse', 'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch'): '.qoder/hooks/pre_write_guard.sh',
            ('PostToolUse', 'Bash'): '.qoder/hooks/post_bash_guard.sh',
            ('PostToolUse', 'Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch'): '.qoder/hooks/post_tool_guard.sh',
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
def test_platform_project_hook_matrix_is_complete(
    client: str,
    config_path: str,
    expected: dict[tuple[str, str], str],
    resolves_git_root: bool,
):
    """平台差异仅存在于配置表，生命周期都绑定唯一共享 wrapper。"""
    path = REPO_ROOT / config_path
    commands = _commands_for_event(path)

    assert set(commands) == set(expected)
    for key, rel_path in expected.items():
        assert len(commands[key]) == 1
        command = commands[key][0]
        if resolves_git_root:
            assert 'git rev-parse --show-toplevel' in command
            assert rel_path in command
            assert '/feipi-session-browser' not in command
        else:
            assert command == rel_path

    if resolves_git_root:
        stop_hook = json.loads(path.read_text(encoding='utf-8'))['hooks']['Stop'][0]['hooks'][0]
        assert stop_hook['timeout'] >= 1230, client


@pytest.mark.parametrize(
    ('client', 'wrapper', 'payload'),
    (
        ('claude', '.claude/hooks/pre-write.sh', {'tool_name': 'Write', 'tool_input': {}}),
        ('codex', '.codex/hooks/pre_write_guard.sh', {'client': 'codex', 'toolName': 'Write', 'toolInput': {}}),
        ('qoder', '.qoder/hooks/pre_write_guard.sh', {'client': 'qoder', 'toolName': 'Write', 'toolInput': {}}),
    ),
    ids=('claude', 'codex', 'qoder'),
)
def test_platform_pre_write_wrappers_are_thin_and_fail_closed(
    tmp_path: Path,
    client: str,
    wrapper: str,
    payload: dict[str, object],
):
    """三个 wrapper 仅委托共享入口，并原样保留 BLOCK exit 2。"""
    text = (REPO_ROOT / wrapper).read_text(encoding='utf-8')
    assert 'scripts/harness/hook-common.sh' in text
    assert f'run_python_hook {client} pre-write "$ROOT"' in text

    env = os.environ.copy()
    for name in (
        'FEIPI_AGENT_CLIENT',
        'FEIPI_AGENT_RUNTIME_ROOT',
        'FEIPI_RUN_ID',
        'FEIPI_SESSION_ID',
    ):
        env.pop(name, None)
    env['PYTHONPATH'] = str(REPO_ROOT)
    env['FEIPI_AGENT_RUNTIME_ROOT'] = str(tmp_path / 'runtime')
    proc = subprocess.run(
        ['bash', wrapper],
        cwd=REPO_ROOT,
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )

    assert proc.returncode == 2
    assert 'BLOCK' in proc.stderr


def test_platform_wrappers_only_delegate_to_shared_entrypoints():
    """event/Stop wrapper 仅转发给共享 Python 入口。"""
    event_wrappers = {
        '.claude/hooks/cwd-changed.sh': 'run_python_hook claude cwd-changed "$ROOT"',
        '.claude/hooks/session-end.sh': 'run_python_hook claude session-end "$ROOT"',
        '.codex/hooks/pre_tool_bootstrap.sh': 'run_python_hook codex pre-tool-bootstrap "$ROOT"',
        '.qoder/hooks/cwd-changed.sh': 'run_python_hook qoder cwd-changed "$ROOT"',
        '.qoder/hooks/user-prompt-submit.sh': 'run_python_hook qoder user-prompt-submit "$ROOT"',
        '.qoder/hooks/pre_tool_bootstrap.sh': 'run_python_hook qoder pre-tool-bootstrap "$ROOT"',
    }
    for rel_path, delegation in event_wrappers.items():
        text = (REPO_ROOT / rel_path).read_text(encoding='utf-8')
        assert 'scripts/harness/hook-common.sh' in text, rel_path
        assert delegation in text, rel_path

    wrappers = {
        '.claude/hooks/stop.sh': 'run_stop_hook claude "$ROOT"',
        '.codex/hooks/stop_check.sh': 'run_stop_hook codex "$ROOT"',
        '.qoder/hooks/stop_check.sh': 'run_stop_hook qoder "$ROOT"',
    }

    for rel_path, delegation in wrappers.items():
        text = (REPO_ROOT / rel_path).read_text(encoding='utf-8')
        assert 'scripts/harness/hook-common.sh' in text, rel_path
        assert delegation in text, rel_path

    text = (REPO_ROOT / 'scripts/harness/hook-common.sh').read_text(encoding='utf-8')
    assert 'scripts.claude_hooks.main "$event"' in text
    assert 'scripts/harness/stop_entry.py" --agent "$client"' in text
    for forbidden in (
        'FEIPI_RUN_ID',
        'resolve_bound_run_record',
        'writerLease',
        'sessionctl',
        'git worktree',
        'mktemp',
    ):
        assert forbidden not in text


def test_agent_configs_do_not_define_per_agent_hooks():
    """per-agent 配置不得复制 hooks；项目级 hooks 是唯一执行面。"""
    for path in (REPO_ROOT / '.claude' / 'agents').glob('*.md'):
        text = path.read_text(encoding='utf-8')
        frontmatter = text.split('---', 2)[1]
        assert '\nhooks:' not in f'\n{frontmatter}'

    for path in (REPO_ROOT / '.codex' / 'agents').glob('*.toml'):
        text = path.read_text(encoding='utf-8')
        assert '[hooks]' not in text
        assert '\nhooks =' not in f'\n{text}'
