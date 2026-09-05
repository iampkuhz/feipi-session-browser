from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml
from scripts.gates.checks.agent.check_entrypoints import _check_agent_entries

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
