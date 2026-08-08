"""用最小合成路径证明高风险改动不会绕过 Gate planner。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.gates.planner import plan

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PATH_GATES = {
    '.claude/agents/qwen-main-default.md': 'languagePolicy',
    'skills/authoring/feipi-java-feature-dev/SKILL.md': 'governanceStructure',
    'docs/acceptance-cases/features/HOOK_HARNESS.md': 'acceptanceCaseMapping',
    'scripts/gates/planner.py': 'pythonHarnessTests',
    'java/web/src/main/java/com/feipi/session/browser/X.java': 'javaCheck',
    'build.gradle.kts': 'javaCheck',
    'java/web/src/main/resources/templates/session-detail.html': 'browserInteraction',
    '.qoder/settings.json': 'agentPolicy',
    'scripts/session-browser.sh': 'scanScriptSmoke',
    '.agents/experimental/new-policy.yaml': 'agentPolicy',
}


def _env() -> dict[str, str]:
    """构造隔离且可审计的 Gate CLI 环境。"""

    env = os.environ.copy()
    env['ACTIVE_CHANGE_ID'] = 'reset-minimal-agent-harness'
    return env


def test_dry_run_selects_harness_gates_for_agent_config_change() -> None:
    result = subprocess.run(
        [
            sys.executable,
            'scripts/gates/cli.py',
            '--change-id',
            'reset-minimal-agent-harness',
            '--changed-files',
            '[".claude/agents/qwen-main-default.md"]',
            '--dry-run',
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=_env(),
        check=False,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert {'languagePolicy', 'agentPolicy'} <= set(json.loads(combined)['gates'])


def test_high_risk_paths_select_their_required_gate() -> None:
    for path, expected in EXPECTED_PATH_GATES.items():
        selected = {gate.name for gate in plan([path]).gates}
        assert expected in selected, (path, selected)
