"""Tests for attribution serializers.

Verifies:
1. attributed_value_to_dict includes precision/source/fill_strategy.
2. request_attribution_to_payload contains coverage, unknown, captured_context_preview.
3. response_attribution_to_payload contains coverage, unknown, blocks, captured_output_preview.
4. Every AttributedValue in payload has precision/source/fill_strategy.
"""

import pytest

from session_browser.domain.models import LLMCall, ChatMessage, ConversationRound, ToolCall
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.attribution.serializers import (
    attributed_value_to_dict,
    request_attribution_to_payload,
    response_attribution_to_payload,
    attribution_error_to_payload,
)
from session_browser.attribution.contracts import (
    AttributedValue,
    LLMRequestAttribution,
    RequestAttributionBucket,
    ValuePrecision,
    ValueSource,
)


def _make_lc(**kwargs):
    defaults = dict(
        id="test-call-001", model="test-model", scope="main",
        subagent_id="", round_index=0, parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
        finish_reason="end_turn", content_blocks=[],
        response_full="", request_full="", tool_calls_raw="",
    )
    defaults.update(kwargs)
    return LLMCall(**defaults)


def _make_ro(user_content="hello", tool_calls=None):
    return ConversationRound(
        user_msg=ChatMessage(role="user", content=user_content, timestamp="2025-01-01T00:00:00Z"),
        assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        tool_calls=tool_calls or [],
        interactions=[],
    )


# ─── attributed_value_to_dict ──────────────────────────────────────────


def test_attributed_value_to_dict_has_all_fields():
    v = AttributedValue(
        value=1234, unit="tokens", precision=ValuePrecision.EXACT,
        source=ValueSource.PROVIDER_USAGE, fill_strategy="direct", note="test",
    )
    d = attributed_value_to_dict(v)
    assert d["value"] == 1234
    assert d["unit"] == "tokens"
    assert d["precision"] == "exact"
    assert d["source"] == "provider_usage"
    assert d["fill_strategy"] == "direct"
    assert d["note"] == "test"


def test_attributed_value_to_dict_none_value():
    v = AttributedValue(
        value=None, unit="tokens", precision=ValuePrecision.UNAVAILABLE,
        source=ValueSource.HEURISTIC, fill_strategy="unknown",
    )
    d = attributed_value_to_dict(v)
    assert d["value"] is None


# ─── request_attribution_to_payload ────────────────────────────────────


def test_request_payload_has_required_fields():
    lc = _make_lc(
        input_tokens=5000, output_tokens=2000,
        cache_read_tokens=3000, cache_write_tokens=500,
        request_preview="some preview",
    )
    ro = _make_ro(user_content="test user message content")
    attr = build_llm_request_attribution("claude_code", lc, ro)
    payload = request_attribution_to_payload(attr)

    assert payload["kind"] == "llm.request_attribution"
    assert payload["agent"] == "claude_code"
    assert payload["model"] == "test-model"
    assert "request_id" in payload
    assert "call_id" in payload
    assert "source_label" in payload
    assert "confidence_label" in payload
    assert payload["raw_body_available"] is False

    # Usage
    assert "usage" in payload
    usage = payload["usage"]
    assert "coverage" in usage
    assert "unknown" in usage
    assert "total_input" in usage
    assert "fresh_input" in usage
    assert "cache_read" in usage
    assert "cache_write" in usage

    # Buckets
    assert "buckets" in payload
    assert isinstance(payload["buckets"], list)

    # Additional fields
    assert "captured_context_preview" in payload
    assert "attribution_notes" in payload
    assert isinstance(payload["attribution_notes"], list)
    assert "availability_rows" in payload


def test_request_payload_attributed_values_have_provenance():
    """Every AttributedValue in the request payload must have precision/source/fill_strategy."""
    lc = _make_lc(
        input_tokens=5000, output_tokens=2000,
        cache_read_tokens=3000, cache_write_tokens=500,
    )
    ro = _make_ro(user_content="test user message")
    attr = build_llm_request_attribution("claude_code", lc, ro)
    payload = request_attribution_to_payload(attr)

    usage = payload["usage"]
    for key in ("total_input", "fresh_input", "cache_read", "cache_write", "coverage", "unknown"):
        val = usage[key]
        assert "precision" in val, f"{key} missing precision"
        assert "source" in val, f"{key} missing source"
        assert "fill_strategy" in val, f"{key} missing fill_strategy"


# ─── response_attribution_to_payload ───────────────────────────────────


def test_response_payload_has_required_fields():
    lc = _make_lc(
        output_tokens=3000,
        response_full="response text",
        response_preview="output preview",
        content_blocks=[
            {"type": "text", "content": "Hello world"},
            {"type": "tool_use", "name": "Read", "id": "tu-001",
             "parameters": {"file_path": "/tmp/test.py"}},
        ],
    )
    ro = _make_ro()
    attr = build_llm_response_attribution("claude_code", lc, ro)
    payload = response_attribution_to_payload(attr)

    assert payload["kind"] == "llm.response_attribution"
    assert payload["agent"] == "claude_code"
    assert "raw_body_available" in payload
    assert payload["raw_body_available"] is False

    # Usage
    assert "usage" in payload
    usage = payload["usage"]
    assert "coverage" in usage
    assert "unknown" in usage
    assert "total_output" in usage
    assert "visible_text" in usage
    assert "tool_use" in usage
    assert "metadata" in usage
    assert "finish_reason" in usage

    # Additional fields
    assert "buckets" in payload
    assert "blocks" in payload
    assert isinstance(payload["blocks"], list)
    assert "captured_output_preview" in payload
    assert "attribution_notes" in payload
    assert "availability_rows" in payload


