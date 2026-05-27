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

        # tool_summary_html should have each tool exactly once
        assert r.tool_summary_html.count("Read") == 1
        assert r.tool_summary_html.count("Bash") == 1
        assert "×2" in r.tool_summary_html  # Read×2
        assert "×1" in r.tool_summary_html  # Bash×1

        # preview_text must NOT contain tool badges
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

        # Each tool name should appear at most once in tool_summary_html
        for name in ["Read", "Bash", "Write"]:
            count = r.tool_summary_html.count(name)
            assert count <= 1, f"{name} appears {count} times in tool_summary_html"

        # preview_text should NOT have tool badges
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

        assert "Fix the bug" not in r.preview_text  # uses assistant response, not user
        assert "Found the issue" in r.preview_text
        assert "Grep" not in r.preview_text
        assert "Read" not in r.preview_text
        assert "×1" not in r.preview_text

    @pytest.mark.contract_case("UI-SD-019")
    def test_empty_tools(self):
        """Round with no tools should have empty tool_summary_html."""
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
        """Round with only user message (no assistant response) should show user text."""
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
    def test_legacy_format_preserved(self):
        """preview_text_legacy should preserve old HTML-embedded format."""
        r = ConversationRound(
            user_msg=ChatMessage(role="user", content="Test", timestamp=""),
            assistant_msg=ChatMessage(
                role="assistant", content="Response text", timestamp=""
            ),
            tool_calls=[_tool("Read"), _tool("Read")],
        )
        r.interactions = [_llm_call(tool_calls=[_tool("Read"), _tool("Read")])]
        r.compute_preview()

        assert "Response text" in r.preview_text_legacy
        assert "preview-tool" in r.preview_text_legacy  # legacy has HTML
        assert "×2" in r.preview_text_legacy


class TestPreviewDoesNotRepeatText:
    """preview_text and secondary content should not repeat each other."""

    @pytest.mark.contract_case("UI-SD-019")
    def test_preview_no_html_badges(self):
        """preview_text must be plain text, no HTML tool badges."""
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
        """tool_summary_html should contain preview-tool spans."""
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
    """Verify v9 template uses component macros for trace rows."""

    @pytest.mark.contract_case("UI-SD-019")
    def test_template_uses_component_macros(self):
        """session.html must use sdt.trace_round macro for trace rows."""
        template_path = (
            __file__.rsplit("/", 1)[0]
            .rsplit("tests", 1)[0]
            + "src/session_browser/web/templates/session.html"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # v9 uses sdt.trace_round macro which encapsulates preview + detail
        assert "sdt.trace_round" in content, (
            "Template must use sdt.trace_round macro for trace rows"
        )
        # v9 passes round object to macro; preview computed in view model
        assert "for row in trace_rows" in content, (
            "Template must iterate over trace_rows"
        )
        assert "sdt.trace_round(row)" in content, (
            "Template must call sdt.trace_round(row) for each row"
        )

    @pytest.mark.contract_case("UI-SD-019")
    def test_normalized_trace_row_text_no_dup(self):
        """Simulated: if preview_text + tool_summary_html were concatenated,
        no tool name×count should appear more than once."""
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
            # Count occurrences of the tool name in the combined string
            # (excluding HTML tag content — just count plain occurrences)
            plain = re.sub(r'<[^>]+>', '', combined)
            occurrences = plain.count(name)
            assert occurrences <= expected_count, (
                f"{name} appears {occurrences} times in combined preview (expected {expected_count})"
            )
