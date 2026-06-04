"""Anthropic Messages API normalizer.

将 parsed usage 标准化为统一格式，供下游 pipeline 使用。
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown


def normalize_anthropic_usage(breakdown: UsageBreakdown) -> UsageBreakdown:
    """标准化 Anthropic UsageBreakdown。

    确保：
    - total_input = cache_read + cache_write + fresh（不变量）
    - 所有字段非负
    - precision 正确
    """
    if breakdown.usage_source == "unavailable":
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
        note=breakdown.note or "Anthropic usage normalized",
    )
