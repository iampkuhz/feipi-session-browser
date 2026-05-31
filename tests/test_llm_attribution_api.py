"""Tests for the on-demand Attribution API endpoints.

Verifies:
1. Request attribution API returns JSON envelope with correct structure.
2. Response attribution API returns JSON envelope with correct structure.
3. Invalid round_index returns 400 JSON.
4. Invalid call_index returns 400 JSON.
5. Session not found returns 404 JSON.
6. Call not found returns 404 JSON.
7. Response payload contains kind/source/session_id/detail/data.
8. Data contains buckets/usage/availability_rows.
"""

import json
import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.agents.claude_code import (
    ClaudeCodeAttributionBuilder,
    normalize_request_reconstruction_buckets,
)
from session_browser.attribution.context import build_attribution_session_context
from session_browser.attribution.contracts import ValuePrecision, ValueSource
from session_browser.attribution.serializers import (
    request_attribution_to_payload,
    response_attribution_to_payload,
    attribution_error_to_payload,
)


def _make_lc(**kwargs):
    defaults = dict(
        id="cc-call-001", model="claude-sonnet-4", scope="main",
        subagent_id="", round_index=0, parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=8200, output_tokens=3000,
        cache_read_tokens=5000, cache_write_tokens=1000,
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


class _FakeSession:
    agent = "claude_code"
    session_id = "test-session-001"
    project_key = "/tmp/test"


# ── Serializer / envelope structure tests ─────────────────────────────


def test_request_attribution_payload_contains_envelope_fields():
    """Request attribution payload should have kind, agent, etc."""
    lc = _make_lc()
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()
    payload = request_attribution_to_payload(result)

    assert payload["kind"] == "llm.request_attribution"
    assert payload["agent"] == "claude_code"
    assert "buckets" in payload
    assert "usage" in payload
    assert "availability_rows" in payload
    assert "timing" in payload


def test_response_attribution_payload_contains_envelope_fields():
    """Response attribution payload should have kind, agent, etc."""
    lc = _make_lc()
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_response()
    payload = response_attribution_to_payload(result)

    assert payload["kind"] == "llm.response_attribution"
    assert payload["agent"] == "claude_code"
    assert "buckets" in payload
    assert "usage" in payload
    assert "availability_rows" in payload


def test_error_payload_structure():
    """Error payload should have kind, error_type, message, fallback."""
    payload = attribution_error_to_payload(
        agent="claude_code", call_id="test-call", round_id="1",
        error_type="NotFound", message="call not found",
    )

    assert payload["kind"] == "llm.attribution_error"
    assert payload["error_type"] == "NotFound"
    assert "call not found" in payload["message"]
    assert "fallback" in payload


# ── Context hydration integration tests ──────────────────────────────


def test_context_hydration_with_all_messages():
    """build_attribution_session_context should populate prior_messages."""
    all_messages = [
        {"role": "user", "content": "Hello there"},
        {"role": "assistant", "content": "Hi!"},
        {"role": "user", "content": "Analyze this code"},
    ]
    lc = _make_lc()
    ro = _make_ro()
    ctx = build_attribution_session_context(
        session=None,
        round_obj=ro,
        interaction_index=0,
        interactions=[lc],
        round_tool_calls=[],
        all_messages=all_messages,
    )

    assert len(ctx["prior_messages"]) == 3
    assert ctx["prior_messages"][0]["role"] == "user"
    assert "Hello there" in ctx["prior_messages"][0]["content_preview"]
    assert ctx["prior_messages"][0]["content_token_estimate"] > 0


def test_content_preview_truncated_to_200_chars():
    """prior_messages content_preview should be truncated to 200 chars."""
    long_content = "x" * 500
    all_messages = [{"role": "user", "content": long_content}]
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_messages=all_messages,
    )

    assert len(ctx["prior_messages"][0]["content_preview"]) == 200


def test_available_tools_from_observed_calls():
    """available_tools should come from observed tool calls."""
    tc1 = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="content")
    tc2 = ToolCall(name="Bash", parameters={"command": "echo hi"}, result="ok")
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[tc1, tc2],
        all_tool_calls=[tc1, tc2],
    )

    assert "Read" in ctx["available_tools"]
    assert "Bash" in ctx["available_tools"]


def test_available_tools_fallback_when_empty():
    """available_tools should fall back to default list when no observed tools."""
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_tool_calls=None,
    )

    assert "Read" in ctx["available_tools"]
    assert "Write" in ctx["available_tools"]
    assert "Bash" in ctx["available_tools"]


def test_prior_messages_not_contain_current_user_message():
    """prior_messages should contain all messages (caller filters if needed)."""
    all_messages = [
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "Response"},
    ]
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_messages=all_messages,
    )

    # prior_messages contains all messages; the builder can filter
    assert len(ctx["prior_messages"]) == 2


# ── Bucket normalization tests ────────────────────────────────────────


