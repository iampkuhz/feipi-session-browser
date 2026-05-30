"""Deterministic contract tests: trace-row preview must not duplicate tool counts.

Ensures:
- A single trace-row never renders the same tool name+count twice.
- preview_text (text summary) does NOT contain HTML tool badges.
- tool_summary_html contains tool chips exactly once.
- Subagent rounds don't duplicate tool counts from multiple interactions.
"""

from __future__ import annotations

import pytest
import re
from session_browser.domain.models import (
    ConversationRound,
    ChatMessage,
    ToolCall,
    LLMCall,
)


def _tool(name: str, scope: str = "main") -> ToolCall:
    return ToolCall(name=name, scope=scope)


def _llm_call(
    scope: str = "main",
    response_preview: str = "",
    tool_calls: list[ToolCall] | None = None,
    round_index: int = 0,
) -> LLMCall:
    return LLMCall(
        id=f"call-{scope}-{round_index}",
        model="test-model",
        scope=scope,
        subagent_id="agent-1" if scope == "subagent" else "",
        round_index=round_index,
        parent_id="",
        parent_tool_name="",
        timestamp="2026-01-01T00:00:00Z",
        status="ok",
        response_preview=response_preview,
        tool_calls=tool_calls or [],
    )


class TestToolCountNoDuplication:
    """Tool counts must appear exactly once per round."""

    @pytest.mark.contract_case("UI-SD-019")
    def test_main_agent_single_tool_count(self):
        """Round with 2 Read + 1 Bash should show each tool name×count once."""
        r = ConversationRound(
            user_msg=ChatMessage(role="user", content="Help me", timestamp=""),
            assistant_msg=ChatMessage(
                role="assistant",
                content="Let me check the files",
                timestamp="",
                usage={"input_tokens": 1000, "output_tokens": 200},
            ),
            tool_calls=[_tool("Read"), _tool("Read"), _tool("Bash")],
        )
        r.interactions = [
            _llm_call(tool_calls=[_tool("Read"), _tool("Read"), _tool("Bash")]),
        ]
        r.compute_preview()

        # tool_summary_html 应包含每个工具恰好一次
        assert r.tool_summary_html.count("Read") == 1
        assert r.tool_summary_html.count("Bash") == 1
        assert "×2" in r.tool_summary_html  # 读取×2
        assert "×1" in r.tool_summary_html  # Bash×1

        # preview_text 不得包含工具徽章
        assert "preview-tool" not in r.preview_text
        assert "×2" not in r.preview_text
        assert "×1" not in r.preview_text

    @pytest.mark.contract_case("UI-SD-019")
    def test_subagent_single_tool_count(self):
        """Subagent round should not duplicate tools across interactions."""
        r = ConversationRound(
            user_msg=ChatMessage(role="user", content="Run agent", timestamp=""),
            assistant_msg=ChatMessage(role="assistant", content="", timestamp=""),
            tool_calls=[_tool("Read"), _tool("Bash"), _tool("Write")],
        )
        r.interactions = [
            _llm_call(
                scope="subagent",
                response_preview="I analyzed the codebase",
                tool_calls=[_tool("Read", "subagent"), _tool("Bash", "subagent")],
            ),
            _llm_call(
                scope="subagent",
                response_preview="Done",
                tool_calls=[_tool("Write", "subagent")],
            ),
        ]
        r.compute_preview()

        # 每个工具名在 tool_summary_html 中应最多出现一次
        for name in ["Read", "Bash", "Write"]:
            count = r.tool_summary_html.count(name)
            assert count <= 1, f"{name} appears {count} times in tool_summary_html"

        # preview_text 不应有工具徽章
        assert "preview-tool" not in r.preview_text

    @pytest.mark.contract_case("UI-SD-019")
    def test_no_tools_in_preview_text(self):
        """preview_text should contain user/assistant text, not tool counts."""
        r = ConversationRound(
            user_msg=ChatMessage(role="user", content="Fix the bug", timestamp=""),
            assistant_msg=ChatMessage(
                role="assistant", content="Found the issue", timestamp=""
            ),
            tool_calls=[_tool("Grep"), _tool("Read")],
        )
        r.interactions = [
            _llm_call(tool_calls=[_tool("Grep"), _tool("Read")]),
        ]
        r.compute_preview()

        assert "Fix the bug" not in r.preview_text  # 使用助手回复，而非用户消息
        assert "Found the issue" in r.preview_text
        assert "Grep" not in r.preview_text
        assert "Read" not in r.preview_text
        assert "×1" not in r.preview_text

    @pytest.mark.contract_case("UI-SD-019")
    def test_empty_tools(self):
        """无工具的轮次应有空的 tool_summary_html。"""
        r = ConversationRound(
            user_msg=ChatMessage(role="user", content="Hello", timestamp=""),
            assistant_msg=ChatMessage(
                role="assistant", content="Hi there!", timestamp=""
            ),
            tool_calls=[],
        )
        r.interactions = []
        r.compute_preview()

        assert r.tool_summary_html == ""
        assert "Hi there!" in r.preview_text

    @pytest.mark.contract_case("UI-SD-019")
    def test_user_only_no_tools(self):
        """仅用户消息无工具的轮次应显示用户文本。"""
        r = ConversationRound(
            user_msg=ChatMessage(
                role="user", content="Please explain this code", timestamp=""
            ),
            assistant_msg=ChatMessage(role="assistant", content="", timestamp=""),
            tool_calls=[],
        )
        r.interactions = []
        r.compute_preview()

        assert "explain this code" in r.preview_text
        assert r.tool_summary_html == ""

    @pytest.mark.contract_case("UI-SD-019")
    def test_preview_and_tool_summary_separated(self):
        """preview_text 是纯文本，tool_summary_html 包含工具 chips。"""
        r = ConversationRound(
            user_msg=ChatMessage(role="user", content="Test", timestamp=""),
            assistant_msg=ChatMessage(
                role="assistant", content="Response text", timestamp=""
            ),
            tool_calls=[_tool("Read"), _tool("Read")],
        )
        r.interactions = [_llm_call(tool_calls=[_tool("Read"), _tool("Read")])]
        r.compute_preview()

        assert "Response text" in r.preview_text
        assert "preview-tool" not in r.preview_text  # preview_text 是纯文本
        assert "preview-tool" in r.tool_summary_html  # tool_summary_html 包含 HTML
        assert "×2" in r.tool_summary_html


