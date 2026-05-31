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
        assert "Raw request" in self.source or "raw request" in self.source

    def test_checks_no_raw_response(self):
        assert "Raw response" in self.source or "raw response" in self.source

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


class TestTextCheckHelpers:
    """Unit tests for _check_request_text and _check_response_text helpers."""

    @pytest.fixture(autouse=True)
    def _import_helpers(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gate_module", str(SCRIPT_PATH))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._check_request_text = mod._check_request_text
        self._check_response_text = mod._check_response_text

    # --- Request text tests ---
    def test_request_all_required_pass(self):
        text = "基于本地日志重建，不等同于真实 provider request/response body。用量分布 归因明细 可见内容摘要 参数可得性表 不计入总量"
        result = self._check_request_text(text)
        assert result["status"] == "PASS"

    def test_request_missing_rebuilt_fails(self):
        result = self._check_request_text("")
        assert result["status"] == "FAIL"
        assert "hasRebuiltBanner" in result["failed"]

    def test_request_raw_request_uppercase_fails(self):
        result = self._check_request_text("RAW REQUEST is bad")
        assert result["status"] == "FAIL"
        assert "hasNoRawRequest" in result["failed"]

    def test_request_raw_http_response_fails(self):
        result = self._check_request_text("raw http response here")
        assert result["status"] == "FAIL"
        assert "hasNoRawHttpResponse" in result["failed"]

    def test_request_no_rendered_lowercase_fails(self):
        result = self._check_request_text("(no rendered content) found")
        assert result["status"] == "FAIL"

    def test_request_missing_provider_disclaimer_fails(self):
        result = self._check_request_text("基于本地日志重建")
        assert result["status"] == "FAIL"
        assert "hasProviderDisclaimer" in result["failed"]

    def test_request_missing_exclusion_label_fails(self):
        result = self._check_request_text("基于本地日志重建，不等同于真实 provider request/response body。用量分布 归因明细 可见内容摘要 参数可得性表")
        assert result["status"] == "FAIL"
        assert "hasExclusionLabel" in result["failed"]

    # --- Response text tests ---
    def test_response_all_required_pass(self):
        text = "基于本地日志重建，不等同于真实 provider request/response body。用量分布 归因明细 Blocks 明细 可见内容摘要 参数可得性表 不计入总量"
        result = self._check_response_text(text)
        assert result["status"] == "PASS"

    def test_response_missing_blocks_detail_fails(self):
        text = "基于本地日志重建，不等同于真实 provider request/response body。用量分布 归因明细 可见内容摘要 参数可得性表 不计入总量"
        result = self._check_response_text(text)
        assert result["status"] == "FAIL"
        assert "hasBlocksDetail" in result["failed"]

    def test_response_raw_response_uppercase_fails(self):
        result = self._check_response_text("RAW RESPONSE is bad")
        assert result["status"] == "FAIL"
        assert "hasNoRawResponse" in result["failed"]

    def test_response_no_raw_content_lowercase_fails(self):
        result = self._check_response_text("(no raw content) here")
        assert result["status"] == "FAIL"


class TestUrlFileSupport:
    """Verify --url-file argument is supported."""

    def test_help_mentions_url_file(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "--url-file" in result.stdout or "--url-file" in result.stderr

    def test_url_file_with_valid_file(self, tmp_path):
        url_file = tmp_path / "url.txt"
        url_file.write_text("http://example.com/session/123\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--url-file", str(url_file), "--out", str(tmp_path / "out")],
            capture_output=True, text=True, timeout=60,
        )
        # Should not be exit code 2 for "no url"
        # It will either run the browser (exit 0/1) or fail with NOT_RUN_ENV_LIMITED (exit 2)
        # But it should NOT output "BLOCKED: No --url provided"
        assert "No --url provided" not in result.stderr

    def test_url_file_with_nonexistent_file(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--url-file", str(tmp_path / "does-not-exist.txt"), "--out", str(tmp_path / "out")],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 2  # BLOCKED
        result_json = tmp_path / "out" / "result.json"
        if result_json.exists():
            data = json.loads(result_json.read_text())
            assert data["status"] == "BLOCKED"

    def test_url_file_with_empty_file(self, tmp_path):
        url_file = tmp_path / "empty.txt"
        url_file.write_text("")
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--url-file", str(url_file), "--out", str(tmp_path / "out")],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 2  # BLOCKED

    def test_url_file_with_comment_lines(self, tmp_path):
        url_file = tmp_path / "comments.txt"
        url_file.write_text("# this is a comment\n\n# another comment\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--url-file", str(url_file), "--out", str(tmp_path / "out")],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 2  # BLOCKED (no valid URL)

    def test_url_file_with_invalid_not_http(self, tmp_path):
        url_file = tmp_path / "invalid.txt"
        url_file.write_text("not-a-url\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--url-file", str(url_file), "--out", str(tmp_path / "out")],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 2  # BLOCKED


class TestResultSchema:
    """Verify result.json schema enhancements."""

    def test_blocked_result_has_summary(self, tmp_path):
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--out", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        result_path = tmp_path / "result.json"
        data = json.loads(result_path.read_text())
        assert "summary" in data
        assert data["summary"]["total"] >= 1
        assert data["summary"]["blocked"] >= 1

    def test_blocked_result_has_report_md(self, tmp_path):
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--out", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        report_path = tmp_path / "report.md"
        assert report_path.exists()
        content = report_path.read_text()
        assert "LLM Attribution Visual Gate Report" in content
        assert "BLOCKED" in content
