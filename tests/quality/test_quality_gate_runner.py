"""测试 scripts/quality/run_quality_gate.py 的质量门禁运行器。"""
import pytest
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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
from scripts.quality import run_quality_gate
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
        assert "noTestSkips" in gates

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_session_detail_gates(self):
        gates = required_gates_for_target("session-detail")
        assert "pytest" in gates
        assert "pythonCompile" in gates
        assert "noTestSkips" in gates

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_validate_unknown_target(self):
        import pytest
        with pytest.raises(ValueError):
            validate_target("nonexistent")

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_acceptance_contract_gates(self):
        gates = required_gates_for_target("acceptance-contracts")
        assert "noTestSkips" in gates
        assert "acceptanceContracts" in gates
        assert "pytest" in gates

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_hook_runtime_runs_acceptance_contract_gate_for_validator_changes(self):
        gates = applicable_gates_for_target(
            "hook-runtime",
            ["scripts/quality/validate_acceptance_contracts.py"],
        )
        assert "acceptanceContracts" in gates

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_acceptance_contracts_runs_no_skip_gate_for_test_changes(self):
        gates = applicable_gates_for_target(
            "acceptance-contracts",
            ["tests/playwright/session-detail.spec.js"],
        )
        assert "noTestSkips" in gates

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_hook_runtime_runs_no_skip_gate_for_gate_changes(self):
        gates = applicable_gates_for_target(
            "hook-runtime",
            ["scripts/quality/check_no_test_skips.py"],
        )
        assert "noTestSkips" in gates


class TestQualityGateRuntime:
    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_pytest_gate_uses_project_python_module(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            run_quality_gate,
            "_project_python",
            lambda repo_root, *, dev=False: "/tmp/dev-python" if dev else "/tmp/runtime-python",
        )
        tests_dir = tmp_path / "tests" / "ui"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_web_template_contract.py").write_text("", encoding="utf-8")
        cmd = run_quality_gate.gate_command("pytest", tmp_path, "session-detail")
        assert cmd[:4] == ["/tmp/dev-python", "-m", "pytest", "-q"]

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_no_test_skips_gate_command(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            run_quality_gate,
            "_project_python",
            lambda repo_root, *, dev=False: "/tmp/runtime-python",
        )

        cmd = run_quality_gate.gate_command("noTestSkips", tmp_path, "hook-runtime")

        assert cmd == ["/tmp/runtime-python", "scripts/quality/check_no_test_skips.py"]

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_browser_layout_gate_includes_dashboard_chart_coordinates(self, tmp_path):
        (tmp_path / "tests" / "playwright").mkdir(parents=True)
        (tmp_path / "playwright.config.js").write_text("", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()

        cmd = run_quality_gate.gate_command("browserLayout", tmp_path, "session-detail")

        assert "dashboard-chart-coordinates" in cmd
        assert "--workers=8" in cmd
        assert "--workers=1" not in cmd

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_browser_interaction_gate_uses_parallel_workers(self, tmp_path):
        (tmp_path / "tests" / "playwright").mkdir(parents=True)
        (tmp_path / "playwright.config.js").write_text("", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()

        cmd = run_quality_gate.gate_command("browserInteraction", tmp_path, "session-detail")

        assert "sessions-list.spec.js" in cmd
        assert "--workers=8" in cmd
        assert "--workers=1" not in cmd

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_playwright_workers_clamps_low_override(self, monkeypatch):
        monkeypatch.setenv("SESSION_BROWSER_PLAYWRIGHT_WORKERS", "1")

        assert run_quality_gate._playwright_workers() == 8

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_playwright_workers_allows_higher_override(self, monkeypatch):
        monkeypatch.setenv("SESSION_BROWSER_PLAYWRIGHT_WORKERS", "12")

        assert run_quality_gate._playwright_workers() == 12

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_selected_playwright_gate_fails_when_tests_skip(self, monkeypatch, tmp_path):
        monkeypatch.setattr(run_quality_gate.shutil, "which", lambda name: name)
        monkeypatch.setattr(
            run_quality_gate.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="2 passed\n1 skipped\n"),
        )

        detail = run_quality_gate.run_cmd(
            "browserInteraction",
            ["npx", "playwright", "test", "session-detail.spec.js", "--workers=8"],
            tmp_path,
        )

        assert detail.status == FAIL
        assert "selected Playwright gate reported 1 skipped tests" in detail.output

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_fixture_playwright_gate_injects_session_url(self, monkeypatch, tmp_path):
        captured_env = {}

        monkeypatch.setattr(
            run_quality_gate,
            "applicable_gates_for_target",
            lambda target, changed_files=None: ["browserInteraction"],
        )
        monkeypatch.setattr(
            run_quality_gate,
            "gate_command",
            lambda gate, repo_root, target: ["npx", "playwright", "test", "session-detail.spec.js", "--workers=8"],
        )
        monkeypatch.setattr(run_quality_gate, "_fixture_session_available", lambda base_url: True)

        def capture_run_cmd(name, cmd, cwd, required=True, env_overrides=None):
            captured_env.update(env_overrides or {})
            return GateDetail(name=name, status=PASS, command=cmd)

        monkeypatch.setattr(run_quality_gate, "run_cmd", capture_run_cmd)

        details = run_quality_gate.run_target(tmp_path, "session-detail")

        assert details[0].status == PASS
        assert captured_env["BASE_URL"] == "http://127.0.0.1:19099"
        assert captured_env["PW_SESSION_URL"] == (
            "http://127.0.0.1:19099/sessions/claude_code/hifi-viz-session-001"
        )

    @pytest.mark.contract_case("HOOK-HARNESS-010")
    def test_fixture_gate_blocks_without_running_playwright(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            run_quality_gate,
            "applicable_gates_for_target",
            lambda target, changed_files=None: ["browserLayout"],
        )
        monkeypatch.setattr(
            run_quality_gate,
            "gate_command",
            lambda gate, repo_root, target: ["npx", "playwright", "test", "session-detail-layout"],
        )
        monkeypatch.setattr(run_quality_gate, "_fixture_session_available", lambda base_url: False)
        monkeypatch.setattr(
            run_quality_gate,
            "_start_fixture_server",
            lambda: (None, None, None, "missing jinja2"),
        )

        def fail_if_called(*args, **kwargs):
            raise AssertionError("fixture-dependent Playwright gate should fail fast")

        monkeypatch.setattr(run_quality_gate, "run_cmd", fail_if_called)

        details = run_quality_gate.run_target(tmp_path, "session-detail")
        assert len(details) == 1
        assert details[0].name == "browserLayout"
        assert details[0].status == BLOCKED
        assert "missing jinja2" in details[0].output
