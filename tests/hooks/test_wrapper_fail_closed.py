from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(path: str, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop('FEIPI_RUN_ID', None)
    env.pop('FEIPI_SESSION_ID', None)
    env['PYTHONPATH'] = str(ROOT)
    return subprocess.run(
        ['bash', path],
        cwd=ROOT,
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


def test_claude_wrapper_preserves_block_exit_2():
    proc = _run('.claude/hooks/pre-write.sh', {'tool_name': 'Write', 'tool_input': {}})
    assert proc.returncode == 2
    assert 'BLOCK' in proc.stderr


def test_codex_wrapper_preserves_block_exit_2():
    proc = _run('.codex/hooks/pre_write_guard.sh', {'client': 'codex', 'toolName': 'Write', 'toolInput': {}})
    assert proc.returncode == 2
    assert 'BLOCK' in proc.stderr


def test_qoder_wrapper_preserves_block_exit_2():
    proc = _run('.qoder/hooks/pre_write_guard.sh', {'client': 'qoder', 'toolName': 'Write', 'toolInput': {}})
    assert proc.returncode == 2
    assert 'BLOCK' in proc.stderr
