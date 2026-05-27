"""Snapshot tests for parser output against fixture corpus.

Each fixture JSONL in ``tests/fixtures/sources/`` has a corresponding
``.expected.json`` that captures the canonical parser output.  These
tests verify that ``parse_jsonl_events`` produces events and diagnostics
matching the stored snapshots.

Coverage:
- All 6 fixture files: claude_valid, codex_valid, qoder_valid,
  multiline_json, empty, mixed_with_bad
- Event list equality (content + order)
- Diagnostic counters: total_lines, non_empty_lines, events_parsed, events_skipped
- Diagnostic issues: issue type, severity, line_no, detail, preview
"""

from __future__ import annotations

import pytest
import json
from pathlib import Path

from session_browser.sources.jsonl_reader import (
    ParseIssue,
    ParseSeverity,
    parse_jsonl_events,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sources"

# Discover all fixture pairs automatically.
FIXTURE_PAIRS = sorted(
    p.stem for p in FIXTURES_DIR.glob("*.jsonl")
)


def _serialize_issue(issue_item) -> dict:
    """Convert a ParseIssueItem to the serialised dict shape used in expected files."""
    return {
        "issue": issue_item.issue.value,
        "severity": issue_item.severity.name,
        "line_no": issue_item.line_no,
        "detail": issue_item.detail,
        "preview": issue_item.preview,
    }


def _serialize_diagnostics(diag) -> dict:
    """Convert JsonlDiagnostics to the serialised dict shape used in expected files."""
    return {
        "total_lines": diag.total_lines,
        "non_empty_lines": diag.non_empty_lines,
        "events_parsed": diag.events_parsed,
        "events_skipped": diag.events_skipped,
        "issues": [_serialize_issue(i) for i in diag.issues],
    }


def _build_actual(jsonl_path: Path) -> dict:
    """Run the parser on a fixture and return the serialised result."""
    events, diagnostics = parse_jsonl_events(jsonl_path)
    return {
        "source_file": jsonl_path.name,
        "events": events,
        "diagnostics": _serialize_diagnostics(diagnostics),
    }


def _load_expected(name: str) -> dict:
    """Load the expected snapshot for a fixture."""
    expected_path = FIXTURES_DIR / f"{name}.expected.json"
    with open(expected_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("fixture_name", FIXTURE_PAIRS)
class TestParserSnapshots:
    """Snapshot-based tests comparing parser output to expected fixtures."""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_events_match(self, fixture_name: str):
        """Parsed events must exactly match the expected snapshot."""
        jsonl_path = FIXTURES_DIR / f"{fixture_name}.jsonl"
        actual = _build_actual(jsonl_path)
        expected = _load_expected(fixture_name)

        assert actual["events"] == expected["events"], (
            f"Events mismatch for {fixture_name}:\n"
            f"  actual count:   {len(actual['events'])}\n"
            f"  expected count: {len(expected['events'])}"
        )

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_diagnostics_counters_match(self, fixture_name: str):
        """Diagnostic counters must match the expected snapshot."""
        jsonl_path = FIXTURES_DIR / f"{fixture_name}.jsonl"
        actual = _build_actual(jsonl_path)
        expected = _load_expected(fixture_name)

        actual_diag = actual["diagnostics"]
        expected_diag = expected["diagnostics"]

        counter_keys = [
            "total_lines", "non_empty_lines",
            "events_parsed", "events_skipped",
        ]
        for key in counter_keys:
            assert actual_diag[key] == expected_diag[key], (
                f"Counter '{key}' mismatch for {fixture_name}: "
                f"actual={actual_diag[key]}, expected={expected_diag[key]}"
            )

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_diagnostics_issues_match(self, fixture_name: str):
        """Diagnostic issues list must match the expected snapshot."""
        jsonl_path = FIXTURES_DIR / f"{fixture_name}.jsonl"
        actual = _build_actual(jsonl_path)
        expected = _load_expected(fixture_name)

        actual_issues = actual["diagnostics"]["issues"]
        expected_issues = expected["diagnostics"]["issues"]

        assert len(actual_issues) == len(expected_issues), (
            f"Issue count mismatch for {fixture_name}: "
            f"actual={len(actual_issues)}, expected={len(expected_issues)}"
        )

        for idx, (act, exp) in enumerate(zip(actual_issues, expected_issues)):
            assert act == exp, (
                f"Issue #{idx} mismatch for {fixture_name}:\n"
                f"  actual:   {act}\n"
                f"  expected: {exp}"
            )
