"""Gate 结构化 report 的有界、fail-closed contract。"""

import json
from pathlib import Path

import pytest
from scripts.gates.report import (
    BLOCKED,
    FAIL,
    PASS,
    GateDetail,
    build_summary,
    compute_overall,
    concise_diagnostic,
    format_quality_report,
    is_artifact_fresh,
    write_quality_summary,
)


@pytest.mark.parametrize(
    ('statuses', 'expected'),
    (
        ({'a': PASS, 'b': PASS}, PASS),
        ({'a': 'SKIPPED'}, FAIL),
        ({'a': BLOCKED}, FAIL),
        ({}, BLOCKED),
    ),
)
def test_required_gate_status_is_fail_closed(statuses: dict[str, str], expected: str) -> None:
    assert compute_overall(statuses)[0] == expected


@pytest.mark.contract_case('HOOK-HARNESS-007')
def test_report_contract_is_bounded_and_actionable(tmp_path: Path) -> None:
    summary = build_summary(
        'harness',
        'change',
        '2026-01-01T00:00:00Z',
        [
            GateDetail(
                name='check',
                status=FAIL,
                command=['python3', 'check.py'],
                exitCode=1,
                output='ERROR scripts/example.py:42 failed\n' + 'noise\n' * 100,
            )
        ],
    )
    path = write_quality_summary(tmp_path, summary)
    rendered = format_quality_report(summary, path)
    payload = json.loads(path.read_text())

    assert 'QUALITY_GATE_RESULT status=FAIL target=harness' in rendered
    assert 'gate=check status=FAIL' in rendered
    assert 'scripts/example.py:42' in rendered
    assert 'fix_hint=' in rendered
    assert payload['schemaVersion'] == 4
    assert payload['reportHash']
    assert 'criticalPathMs' not in payload
    assert 'queueWaitMs' not in payload['gateDetails'][0]
    assert 'resourceWaitMs' not in payload['gateDetails'][0]
    assert len(concise_diagnostic('x\n' * 100)) < 1800
    assert is_artifact_fresh(str(path))


@pytest.mark.contract_case('HOOK-HARNESS-007')
def test_pass_report_is_concise(tmp_path: Path) -> None:
    summary = build_summary(
        'harness',
        'change',
        '2026-01-01T00:00:00Z',
        [GateDetail(name='check', status=PASS)],
    )
    path = write_quality_summary(tmp_path, summary)
    rendered = format_quality_report(summary, path)
    details_path = path.parent / 'gate-details.harness.json'

    assert rendered.startswith('QUALITY_GATE_RESULT status=PASS target=harness passed=1/1')
    assert '\n' not in rendered
    assert path.name == 'quality-gate-summary.harness.json'
    assert details_path.exists()


@pytest.mark.contract_case('HOOK-HARNESS-007')
def test_blocked_report_keeps_first_cause(tmp_path: Path) -> None:
    rendered = format_quality_report(
        {
            'status': BLOCKED,
            'target': 'session-detail',
            'requiredGates': {'browserLayout': BLOCKED},
            'blockingFailures': ['browserLayout=BLOCKED'],
            'gateDetails': [
                {
                    'name': 'browserLayout',
                    'status': BLOCKED,
                    'output': 'BASE_URL is missing',
                }
            ],
        },
        tmp_path / 'summary.json',
    )
    assert 'gate=browserLayout status=BLOCKED' in rendered
    assert 'BASE_URL is missing' in rendered
    assert 'Provide the missing command' in rendered
