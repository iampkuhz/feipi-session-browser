"""OpenAI Responses API normalizer."""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown


def normalize_openai_responses_usage(breakdown: UsageBreakdown) -> UsageBreakdown:
    """标准化 OpenAI Responses UsageBreakdown。"""
    if breakdown.usage_source == "unavailable":
        return breakdown

    fresh = breakdown.fresh_input or 0
    cache_read = breakdown.cache_read or 0
    input_side_component_total = fresh + cache_read

    return UsageBreakdown(
        total_input=input_side_component_total if input_side_component_total > 0 else None,
        fresh_input=fresh if fresh > 0 else None,
        cache_read=cache_read if (fresh > 0 and cache_read > 0) else (0 if fresh > 0 else None),
        cache_write=None,
        output=breakdown.output,
        hidden_reasoning=breakdown.hidden_reasoning,
        usage_source=breakdown.usage_source,
        precision=breakdown.precision,
        note=breakdown.note or "OpenAI Responses usage normalized",
    )
