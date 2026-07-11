import os
import subprocess
import sys
from pathlib import Path

from scripts.claude_hooks.classify import required_quality_targets
from scripts.quality.quality_targets import (
    applicable_gates_for_target,
    required_gates_for_target,
)
from scripts.quality.run_quality_gate import gate_command


REPO_ROOT = Path(__file__).resolve().parents[1]

NEW_GATE_SCRIPTS = [
    'scripts/quality/check_agent_runtime_isolation.py',
    'scripts/quality/check_gate_bypass_resistance.py',
    'scripts/quality/measure_gate_escape_rate.py',
    'scripts/quality/check_protected_roots_sync.py',
    'scripts/quality/check_qoder_runtime_parity.py',
    'scripts/quality/check_hook_payload_compat.py',
    'scripts/quality/check_subagent_handoff_protocol.py',
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
    for script in NEW_GATE_SCRIPTS:
        assert script in doctor


def test_manifest_required_gates_include_new_gates():
    manifest = _read('harness/agent-runtime.manifest.yaml')
    for script in NEW_GATE_SCRIPTS:
        assert f'- {script}' in manifest
        assert (REPO_ROOT / script).is_file()


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


def test_run_quality_gate_can_resolve_new_gate_commands():
    for gate, script in zip(NEW_GATE_IDS, NEW_GATE_SCRIPTS, strict=True):
        cmd = gate_command(gate, REPO_ROOT, 'harness')
        assert cmd
        assert script in cmd
    assert '--threshold' in gate_command('gateEscapeRate', REPO_ROOT, 'harness')
    assert '0' in gate_command('gateEscapeRate', REPO_ROOT, 'harness')


def test_required_runner_dry_run_includes_runtime_gates_for_agent_config_change():
    env = os.environ.copy()
    env['ACTIVE_CHANGE_ID'] = 'harden-agent-runtime-full-v3'
    proc = subprocess.run(
        [
            sys.executable,
            'scripts/quality/run_required_quality_gates.py',
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
        assert f'would run gate: {gate}' in output
