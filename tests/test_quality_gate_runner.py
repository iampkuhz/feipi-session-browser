"""Tests for scripts/quality/run_quality_gate.py."""
import importlib.util
import json
import os
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "quality" / "run_quality_gate.py"
_spec = importlib.util.spec_from_file_location("run_quality_gate", SCRIPT_PATH)
_rqg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rqg)


class TestResolveChangeId:
    def test_explicit(self):
        assert _rqg.resolve_change_id("my-change") == "my-change"

    def test_env(self):
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            os.environ["ACTIVE_CHANGE_ID"] = "env-id"
            assert _rqg.resolve_change_id(None) == "env-id"
        finally:
            if old is not None:
                os.environ["ACTIVE_CHANGE_ID"] = old
            else:
                os.environ.pop("ACTIVE_CHANGE_ID", None)

    def test_fallback_unknown(self):
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            os.environ.pop("ACTIVE_CHANGE_ID", None)
            cid = _rqg.resolve_change_id(None)
            assert isinstance(cid, str)
            assert len(cid) > 0
        finally:
            if old is not None:
                os.environ["ACTIVE_CHANGE_ID"] = old


class TestAggregateStatus:
    def test_all_pass(self):
        results = [
            {"gate": "a", "status": "PASS", "summary": ""},
            {"gate": "b", "status": "PASS", "summary": ""},
        ]
        overall, blocking, warnings = _rqg.aggregate_status(results)
        assert overall == "PASS"
        assert blocking == []

    def test_single_fail(self):
        results = [
            {"gate": "a", "status": "PASS", "summary": ""},
            {"gate": "b", "status": "FAIL", "summary": "bad"},
        ]
        overall, blocking, _ = _rqg.aggregate_status(results)
        assert overall == "FAIL"
        assert len(blocking) == 1
        assert "b" in blocking[0]

    def test_blocked(self):
        results = [
            {"gate": "a", "status": "BLOCKED", "summary": "missing service"},
        ]
        overall, blocking, _ = _rqg.aggregate_status(results)
        assert overall == "FAIL"

    def test_skipped_goes_to_warnings(self):
        results = [
            {"gate": "a", "status": "SKIPPED", "summary": ""},
            {"gate": "b", "status": "PASS", "summary": ""},
        ]
        overall, blocking, warnings = _rqg.aggregate_status(results)
        assert overall == "PASS"
        assert len(warnings) == 1


class TestSummaryStructure:
    def test_schema_version(self):
        summary = _rqg.build_summary(
            target="session-detail",
            change_id="test",
            gate_results=[],
            overall="PASS",
            blocking=[],
            warnings=[],
            started_at="2026-01-01T00:00:00Z",
        )
        assert summary["schemaVersion"] == 1
        assert summary["target"] == "session-detail"
        assert summary["changeId"] == "test"
        assert summary["status"] == "PASS"
        assert "requiredGates" in summary
        assert "startedAt" in summary
        assert "finishedAt" in summary

    def test_blocking_in_summary(self):
        summary = _rqg.build_summary(
            target="session-detail",
            change_id="test",
            gate_results=[
                {"gate": "css", "status": "FAIL", "summary": "missing rule"},
            ],
            overall="FAIL",
            blocking=["css: missing rule"],
            warnings=[],
            started_at="2026-01-01T00:00:00Z",
        )
        assert summary["status"] == "FAIL"
        assert len(summary["blockingFailures"]) == 1


class TestRunGates:
    def test_summary_written(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            started = "2026-01-01T00:00:00Z"
            results = [
                {"gate": "staticCssContract", "status": "SKIPPED", "summary": "not yet"},
                {"gate": "pytest", "status": "PASS", "summary": "mocked"},
            ]
            overall, blocking, warnings = _rqg.aggregate_status(results)
            summary = _rqg.build_summary("session-detail", "test", results, overall, blocking, warnings, started)
            _rqg._write_summary_artifact(out, summary)
            summary_path = out / "quality-gate-summary.json"
            assert summary_path.exists()
            data = json.loads(summary_path.read_text())
            assert data["schemaVersion"] == 1
            assert data["target"] == "session-detail"

    def test_unknown_change_id(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            started = "2026-01-01T00:00:00Z"
            summary = _rqg.build_summary("session-detail", "unknown", [], "PASS", [], [], started)
            _rqg._write_summary_artifact(out, summary)
            assert summary["changeId"] == "unknown"