def test_response_payload_attributed_values_have_provenance():
    """Every AttributedValue in response payload must have precision/source/fill_strategy."""
    lc = _make_lc(output_tokens=3000, response_full="response text")
    ro = _make_ro()
    attr = build_llm_response_attribution("claude_code", lc, ro)
    payload = response_attribution_to_payload(attr)

    usage = payload["usage"]
    for key in ("total_output", "visible_text", "tool_use", "metadata",
                "coverage", "unknown", "finish_reason"):
        val = usage[key]
        assert "precision" in val, f"{key} missing precision"
        assert "source" in val, f"{key} missing source"
        assert "fill_strategy" in val, f"{key} missing fill_strategy"


# ─── attribution_error_to_payload ──────────────────────────────────────


def test_error_payload_structure():
    err = attribution_error_to_payload(
        agent="claude_code",
        call_id="call-001",
        round_id="R1",
        error_type="ValueError",
        message="test error",
    )
    assert err["kind"] == "llm.attribution_error"
    assert err["agent"] == "claude_code"
    assert err["call_id"] == "call-001"
    assert err["round_id"] == "R1"
    assert err["error_type"] == "ValueError"
    assert err["message"] == "test error"
    assert "fallback" in err


# ─── Bucket serialization includes contributes_to_total ────────────────


def test_request_bucket_serialized_with_contributes_to_total():
    lc = _make_lc(input_tokens=10000, request_full="some context")
    ro = _make_ro(user_content="test")
    attr = build_llm_request_attribution("claude_code", lc, ro)
    payload = request_attribution_to_payload(attr)

    for b in payload["buckets"]:
        assert "contributes_to_total" in b, f"Bucket {b['key']} missing contributes_to_total"


def test_response_bucket_serialized_with_contributes_to_total():
    lc = _make_lc(
        output_tokens=3000,
        content_blocks=[
            {"type": "text", "content": "Hello"},
            {"type": "tool_use", "name": "Read", "id": "tu-001",
             "parameters": {"file_path": "/tmp/test.py"}},
        ],
    )
    ro = _make_ro()
    attr = build_llm_response_attribution("claude_code", lc, ro)
    payload = response_attribution_to_payload(attr)

    for b in payload["buckets"]:
        assert "contributes_to_total" in b, f"Bucket {b['key']} missing contributes_to_total"


def test_request_bucket_display_percent_normalized_and_capped():
    """UI bucket percentages should not inherit invalid builder denominators."""
    value = AttributedValue(
        value=100, unit="tokens", precision=ValuePrecision.ESTIMATED,
        source=ValueSource.HEURISTIC,
    )
    attr = LLMRequestAttribution(
        agent="claude_code",
        model="test-model",
        request_id="req-1",
        call_id="call-1",
        source_label="local logs",
        confidence_label="中",
        raw_body_available=False,
        total_input=value,
        fresh_input=value,
        cache_read=value,
        cache_write=value,
        coverage=AttributedValue(
            value=0.25, unit="ratio", precision=ValuePrecision.ESTIMATED,
            source=ValueSource.HEURISTIC,
        ),
        unknown=AttributedValue(
            value=200, unit="tokens", precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
        ),
        buckets=[
            RequestAttributionBucket(
                key="known", label="Known", tokens=100, percent=100.0,
            ),
            RequestAttributionBucket(
                key="unlocated_residual", label="未定位", tokens=200, percent=185.7,
                precision=ValuePrecision.RESIDUAL, source=ValueSource.RESIDUAL,
            ),
        ],
        captured_context_preview="",
        attribution_notes=[],
        availability_rows=[],
    )

    payload = request_attribution_to_payload(attr)
    residual = next(b for b in payload["buckets"] if b["key"] == "unlocated_residual")
    assert residual["raw_percent"] == 185.7
    assert 0 <= residual["percent"] <= 100
    assert sum(b["percent"] for b in payload["buckets"] if b["contributes_to_total"]) == 100.0


def test_response_tool_bucket_details_show_actual_command_not_schema():
    lc = _make_lc(
        output_tokens=120,
        finish_reason="tool_use",
        content_blocks=[
            {
                "type": "tool_use",
                "name": "Bash",
                "id": "tu-bash-001",
                "input": {"command": "pytest -q", "description": "Run tests"},
            },
        ],
    )
    attr = build_llm_response_attribution("claude_code", lc, _make_ro())
    payload = response_attribution_to_payload(attr)

    tool_bucket = next(b for b in payload["buckets"] if b["key"] == "tool_use")
    assert tool_bucket["label"] == "Tool command (total)"
    assert tool_bucket["details"]["kind"] == "tool_commands"
    assert tool_bucket["details"]["items"][0]["command_preview"] == "pytest -q"
    assert "total_schema_tokens" not in tool_bucket["details"]
    assert "description_preview" not in tool_bucket["details"]["items"][0]
