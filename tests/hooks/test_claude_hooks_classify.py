import json
from pathlib import Path

import pytest
from scripts.claude_hooks.classify import classify_file, required_quality_targets


@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_hook_classification():
    c = classify_file('.claude/hooks/claude-hook.sh')
    assert c.category == 'hook'
    assert c.quality_target == 'hook-runtime'


@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_cross_agent_hook_classification():
    assert classify_file('.codex/hooks/stop_check.sh').quality_target == 'hook-runtime'
    assert classify_file('.qoder/hooks/stop_check.sh').quality_target == 'hook-runtime'
    assert classify_file('scripts/session-browser.sh').category == 'repo-script'
    assert classify_file('scripts/session-browser.sh').quality_target == 'hook-runtime'
    assert classify_file('.codex/hooks.json').quality_target == 'hook-runtime'
    assert classify_file('.codex/config.toml').quality_target == 'hook-runtime'
    assert (
        classify_file('skills/authoring/feipi-openspec-orchestrate-change/SKILL.md').quality_target
        == 'hook-runtime'
    )
    assert (
        classify_file('.agents/skills/feipi-openspec-orchestrate-change/SKILL.md').quality_target
        == 'hook-runtime'
    )
    assert (
        classify_file('.codex/skills/feipi-openspec-orchestrate-change/SKILL.md').quality_target
        == 'hook-runtime'
    )
    assert (
        classify_file('.claude/skills/feipi-openspec-orchestrate-change/SKILL.md').quality_target
        == 'hook-runtime'
    )
    assert classify_file('AGENTS.md').quality_target == 'hook-runtime'
    assert classify_file('CLAUDE.md').quality_target == 'hook-runtime'
    assert classify_file('config/api-snapshots/java-public-api.txt').quality_target == 'java-build'
    assert (
        classify_file('java/web/src/main/resources/static/css/session-detail.css').quality_target
        == 'session-detail'
    )
    assert (
        classify_file('java/web/src/main/resources/static/js/session-detail/init.js').quality_target
        == 'session-detail'
    )


@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_codex_hooks_json_uses_current_repo_relative_commands():
    hooks = json.loads(Path('.codex/hooks.json').read_text(encoding='utf-8'))
    commands = [
        hook['command']
        for entries in hooks['hooks'].values()
        for entry in entries
        for hook in entry['hooks']
    ]

    assert commands == [
        '.codex/hooks/pre_tool_guard.sh',
        '.codex/hooks/post_bash_guard.sh',
        '.codex/hooks/post_tool_guard.sh',
        '.codex/hooks/stop_check.sh',
    ]
    assert all('/feipi-session-browser/' not in command for command in commands)


@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_qoder_cross_agent_hook_entrypoints_exist():
    """Qoder 入口必须覆盖 pre/post/stop，避免只在 Stop 阶段才发现已清空工作树。"""
    for path in [
        Path('.qoder/hooks/pre_tool_guard.sh'),
        Path('.qoder/hooks/post_bash_guard.sh'),
        Path('.qoder/hooks/post_tool_guard.sh'),
        Path('.qoder/hooks/stop_check.sh'),
    ]:
        assert path.exists(), f'missing hook entrypoint: {path}'


@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_python_tooling_config_classification():
    assert classify_file('pyproject.toml').category == 'python-tooling-config'
    assert classify_file('requirements-dev.txt').quality_target == 'hook-runtime'
    assert classify_file('requirements-dev.lock').quality_target == 'hook-runtime'
    assert classify_file('uv.lock').quality_target == 'hook-runtime'
    assert classify_file('.pre-commit-config.yaml').quality_target == 'hook-runtime'
    assert classify_file('.github/workflows/quality.yml').quality_target == 'hook-runtime'


@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_acceptance_contract_classification():
    doc = classify_file('docs/acceptance-contracts/features/DATA_PRESENTERS.md')
    test = classify_file('tests/backend/test_round_signals.py')
    assert doc.category == 'acceptance-contract'
    assert doc.requires_quality_gate
    assert doc.quality_target == 'acceptance-contracts'
    assert test.category == 'test'
    assert test.requires_quality_gate
    assert test.quality_target == 'acceptance-contracts'


@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_targets_deduped():
    assert required_quality_targets(
        ['java/core/src/main/java/Foo.java', 'java/core/src/main/java/Bar.java']
    ) == ['java-src']


@pytest.mark.contract_case('HOOK-HARNESS-002')
def test_acceptance_contract_target_required():
    targets = required_quality_targets(
        [
            'docs/acceptance-contracts/features/DATA_PRESENTERS.md',
            'tests/backend/test_round_signals.py',
        ]
    )
    assert targets == ['acceptance-contracts']
