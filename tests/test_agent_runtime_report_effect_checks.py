from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

from scripts.checks import check_agent_runtime_report as checker

if TYPE_CHECKING:
    from pathlib import Path

PROTECTED_FILE = "harness/agent-runtime-report.schema.json"


def _base_report() -> dict:
    outcomes = []
    for oid in "ABCDEFGHIJKL":
        outcomes.append(
            {
                "id": oid,
                "name": f"Outcome {oid}",
                "required": True,
                "status": "PASS",
                "evidence_command": "synthetic",
                "evidence_file": "none",
                "notes": "synthetic unit-test evidence",
            }
        )
    return {
        "change_id": "unit-test-change",
        "created_at": "2026-07-10T00:00:00+08:00",
        "agent_platform": "qoder",
        "subagents": [],
        "changed_files": [PROTECTED_FILE],
        "expected_outcomes": outcomes,
        "effect_checks": [
            {
                "id": "schema-required-fields",
                "description": "schema requires runtime report proof fields",
                "command": "synthetic",
                "expected": "PASS",
                "actual": "PASS",
                "status": "PASS",
                "artifact": "none",
            }
        ],
        "gate_escape_rate": {
            "threshold": 0.0,
            "total_required_cases": 1,
            "escaped_required_cases": 0,
            "escape_rate": 0.0,
            "cases": [],
        },
        "concurrency_matrix": [
            {
                "id": "C1",
                "description": "synthetic isolation proof",
                "actors": ["qoder/session-a/main", "qoder/session-b/main"],
                "expected": "isolated evidence directories",
                "actual": "isolated",
                "status": "PASS",
            }
        ],
        "gates": [
            {
                "name": "unit-gate",
                "command": "synthetic",
                "status": "PASS",
                "skipped_count": 0,
                "evidence": "synthetic",
            }
        ],
        "skipped_count": 0,
        "blocked_items": [],
        "risks": [],
        "notes": [],
    }


def _run_checker(tmp_path: Path, monkeypatch, report: dict) -> int:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(checker, "find_report", lambda change_id: report_path)
    monkeypatch.setattr(checker, "get_protected_roots", lambda: ["harness/"])
    monkeypatch.setattr(checker, "get_diff_changed_files", lambda: [PROTECTED_FILE])
    monkeypatch.setattr(
        checker, "is_protected", lambda path, roots=None: path.startswith("harness/")
    )
    monkeypatch.setattr(
        sys, "argv", ["check_agent_runtime_report.py", "--change-id", "unit-test-change"]
    )
    return checker.main()


def test_report_checker_requires_expected_outcomes(tmp_path, monkeypatch):
    report = _base_report()
    report.pop("expected_outcomes")

    assert _run_checker(tmp_path, monkeypatch, report) == 1


def test_report_checker_fails_required_outcome_not_run(tmp_path, monkeypatch):
    report = _base_report()
    report["expected_outcomes"][0]["status"] = "NOT_RUN"

    assert _run_checker(tmp_path, monkeypatch, report) == 1


def test_report_checker_fails_effect_check_failure(tmp_path, monkeypatch):
    report = _base_report()
    report["effect_checks"][0]["status"] = "FAIL"
    report["effect_checks"][0]["actual"] = "FAIL"

    assert _run_checker(tmp_path, monkeypatch, report) == 1


def test_report_checker_fails_escape_rate_above_zero(tmp_path, monkeypatch):
    report = _base_report()
    report["gate_escape_rate"]["escaped_required_cases"] = 1
    report["gate_escape_rate"]["escape_rate"] = 0.1

    assert _run_checker(tmp_path, monkeypatch, report) == 1

    report = _base_report()
    report["gate_escape_rate"]["threshold"] = 0.1
    assert _run_checker(tmp_path, monkeypatch, report) == 1


def test_report_checker_accepts_full_pass_report(tmp_path, monkeypatch):
    assert _run_checker(tmp_path, monkeypatch, _base_report()) == 0
