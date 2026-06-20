"""Qoder 专属 attribution 测试。"""

import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.agents.qoder_attribution_builder import QoderAttributionBuilder
from session_browser.attribution.contracts import ValuePrecision, ValueSource
from session_browser.attribution.serializers import request_attribution_to_payload


def _make_lc(**kwargs):
    defaults = dict(
        id="qoder-call-001", model="qwen3.6-plus", scope="main",
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
    return {"normalized_call": {"call_id": "qoder-call-001", "source_units": list(units)}}


def test_qoder_cache_split_from_normalized():
    """Qoder 使用标准化后的真实 cache 数据。"""
    lc = _make_lc(input_tokens=500, cache_read_tokens=300, cache_write_tokens=50,
                   output_tokens=200)
    ro = _make_ro(user_content="test user message content here")
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.total_input.value == 850
    assert result.fresh_input.value == 500
    assert result.cache_read.value == 300
    assert result.cache_write.value == 50
    assert result.fresh_input.precision == ValuePrecision.PROVIDER_REPORTED
    assert result.cache_read.precision == ValuePrecision.PROVIDER_REPORTED
    assert result.cache_write.precision == ValuePrecision.PROVIDER_REPORTED


def test_qoder_zero_values_are_valid():
    """0 是有效值，availability 应显示为 available。"""
    lc = _make_lc(input_tokens=1000, cache_read_tokens=0, cache_write_tokens=0,
                   output_tokens=500)
    ro = _make_ro(user_content="test")
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.cache_read.value == 0
    assert result.cache_write.value == 0
    assert result.accounting_attribution["cache_read_tokens"]["tokens"] == 0
    assert result.accounting_attribution["cache_write_tokens"]["tokens"] == 0


def test_qoder_availability_notes_cache_from_usage():
    """availability rows 应反映真实的 cache 数据来源。"""
    lc = _make_lc(input_tokens=5000, cache_read_tokens=2000, cache_write_tokens=500,
                   output_tokens=1000)
    ro = _make_ro(user_content="test")
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_request()

    fields = {
        r.field if hasattr(r, "field") else r["field"]
        for r in result.availability_rows
    }
    assert fields == {"provider_usage", "normalized_source_units"}

    for row in result.availability_rows:
        if row.field == "provider_usage":
            assert row.available is True


def test_qoder_transcript_reconstruction():
    """没有 normalized source_units 时不再执行旧 transcript reconstruction。"""
    lc = _make_lc(input_tokens=10000, output_tokens=5000,
                   request_full="some request context\n\nmore context")
    ro = _make_ro(user_content="user prompt text here")
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.agent == "qoder"
    assert result.source_label == "normalized source_units unavailable"
    assert result.buckets[-1].key == "unlocated_residual"


def test_qoder_bucket_sum_within_total():
    lc = _make_lc(input_tokens=10000, output_tokens=5000,
                   request_full="context\n\nmore\n\ndata")
    ro = _make_ro(user_content="test user message")
    builder = QoderAttributionBuilder(
        lc,
        ro,
        session_context=_ctx(_unit("user_input", "request", "test user message")),
    )
    result = builder.build_request()

    total = result.total_input.value or 0
    bucket_sum = sum(b.tokens for b in result.buckets)
    assert bucket_sum <= total


def test_qoder_response_attribution():
    lc = _make_lc(output_tokens=3000, response_full="response text here",
                   content_blocks=[
                       {"type": "text", "content": "Hello"},
                       {"type": "tool_use", "name": "Read", "id": "tu-001",
                        "parameters": {"file_path": "/tmp/test.py"}},
                   ])
    ro = _make_ro()
    builder = QoderAttributionBuilder(
        lc,
        ro,
        session_context=_ctx(
            _unit("assistant_output", "response", "Hello"),
            _unit("tool_calls", "response", "Read({\"file_path\":\"/tmp/test.py\"})", 2),
        ),
    )
    result = builder.build_response()

    assert result.agent == "qoder"
    assert result.total_output.value == 3000
    assert result.visible_text.value is not None
    assert result.visible_text.value > 0


def test_qoder_full_messages_are_request_buckets_cache_read_is_summary_only():
    lc = _make_lc(input_tokens=2000, cache_read_tokens=3000, cache_write_tokens=0)
    ro = _make_ro(user_content="current task")
    builder = QoderAttributionBuilder(
        lc,
        ro,
        session_context={
            "full_messages_array": [
                {
                    "role": "user",
                    "content_type": "user_text",
                    "content_preview": "prior user",
                    "content_token_estimate": 120,
                    "message_index": 0,
                    "has_full_content": True,
                },
                {
                    "role": "assistant",
                    "content_type": "tool_use",
                    "tool_name": "Bash",
                    "content_preview": "Bash command",
                    "content_token_estimate": 180,
                    "message_index": 1,
                    "has_full_content": True,
                },
            ],
            "available_tools": [],
            **_ctx(
                _unit("conversation_history", "request", "prior user", 1),
                _unit("tool_calls", "response", "Bash command", 2),
            ),
        },
    )

    result = builder.build_request()
    messages = next((b for b in result.buckets if b.key == "conversation_messages"), None)
    cache = next((b for b in result.buckets if b.key == "provider_cached_context"), None)
    payload = request_attribution_to_payload(result)

    assert result.total_input.value == 5000
    assert result.fresh_input.value == 2000
    assert result.cache_read.value == 3000
    assert messages is not None
    assert messages.details["kind"] == "source_units"
    assert cache is None
    assert all(b["key"] != "provider_cached_context" for b in payload["buckets"])
    assert payload["coverage"]["input_side_component_total"] == 5000
    assert payload["coverage"]["request_content_denominator"] == 2000
    assert payload["coverage"]["accounting_cache_read_tokens"] == 3000
    assert result.coverage.value is not None
    assert 0 <= result.coverage.value <= 1


def test_qoder_request_full_tool_result_is_not_captured_context():
    request_full = "Tool result for call_1:\n" + ("tool output body " * 80)
    lc = _make_lc(input_tokens=2500, request_full=request_full)
    ro = _make_ro(user_content="")
    builder = QoderAttributionBuilder(
        lc,
        ro,
        session_context={
            "available_tools": [],
            **_ctx(_unit("tool_results", "request", "tool output body " * 80)),
        },
    )

    result = builder.build_request()
    tool_results = next((b for b in result.buckets if b.key == "tool_result_context"), None)
    captured = next((b for b in result.buckets if b.key == "captured_context_fragment"), None)

    assert tool_results is not None
    assert tool_results.tokens > 0
    assert tool_results.source == ValueSource.TRANSCRIPT
    assert captured is None or "tool output body" not in (captured.content_preview or "")


def test_qoder_tool_schema_uses_claude_like_default_registry():
    lc = _make_lc(input_tokens=20000)
    ro = _make_ro(user_content="task")
    builder = QoderAttributionBuilder(
        lc,
        ro,
        session_context={
            "available_tools": ["Skill"],
            **_ctx(_unit("tool_definitions", "request", "Skill tool schema")),
        },
    )

    result = builder.build_request()
    tool_definitions = next((b for b in result.buckets if b.key == "tool_definitions"), None)

    assert tool_definitions is not None
    assert tool_definitions.details["kind"] == "source_units"
    assert any(item["unit_type"] == "tool_definitions_unit" for item in tool_definitions.details["items"])


def test_qoder_availability_notes_zero_cache_from_usage():
    """availability rows 应反映真实的 usage 数据，0 也是有效值。"""
    lc = _make_lc(input_tokens=5000, cache_read_tokens=0, cache_write_tokens=0)
    ro = _make_ro(user_content="test")
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_request()

    fields = {
        r.field if hasattr(r, "field") else r["field"]
        for r in result.availability_rows
    }
    assert fields == {"provider_usage", "normalized_source_units"}

    for row in result.availability_rows:
        if row.field == "provider_usage":
            assert row.available is True
