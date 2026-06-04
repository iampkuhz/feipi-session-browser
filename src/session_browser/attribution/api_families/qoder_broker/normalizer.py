"""Qoder Broker normalizer。"""

from __future__ import annotations
from session_browser.attribution.core.models import UsageBreakdown


def normalize_qoder_broker_usage(breakdown: UsageBreakdown) -> UsageBreakdown:
    """标准化 Qoder Broker UsageBreakdown。"""
    if breakdown.usage_source == "unavailable":
        return breakdown

    total_input = breakdown.total_input or 0
    fresh = breakdown.fresh_input or 0
    cache_read = breakdown.cache_read or 0
    cache_write = breakdown.cache_write or 0

    if total_input > 0 and (fresh + cache_read + cache_write) > total_input:
        # 超过 total，按比例缩放
        ratio = total_input / (fresh + cache_read + cache_write)
        cache_read = int(cache_read * ratio)
        cache_write = int(cache_write * ratio)
        fresh = total_input - cache_read - cache_write

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
