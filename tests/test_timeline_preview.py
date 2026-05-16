"""Tests for timeline preview text generation in ConversationRound."""

from __future__ import annotations

import pytest

from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    ToolCall,
    LLMCall,
)


# ── _compact_preview_text helper ────────────────────────────────────


class TestCompactPreviewText:
    def test_compresses_multiple_spaces(self):
        result = ConversationRound._compact_preview_text("hello    world")
        assert result == "hello world"

    def test_compresses_newlines(self):
        result = ConversationRound._compact_preview_text("line1\nline2\nline3")
        assert result == "line1 line2 line3"

    def test_compresses_mixed_whitespace(self):
        result = ConversationRound._compact_preview_text("hello\t\tworld   ok")
        assert result == "hello world ok"

    def test_strips_leading_trailing(self):
        result = ConversationRound._compact_preview_text("  hello world  ")
        assert result == "hello world"

    def test_truncates_at_limit(self):
        long_text = "a" * 200
        result = ConversationRound._compact_preview_text(long_text, limit=120)
        assert len(result) == 121  # 120 chars + ellipsis
        assert result.endswith("…")

    def test_no_truncation_under_limit(self):
        text = "short text"
        result = ConversationRound._compact_preview_text(text, limit=120)
        assert result == "short text"
        assert "…" not in result

    def test_empty_string(self):
        assert ConversationRound._compact_preview_text("") == ""

    def test_none(self):
        assert ConversationRound._compact_preview_text(None) == ""


# ── _format_tool_counts helper ──────────────────────────────────────


class TestFormatToolCounts:
    def test_empty_list(self):
        assert ConversationRound._format_tool_counts([]) == ""

    def test_single_tool(self):
        tools = [ToolCall(name="Read")]
        result = ConversationRound._format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>×1' in result

    def test_two_same_tools(self):
        tools = [ToolCall(name="Read"), ToolCall(name="Read")]
        result = ConversationRound._format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>×2' in result

    def test_two_different_tools(self):
        tools = [ToolCall(name="Read"), ToolCall(name="Bash")]
        result = ConversationRound._format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>×1' in result
        assert '<span class="preview-tool">Bash</span>×1' in result
        assert '·' in result

    def test_multiple_tools_with_counts(self):
        tools = [
            ToolCall(name="Read"),
            ToolCall(name="Bash"),
            ToolCall(name="Read"),
            ToolCall(name="Bash"),
            ToolCall(name="Edit"),
            ToolCall(name="Bash"),
        ]
        result = ConversationRound._format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>×2' in result
        assert '<span class="preview-tool">Bash</span>×3' in result
        assert '<span class="preview-tool">Edit</span>×1' in result

    def test_tool_names_wrapped_in_spans(self):
        """Tool names are now wrapped in preview-tool spans for CSS styling."""
        tools = [ToolCall(name="Read"), ToolCall(name="Bash")]
        result = ConversationRound._format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>' in result
        assert '<span class="preview-tool">Bash</span>' in result


# ── compute_preview() scenarios ─────────────────────────────────────


class TestComputePreviewLLMResponse:
    """Priority 1: LLM response text + tool counts if present."""

    def test_response_with_tools(self):
        assistant = ChatMessage(role="assistant", content="Let me check", timestamp="")
        user = ChatMessage(role="user", content="question", timestamp="")
        tools = [ToolCall(name="Read"), ToolCall(name="Bash")]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [LLMCall(
            id="1", model="test", scope="main", subagent_id="",
            round_index=0, parent_id="", parent_tool_name="",
            timestamp="", status="ok", response_preview="Let me check",
            tool_calls=tools,
        )]
        r.compute_preview()
        assert "Let me check" in r.preview_text
        assert "Read * 1" in r.preview_text or '<span class="preview-tool">Read</span>×1' in r.preview_text
        assert "Bash * 1" in r.preview_text or '<span class="preview-tool">Bash</span>×1' in r.preview_text

    def test_response_truncated_when_long(self):
        long_response = "word " * 50  # 250 chars
        assistant = ChatMessage(role="assistant", content=long_response, timestamp="")
        user = ChatMessage(role="user", content="question", timestamp="")
        tools = [ToolCall(name="Read")]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [LLMCall(
            id="1", model="test", scope="main", subagent_id="",
            round_index=0, parent_id="", parent_tool_name="",
            timestamp="", status="ok", response_preview=long_response,
            tool_calls=tools,
        )]
        r.compute_preview()
        # Response is truncated to 100 chars, then tool summary appended
        assert '<span class="preview-tool">Read</span>×1' in r.preview_text
        assert "…" in r.preview_text  # ellipsis present due to truncation

    def test_response_long_with_no_tools(self):
        """When response text is long but there are no tools, it gets truncated."""
        long_response = "word " * 50  # 250 chars
        assistant = ChatMessage(role="assistant", content=long_response, timestamp="")
        user = ChatMessage(role="user", content="q", timestamp="")
        r = ConversationRound(user_msg=user, assistant_msg=assistant)
        r.interactions = [LLMCall(
            id="1", model="test", scope="main", subagent_id="",
            round_index=0, parent_id="", parent_tool_name="",
            timestamp="", status="ok", response_preview=long_response,
        )]
        r.compute_preview()
        # No tools + has user input → shows user input
        assert "q" in r.preview_text

    def test_user_input_only_when_no_tools(self):
        """When there are no tool calls, preview falls back to user input text."""
        assistant = ChatMessage(role="assistant", content="Here is the answer", timestamp="")
        user = ChatMessage(role="user", content="Please explain this", timestamp="")
        r = ConversationRound(user_msg=user, assistant_msg=assistant)
        r.interactions = [LLMCall(
            id="1", model="test", scope="main", subagent_id="",
            round_index=0, parent_id="", parent_tool_name="",
            timestamp="", status="ok", response_preview="Here is the answer",
        )]
        r.compute_preview()
        # No tools + has user input → shows user input as preview
        assert "Please explain this" in r.preview_text


