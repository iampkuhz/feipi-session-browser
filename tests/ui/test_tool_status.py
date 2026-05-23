"""Regression tests for tool call success/failure判定.

Ensures that:
- Nonzero exit codes do NOT make a tool call failed.
- Result text containing error keywords (failed, error:, exit code) does NOT
  make a tool call failed unless it's a genuine tool runtime error.
- Genuine tool runtime errors (is_error: true, user rejected, API error,
  command not found, file not found) still make a tool call failed.
- Both Claude and Qoder parsers follow the same conservative判定.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ── Claude parser tests ───────────────────────────────────────────────


class TestClaudeToolResultHeuristic:
    """Test _tool_result_looks_failed for Claude parser."""

    def _looks_failed(self, text, tool_name=""):
        from session_browser.sources.claude import _tool_result_looks_failed
        return _tool_result_looks_failed(text, tool_name=tool_name)

    # ── Should NOT be failed: command output with error keywords ──────

    def test_exit_code_1_not_failed(self):
        """Bash result with 'exit code 1' but no is_error should NOT be failed."""
        text = "error: 'unusedVariable' is defined but never used\nerror: missing semicolon\nexit code 1"
        assert not self._looks_failed(text, tool_name="Bash")

    def test_lint_error_output_not_failed(self):
        """Lint error output is command output, not tool runtime error."""
        text = "src/index.ts\n  1:5  error  'x' is defined but never used\n\n✖ 1 problem (1 error, 0 warnings)\nexit code 1"
        assert not self._looks_failed(text, tool_name="Bash")

    def test_test_failure_output_not_failed(self):
        """Test runner output with FAILED is command output."""
        text = "FAILED tests/test_x.py - AssertionError: expected 1 == 2\n\n1 failed, 9 passed in 2.34s"
        assert not self._looks_failed(text, tool_name="Bash")

    def test_html_error_class_not_failed(self):
        """HTML with error classes should not trigger heuristic."""
        text = '<span class="badge badge-error">failed</span>'
        assert not self._looks_failed(text, tool_name="Bash")

    def test_sql_schema_with_failed_keyword_not_failed(self):
        """SQL schema containing 'failed' keyword should not trigger."""
        text = "    failed_tool_count INTEGER NOT NULL DEFAULT 0,"
        assert not self._looks_failed(text, tool_name="Bash")

    def test_source_code_with_error_keywords_not_failed(self):
        """Source code referencing error strings should not trigger."""
        text = 'const error = new Error("text-error")\nclass BadgeError { status = "error:" }'
        assert not self._looks_failed(text, tool_name="Bash")

    def test_grep_output_with_error_in_filename_not_failed(self):
        """Grep output showing error: in a matched file."""
        text = "src/config.py:    if status == 'error':\nsrc/handler.py:    return {'error': 'not found'}"
        assert not self._looks_failed(text, tool_name="Bash")

    def test_diff_output_not_failed(self):
        """Diff output with context lines containing error keywords."""
        text = "--- a/src/app.py\n+++ b/src/app.py\n-    raise Exception('error: something failed')\n+    pass"
        assert not self._looks_failed(text, tool_name="Bash")

    # ── Read/Write/etc. file tool false positives ─────────────────────

    def test_read_file_with_error_in_content_not_failed(self):
        """Read tool returning file content that has 'error:' in it."""
        text = "def handle_error():\n    print('error: something went wrong')\n    return {'failed': True}"
        assert not self._looks_failed(text, tool_name="Read")

    def test_read_file_with_exit_code_in_content_not_failed(self):
        """Read tool returning file content mentioning 'exit code'."""
        text = "# Exit code meanings:\n# 0 = success\n# 1 = general error"
        assert not self._looks_failed(text, tool_name="Read")

    # ── Should BE failed: genuine tool runtime errors ─────────────────

    def test_user_rejected_is_failed(self):
        """User rejecting a tool use should be failed."""
        assert self._looks_failed("User rejected tool use", tool_name="Bash")
        assert self._looks_failed("User rejected tool use", tool_name="Agent")

    def test_api_error_is_failed(self):
        """API error should be failed."""
        assert self._looks_failed("API Error: 401 Unauthorized", tool_name="Bash")
        assert self._looks_failed("api error: rate limited", tool_name="Bash")

    def test_tool_use_error_is_failed(self):
        """tool_use_error should be failed."""
        assert self._looks_failed("tool_use_error: tool execution failed", tool_name="Bash")

    def test_key_model_access_denied_is_failed(self):
        """key_model_access_denied should be failed."""
        assert self._looks_failed("API Error: 403 key_model_access_denied", tool_name="Bash")

    def test_rate_limit_exceeded_is_failed(self):
        """Rate limit exceeded should be failed."""
        assert self._looks_failed("Rate limit exceeded. Please try again later.", tool_name="Bash")

    def test_request_cancelled_is_failed(self):
        """Request cancelled should be failed."""
        assert self._looks_failed("Request cancelled by user", tool_name="Bash")

    def test_command_not_found_is_failed(self):
        """Command not found should be failed."""
        assert self._looks_failed("command not found", tool_name="Bash")
        assert self._looks_failed("bash: kubectl: command not found", tool_name="Bash")
        assert self._looks_failed("sh: xyz: command not found", tool_name="Bash")

    def test_timeout_is_failed(self):
        """Tool timeout should be failed."""
        assert self._looks_failed("timeout", tool_name="Bash")

    # ── File-level errors for Read/Write/etc. ─────────────────────────

    def test_read_file_does_not_exist_is_failed(self):
        """Read tool reporting file doesn't exist should be failed."""
        assert self._looks_failed("File does not exist: /tmp/missing.txt", tool_name="Read")

    def test_read_permission_denied_is_failed(self):
        """Read tool reporting permission denied should be failed."""
        assert self._looks_failed("Permission denied: /etc/shadow", tool_name="Read")

    def test_read_no_such_file_is_failed(self):
        """Read tool reporting no such file should be failed."""
        assert self._looks_failed("No such file or directory", tool_name="Read")

    # ── Bash-level runtime errors ─────────────────────────────────────

    def test_bash_permission_denied_is_failed(self):
        """Bash runtime error: permission denied should be failed."""
        assert self._looks_failed("bash: ./deploy.sh: Permission denied", tool_name="Bash")
        assert self._looks_failed("Permission denied", tool_name="Bash")

    def test_git_fatal_error_is_failed(self):
        """Git fatal error should be failed."""
        assert self._looks_failed("fatal: not a git repository (or any of the parent directories)", tool_name="Bash")
        assert self._looks_failed("fatal: ambiguous argument 'HEAD'", tool_name="Bash")


