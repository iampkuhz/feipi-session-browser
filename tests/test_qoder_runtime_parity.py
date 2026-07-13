from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_qoder_config_calls_only_shared_dispatcher() -> None:
    settings = json.loads((ROOT / '.qoder/settings.json').read_text(encoding='utf-8'))
    commands = [
        hook['command']
        for entries in settings['hooks'].values()
        for entry in entries
        for hook in entry['hooks']
    ]
    assert commands
    assert all('scripts/harness/hook_dispatch.py' in command for command in commands)
    assert all('--client qoder --event ' in command for command in commands)
    assert not list((ROOT / '.qoder/hooks').glob('*.sh'))


def test_qoder_manifest_uses_dispatcher_and_skill_entries() -> None:
    manifest = yaml.safe_load(
        (ROOT / 'harness/agent-runtime.manifest.yaml').read_text(encoding='utf-8')
    )
    qoder = manifest['platforms']['qoder']
    assert qoder['hook_dispatch']['entry'] == 'scripts/harness/hook_dispatch.py'
    assert qoder['agents_dir'] == '.qoder/agents'
    assert qoder['skills_dir'] == '.qoder/skills'
    for config in manifest['domain_agents'].values():
        path = ROOT / config['entries']['qoder']
        assert path.is_file()
        assert config['skill'] in path.read_text(encoding='utf-8')


def test_check_qoder_runtime_parity_passes() -> None:
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.checks', 'agent.qoder-parity'],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert '[agent.qoder-parity] PASS' in result.stdout
