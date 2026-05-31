"""Claude Code specific attribution tests.

Verifies:
1. Claude Code can use provider usage input/output/cache_read/cache_write.
2. Fresh/cache read/cache write are correctly extracted.
3. Bucket tokens sum does not exceed total input.
4. Tool schemas estimation works with tool count.
"""

import json
import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.agents.claude_code import ClaudeCodeAttributionBuilder
from session_browser.attribution.contracts import ValuePrecision, ValueSource


def _make_lc(**kwargs):
    defaults = dict(
        id="cc-call-001", model="claude-sonnet-4", scope="main",
        subagent_id="", round_index=0, parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
        finish_reason="end_turn", content_blocks=[],
        response_full="", request_full="", tool_calls_raw="",
    )
    defaults.update(kwargs)
    return LLMCall(**defaults)


def _make_ro(user_content="hello", tool_calls=None, interactions=None):
    return ConversationRound(
        user_msg=ChatMessage(role="user", content=user_content, timestamp="2025-01-01T00:00:00Z"),
        assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        tool_calls=tool_calls or [],
        interactions=interactions or [],
    )


def test_claude_code_provider_usage_extracted():
    """Claude Code builder should extract provider usage values."""
    lc = _make_lc(input_tokens=8200, output_tokens=3000,
                   cache_read_tokens=88500, cache_write_tokens=3300)
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    # total_input = input + cache_read + cache_write
    assert result.total_input.value == 8200 + 88500 + 3300
    assert result.total_input.precision == ValuePrecision.PROVIDER_REPORTED
    assert result.total_input.source == ValueSource.PROVIDER_USAGE

    # fresh_input = input_tokens (non-cache)
    assert result.fresh_input.value == 8200
    assert result.fresh_input.precision == ValuePrecision.PROVIDER_REPORTED

    assert result.cache_read.value == 88500
    assert result.cache_read.precision == ValuePrecision.PROVIDER_REPORTED

    assert result.cache_write.value == 3300
    assert result.cache_write.precision == ValuePrecision.PROVIDER_REPORTED


def test_claude_code_bucket_sum_within_total():
    lc = _make_lc(input_tokens=8200, output_tokens=3000,
                   cache_read_tokens=88500, cache_write_tokens=3300)
    ro = _make_ro(user_content="test user message with some content")
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    total = result.total_input.value
    bucket_sum = sum(b.tokens for b in result.buckets)
    assert bucket_sum <= total


def test_claude_code_response_attribution():
    lc = _make_lc(output_tokens=3000, response_full="This is a response text",
                   content_blocks=[
                       {"type": "text", "content": "Hello world"},
                       {"type": "tool_use", "name": "Read", "id": "tu-001",
                        "parameters": {"file_path": "/tmp/test.py"}},
                   ])
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_response()

    assert result.total_output.value == 3000
    assert result.visible_text.value is not None
    assert result.visible_text.value > 0
    assert result.tool_use.value is not None
    assert result.finish_reason.value == "end_turn"


def test_claude_code_tool_schema_estimation_no_available_tools():
    """Without available_tools list, tool_schemas tokens must be 0.

    Tool schemas refers to available tool definitions, NOT observed tool calls.
    When local logs don't provide available_tools, we cannot generate positive
    tool_schemas tokens.
    """
    tc1 = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="result1")
    tc2 = ToolCall(name="Bash", parameters={"command": "echo hello"}, result="done")
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="do something", tool_calls=[tc1, tc2])
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    # Should have a tool_schemas bucket but with 0 tokens (unavailable)
    schema_bucket = next((b for b in result.buckets if b.key == "tool_schemas"), None)
    assert schema_bucket is not None
    assert schema_bucket.tokens == 0
    assert schema_bucket.precision == ValuePrecision.UNAVAILABLE


def test_claude_code_unlocated_residual_is_last_bucket():
    """unlocated_residual should always be the last bucket."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello")
    ctx = {"available_tools": ["Read", "Bash"]}
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    assert result.buckets[-1].key == "unlocated_residual"


def test_claude_code_tool_schema_from_available_tools():
    """When available_tools is provided, tool_schemas should use that count."""
    tc1 = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="result1")
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="do something", tool_calls=[tc1])
    # Provide available_tools via session_context
    session_context = {
        "available_tools": ["Read", "Bash", "Edit"],
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=session_context)
    result = builder.build_request()

    schema_bucket = next((b for b in result.buckets if b.key == "tool_schemas"), None)
    assert schema_bucket is not None
    # 3 available tools × 240 tokens/tool = 720
    assert schema_bucket.tokens == 3 * 240
    assert "3 tools" in schema_bucket.count_label


def test_claude_code_availability_rows():
    lc = _make_lc(input_tokens=5000, output_tokens=2000,
                   cache_read_tokens=3000, cache_write_tokens=500)
    ro = _make_ro(user_content="test")
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    fields = {
        r.field if hasattr(r, "field") else r["field"]
        for r in result.availability_rows
    }
    assert "total_input" in fields
    assert "fresh_input" in fields
    assert "cache_read" in fields
    assert "cache_write" in fields
