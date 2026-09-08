from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from scripts.gates.checks.agent import check_entrypoints as entrypoints
from scripts.gates.checks.agent.check_entrypoints import _check_agent_entries
from scripts.gates.checks.check_protocol import CheckStatus

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'harness' / 'agent-runtime.manifest.yaml'
EXPECTED_DOMAIN_AGENTS = {
    'java-backend-implementer',
    'session-ingestion-specialist',
    'ui-implementation-specialist',
    'mhtml-export-specialist',
    'quality-gate-diagnoser',
    'privacy-reviewer',
}


def test_claude_project_memory_has_one_client_owned_entry():
    entry = ROOT / '.claude/CLAUDE.md'
    assert entry.is_file() and not entry.is_symlink()
    assert not (ROOT / 'CLAUDE.md').exists()
    text = entry.read_text(encoding='utf-8')
    assert '.claude/agents/qwen-main-default.md' in text
    assert 'harness/agent-policy.manifest.yaml' in text


def _domain_agents() -> dict:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))
    return manifest['domain_agents']


def test_manifest_is_the_domain_agent_skill_mapping_authority():
    agents = _domain_agents()
    assert set(agents) == EXPECTED_DOMAIN_AGENTS
    for name, config in agents.items():
        skill = config['skill']
        assert (ROOT / skill).is_file(), (name, skill)
        assert set(config['entries']) == {'claude', 'codex', 'qoder'}
        for platform, relative in config['entries'].items():
            text = (ROOT / relative).read_text(encoding='utf-8')
            assert skill in text, (name, platform)


def test_domain_agent_entries_are_thin_on_all_platforms():
    assert _check_agent_entries() == []


def test_shared_agent_entry_parity_check_passes():
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.gates.checks', 'agent.entrypoints'],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'GATE_RESULT status=PASS check=agent.entrypoints' in result.stdout


@pytest.mark.parametrize(
    'text',
    [
        '# synthetic-agent\n',
        '---\nname: [broken\n---\nbody\n',
        '---\n- list\n---\nbody\n',
        '---\nname: wrong-name\ndescription: valid\n---\nbody\n',
        '---\nname: synthetic-agent\ndescription: " "\n---\nbody\n',
        '---\nname: synthetic-agent\ndescription: 42\n---\nbody\n',
        '---\nname: synthetic-agent\ndescription: valid\nmodel: pinned\n---\nbody\n',
        '---\nname: synthetic-agent\ndescription: valid\n',
    ],
)
def test_invalid_unregistered_qoder_agent_is_blocked(text, monkeypatch):
    """未登记在领域 manifest 的坏入口也必须阻断，避免静态检查自洽但不可加载。"""
    current = entrypoints._load_runtime_inputs(ROOT)
    entries = {**current.entries, '.qoder/agents/synthetic-agent.md': text}
    monkeypatch.setattr(
        entrypoints, '_load_runtime_inputs', lambda _root: replace(current, entries=entries)
    )
    result = entrypoints.check([])
    assert result.status is CheckStatus.BLOCKED
    assert any('synthetic-agent.md' in diagnostic.message for diagnostic in result.diagnostics)


@pytest.mark.parametrize('settings', [[], {}, {'agent': 'missing'}, {'agent': ['invalid']}])
def test_invalid_qoder_default_is_blocked(settings, monkeypatch):
    """默认 agent 必须指向真实项目入口，列表或缺失引用不能被视为有效名称。"""
    current = entrypoints._load_runtime_inputs(ROOT)
    monkeypatch.setattr(
        entrypoints,
        '_load_runtime_inputs',
        lambda _root: replace(current, qoder_settings=settings),
    )
    assert entrypoints.check([]).status is CheckStatus.BLOCKED


def test_valid_qoder_metadata_keeps_body_thin():
    """真实 metadata 不占领域正文配额，七个项目入口都进入一次性输入快照。"""
    current = entrypoints._load_runtime_inputs(ROOT)
    expected = {str(path.relative_to(ROOT)) for path in (ROOT / '.qoder/agents').glob('*.md')}
    assert len(expected) == 7
    assert expected.issubset(current.entries)
    assert entrypoints._check_qoder_configuration(current) == []
    assert entrypoints._check_agent_entries(current) == []


def test_unregistered_valid_qoder_default_is_supported(monkeypatch):
    """默认入口无需伪装为领域 specialist，合法的新增项目入口同样能被检查。"""
    current = entrypoints._load_runtime_inputs(ROOT)
    entries = {
        **current.entries,
        '.qoder/agents/synthetic-agent.md': (
            '---\nname: synthetic-agent\ndescription: synthetic only\n---\nbody\n'
        ),
    }
    monkeypatch.setattr(
        entrypoints,
        '_load_runtime_inputs',
        lambda _root: replace(
            current, entries=entries, qoder_settings={'agent': 'synthetic-agent'}
        ),
    )
    assert entrypoints.check([]).status is CheckStatus.PASS