class TestPreviewDoesNotRepeatText:
    """preview_text 和次要内容不应互相重复。"""

    @pytest.mark.contract_case("UI-SD-019")
    def test_preview_no_html_badges(self):
        """preview_text 应为纯文本，无 HTML 工具徽章。"""
        r = ConversationRound(
            user_msg=ChatMessage(role="user", content="test", timestamp=""),
            assistant_msg=ChatMessage(
                role="assistant", content="answer", timestamp=""
            ),
            tool_calls=[_tool("Bash"), _tool("Read"), _tool("Read")],
        )
        r.interactions = [_llm_call(tool_calls=[_tool("Bash"), _tool("Read"), _tool("Read")])]
        r.compute_preview()

        assert "<span" not in r.preview_text
        assert "preview-tool" not in r.preview_text

    @pytest.mark.contract_case("UI-SD-019")
    def test_tool_summary_is_valid_html(self):
        """tool_summary_html 应包含 preview-tool span。"""
        r = ConversationRound(
            user_msg=ChatMessage(role="user", content="test", timestamp=""),
            assistant_msg=ChatMessage(
                role="assistant", content="answer", timestamp=""
            ),
            tool_calls=[_tool("Bash"), _tool("Read")],
        )
        r.interactions = [_llm_call(tool_calls=[_tool("Bash"), _tool("Read")])]
        r.compute_preview()

        assert '<span class="preview-tool">' in r.tool_summary_html
        assert "Bash" in r.tool_summary_html
        assert "Read" in r.tool_summary_html


class TestTraceRowDOMContract:
    """验证模板使用组件宏渲染 trace 行。"""

    @pytest.mark.contract_case("UI-SD-019")
    def test_template_uses_component_macros(self):
        """session.html 应使用 sdt.trace_round 宏渲染 trace 行。"""
        template_path = (
            __file__.rsplit("/", 1)[0]
            .rsplit("tests", 1)[0]
            + "src/session_browser/web/templates/session.html"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 使用 sdt.trace_round 宏封装 preview + detail
        assert "sdt.trace_round" in content, (
            "Template must use sdt.trace_round macro for trace rows"
        )
        # 将 round 对象传递给宏；preview 在视图模型中计算
        assert "for row in trace_rows" in content, (
            "Template must iterate over trace_rows"
        )
        assert "sdt.trace_round(row)" in content, (
            "Template must call sdt.trace_round(row) for each row"
        )

    @pytest.mark.contract_case("UI-SD-019")
    def test_normalized_trace_row_text_no_dup(self):
        """模拟：如果 preview_text + tool_summary_html 拼接，工具名×计数不应出现多次。"""
        r = ConversationRound(
            user_msg=ChatMessage(role="user", content="test", timestamp=""),
            assistant_msg=ChatMessage(
                role="assistant", content="Let me help", timestamp=""
            ),
            tool_calls=[
                _tool("Read"), _tool("Read"),
                _tool("Bash"),
                _tool("TaskCreate"),
            ],
        )
        r.interactions = [
            _llm_call(tool_calls=[
                _tool("Read"), _tool("Read"),
                _tool("Bash"),
                _tool("TaskCreate"),
            ]),
        ]
        r.compute_preview()

        combined = r.preview_text + " " + r.tool_summary_html
        for name, expected_count in [("Read", 1), ("Bash", 1), ("TaskCreate", 1)]:
            # 统计组合字符串中工具名的出现次数
            #（排除 HTML 标签内容——只统计纯文本出现次数）
            plain = re.sub(r'<[^>]+>', '', combined)
            occurrences = plain.count(name)
            assert occurrences <= expected_count, (
                f"{name} appears {occurrences} times in combined preview (expected {expected_count})"
            )
