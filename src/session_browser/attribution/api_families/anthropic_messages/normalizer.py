"""Normalize Anthropic Messages usage into attribution boundaries.

This API-family normalizer runs after parsing the provider ``usage`` payload and
before cache allocation or downstream attribution rendering. It clamps negative
values, preserves provider provenance, and emits a ``UsageBreakdown`` whose
input boundary is exactly ``cache_read + cache_write + fresh_input``. It does
not infer missing cache fields beyond the parsed payload boundary.
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown


def normalize_anthropic_usage(breakdown: UsageBreakdown) -> UsageBreakdown:
    """Normalize parsed Anthropic usage for downstream token buckets.

    Args:
        breakdown: Parsed Anthropic Messages usage, typically produced from
            ``input_tokens``, ``cache_read_input_tokens``,
            ``cache_creation_input_tokens``, and ``output_tokens``.

    Returns:
        A ``UsageBreakdown`` with non-negative token fields and ``total_input``
        equal to the cache-read, cache-write, and fresh-input bucket sum. An
        unavailable input is returned unchanged.
    """
    if breakdown.usage_source == 'unavailable':
        return breakdown

    cache_read = max(0, breakdown.cache_read or 0)
    cache_write = max(0, breakdown.cache_write or 0)
    fresh = max(0, breakdown.fresh_input or 0)
    total_input = cache_read + cache_write + fresh

    return UsageBreakdown(
        total_input=total_input,
        fresh_input=fresh,
        cache_read=cache_read,
        cache_write=cache_write,
        output=max(0, breakdown.output or 0),
        hidden_reasoning=breakdown.hidden_reasoning,
        usage_source=breakdown.usage_source,
        precision=breakdown.precision,
        note=breakdown.note or 'Anthropic usage normalized',
    )