class TestClaudeExtractToolCalls:
    """Test _extract_tool_calls end-to-end for Claude parser."""

    def _parse(self, events):
        from session_browser.sources.claude import (
            _extract_tool_calls,
            _extract_messages,
        )
        messages = _extract_messages(events)
        return _extract_tool_calls(events, messages)

    def test_bash_exit_code_1_not_failed(self):
        """Bash with exit code 1 but no is_error should NOT be failed."""
        events = [
            {"type": "user", "message": {"role": "user", "content": "run lint"},
             "timestamp": "2026-01-01T00:00:00Z"},
            {"type": "assistant", "message": {
                "id": "msg1", "role": "assistant", "model": "claude",
                "content": [{"type": "tool_use", "id": "tu1", "name": "Bash",
                             "input": {"command": "npm run lint"}}],
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "stop_reason": "tool_use",
            }, "timestamp": "2026-01-01T00:00:01Z"},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu1",
                 "content": "error: unused variable\nexit code 1"}
            ]}, "timestamp": "2026-01-01T00:00:02Z"},
        ]
        tcs = self._parse(events)
        assert len(tcs) == 1
        tc = tcs[0]
        assert tc.name == "Bash"
        assert tc.exit_code == 1
        assert not tc.is_failed
        assert tc.status == "completed"
        assert tc.has_nonzero_exit

    def test_bash_exit_code_0_not_failed(self):
        """Bash with exit code 0 should NOT be failed."""
        events = [
            {"type": "user", "message": {"role": "user", "content": "ls"},
             "timestamp": "2026-01-01T00:00:00Z"},
            {"type": "assistant", "message": {
                "id": "msg1", "role": "assistant", "model": "claude",
                "content": [{"type": "tool_use", "id": "tu1", "name": "Bash",
                             "input": {"command": "ls"}}],
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "stop_reason": "tool_use",
            }, "timestamp": "2026-01-01T00:00:01Z"},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu1",
                 "content": "file1.txt\nfile2.txt\nexit code 0"}
            ]}, "timestamp": "2026-01-01T00:00:02Z"},
        ]
        tcs = self._parse(events)
        assert len(tcs) == 1
        tc = tcs[0]
        assert tc.exit_code == 0
        assert not tc.is_failed
        assert not tc.has_nonzero_exit

    def test_bash_is_error_true_is_failed(self):
        """Bash with is_error: true should be failed."""
        events = [
            {"type": "user", "message": {"role": "user", "content": "run"},
             "timestamp": "2026-01-01T00:00:00Z"},
            {"type": "assistant", "message": {
                "id": "msg1", "role": "assistant", "model": "claude",
                "content": [{"type": "tool_use", "id": "tu1", "name": "Bash",
                             "input": {"command": "npm run lint"}}],
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "stop_reason": "tool_use",
            }, "timestamp": "2026-01-01T00:00:01Z"},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu1",
                 "content": "error: something broke\nexit code 1",
                 "is_error": True}
            ]}, "timestamp": "2026-01-01T00:00:02Z"},
        ]
        tcs = self._parse(events)
        assert len(tcs) == 1
        tc = tcs[0]
        assert tc.is_failed
        assert tc.status == "error"

    def test_user_rejected_tool_use_is_failed(self):
        """User rejected tool use should be failed."""
        events = [
            {"type": "user", "message": {"role": "user", "content": "run"},
             "timestamp": "2026-01-01T00:00:00Z"},
            {"type": "assistant", "message": {
                "id": "msg1", "role": "assistant", "model": "claude",
                "content": [{"type": "tool_use", "id": "tu1", "name": "Bash",
                             "input": {"command": "rm -rf /tmp/thing"}}],
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "stop_reason": "tool_use",
            }, "timestamp": "2026-01-01T00:00:01Z"},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu1",
                 "content": "User rejected tool use",
                 "is_error": True}
            ]}, "timestamp": "2026-01-01T00:00:02Z"},
        ]
        tcs = self._parse(events)
        assert len(tcs) == 1
        tc = tcs[0]
        assert tc.is_failed
        assert tc.status == "error"

    def test_api_error_in_result_is_failed(self):
        """API error in result should be failed."""
        events = [
            {"type": "user", "message": {"role": "user", "content": "call api"},
             "timestamp": "2026-01-01T00:00:00Z"},
            {"type": "assistant", "message": {
                "id": "msg1", "role": "assistant", "model": "claude",
                "content": [{"type": "tool_use", "id": "tu1", "name": "Bash",
                             "input": {"command": "curl https://api.example.com"}}],
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "stop_reason": "tool_use",
            }, "timestamp": "2026-01-01T00:00:01Z"},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu1",
                 "content": "API Error: 401 Unauthorized key_model_access_denied"}
            ]}, "timestamp": "2026-01-01T00:00:02Z"},
        ]
        tcs = self._parse(events)
        assert len(tcs) == 1
        tc = tcs[0]
        assert tc.is_failed
        assert tc.status == "error"


