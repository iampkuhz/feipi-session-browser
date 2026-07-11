import json
from pathlib import Path

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


def test_claude_project_hook_matrix_is_complete():
    """Claude 配置必须覆盖完整项目级 hook 生命周期，而不只覆盖 Stop。"""
    commands = _commands_for_event(REPO_ROOT / '.claude' / 'settings.json')

    assert commands == {
        ('SessionStart', ''): ['.claude/hooks/session-start.sh'],
        ('SubagentStart', ''): ['.claude/hooks/subagent-start.sh'],
        ('PreToolUse', 'Bash'): ['.claude/hooks/pre-bash.sh'],
        ('PreToolUse', 'Write|Edit|MultiEdit|NotebookEdit'): ['.claude/hooks/pre-write.sh'],
        ('PostToolUse', 'Bash'): ['.claude/hooks/post-bash.sh'],
        ('PostToolUse', 'Write|Edit|MultiEdit|NotebookEdit'): ['.claude/hooks/post-write.sh'],
        ('PostToolUseFailure', ''): ['.claude/hooks/tool-failure.sh'],
        ('Stop', ''): ['.claude/hooks/stop.sh'],
        ('SubagentStop', ''): ['.claude/hooks/subagent-stop.sh'],
        ('ConfigChange', ''): ['.claude/hooks/config-change.sh'],
    }


def test_codex_project_hook_matrix_is_complete():
    """Codex repo 配置必须覆盖 Bash pre、write pre/post 和 Stop。"""
    commands = _commands_for_event(REPO_ROOT / '.codex' / 'hooks.json')

    expected = {
        ('SessionStart', ''): '.codex/hooks/session-start.sh',
        ('PreToolUse', 'Bash'): '.codex/hooks/pre_tool_guard.sh',
        ('PreToolUse', 'Write|Edit|MultiEdit|NotebookEdit'): '.codex/hooks/pre_write_guard.sh',
        ('PostToolUse', 'Bash'): '.codex/hooks/post_bash_guard.sh',
        ('PostToolUse', 'Write|Edit|MultiEdit|NotebookEdit'): '.codex/hooks/post_tool_guard.sh',
        ('PostToolUseFailure', ''): '.codex/hooks/tool_failure.sh',
        ('Stop', ''): '.codex/hooks/stop_check.sh',
        ('StopFailure', ''): '.codex/hooks/stop_failure.sh',
        ('SessionEnd', ''): '.codex/hooks/session_end.sh',
    }
    assert set(commands) == set(expected)
    for key, rel_path in expected.items():
        assert len(commands[key]) == 1
        command = commands[key][0]
        assert 'git rev-parse --show-toplevel' in command
        assert rel_path in command
        assert '/feipi-session-browser' not in command

    stop_hook = json.loads((REPO_ROOT / '.codex' / 'hooks.json').read_text(encoding='utf-8'))['hooks']['Stop'][0]['hooks'][0]
    assert stop_hook['timeout'] >= 1230


def test_qoder_project_hook_matrix_is_complete():
    """Qoder 项目配置必须真实绑定共享 wrapper，而不是只检查文件存在。"""
    commands = _commands_for_event(REPO_ROOT / '.qoder' / 'settings.json')

    expected = {
        ('SessionStart', ''): '.qoder/hooks/session-start.sh',
        ('PreToolUse', 'Bash'): '.qoder/hooks/pre_tool_guard.sh',
        ('PreToolUse', 'Write|Edit|MultiEdit|NotebookEdit'): '.qoder/hooks/pre_write_guard.sh',
        ('PostToolUse', 'Bash'): '.qoder/hooks/post_bash_guard.sh',
        ('PostToolUse', 'Write|Edit|MultiEdit|NotebookEdit'): '.qoder/hooks/post_tool_guard.sh',
        ('PostToolUseFailure', ''): '.qoder/hooks/tool_failure.sh',
        ('Stop', ''): '.qoder/hooks/stop_check.sh',
        ('StopFailure', ''): '.qoder/hooks/stop_failure.sh',
        ('SessionEnd', ''): '.qoder/hooks/session_end.sh',
    }
    assert set(commands) == set(expected)
    for key, rel_path in expected.items():
        assert len(commands[key]) == 1
        command = commands[key][0]
        assert 'git rev-parse --show-toplevel' in command
        assert rel_path in command
        assert '/feipi-session-browser' not in command

    stop_hook = json.loads((REPO_ROOT / '.qoder' / 'settings.json').read_text(encoding='utf-8'))['hooks']['Stop'][0]['hooks'][0]
    assert stop_hook['timeout'] >= 1230


def test_qoder_hook_wrappers_delegate_to_shared_entrypoints():
    """Qoder wrapper 只设置 client 标识并 exec 共享 Python 入口。"""
    qoder_hooks = REPO_ROOT / '.qoder' / 'hooks'
    for name, event in {
        'pre_tool_guard.sh': 'pre-bash',
        'pre_write_guard.sh': 'pre-write',
        'post_bash_guard.sh': 'post-bash',
        'post_tool_guard.sh': 'post-write',
        'tool_failure.sh': 'tool-failure',
        'stop_failure.sh': 'stop-failure',
        'session_end.sh': 'session-end',
    }.items():
        text = (qoder_hooks / name).read_text(encoding='utf-8')
        assert 'FEIPI_AGENT_CLIENT="qoder"' in text
        assert f'scripts.claude_hooks.main {event}' in text
        assert 'exec python3' in text

    stop = (qoder_hooks / 'stop_check.sh').read_text(encoding='utf-8')
    assert 'scripts/harness/stop_entry.py' in stop
    assert '--agent qoder' in stop


def test_all_stop_wrappers_use_shared_agent_stop_check():
    """三类 agent 的 Stop wrapper 都必须委托 shared harness stop runner。"""
    wrappers = {
        '.claude/hooks/stop.sh': '--agent claude',
        '.codex/hooks/stop_check.sh': '--agent codex',
        '.qoder/hooks/stop_check.sh': '--agent qoder',
    }

    for rel_path, agent_arg in wrappers.items():
        text = (REPO_ROOT / rel_path).read_text(encoding='utf-8')
        assert (
            'scripts/harness/agent_stop_check.py' in text
            or 'scripts/harness/stop_entry.py' in text
        ), rel_path
        assert agent_arg in text, rel_path


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
