"""Claude Code 专属 attribution 测试。"""

import json
import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.agents.claude_code_attribution_builder import ClaudeCodeAttributionBuilder
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


def _unit(candidate: str, direction: str, text: str, index: int = 1) -> dict:
    return {
        "source_id": f"test:{direction}:{candidate}:{index}",
        "dedupe_key": f"dedupe:{direction}:{candidate}:{index}",
        "origin_path": f"fixture.{candidate}",
        "canonical_source_locator": f"fixture:{candidate}:{index}",
        "unit_type": f"{candidate}_unit",
        "candidate": candidate,
        "direction": direction,
        "event_order": 1,
        "part_index": index,
        "byte_range": [0, len(text.encode("utf-8"))],
        "text": text,
        "label": candidate,
        "preview": text[:120],
    }


def _ctx(*units: dict) -> dict:
    return {"normalized_call": {"call_id": "cc-call-001", "source_units": list(units)}}


def test_claude_code_provider_usage_extracted():
    """Claude Code builder 应提取 provider usage。"""
    lc = _make_lc(input_tokens=8200, output_tokens=3000,
                   cache_read_tokens=88500, cache_write_tokens=3300)
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.total_input.value == 8200 + 88500 + 3300
    assert result.total_input.precision == ValuePrecision.PROVIDER_REPORTED
    assert result.total_input.source == ValueSource.PROVIDER_USAGE

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
    builder = ClaudeCodeAttributionBuilder(
        lc,
        ro,
        session_context=_ctx(
            _unit("assistant_output", "response", "Hello world"),
            _unit("tool_calls", "response", "Read({\"file_path\":\"/tmp/test.py\"})", 2),
        ),
    )
    result = builder.build_response()

    assert result.total_output.value == 3000
    assert result.visible_text.value is not None
    assert result.visible_text.value > 0
    assert result.tool_use.value is not None
    assert result.finish_reason.value == "end_turn"


def test_claude_code_tool_schema_estimation_no_available_tools():
    """没有 normalized source_units 时不再使用旧工具定义 fallback。"""
    tc1 = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="result1")
    tc2 = ToolCall(name="Bash", parameters={"command": "echo hello"}, result="done")
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="do something", tool_calls=[tc1, tc2])
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    schema_bucket = next((b for b in result.buckets if b.key == "tool_definitions"), None)
    assert schema_bucket is None
    assert result.source_label == "normalized source_units unavailable"


def test_claude_code_unlocated_residual_is_last_bucket():
    """unlocated_residual 仍保持在兼容 bucket 列表末尾。"""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello")
    ctx = _ctx(_unit("user_input", "request", "hello"))
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    assert result.buckets[-1].key == "unlocated_residual"


def test_claude_code_tool_schema_from_available_tools():
    """工具定义必须来自 normalized source_units，而不是旧 available_tools fallback。"""
    tc1 = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="result1")
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="do something", tool_calls=[tc1])
    session_context = {
        **_ctx(_unit("tool_definitions", "request", "Read Bash Edit tool schema")),
        "available_tools": ["Read", "Bash", "Edit"],
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=session_context)
    result = builder.build_request()

    schema_bucket = next((b for b in result.buckets if b.key == "tool_definitions"), None)
    assert schema_bucket is not None
    assert any(
        item["candidate"] == "tool_definitions"
        for item in result.accounting_attribution["fresh_input_tokens"]["candidates"]
    )


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
    assert fields == {"provider_usage", "normalized_source_units"}
    assert result.accounting_attribution["field_order"] == [
        "fresh_input_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "output_tokens",
    ]
