"""Qoder Broker normalizer。"""

from __future__ import annotations
from session_browser.attribution.core.models import UsageBreakdown


def normalize_qoder_broker_usage(breakdown: UsageBreakdown) -> UsageBreakdown:
    """标准化 Qoder Broker UsageBreakdown。"""
    if breakdown.usage_source == "unavailable":
        return breakdown

    fresh = breakdown.fresh_input or 0
    cache_read = breakdown.cache_read or 0
    cache_write = breakdown.cache_write or 0
    total_input = fresh + cache_read + cache_write

    return UsageBreakdown(
        total_input=total_input if total_input > 0 else None,
        fresh_input=fresh,
        cache_read=cache_read,
        cache_write=cache_write,
        output=breakdown.output,
        hidden_reasoning=breakdown.hidden_reasoning,
        usage_source=breakdown.usage_source,
        precision=breakdown.precision,
        note=breakdown.note or "Qoder broker usage normalized",
    )
