"""工程 Qoder 退役护栏；不读取或清理 ignored 的客户端历史数据。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RETIRED_FILES = (
    'scripts/harness/qoder_task.py',
    'scripts/harness/qoder_task_lifecycle.py',
    'scripts/tests/harness/test_qoder_task.py',
    'scripts/tests/harness/test_qoder_task_lifecycle.py',
    'docs/development/qoder-subtasks.md',
    'openspec/specs/qoder-subtask-cli/spec.md',
)


def _manifest(name: str) -> dict:
    return yaml.safe_load((ROOT / 'harness' / name).read_text(encoding='utf-8'))


def test_retired_producers_and_contract_are_not_forwarding_wrappers() -> None:
    for relative in RETIRED_FILES:
        path = ROOT / relative
        assert not path.exists() and not path.is_symlink(), relative
    commands = _manifest('manifest.yaml')['public_executables']
    assert 'qoder_task' not in commands
    assert 'qoder' not in yaml.safe_dump(commands).lower()


def test_retired_engineering_platform_has_no_active_registration() -> None:
    runtime = _manifest('agent-runtime.manifest.yaml')
    assert set(runtime['platforms']) == {'claude', 'codex'}
    assert '.qoder' not in yaml.safe_dump(runtime).lower()
    for agent in runtime['domain_agents'].values():
        assert set(agent['entries']) == {'claude', 'codex'}
    registry = _manifest('skill-registry.yaml')
    assert '.qoder' not in yaml.safe_dump(registry).lower()
    # 产品来源说明仍包含 Qoder；平台退役不是产品来源退役。
    assert 'Qoder session data' in _manifest('manifest.yaml')['project']['description']


def test_qoder_local_tree_is_ignored_and_has_no_remaining_tracked_entries() -> None:
    result = subprocess.run(
        ['git', 'ls-files', '-z', '--', '.qoder'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    # 未暂存删除仍在 index 中；只检查 checkout 中仍存在的 tracked 入口。
    for relative in filter(None, result.stdout.split('\0')):
        path = ROOT / relative
        assert not path.exists() and not path.is_symlink(), relative
    ignored = subprocess.run(
        ['git', 'check-ignore', '--no-index', '--stdin'],
        input='.qoder/settings.local.json\n.qoder/agents/new-entry.md\n.qoder/task-packs/history.json\n',
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(ignored.stdout.splitlines()) == 3
    assert not any(
        line.startswith('!') and '.qoder' in line
        for line in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
    )


def test_native_contract_replaces_the_default_dispatch_policy() -> None:
    policy = _manifest('agent-policy.manifest.yaml')
    assert 'qoder_delegation' not in policy
    native = policy['native_delegation']
    text = yaml.safe_dump(native, allow_unicode=True)
    assert native['implementation'] == 'current-agent-native-subagents'
    assert native['model_routing'] == {
        'important_implementation': 'gpt-6.1-sol',
        'complex_analysis': 'gpt-6.1-sol',
        'independent_validation': 'gpt-6.1-sol',
        'lightweight_lookup': 'gpt-6-luna',
    }
    assert 'subagent_instance_protocol' in policy
    assert 'bypass_permissions' not in native
    permissions = '\n'.join(native['permissions'])
    assert '保持当前环境权限' in permissions
    assert '不继承 Qoder bypass_permissions' in permissions
    assert '不因失败升级权限' in permissions
    assert not any(token in text for token in ('qodercli', 'qoder_task.py'))
    for relative in ('AGENTS.md', '.codex/model-instructions.md'):
        current = (ROOT / relative).read_text(encoding='utf-8')
        assert 'qoder_delegation' not in current
        assert 'scripts/harness/qoder_task.py' not in current
