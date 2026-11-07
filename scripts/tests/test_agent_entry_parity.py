from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_claude_project_memory_has_one_client_owned_entry():
    entry = ROOT / '.claude/CLAUDE.md'
    assert entry.is_file() and not entry.is_symlink()
    assert not (ROOT / 'CLAUDE.md').exists()
    text = entry.read_text(encoding='utf-8')
    assert '.claude/agents/qwen-main-default.md' in text
    assert 'harness/agent-policy.manifest.yaml' in text


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
