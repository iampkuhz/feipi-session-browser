"""OpenAI Responses API normalizer."""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown


def normalize_openai_responses_usage(breakdown: UsageBreakdown) -> UsageBreakdown:
    """标准化 OpenAI Responses UsageBreakdown。"""
    if breakdown.usage_source == "unavailable":
        return breakdown

    total_input = breakdown.total_input or 0
    cache_read = breakdown.cache_read or 0
    if total_input > 0:
        cache_read = min(cache_read, total_input)
    fresh = max(0, total_input - cache_read)

    return UsageBreakdown(
        total_input=total_input if total_input > 0 else None,
        fresh_input=fresh if total_input > 0 else None,
        cache_read=cache_read if (total_input > 0 and cache_read > 0) else (0 if total_input > 0 else None),
        cache_write=None,
        output=breakdown.output,
        hidden_reasoning=breakdown.hidden_reasoning,
        usage_source=breakdown.usage_source,
        precision=breakdown.precision,
        note=breakdown.note or "OpenAI Responses usage normalized",
    )
