"""工具调用成功/失败判定的回归测试。

确保：
- 非零退出码不会使工具调用判定为失败。
- 结果文本中包含错误关键词（failed、error:、exit code）不会
  使工具调用判定为失败，除非是真正的工具运行时错误。
- 真正的工具运行时错误（is_error: true、用户拒绝、API 错误、
  命令未找到、文件未找到）仍会使工具调用判定为失败。
- Claude 和 Qoder 解析器遵循相同的保守判定策略。
"""

from __future__ import annotations

import pytest
import json
import tempfile
from pathlib import Path


# ── Claude 解析器测试 ─────────────────────────────────────────────────


class TestClaudeToolResultHeuristic:
    """测试 Claude 解析器的 _tool_result_looks_failed。"""

    def _looks_failed(self, text, tool_name=""):
        from session_browser.sources.claude import _tool_result_looks_failed
        return _tool_result_looks_failed(text, tool_name=tool_name)

    # ── 不应判定为失败：命令输出中含错误关键词 ──────

    @pytest.mark.contract_case("UI-SD-025")
    def test_exit_code_1_not_failed(self):
        """Bash 结果含 'exit code 1' 但无 is_error 不应判定为失败。"""
        text = "error: 'unusedVariable' is defined but never used\nerror: missing semicolon\nexit code 1"
        assert not self._looks_failed(text, tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_lint_error_output_not_failed(self):
        """Lint 错误输出是命令输出，非工具运行时错误。"""
        text = "src/index.ts\n  1:5  error  'x' is defined but never used\n\n✖ 1 problem (1 error, 0 warnings)\nexit code 1"
        assert not self._looks_failed(text, tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_test_failure_output_not_failed(self):
        """测试运行器输出含 FAILED 是命令输出。"""
        text = "FAILED tests/test_x.py - AssertionError: expected 1 == 2\n\n1 failed, 9 passed in 2.34s"
        assert not self._looks_failed(text, tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_html_error_class_not_failed(self):
        """含错误类名的 HTML 不应触发启发式判定。"""
        text = '<span class="badge badge-error">failed</span>'
        assert not self._looks_failed(text, tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_sql_schema_with_failed_keyword_not_failed(self):
        """SQL schema 含 'failed' 关键词不应触发。"""
        text = "    failed_tool_count INTEGER NOT NULL DEFAULT 0,"
        assert not self._looks_failed(text, tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_source_code_with_error_keywords_not_failed(self):
        """引用错误字符串的源代码不应触发。"""
        text = 'const error = new Error("text-error")\nclass BadgeError { status = "error:" }'
        assert not self._looks_failed(text, tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_grep_output_with_error_in_filename_not_failed(self):
        """Grep 输出显示匹配文件中的 error: 不应判定为失败。"""
        text = "src/config.py:    if status == 'error':\nsrc/handler.py:    return {'error': 'not found'}"
        assert not self._looks_failed(text, tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_diff_output_not_failed(self):
        """Diff 输出含错误关键词的上下文行不应判定为失败。"""
        text = "--- a/src/app.py\n+++ b/src/app.py\n-    raise Exception('error: something failed')\n+    pass"
        assert not self._looks_failed(text, tool_name="Bash")

    # ── Read/Write 等文件工具的误判 ─────────────────────

    @pytest.mark.contract_case("UI-SD-025")
    def test_read_file_with_error_in_content_not_failed(self):
        """Read 工具返回含 'error:' 的文件内容不应判定为失败。"""
        text = "def handle_error():\n    print('error: something went wrong')\n    return {'failed': True}"
        assert not self._looks_failed(text, tool_name="Read")

    @pytest.mark.contract_case("UI-SD-025")
    def test_read_file_with_exit_code_in_content_not_failed(self):
        """Read 工具返回含 'exit code' 的文件内容不应判定为失败。"""
        text = "# Exit code meanings:\n# 0 = success\n# 1 = general error"
        assert not self._looks_failed(text, tool_name="Read")

    # ── 应判定为失败：真实的工具运行时错误 ─────────────────

    @pytest.mark.contract_case("UI-SD-025")
    def test_user_rejected_is_failed(self):
        """用户拒绝工具使用应判定为失败。"""
        assert self._looks_failed("User rejected tool use", tool_name="Bash")
        assert self._looks_failed("User rejected tool use", tool_name="Agent")

    @pytest.mark.contract_case("UI-SD-025")
    def test_api_error_is_failed(self):
        """API 错误应判定为失败。"""
        assert self._looks_failed("API Error: 401 Unauthorized", tool_name="Bash")
        assert self._looks_failed("api error: rate limited", tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_tool_use_error_is_failed(self):
        """tool_use_error 应判定为失败。"""
        assert self._looks_failed("tool_use_error: tool execution failed", tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_key_model_access_denied_is_failed(self):
        """key_model_access_denied 应判定为失败。"""
        assert self._looks_failed("API Error: 403 key_model_access_denied", tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_rate_limit_exceeded_is_failed(self):
        """速率限制超限应判定为失败。"""
        assert self._looks_failed("Rate limit exceeded. Please try again later.", tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_request_cancelled_is_failed(self):
        """请求被取消应判定为失败。"""
        assert self._looks_failed("Request cancelled by user", tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_command_not_found_is_failed(self):
        """命令未找到应判定为失败。"""
        assert self._looks_failed("command not found", tool_name="Bash")
        assert self._looks_failed("bash: kubectl: command not found", tool_name="Bash")
        assert self._looks_failed("sh: xyz: command not found", tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_timeout_is_failed(self):
        """工具超时应判定为失败。"""
        assert self._looks_failed("timeout", tool_name="Bash")

    # ── Read/Write 等的文件级错误 ─────────────────────────

    @pytest.mark.contract_case("UI-SD-025")
    def test_read_file_does_not_exist_is_failed(self):
        """Read 工具报告文件不存在应判定为失败。"""
        assert self._looks_failed("File does not exist: /tmp/missing.txt", tool_name="Read")

    @pytest.mark.contract_case("UI-SD-025")
    def test_read_permission_denied_is_failed(self):
        """Read 工具报告权限拒绝应判定为失败。"""
        assert self._looks_failed("Permission denied: /etc/shadow", tool_name="Read")

    @pytest.mark.contract_case("UI-SD-025")
    def test_read_no_such_file_is_failed(self):
        """Read 工具报告文件不存在应判定为失败。"""
        assert self._looks_failed("No such file or directory", tool_name="Read")

    # ── Bash 运行时错误 ─────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-025")
    def test_bash_permission_denied_is_failed(self):
        """Bash 运行时错误：权限拒绝应判定为失败。"""
        assert self._looks_failed("bash: ./deploy.sh: Permission denied", tool_name="Bash")
        assert self._looks_failed("Permission denied", tool_name="Bash")

    @pytest.mark.contract_case("UI-SD-025")
    def test_git_fatal_error_is_failed(self):
        """Git 致命错误应判定为失败。"""
        assert self._looks_failed("fatal: not a git repository (or any of the parent directories)", tool_name="Bash")
        assert self._looks_failed("fatal: ambiguous argument 'HEAD'", tool_name="Bash")


class TestClaudeExtractToolCalls:
    """端到端测试 Claude 解析器的 _extract_tool_calls。"""

    def _parse(self, events):
        from session_browser.sources.claude import (
            _extract_tool_calls,
            _extract_messages,
        )
        messages = _extract_messages(events)
        return _extract_tool_calls(events, messages)

    @pytest.mark.contract_case("UI-SD-025")
    def test_bash_exit_code_1_not_failed(self):
        """Bash 含 exit code 1 但无 is_error 不应判定为失败。"""
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

    @pytest.mark.contract_case("UI-SD-025")
    def test_bash_exit_code_0_not_failed(self):
        """Bash 含 exit code 0 不应判定为失败。"""
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

    @pytest.mark.contract_case("UI-SD-025")
    def test_bash_is_error_true_is_failed(self):
        """Bash 含 is_error: true 应判定为失败。"""
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

    @pytest.mark.contract_case("UI-SD-025")
    def test_user_rejected_tool_use_is_failed(self):
        """用户拒绝工具使用应判定为失败。"""
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

    @pytest.mark.contract_case("UI-SD-025")
    def test_api_error_in_result_is_failed(self):
        """结果中的 API 错误应判定为失败。"""
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


# ── Qoder 解析器测试 ────────────────────────────────────────────────


class TestQoderToolResultHeuristic:
    """测试 Qoder 解析器的 _tool_result_looks_failed。"""

    def _looks_failed(self, text, tool_name=""):
        from session_browser.sources.qoder import _tool_result_looks_failed
        return _tool_result_looks_failed(text, tool_name=tool_name)

    # ── 不应判定为失败 ──────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-025")
    def test_exit_code_1_not_failed(self):
        text = "error: unused variable\nexit code 1"
        assert not self._looks_failed(text)

    @pytest.mark.contract_case("UI-SD-025")
    def test_html_error_class_not_failed(self):
        text = '<span class="badge badge-error">failed</span>'
        assert not self._looks_failed(text)

    @pytest.mark.contract_case("UI-SD-025")
    def test_sql_schema_not_failed(self):
        text = "    failed_tool_count INTEGER NOT NULL DEFAULT 0,"
        assert not self._looks_failed(text)

    @pytest.mark.contract_case("UI-SD-025")
    def test_text_error_class_not_failed(self):
        text = '<span class="text-error">some error text</span>'
        assert not self._looks_failed(text)

    @pytest.mark.contract_case("UI-SD-025")
    def test_lint_output_not_failed(self):
        text = "src/index.ts\n  1:5  error  'x' is not defined\n\n✖ 1 problem\nexit code 1"
        assert not self._looks_failed(text)

    # ── 应判定为失败 ──────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-025")
    def test_user_rejected_is_failed(self):
        assert self._looks_failed("User rejected tool use")

    @pytest.mark.contract_case("UI-SD-025")
    def test_api_error_is_failed(self):
        assert self._looks_failed("API Error: 401")

    @pytest.mark.contract_case("UI-SD-025")
    def test_tool_use_error_is_failed(self):
        assert self._looks_failed("tool_use_error: execution failed")

    @pytest.mark.contract_case("UI-SD-025")
    def test_command_not_found_is_failed(self):
        assert self._looks_failed("bash: kubectl: command not found")

    # ── 文件级错误（Qoder 也支持这些） ─────────────────────

    @pytest.mark.contract_case("UI-SD-025")
    def test_qoder_read_file_does_not_exist_is_failed(self):
        assert self._looks_failed("File does not exist: /tmp/missing.txt", tool_name="Read")

    @pytest.mark.contract_case("UI-SD-025")
    def test_qoder_read_permission_denied_is_failed(self):
        assert self._looks_failed("Permission denied: /etc/shadow", tool_name="Read")

    @pytest.mark.contract_case("UI-SD-025")
    def test_qoder_read_no_such_file_is_failed(self):
        assert self._looks_failed("No such file or directory", tool_name="Read")

    # ── Bash 运行时错误 ─────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-025")
    def test_qoder_bash_permission_denied_is_failed(self):
        assert self._looks_failed("bash: ./deploy.sh: Permission denied")
        assert self._looks_failed("Permission denied")

    @pytest.mark.contract_case("UI-SD-025")
    def test_qoder_git_fatal_error_is_failed(self):
        assert self._looks_failed("fatal: not a git repository")
        assert self._looks_failed("fatal: ambiguous argument 'HEAD'")


# ── 模型层测试 ────────────────────────────────────────────────────────


class TestToolCallIsFailed:
    """测试 ToolCall.is_failed 和 has_nonzero_exit 属性。"""

    def _tc(self, **kwargs):
        from session_browser.domain.models import ToolCall
        defaults = {"name": "Bash", "status": "completed"}
        defaults.update(kwargs)
        return ToolCall(**defaults)

    @pytest.mark.contract_case("UI-SD-025")
    def test_completed_not_failed(self):
        tc = self._tc()
        assert not tc.is_failed

    @pytest.mark.contract_case("UI-SD-025")
    def test_error_status_is_failed(self):
        tc = self._tc(status="error")
        assert tc.is_failed

    @pytest.mark.contract_case("UI-SD-025")
    def test_exit_code_1_without_error_not_failed(self):
        tc = self._tc(exit_code=1)
        assert not tc.is_failed
        assert tc.has_nonzero_exit

    @pytest.mark.contract_case("UI-SD-025")
    def test_exit_code_0_not_failed(self):
        tc = self._tc(exit_code=0)
        assert not tc.is_failed
        assert not tc.has_nonzero_exit

    @pytest.mark.contract_case("UI-SD-025")
    def test_exit_code_2_with_error_status_failed(self):
        tc = self._tc(status="error", exit_code=2)
        assert tc.is_failed
        assert tc.has_nonzero_exit

    @pytest.mark.contract_case("UI-SD-025")
    def test_no_exit_code_not_has_nonzero_exit(self):
        tc = self._tc()
        assert not tc.has_nonzero_exit
