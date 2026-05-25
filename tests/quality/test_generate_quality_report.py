"""Tests for scripts/quality/generate_quality_report.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "quality"))

from generate_quality_report import (
    format_duration,
    generate_report,
    status_badge,
)


class TestStatusBadge:
    def test_pass(self):
        assert status_badge("PASS") == "PASS"

    def test_fail(self):
        assert status_badge("FAIL") == "FAIL"

    def test_blocked(self):
        assert status_badge("BLOCKED") == "BLOCKED"

    def test_skipped(self):
        assert status_badge("SKIPPED") == "SKIPPED"

    def test_case_insensitive(self):
        assert status_badge("pass") == "PASS"

    def test_unknown(self):
        assert status_badge("UNKNOWN") == "UNKNOWN"


class TestFormatDuration:
    def test_none(self):
        assert format_duration(None) == "N/A"

    def test_milliseconds(self):
        assert format_duration(500) == "500ms"

    def test_seconds(self):
        assert format_duration(1500) == "1.5s"

    def test_exact_second(self):
        assert format_duration(1000) == "1.0s"

    def test_large_duration(self):
        assert format_duration(123456) == "123.5s"


class TestGenerateReport:
    def _sample(self, **overrides) -> dict:
        data = {
            "schemaVersion": 3,
            "status": "PASS",
            "target": "session-detail",
            "changeId": "test-change",
            "startedAt": "2026-01-01T00:00:00+00:00",
            "finishedAt": "2026-01-01T00:01:00+00:00",
            "requiredGates": {"pytest": "PASS"},
            "blockingFailures": [],
            "warnings": [],
            "artifacts": {},
            "gateDetails": [
                {
                    "name": "pytest",
                    "status": "PASS",
                    "command": ["pytest", "-q"],
                    "exitCode": 0,
                    "durationMs": 1500,
                    "output": "",
                }
            ],
        }
        data.update(overrides)
        return data

    def test_basic_report(self):
        report = generate_report(self._sample())
        assert "# Quality Report: session-detail" in report
        assert "**PASS**" in report
        assert "`test-change`" in report

    def test_failed_status(self):
        report = generate_report(self._sample(status="FAIL", blockingFailures=["pytest failed"]))
        assert "**FAIL**" in report
        assert "## 阻断失败" in report
        assert "pytest failed" in report

    def test_gate_table(self):
        report = generate_report(self._sample())
        assert "| Gate | 状态 | 耗时 | 退出码 |" in report
        assert "pytest" in report
        assert "1.5s" in report

    def test_failed_gate_details(self):
        sample = self._sample(
            status="FAIL",
            blockingFailures=["css failed"],
            gateDetails=[
                {
                    "name": "cssOwnership",
                    "status": "FAIL",
                    "command": ["python3", "check.py"],
                    "exitCode": 1,
                    "durationMs": 200,
                    "output": "BLOCK: violation found",
                }
            ],
        )
        report = generate_report(sample)
        assert "## 失败详情" in report
        assert "### cssOwnership (FAIL)" in report
        assert "BLOCK: violation found" in report

    def test_warnings_section(self):
        sample = self._sample(warnings=["legacy alias found"])
        report = generate_report(sample)
        assert "## 警告" in report
        assert "legacy alias found" in report

    def test_blocked_gate(self):
        sample = self._sample(
            gateDetails=[
                {"name": "browserLayout", "status": "BLOCKED", "command": [], "output": "playwright not installed"}
            ],
            blockingFailures=["browserLayout=BLOCKED"],
        )
        report = generate_report(sample)
        assert "BLOCKED" in report
        assert "browserLayout" in report

    def test_long_output_truncated(self):
        long_output = "x" * 5000
        sample = self._sample(
            status="FAIL",
            blockingFailures=["test failed"],
            gateDetails=[
                {
                    "name": "pytest",
                    "status": "FAIL",
                    "command": ["pytest"],
                    "exitCode": 1,
                    "output": long_output,
                }
            ],
        )
        report = generate_report(sample)
        assert "(truncated)" in report
        # Should not contain the full 5000 chars
        assert long_output not in report

    def test_no_gate_details(self):
        sample = self._sample(gateDetails=[])
        report = generate_report(sample)
        # Should not have gate table if no details
        assert "| Gate |" not in report
