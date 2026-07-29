from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml
from scripts.checks.agent.check_agent_entry_parity import _check_agent_entries

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'harness' / 'agent-runtime.manifest.yaml'
EXPECTED_DOMAIN_AGENTS = {
    'java-backend-implementer',
    'session-ingestion-specialist',
    'ui-implementation-specialist',
    'mhtml-export-specialist',
    'quality-gate-diagnoser',
    'privacy-reviewer',
}


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
        [sys.executable, '-m', 'scripts.checks', 'agent.entry-parity'],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '[agent.entry-parity] PASS' in result.stdout
