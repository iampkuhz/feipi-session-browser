import os
import subprocess
import sys
from pathlib import Path

from scripts.gates.executor import gate_command
from scripts.gates.planner import (
    applicable_gates_for_target,
    required_gates_for_target,
    required_quality_targets,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

NEW_SHARED_CHECKS = [
    'agent.runtime-isolation',
    'repository.gate-bypass',
    'repository.gate-escape-rate',
    'agent.protected-roots',
    'agent.qoder-parity',
    'agent.hook-payload',
    'agent.subagent-handoff',
]
RUNTIME_REQUIRED_SHARED_CHECKS = [
    check_id for check_id in NEW_SHARED_CHECKS if check_id != 'repository.gate-escape-rate'
]

NEW_GATE_IDS = [
    'agentRuntimeIsolation',
    'gateBypassResistance',
    'gateEscapeRate',
    'protectedRootsSync',
    'qoderRuntimeParity',
    'hookPayloadCompat',
    'subagentHandoffProtocol',
]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding='utf-8')


def test_doctor_mentions_new_agent_runtime_gates():
    doctor = _read('scripts/harness/doctor.sh')
    for check_id in RUNTIME_REQUIRED_SHARED_CHECKS:
        assert check_id in doctor
    assert 'scripts/checks/check_' not in doctor


def test_manifest_required_gates_include_new_gates():
    manifest = _read('harness/agent-runtime.manifest.yaml')
    for check_id in RUNTIME_REQUIRED_SHARED_CHECKS:
        assert f'- {check_id}' in manifest


def test_quality_targets_route_agent_config_to_runtime_gates():
    changed_files = ['.qoder/AGENTS.md', 'scripts/harness/stop_entry.py']
    targets = required_quality_targets(changed_files)
    assert 'hook-runtime' in targets
    assert 'harness' in targets

    hook_gates = set(required_gates_for_target('hook-runtime'))
    harness_gates = set(required_gates_for_target('harness'))
    hook_applicable = set(applicable_gates_for_target('hook-runtime', changed_files))
    harness_applicable = set(applicable_gates_for_target('harness', changed_files))
    for gate in NEW_GATE_IDS:
        assert gate in hook_gates
        assert gate in harness_gates
        assert gate in hook_applicable
        assert gate in harness_applicable


def test_gate_service_can_resolve_new_gate_commands():
    for gate, check_id in zip(NEW_GATE_IDS, NEW_SHARED_CHECKS, strict=True):
        cmd = gate_command(gate, REPO_ROOT, 'harness')
        assert cmd
        assert cmd[1:3] == ['-m', 'scripts.checks']
        assert check_id in cmd
    assert '--threshold' in gate_command('gateEscapeRate', REPO_ROOT, 'harness')
    assert '0' in gate_command('gateEscapeRate', REPO_ROOT, 'harness')


def test_required_runner_dry_run_includes_runtime_gates_for_agent_config_change():
    env = os.environ.copy()
    env['ACTIVE_CHANGE_ID'] = 'harden-agent-runtime-full-v3'
    proc = subprocess.run(
        [
            sys.executable,
            'scripts/gates/cli.py',
            '--tier',
            'quick',
            '--dry-run',
            '--changed-files',
            '[".qoder/AGENTS.md","scripts/harness/stop_entry.py"]',
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    output = proc.stdout or ''
    assert proc.returncode == 0, output
    for gate in NEW_GATE_IDS:
        assert f'"gate": "{gate}"' in output
