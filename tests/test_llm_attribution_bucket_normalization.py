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
    estimated = sum(b.tokens for b in buckets if b.key in ("tool_schemas", "local_instruction_context"))
    heuristic = sum(b.tokens for b in buckets if b.key == "hidden_builtin_system_estimate")

    assert measured + estimated + heuristic <= fresh_input


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


def test_heuristic_scaled_to_zero_when_no_budget():
    """When fresh_input equals measured, heuristic should be zero."""
    buckets = [
        _make_bucket("current_user_message", 1000),
        _make_bucket("preceding_tool_results", 500),
        _make_bucket("hidden_builtin_system_estimate", 500),
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 1500
    fresh_input = 1500  # exactly measured, no room for heuristic

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    hidden = next(b for b in buckets if b.key == "hidden_builtin_system_estimate")

    assert hidden.tokens == 0


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
    """Estimated buckets should be scaled proportionally when they exceed remaining budget."""
    buckets = [
        _make_bucket("current_user_message", 500),
        _make_bucket("tool_schemas", 1000),  # estimated
        _make_bucket("local_instruction_context", 800),  # estimated
        _make_bucket("unlocated_residual", 0),
    ]

    total_input = 3000
    fresh_input = 1000  # only 500 available for estimated after measured

    normalize_request_reconstruction_buckets(
        buckets, total_input=total_input, fresh_input=fresh_input,
    )

    estimated_sum = sum(
        b.tokens for b in buckets
        if b.key in ("tool_schemas", "local_instruction_context")
    )
    remaining = fresh_input - 500  # measured
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
    assert "tool_schemas" in _ESTIMATED_BUCKET_KEYS
    assert "local_instruction_context" in _ESTIMATED_BUCKET_KEYS
    assert "hidden_builtin_system_estimate" in _HEURISTIC_FIXED_KEYS
    # provider_wrapper_estimate removed — now noted in attribution_notes instead
    assert "top_level_system_estimate" in _HEURISTIC_SCALED_KEYS