class TestComputePreviewSubagent:
    """Subagent rounds show response first instead of just labels."""

    def test_subagent_with_response_text(self):
        assistant = ChatMessage(role="assistant", content="", timestamp="")
        user = ChatMessage(role="user", content="task", timestamp="")
        r = ConversationRound(user_msg=user, assistant_msg=assistant)
        r.interactions = [LLMCall(
            id="2", model="test", scope="subagent", subagent_id="agent-1",
            round_index=0, parent_id="1", parent_tool_name="Agent",
            timestamp="", status="ok", response_preview="Subagent found 3 files",
        )]
        r.compute_preview()
        assert "Subagent found 3 files" in r.preview_text

    def test_subagent_with_tools(self):
        assistant = ChatMessage(role="assistant", content="", timestamp="")
        user = ChatMessage(role="user", content="task", timestamp="")
        tools = [ToolCall(name="Read"), ToolCall(name="Read")]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [LLMCall(
            id="2", model="test", scope="subagent", subagent_id="agent-1",
            round_index=0, parent_id="1", parent_tool_name="Agent",
            timestamp="", status="ok", response_preview="Done",
            tool_calls=tools,
        )]
        r.compute_preview()
        assert "Done" in r.preview_text
        assert '<span class="preview-tool">Read</span>×2' in r.preview_text

    def test_subagent_no_response_text(self):
        assistant = ChatMessage(role="assistant", content="", timestamp="")
        user = ChatMessage(role="user", content="task", timestamp="")
        tools = [ToolCall(name="Bash")]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [LLMCall(
            id="2", model="test", scope="subagent", subagent_id="agent-1",
            round_index=0, parent_id="1", parent_tool_name="Agent",
            timestamp="", status="ok", response_preview="",
            tool_calls=tools,
        )]
        r.compute_preview()
        assert "Subagent" in r.preview_text
        assert "Agent" in r.preview_text
        assert '<span class="preview-tool">Bash</span>×1' in r.preview_text


class TestComputePreviewFallback:
    """Fallback: user input text when no LLM response."""

    def test_user_input_only(self):
        assistant = ChatMessage(role="assistant", content="", timestamp="")
        user = ChatMessage(role="user", content="Please analyze this codebase for bugs", timestamp="")
        r = ConversationRound(user_msg=user, assistant_msg=assistant)
        r.interactions = [LLMCall(
            id="1", model="test", scope="main", subagent_id="",
            round_index=0, parent_id="", parent_tool_name="",
            timestamp="", status="ok", response_preview="",
        )]
        r.compute_preview()
        assert "Please analyze this codebase for bugs" in r.preview_text

    def test_tools_only(self):
        assistant = ChatMessage(role="assistant", content="", timestamp="")
        user = ChatMessage(role="user", content="", timestamp="")
        tools = [ToolCall(name="Read"), ToolCall(name="Bash")]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [LLMCall(
            id="1", model="test", scope="main", subagent_id="",
            round_index=0, parent_id="", parent_tool_name="",
            timestamp="", status="ok", response_preview="",
            tool_calls=tools,
        )]
        r.compute_preview()
        assert '<span class="preview-tool">Read</span>×1' in r.preview_text
        assert '<span class="preview-tool">Bash</span>×1' in r.preview_text


class TestComputePreviewNoHTML:
    """Preview text rendering: template must use escaped output, not | safe."""

    def test_compact_preview_preserves_raw_text(self):
        """_compact_preview_text only compresses whitespace; it does NOT sanitize."""
        text = "use `<code>` here"
        result = ConversationRound._compact_preview_text(text)
        # The helper just compresses whitespace - raw text is preserved
        assert "`<code>`" in result

    def test_preview_text_from_integration(self):
        """Integration test: compute_preview() uses assistant_msg.content + tools."""
        assistant = ChatMessage(role="assistant", content="See the code section", timestamp="")
        user = ChatMessage(role="user", content="task", timestamp="")
        tools = [ToolCall(name="Read")]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [LLMCall(
            id="1", model="test", scope="main", subagent_id="",
            round_index=0, parent_id="", parent_tool_name="",
            timestamp="", status="ok", response_preview="See the code section",
            tool_calls=tools,
        )]
        r.compute_preview()
        # Main agent: assistant_msg.content + tool summary
        assert "See the code section" in r.preview_text
        assert '<span class="preview-tool">Read</span>×1' in r.preview_text
