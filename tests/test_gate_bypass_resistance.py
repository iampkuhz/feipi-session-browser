import json
import os
import subprocess
import sys

from scripts.checks.measure_gate_escape_rate import REQUIRED_CASE_IDS, build_report
from scripts.gates.planner import required_quality_targets


def _env():
    env = os.environ.copy()
    env['ACTIVE_CHANGE_ID'] = 'reset-minimal-agent-harness'
    return env


def test_dry_run_harness_target_for_agent_config_change():
    proc = subprocess.run(
        [
            sys.executable,
            'scripts/gates/cli.py',
            '--change-id',
            'reset-minimal-agent-harness',
            '--changed-files',
            '[".claude/agents/qwen-main-default.md"]',
            '--dry-run',
        ],
        text=True,
        capture_output=True,
        env=_env(),
        check=False,
    )

    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    payload = json.loads(combined)
    assert 'harness' in payload['effectiveTargets']


def test_measure_gate_escape_rate_stdout_and_json_contract(tmp_path):
    json_out = tmp_path / 'gate-escape-rate.json'
    proc = subprocess.run(
        [
            sys.executable,
            '-m',
            'scripts.checks',
            'repository.gate-escape-rate',
            '--threshold',
            '0',
            '--json-out',
            str(json_out),
        ],
        text=True,
        capture_output=True,
        env=_env(),
        check=False,
    )

    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert '[repository.gate-escape-rate] PASS' in proc.stdout

    report = json.loads(json_out.read_text(encoding='utf-8'))
    assert set(report) >= {'total_required_cases', 'escaped_required_cases', 'escape_rate', 'cases'}
    assert report['escaped_required_cases'] == 0
    assert report['escape_rate'] == 0.0
    assert report['total_required_cases'] >= 10
    case_ids = {case['id'] for case in report['cases']}
    assert REQUIRED_CASE_IDS <= case_ids
    for case in report['cases']:
        assert set(case) >= {
            'id',
            'description',
            'expected_gate',
            'observed',
            'escaped',
            'evidence',
        }
        assert case['observed'] in {'PASS', 'BLOCK', 'FAIL', 'TARGET_TRIGGERED', 'TARGET_MISSING'}
        assert case['escaped'] is False
        assert case['evidence']


def test_check_gate_bypass_resistance_reuses_measurement():
    proc = subprocess.run(
        [
            sys.executable,
            '-m',
            'scripts.checks',
            'repository.gate-bypass',
            '--threshold',
            '0',
        ],
        text=True,
        capture_output=True,
        env=_env(),
        check=False,
    )

    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert '[repository.gate-bypass] PASS' in proc.stdout


def test_required_case_coverage_and_zero_escape_rate():
    report = build_report()
    assert report['total_required_cases'] >= 10
    assert report['escaped_required_cases'] == 0
    assert report['escape_rate'] == 0.0
    assert REQUIRED_CASE_IDS <= {case['id'] for case in report['cases']}


def test_synthetic_target_selection_is_fail_closed_or_targeted():
    expectations = {
        '.claude/agents/qwen-main-default.md': 'harness',
        '.qoder/settings.json': 'harness',
        'harness/manifest.yaml': 'harness',
        'java/web/src/main/java/com/feipi/session/browser/X.java': 'java-src',
        'java/web/src/main/resources/templates/session-detail.html': 'session-detail',
    }
    for path, expected in expectations.items():
        targets = required_quality_targets([path])
        assert expected in targets, (path, targets)

    unknown_case = next(
        case for case in build_report()['cases'] if case['id'] == 'unknown-risky-path'
    )
    assert unknown_case['observed'] in {'BLOCK', 'TARGET_TRIGGERED'}
    assert unknown_case['escaped'] is False
