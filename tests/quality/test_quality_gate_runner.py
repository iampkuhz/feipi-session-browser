"""测试 scripts/quality/run_quality_gate.py 的质量门禁运行器。"""
import pytest
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.quality.quality_artifact import (
    GateDetail,
    QualitySummary,
    compute_overall,
    write_quality_summary,
    PASS,
    FAIL,
    BLOCKED,
)
from scripts.quality.run_quality_gate import build_summary
from scripts.quality.quality_targets import (
    applicable_gates_for_target,
    required_gates_for_target,
    validate_target,
)


class TestComputeOverall:
    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_all_pass(self):
        status, failures = compute_overall({"a": "PASS", "b": "PASS"})
        assert status == "PASS"
        assert failures == []

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_single_fail(self):
        status, failures = compute_overall({"a": "PASS", "b": "FAIL"})
        assert status == "FAIL"
        assert any("b" in f for f in failures)

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_blocked(self):
        status, failures = compute_overall({"a": "BLOCKED"})
        assert status == "FAIL"

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_skipped_is_failure(self):
        status, failures = compute_overall({"a": "SKIPPED"})
        assert status == "FAIL"
        assert any("SKIPPED" in f for f in failures)

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_empty_is_blocked(self):
        status, failures = compute_overall({})
        assert status == "BLOCKED"
        assert failures


class TestBuildSummary:
    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_schema_version_3(self):
        started = "2026-01-01T00:00:00Z"
        details = [
            GateDetail(name="pytest", status=PASS, command=["pytest", "-q"], exitCode=0),
        ]
        summary = build_summary("session-detail", "test", started, details)
        assert summary.schemaVersion == 3
        assert summary.target == "session-detail"
        assert summary.changeId == "test"
        assert summary.status == PASS
        assert "pytest" in summary.requiredGates

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_blocking_in_summary(self):
        started = "2026-01-01T00:00:00Z"
        details = [
            GateDetail(name="css", status=FAIL, command=["python3", "check.py"], exitCode=1, output="missing rule"),
        ]
        summary = build_summary("session-detail", "test", started, details)
        assert summary.status == FAIL
        assert len(summary.blockingFailures) >= 1


class TestWriteSummary:
    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_summary_written(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            started = "2026-01-01T00:00:00Z"
            details = [GateDetail(name="pytest", status=PASS)]
            summary = build_summary("session-detail", "test", started, details)
            write_quality_summary(out, summary)
            summary_path = out / "test" / "quality-gate-summary.session-detail.json"
            assert summary_path.exists()
            data = json.loads(summary_path.read_text())
            assert data["schemaVersion"] == 3
            assert data["target"] == "session-detail"


class TestQualityTargets:
    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_hook_runtime_gates(self):
        gates = required_gates_for_target("hook-runtime")
        assert "settingsJson" in gates
        assert "bashSyntax" in gates
        assert "pythonCompile" in gates

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_session_detail_gates(self):
        gates = required_gates_for_target("session-detail")
        assert "pytest" in gates
        assert "pythonCompile" in gates

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_validate_unknown_target(self):
        import pytest
        with pytest.raises(ValueError):
            validate_target("nonexistent")

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_acceptance_contract_gates(self):
        gates = required_gates_for_target("acceptance-contracts")
        assert "acceptanceContracts" in gates
        assert "pytest" in gates

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_hook_runtime_runs_acceptance_contract_gate_for_validator_changes(self):
        gates = applicable_gates_for_target(
            "hook-runtime",
            ["scripts/quality/validate_acceptance_contracts.py"],
        )
        assert "acceptanceContracts" in gates
