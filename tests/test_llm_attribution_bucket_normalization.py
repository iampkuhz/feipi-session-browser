"""Tests for LLM attribution bucket normalization.

Verifies:
1. Heuristic buckets sum cannot exceed total_input.
2. Hidden builtin / provider wrapper scaled down for small total.
3. Unlocated_residual computed correctly.
4. Coverage never exceeds 100%.
5. Measured buckets never scaled down.
6. Normalization with zero total_input.
7. Percentages recomputed after normalization.
"""

import pytest

from session_browser.attribution.contracts import RequestAttributionBucket
from session_browser.attribution.agents.claude_code import (
    normalize_request_reconstruction_buckets,
)
from session_browser.domain.models import LLMCall, ChatMessage, ConversationRound


def _make_bucket(key, tokens, **kwargs):
    """Helper to create a RequestAttributionBucket."""
    defaults = dict(label=key, tokens=tokens, percent=0.0)
    defaults.update(kwargs)
    return RequestAttributionBucket(key=key, **defaults)


# ── Heuristic bucket constraints ─────────────────────────────────────


def test_heuristic_buckets_sum_cannot_exceed_total_input():
    """Sum of measured + estimated + heuristic buckets must not exceed fresh_input."""
    buckets = [
        _make_bucket("current_user_message", 2000),
        _make_bucket("tool_schemas", 500),
        _make_bucket("local_instruction_context", 300),
        _make_bucket("hidden_builtin_system_estimate", 500),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 4000
    fresh_input = 3000  # less than measured + heuristic

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    measured = sum(b.tokens for b in buckets if b.key in ("current_user_message",))
    estimated = sum(b.tokens for b in buckets if b.key in ("local_instruction_context",))
    heuristic_fixed = sum(b.tokens for b in buckets if b.key == "tool_schemas")
    heuristic_scaled = sum(b.tokens for b in buckets if b.key == "hidden_builtin_system_estimate")

    # measured + estimated should fit within fresh_input (estimated is scaled)
    assert measured + estimated <= fresh_input
    # heuristic_fixed is scaled proportionally when budget exists but insufficient
    # budget = 3000 - 2000 - 300 = 700, heuristic_fixed_sum = 1000, scale = 700/1000 = 0.7
    assert heuristic_fixed + heuristic_scaled <= fresh_input - measured - estimated
    # Each bucket scaled: 500 * 0.7 = 350, total heuristic = 700
    assert heuristic_fixed == 350
    assert heuristic_scaled == 350


def test_hidden_builtin_scaled_down_for_small_total():
    """When fresh_input is very small, heuristic_fixed should be scaled down."""
    buckets = [
        _make_bucket("current_user_message", 1000),
        _make_bucket("hidden_builtin_system_estimate", 500),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 1500
    fresh_input = 1100  # barely above measured

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    hidden = next(b for b in buckets if b.key == "hidden_builtin_system_estimate")

    # Should be scaled down from 500
    assert hidden.tokens < 500


def test_heuristic_fixed_not_zeroed_when_no_budget():
    """When fresh_input equals measured, heuristic_fixed should keep values.

    Previously heuristic_fixed was zeroed when budget was exhausted.
    Now we preserve these values (e.g. tool_schemas represents real known
    token costs from SDK definitions) and let residual absorb the overflow.
    """
    buckets = [
        _make_bucket("current_user_message", 1000),
        _make_bucket("preceding_tool_results", 500),
        _make_bucket("hidden_builtin_system_estimate", 500),
        _make_bucket("tool_schemas", 300),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 2000
    fresh_input = 1500  # exactly measured, no room for heuristic

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    hidden = next(b for b in buckets if b.key == "hidden_builtin_system_estimate")
    tool_schemas = next(b for b in buckets if b.key == "tool_schemas")

    # heuristic_fixed buckets keep their original values
    assert hidden.tokens == 500
    assert tool_schemas.tokens == 300

    # residual absorbs the overflow (total=2000, known=1000+500+500+300=2300 > total)
    residual = next(b for b in buckets if b.key == "unlocated_residual")
    assert residual.tokens == 0  # max(2000 - 2300, 0) = 0


# ── Unlocated residual ───────────────────────────────────────────────


def test_unlocated_residual_computed_correctly():
    """unlocated_residual should be max(total_input - known_sum, 0)."""
    buckets = [
        _make_bucket("current_user_message", 1000),
        _make_bucket("tool_schemas", 500),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 3000
    fresh_input = 3000

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    residual = next(b for b in buckets if b.key == "unlocated_residual")
    known_sum = sum(b.tokens for b in buckets if b.key != "unlocated_residual")
    assert residual.tokens == max(total_input - known_sum, 0)


def test_unlocated_residual_non_negative():
    """unlocated_residual should never be negative."""
    buckets = [
        _make_bucket("current_user_message", 5000),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 3000  # less than measured!
    fresh_input = 3000

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    residual = next(b for b in buckets if b.key == "unlocated_residual")
    assert residual.tokens >= 0


# ── Coverage ─────────────────────────────────────────────────────────


def test_coverage_never_exceeds_100_percent():
    """Coverage (known/total) should never exceed 1.0 after normalization."""
    buckets = [
        _make_bucket("current_user_message", 1000),
        _make_bucket("tool_schemas", 500),
        _make_bucket("hidden_builtin_system_estimate", 500),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 2000
    fresh_input = 2000

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    contributing_sum = sum(
        b.tokens for b in buckets
        if b.key != "unlocated_residual" and b.contributes_to_total
    )
    coverage = contributing_sum / total_input if total_input > 0 else 0
    assert coverage <= 1.0


# ── Measured bucket protection ───────────────────────────────────────


def test_measured_buckets_never_scaled_down():
    """Measured buckets (current_user_message, preceding_tool_results, prior_conversation_messages)
    should never be scaled down regardless of budget constraints."""
    original_measured = 2000
    buckets = [
        _make_bucket("current_user_message", original_measured),
        _make_bucket("hidden_builtin_system_estimate", 500),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 2500
    fresh_input = 2100  # barely above measured

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    measured = next(b for b in buckets if b.key == "current_user_message")
    assert measured.tokens == original_measured


def test_measured_bucket_preceding_tool_results_preserved():
    """preceding_tool_results should not be scaled down."""
    buckets = [
        _make_bucket("preceding_tool_results", 1500),
        _make_bucket("hidden_builtin_system_estimate", 500),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 2500
    fresh_input = 1600

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    measured = next(b for b in buckets if b.key == "preceding_tool_results")
    assert measured.tokens == 1500


# ── Zero total_input ─────────────────────────────────────────────────


def test_normalization_with_zero_total_input():
    """Normalization should handle zero total_input without crashing."""
    buckets = [
        _make_bucket("current_user_message", 0),
        _make_bucket("hidden_builtin_system_estimate", 500),
        _make_bucket("unlocated_residual", 0),
    ]

    # Should not crash
    result = normalize_request_reconstruction_buckets(
        buckets, total_input=0, fresh_input=0,
    )
    assert result is not None


# ── Percentage recomputation ─────────────────────────────────────────


def test_percentages_recomputed_after_normalization():
    """Percentages should be recomputed to reflect new token values."""
    buckets = [
        _make_bucket("current_user_message", 1000, percent=50.0),
        _make_bucket("hidden_builtin_system_estimate", 500, percent=25.0),
        _make_bucket("unlocated_residual", 500, percent=25.0),
    ]

    total_input = 2000
    fresh_input = 2000

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    total_pct = sum(b.percent for b in buckets)
    assert abs(total_pct - 100.0) < 0.1  # should sum to ~100%


def test_percentages_valid_range():
    """All bucket percentages should be in [0, 100]."""
    buckets = [
        _make_bucket("current_user_message", 1000),
        _make_bucket("tool_schemas", 500),
        _make_bucket("local_instruction_context", 300),
        _make_bucket("hidden_builtin_system_estimate", 500),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 5000
    fresh_input = 3000

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    for b in buckets:
        assert 0 <= b.percent <= 100, f"Bucket {b.key} has invalid percent: {b.percent}"


# ── Estimated bucket scaling ──────────────────────────────────────────


def test_estimated_buckets_scaled_when_exceed_remaining():
    """Estimated buckets should be scaled proportionally when they exceed total_input budget."""
    buckets = [
        _make_bucket("current_user_message", 500),
        _make_bucket("local_instruction_context", 800),  # estimated
        _make_bucket("agent_subagent_prompt", 600),  # estimated
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 1200  # measured(500) + estimated(1400) = 1900 > total_input
    fresh_input = 1000  # fresh is small but estimated now uses total_input for budget

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    estimated_sum = sum(
        b.tokens for b in buckets
        if b.key in ("local_instruction_context", "agent_subagent_prompt")
    )
    # Estimated is now scaled against total_input: remaining = 1200 - 500 = 700
    remaining = total_input - 500
    assert estimated_sum <= remaining


# ── Edge cases ───────────────────────────────────────────────────────


def test_empty_buckets():
    """Empty bucket list should return unchanged."""
    result = normalize_request_reconstruction_buckets(
        [], total_input=1000, fresh_input=1000,
    )
    assert result == []


def test_single_bucket_no_normalization_needed():
    """Single bucket within budget should not be modified."""
    buckets = [
        _make_bucket("current_user_message", 1000),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 2000
    fresh_input = 2000

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    measured = next(b for b in buckets if b.key == "current_user_message")
    assert measured.tokens == 1000


def test_all_bucket_keys_classified():
    """All expected bucket keys should be classified by the normalization function."""
    from session_browser.attribution.agents.claude_code import (
        _MEASURED_BUCKET_KEYS,
        _ESTIMATED_BUCKET_KEYS,
        _HEURISTIC_FIXED_KEYS,
        _HEURISTIC_SCALED_KEYS,
    )

    all_known = (
        _MEASURED_BUCKET_KEYS | _ESTIMATED_BUCKET_KEYS |
        _HEURISTIC_FIXED_KEYS | _HEURISTIC_SCALED_KEYS
    )

    # Should include the expected keys
    assert "current_user_message" in _MEASURED_BUCKET_KEYS
    assert "preceding_tool_results" in _MEASURED_BUCKET_KEYS
    assert "tool_schemas" in _HEURISTIC_FIXED_KEYS  # moved from estimated
    assert "local_instruction_context" in _ESTIMATED_BUCKET_KEYS
    assert "hidden_builtin_system_estimate" in _HEURISTIC_FIXED_KEYS
    # provider_wrapper_estimate removed — now noted in attribution_notes instead
    assert "top_level_system_estimate" in _HEURISTIC_SCALED_KEYS


def test_estimated_bucket_details_scaled_proportionally():
    """When estimated buckets are scaled, their details.items tokens should also scale."""
    buckets = [
        _make_bucket(
            "current_user_message", 500,
        ),
        _make_bucket(
            "local_instruction_context", 800,
            details={
                "kind": "system_sources",
                "items": [
                    {"file_path": "CLAUDE.md", "tokens": 500, "preview": "test"},
                    {"file_path": "system-reminder", "tokens": 300},
                ],
            },
        ),
        _make_bucket("unlocated_residual", 0),
    ]

    # total_input < measured + estimated to trigger scaling
    total_input = 900
    fresh_input = 900

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    li_bucket = next(b for b in buckets if b.key == "local_instruction_context")
    # remaining = 900 - 500 = 400, scale = 400/800 = 0.5
    assert li_bucket.tokens == 400
    # Detail items should also be scaled proportionally
    items = li_bucket.details["items"]
    assert items[0]["tokens"] == 250  # 500 * 0.5
    assert items[1]["tokens"] == 150  # 300 * 0.5


def test_estimated_buckets_preserve_floor_with_content():
    """Estimated buckets with content should preserve original values when budget allows."""
    buckets = [
        _make_bucket("current_user_message", 1000),
        _make_bucket(
            "local_instruction_context", 200,
            content_preview="Some content here",
            details={
                "kind": "system_sources",
                "items": [{"file_path": "CLAUDE.md", "tokens": 200}],
            },
        ),
        _make_bucket("unlocated_residual", 0),
    ]

    # With the new total_input-based budget:
    # remaining = total_input(1200) - measured(1000) = 200 >= estimated(200)
    # So the estimated bucket is NOT scaled.
    total_input = 1200
    fresh_input = 1000  # fresh is small but estimated uses total_input now

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    li_bucket = next(b for b in buckets if b.key == "local_instruction_context")
    # Estimated bucket keeps original value since budget allows
    assert li_bucket.tokens == 200
    assert li_bucket.details["items"][0]["tokens"] == 200


def test_estimated_buckets_not_crushed_by_high_cache_hit():
    """Estimated buckets should not be crushed to 0 when cache hit rate is high.

    When most input is cached, fresh_input becomes small but total_input
    stays the same. Estimated buckets (CLAUDE.md, agent prompts) represent
    real content and should be preserved against total_input budget.
    """
    buckets = [
        _make_bucket("current_user_message", 2000),
        _make_bucket("preceding_tool_results", 3000),
        _make_bucket("local_instruction_context", 500),
        _make_bucket("tool_schemas", 800),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 10000
    fresh_input = 2000  # very small due to high cache hit rate

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    li_bucket = next(b for b in buckets if b.key == "local_instruction_context")
    # Should NOT be crushed to 0 or 1 — should keep original 500
    assert li_bucket.tokens == 500


def _make_full_lc(**kwargs):
    """Helper to create a full LLMCall for builder tests."""
    defaults = dict(
        id="test-1", scope="round", subagent_id="", round_index=0,
        parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=5000, output_tokens=100,
        cache_read_tokens=1000, cache_write_tokens=200,
        model="claude-sonnet-4-20250514",
        finish_reason="end_turn", content_blocks=[],
        response_full="", request_full="", tool_calls_raw="",
    )
    defaults.update(kwargs)
    return LLMCall(**defaults)


def test_tool_schemas_details_sorted():
    """Tool schemas details items should be sorted by name for stable display."""
    from session_browser.attribution.agents.claude_code import ClaudeCodeAttributionBuilder
    from session_browser.domain.models import LLMCall, ChatMessage, ConversationRound

    lc = _make_full_lc()
    ro = ConversationRound(
        round_index=0,
        user_msg=ChatMessage(role="user", content="hello", timestamp="2025-01-01T00:00:00Z"),
        assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        tool_calls=[],
        interactions=[lc],
    )
    session_context = {
        "available_tools": ["ZTool", "ATool", "MTool"],  # intentionally unsorted
        "prior_messages": [],
        "preceding_tool_results": [],
    }

    builder = ClaudeCodeAttributionBuilder(lc, ro, None, session_context)
    attr = builder.build_request()

    # Find tool_schemas bucket
    tool_bucket = next(b for b in attr.buckets if b.key == "tool_schemas")
    items = tool_bucket.details["items"]
    names = [item["name"] for item in items]
    assert names == sorted(names), f"Tool names not sorted: {names}"
