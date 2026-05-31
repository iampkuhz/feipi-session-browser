"""Tests for the LLM attribution browser visual gate script.

Verifies:
1. scripts/quality/run_llm_attribution_visual_gate.py exists.
2. script --help exits 0.
3. script supports --out.
4. result schema includes PASS / FAIL / NOT_RUN_ENV_LIMITED / BLOCKED.
5. script source contains checks for Request modal and Response modal.
6. script source checks no Raw request / Raw response.
7. script source checks no horizontal overflow.
8. script source writes request/response screenshot names.
"""

import json
import pathlib
import subprocess
import sys

import pytest

SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts"
    / "quality"
    / "run_llm_attribution_visual_gate.py"
)


class TestVisualGateScriptExists:
    """Verify the visual gate script exists and is runnable."""

    def test_script_file_exists(self):
        assert SCRIPT_PATH.exists(), f"Script not found: {SCRIPT_PATH}"

    def test_script_is_python_file(self):
        content = SCRIPT_PATH.read_text()
        assert content.startswith("#!/usr/bin/env python3") or "#!/usr/bin/env python3" in content[:100]


class TestVisualGateHelp:
    """Verify --help exits successfully."""

    def test_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"--help failed: {result.stderr}"

    def test_help_mentions_url(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "--url" in result.stdout or "--url" in result.stderr


class TestVisualGateSourceContent:
    """Verify the script source contains the required check patterns."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        self.source = SCRIPT_PATH.read_text()

    def test_checks_request_modal(self):
        assert "llm.request_attribution" in self.source

    def test_checks_response_modal(self):
        assert "llm.response_attribution" in self.source

    def test_checks_no_raw_request(self):
        assert "Raw request" in self.source

    def test_checks_no_raw_response(self):
        assert "Raw response" in self.source

    def test_checks_horizontal_overflow(self):
        assert "scrollWidth" in self.source
        assert "innerWidth" in self.source

    def test_checks_modal_within_viewport(self):
        assert "modalWithinViewport" in self.source or "withinViewport" in self.source

    def test_checks_distribution_bar(self):
        assert "sd-attribution-distribution__bar" in self.source or "distributionVisible" in self.source

    def test_checks_availability_table(self):
        assert "sd-attrib-table" in self.source or "tableWithinModal" in self.source

    def test_checks_bucket_preview(self):
        assert "sd-attribution-bucket__preview" in self.source or "previewWithinModal" in self.source

    def test_checks_rebuilt_banner(self):
        assert "基于本地日志重建" in self.source

    def test_writes_request_screenshot(self):
        assert "request-" in self.source and ".png" in self.source

    def test_writes_response_screenshot(self):
        assert "response-" in self.source and ".png" in self.source

    def test_writes_result_json(self):
        assert "result.json" in self.source

    def test_supports_viewports(self):
        assert "1440" in self.source
        assert "2560" in self.source

    def test_self_test_mode(self):
        assert "--self-test" in self.source


class TestVisualGateSelfTest:
    """Verify the --self-test mode works."""

    def test_self_test_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--self-test"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"--self-test failed: {result.stderr}"

    def test_self_test_passes_all_assertions(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--self-test"],
            capture_output=True, text=True, timeout=30,
        )
        assert "All self-tests passed" in result.stdout


class TestVisualGateBlockedWithoutUrl:
    """Verify the script returns BLOCKED when no URL is provided."""

    def test_blocked_without_url(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--out", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        # Exit code 2 for BLOCKED
        assert result.returncode == 2

    def test_blocked_writes_result_json(self, tmp_path):
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--out", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        result_path = tmp_path / "result.json"
        assert result_path.exists()
        data = json.loads(result_path.read_text())
        assert data["status"] == "BLOCKED"
        assert "gate" in data
        assert data.get("gate") == "llm-attribution-visual"

    def test_blocked_result_has_required_fields(self, tmp_path):
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--out", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        result_path = tmp_path / "result.json"
        data = json.loads(result_path.read_text())
        assert "schemaVersion" in data
        assert "viewports" in data
        assert "checks" in data
        assert "screenshots" in data
        assert "diagnostics" in data

    def test_blocked_result_has_viewports(self, tmp_path):
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--out", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        result_path = tmp_path / "result.json"
        data = json.loads(result_path.read_text())
        assert "1440x900" in data["viewports"]
        assert "2560x1440" in data["viewports"]