# ── Qoder parser tests ────────────────────────────────────────────────


class TestQoderToolResultHeuristic:
    """Test _tool_result_looks_failed for Qoder parser."""

    def _looks_failed(self, text, tool_name=""):
        from session_browser.sources.qoder import _tool_result_looks_failed
        return _tool_result_looks_failed(text, tool_name=tool_name)

    # ── Should NOT be failed ──────────────────────────────────────────

    def test_exit_code_1_not_failed(self):
        text = "error: unused variable\nexit code 1"
        assert not self._looks_failed(text)

    def test_html_error_class_not_failed(self):
        text = '<span class="badge badge-error">failed</span>'
        assert not self._looks_failed(text)

    def test_sql_schema_not_failed(self):
        text = "    failed_tool_count INTEGER NOT NULL DEFAULT 0,"
        assert not self._looks_failed(text)

    def test_text_error_class_not_failed(self):
        text = '<span class="text-error">some error text</span>'
        assert not self._looks_failed(text)

    def test_lint_output_not_failed(self):
        text = "src/index.ts\n  1:5  error  'x' is not defined\n\n✖ 1 problem\nexit code 1"
        assert not self._looks_failed(text)

    # ── Should BE failed ──────────────────────────────────────────────

    def test_user_rejected_is_failed(self):
        assert self._looks_failed("User rejected tool use")

    def test_api_error_is_failed(self):
        assert self._looks_failed("API Error: 401")

    def test_tool_use_error_is_failed(self):
        assert self._looks_failed("tool_use_error: execution failed")

    def test_command_not_found_is_failed(self):
        assert self._looks_failed("bash: kubectl: command not found")

    # ── File-level errors (Qoder also supports these now) ─────────────

    def test_qoder_read_file_does_not_exist_is_failed(self):
        assert self._looks_failed("File does not exist: /tmp/missing.txt", tool_name="Read")

    def test_qoder_read_permission_denied_is_failed(self):
        assert self._looks_failed("Permission denied: /etc/shadow", tool_name="Read")

    def test_qoder_read_no_such_file_is_failed(self):
        assert self._looks_failed("No such file or directory", tool_name="Read")

    # ── Bash-level runtime errors ─────────────────────────────────────

    def test_qoder_bash_permission_denied_is_failed(self):
        assert self._looks_failed("bash: ./deploy.sh: Permission denied")
        assert self._looks_failed("Permission denied")

    def test_qoder_git_fatal_error_is_failed(self):
        assert self._looks_failed("fatal: not a git repository")
        assert self._looks_failed("fatal: ambiguous argument 'HEAD'")


# ── Model-level tests ─────────────────────────────────────────────────


class TestToolCallIsFailed:
    """Test ToolCall.is_failed and has_nonzero_exit properties."""

    def _tc(self, **kwargs):
        from session_browser.domain.models import ToolCall
        defaults = {"name": "Bash", "status": "completed"}
        defaults.update(kwargs)
        return ToolCall(**defaults)

    def test_completed_not_failed(self):
        tc = self._tc()
        assert not tc.is_failed

    def test_error_status_is_failed(self):
        tc = self._tc(status="error")
        assert tc.is_failed

    def test_exit_code_1_without_error_not_failed(self):
        tc = self._tc(exit_code=1)
        assert not tc.is_failed
        assert tc.has_nonzero_exit

    def test_exit_code_0_not_failed(self):
        tc = self._tc(exit_code=0)
        assert not tc.is_failed
        assert not tc.has_nonzero_exit

    def test_exit_code_2_with_error_status_failed(self):
        tc = self._tc(status="error", exit_code=2)
        assert tc.is_failed
        assert tc.has_nonzero_exit

    def test_no_exit_code_not_has_nonzero_exit(self):
        tc = self._tc()
        assert not tc.has_nonzero_exit
