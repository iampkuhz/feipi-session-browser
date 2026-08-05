"""Gate report 的外部二态与内部三态 contract。"""

import json
from pathlib import Path

import pytest
from scripts.gates.report import (
    BLOCKED,
    FAIL,
    NOT_PASS,
    PASS,
    GateDetail,
    build_summary,
    compute_overall,
    concise_diagnostic,
    format_quality_report,
    write_quality_summary,
)


@pytest.mark.parametrize(
    ('statuses', 'expected'),
    [
        ({'a': PASS}, PASS),
        ({'a': BLOCKED}, NOT_PASS),
        ({'a': FAIL}, NOT_PASS),
        ({'a': 'SKIPPED'}, NOT_PASS),
        ({}, NOT_PASS),
    ],
)
def test_overall_is_only_pass_or_not_pass(statuses, expected) -> None:
    assert compute_overall(statuses)[0] == expected


@pytest.mark.contract_case('HOOK-HARNESS-007')
def test_summary_keeps_blocked_and_fail_details(tmp_path: Path) -> None:
    summary = build_summary(
        'incremental',
        'change',
        '2026-01-01T00:00:00Z',
        [GateDetail(name='rule', status=BLOCKED), GateDetail(name='runtime', status=FAIL)],
    )
    path = write_quality_summary(tmp_path, summary)
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['status'] == NOT_PASS
    assert payload['gateResults'] == {'rule': BLOCKED, 'runtime': FAIL}
    assert payload['gateDetails'][1]['reason'] == 'outcome-unknown'
    assert payload['schemaVersion'] == 4
    assert len(payload['reportHash']) == 12
    assert len(concise_diagnostic('ERROR first cause\n' + 'noise\n' * 100)) <= 1700


def test_fail_report_gives_environment_recovery_hint(tmp_path: Path) -> None:
    rendered = format_quality_report(
        {
            'status': NOT_PASS,
            'mode': 'incremental',
            'gateResults': {'audit': FAIL},
            'gateDetails': [
                {
                    'name': 'audit',
                    'status': FAIL,
                    'reason': 'runtime-missing',
                    'output': 'runtime missing',
                }
            ],
        },
        tmp_path / 'summary.json',
    )
    assert 'status=NOT_PASS' in rendered
    assert 'reason=runtime-missing' in rendered
    assert 'Restore the missing runtime' in rendered


def test_blocked_report_tells_owner_to_fix_repository(tmp_path: Path) -> None:
    rendered = format_quality_report(
        {
            'status': NOT_PASS,
            'mode': 'incremental',
            'gateResults': {'lint': BLOCKED},
            'gateDetails': [
                {
                    'name': 'lint',
                    'status': BLOCKED,
                    'command': ['ruff', 'check'],
                    'output': 'lint finding',
                }
            ],
        },
        tmp_path / 'summary.json',
    )
    assert 'Fix the repository issue' in rendered


def test_missing_summary_status_stays_external_not_pass(tmp_path: Path) -> None:
    rendered = format_quality_report(
        {'mode': 'incremental', 'gateResults': {}}, tmp_path / 'summary.json'
    )
    assert 'status=NOT_PASS' in rendered


@pytest.mark.contract_case('HOOK-HARNESS-007')
def test_pass_report_is_one_line(tmp_path: Path) -> None:
    summary = build_summary(
        'incremental',
        'change',
        '2026-01-01T00:00:00Z',
        [GateDetail(name='check', status=PASS)],
    )
    path = write_quality_summary(tmp_path, summary)
    assert '\n' not in format_quality_report(summary, path)
