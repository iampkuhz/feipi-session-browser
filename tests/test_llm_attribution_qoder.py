"""Qoder specific attribution tests.

Verifies:
1. Qoder 使用标准化后的真实 usage 数据（fresh/cache_read/cache_write）。
2. Qoder uses transcript-level reconstruction for semantic buckets.
3. Bucket tokens sum does not exceed total input.
4. 0 值是有效值，不显示为 unavailable。
"""

import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.agents.qoder import QoderAttributionBuilder
from session_browser.attribution.contracts import ValuePrecision


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


def test_qoder_cache_split_from_normalized():
    """Qoder 使用标准化后的真实 cache 数据。"""
    lc = _make_lc(input_tokens=500, cache_read_tokens=300, cache_write_tokens=50,
                   output_tokens=200)
    ro = _make_ro(user_content="test user message content here")
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_request()

    # total = fresh + cache_read + cache_write = 500 + 300 + 50 = 850
    assert result.total_input.value == 850
    assert result.fresh_input.value == 500
    assert result.cache_read.value == 300
    assert result.cache_write.value == 50
    # 所有值都是 provider_reported
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

    # 0 值应显示为 valid
    assert result.cache_read.value == 0
    assert result.cache_write.value == 0
    # availability rows 应显示为 available
    for row in result.availability_rows:
        field_val = row.field if hasattr(row, "field") else row["field"]
        avail_val = row.available if hasattr(row, "available") else row["available"]
        if field_val in ("fresh_input", "cache_read", "cache_write"):
            assert avail_val is True  # 有 usage 数据，0 也是有效值


def test_qoder_availability_notes_cache_from_usage():
    """Availability rows 应反映真实的 cache 数据来源。"""
    lc = _make_lc(input_tokens=5000, cache_read_tokens=2000, cache_write_tokens=500,
                   output_tokens=1000)
    ro = _make_ro(user_content="test")
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_request()

    fields = {
        r.field if hasattr(r, "field") else r["field"]
        for r in result.availability_rows
    }
    assert "fresh_input" in fields
    assert "cache_read" in fields
    assert "cache_write" in fields

    # 有 usage 数据时，availability 应显示为 available
    for row in result.availability_rows:
        field_val = row.field if hasattr(row, "field") else row["field"]
        avail_val = row.available if hasattr(row, "available") else row["available"]
        if field_val in ("fresh_input", "cache_read", "cache_write"):
            assert avail_val is True


def test_qoder_transcript_reconstruction():
    """Qoder should reconstruct from transcript."""
    lc = _make_lc(input_tokens=10000, output_tokens=5000,
                   request_full="some request context\n\nmore context")
    ro = _make_ro(user_content="user prompt text here")
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.agent == "qoder"
    assert result.source_label == "transcript"
    # Should have buckets even without exact values
    assert len(result.buckets) > 0


def test_qoder_bucket_sum_within_total():
    lc = _make_lc(input_tokens=10000, output_tokens=5000,
                   request_full="context\n\nmore\n\ndata")
    ro = _make_ro(user_content="test user message")
    builder = QoderAttributionBuilder(lc, ro)
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
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_response()

    assert result.agent == "qoder"
    assert result.total_output.value == 3000
    assert result.visible_text.value is not None
    assert result.visible_text.value > 0


def test_qoder_availability_notes_cache_from_usage():
    """Availability rows 应反映真实的 usage 数据，0 也是有效值。"""
    lc = _make_lc(input_tokens=5000, cache_read_tokens=0, cache_write_tokens=0)
    ro = _make_ro(user_content="test")
    builder = QoderAttributionBuilder(lc, ro)
    result = builder.build_request()

    fields = {
        r.field if hasattr(r, "field") else r["field"]
        for r in result.availability_rows
    }
    assert "fresh_input" in fields
    assert "cache_read" in fields
    assert "cache_write" in fields

    # 有 usage 数据时，availability 应显示为 available（0 也是有效值）
    for row in result.availability_rows:
        field_val = row.field if hasattr(row, "field") else row["field"]
        avail_val = row.available if hasattr(row, "available") else row["available"]
        if field_val in ("fresh_input", "cache_read", "cache_write"):
            assert avail_val is True