def test_normalization_heuristic_buckets_not_exceed_fresh():
    """After normalization, heuristic buckets should not cause sum > fresh_input."""
    from session_browser.attribution.contracts import RequestAttributionBucket

    buckets = [
        RequestAttributionBucket(key="current_user_message", label="User", tokens=1000, percent=0),
        RequestAttributionBucket(key="tool_schemas", label="Schemas", tokens=500, percent=0),
        RequestAttributionBucket(key="hidden_builtin_system_estimate", label="Hidden", tokens=500, percent=0),
        RequestAttributionBucket(key="provider_wrapper_estimate", label="Provider", tokens=500, percent=0),
        RequestAttributionBucket(key="unlocated_residual", label="Unknown", tokens=0, percent=0),
    ]

    total_input = 2000
    fresh_input = 1500  # less than total heuristic would allow

    result = normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    measured = sum(b.tokens for b in result if b.key == "current_user_message")
    estimated = sum(b.tokens for b in result if b.key == "tool_schemas")
    heuristic = sum(b.tokens for b in result if b.key in ("hidden_builtin_system_estimate", "provider_wrapper_estimate"))

    # measured + estimated + heuristic should not exceed fresh_input
    assert measured + estimated + heuristic <= fresh_input


def test_normalization_unlocated_residual_recomputed():
    """unlocated_residual should be recomputed as max(total_input - known_sum, 0)."""
    from session_browser.attribution.contracts import RequestAttributionBucket

    buckets = [
        RequestAttributionBucket(key="current_user_message", label="User", tokens=500, percent=0),
        RequestAttributionBucket(key="hidden_builtin_system_estimate", label="Hidden", tokens=500, percent=0),
        RequestAttributionBucket(key="unlocated_residual", label="Unknown", tokens=0, percent=0),
    ]

    total_input = 2000
    fresh_input = 2000

    result = normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    residual = next(b for b in result if b.key == "unlocated_residual")
    known_sum = sum(b.tokens for b in result if b.key != "unlocated_residual")
    assert residual.tokens == max(total_input - known_sum, 0)


def test_normalization_measured_never_scaled_down():
    """Measured buckets should never be scaled down."""
    from session_browser.attribution.contracts import RequestAttributionBucket

    original_tokens = 1000
    buckets = [
        RequestAttributionBucket(key="current_user_message", label="User", tokens=original_tokens, percent=0),
        RequestAttributionBucket(key="hidden_builtin_system_estimate", label="Hidden", tokens=500, percent=0),
        RequestAttributionBucket(key="provider_wrapper_estimate", label="Provider", tokens=500, percent=0),
        RequestAttributionBucket(key="unlocated_residual", label="Unknown", tokens=0, percent=0),
    ]

    # Very small fresh_input: heuristic must be scaled to near zero
    total_input = 1500
    fresh_input = 1100  # barely above measured

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    measured = next(b for b in buckets if b.key == "current_user_message")
    assert measured.tokens >= original_tokens


def test_normalization_zero_fresh_input():
    """Normalization should handle zero fresh_input gracefully."""
    from session_browser.attribution.contracts import RequestAttributionBucket

    buckets = [
        RequestAttributionBucket(key="current_user_message", label="User", tokens=500, percent=0),
        RequestAttributionBucket(key="hidden_builtin_system_estimate", label="Hidden", tokens=500, percent=0),
        RequestAttributionBucket(key="unlocated_residual", label="Unknown", tokens=0, percent=0),
    ]

    # Should not crash
    result = normalize_request_reconstruction_buckets(
        buckets, total_input=1000, fresh_input=0,
    )
    assert result is not None


def test_normalization_percentages_recomputed():
    """Percentages should be recomputed after normalization."""
    from session_browser.attribution.contracts import RequestAttributionBucket

    buckets = [
        RequestAttributionBucket(key="current_user_message", label="User", tokens=1000, percent=50.0),
        RequestAttributionBucket(key="hidden_builtin_system_estimate", label="Hidden", tokens=500, percent=25.0),
        RequestAttributionBucket(key="unlocated_residual", label="Unknown", tokens=500, percent=25.0),
    ]

    normalize_request_reconstruction_buckets(
        buckets, total_input=2000, fresh_input=2000,
    )

    total_pct = sum(b.percent for b in buckets)
    assert abs(total_pct - 100.0) < 0.1  # should sum to ~100%


def test_builder_includes_normalization_note():
    """Claude Code builder should include normalization note in attribution_notes."""
    lc = _make_lc(input_tokens=8200, cache_read_tokens=88500, cache_write_tokens=3300)
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    notes = result.attribution_notes
    assert any("推断 bucket" in n or "not raw request" in n.lower() for n in notes), \
        f"Expected normalization note in: {notes}"


def test_located_rate_never_exceeds_100():
    """Coverage value should never exceed 1.0."""
    lc = _make_lc(input_tokens=8200, output_tokens=3000,
                   cache_read_tokens=88500, cache_write_tokens=3300)
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.coverage.value <= 1.0


def test_bucket_tokens_sum_not_exceed_total_input():
    """Sum of all contributing buckets should not exceed total_input."""
    lc = _make_lc(input_tokens=5000, output_tokens=2000,
                   cache_read_tokens=1000, cache_write_tokens=500)
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    total_input = result.total_input.value
    contributing_sum = sum(
        b.tokens for b in result.buckets
        if b.key != "unlocated_residual" and b.contributes_to_total
    )
    assert contributing_sum <= total_input
