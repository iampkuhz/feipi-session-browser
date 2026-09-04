"""用最小合成路径证明高风险改动不会绕过 Gate planner。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.gates.planning import ChangeSnapshot, compile_gate_plan

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PATH_GATES = {
    '.claude/agents/qwen-main-default.md': 'maintenanceLanguagePolicy',
    'skills/authoring/feipi-java-feature-dev/SKILL.md': 'governanceLayoutValidation',
    'docs/acceptance-cases/features/HOOK_HARNESS.md': 'acceptanceTraceability',
    'scripts/gates/planning/plan_compiler.py': 'gateFrameworkTests',
    'java/web/src/main/java/com/feipi/session/browser/X.java': 'javaBuildVerification',
    'build.gradle.kts': 'javaBuildVerification',
    'java/web/src/main/resources/templates/session-detail.html': 'browserBehaviorTests',
    '.qoder/settings.json': 'agentConfigurationPolicy',
    'scripts/session-browser.sh': 'scanCommandSmoke',
    '.agents/experimental/new-policy.yaml': 'agentConfigurationPolicy',
}


def _env() -> dict[str, str]:
    """构造隔离且可审计的 Gate CLI 环境。"""

    env = os.environ.copy()
    env['ACTIVE_CHANGE_ID'] = 'reset-minimal-agent-harness'
    return env


def test_plan_selects_governance_gates_for_agent_config_change() -> None:
    result = subprocess.run(
        [
            sys.executable,
            'scripts/gates/cli.py',
            'plan',
            '--mode',
            'incremental',
            '--changed-files',
            '[".claude/agents/qwen-main-default.md"]',
            '--format',
            'json',
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=_env(),
        check=False,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert {'maintenanceLanguagePolicy', 'agentConfigurationPolicy'} <= {
        item['id'] for item in json.loads(combined)['gates']
    }


def test_high_risk_paths_select_their_required_gate() -> None:
    for path, expected in EXPECTED_PATH_GATES.items():
        snapshot = ChangeSnapshot('test', 'head', None, (path,), 'fingerprint')
        selected = {gate.name for gate in compile_gate_plan(snapshot).gates}
        assert expected in selected, (path, selected)
