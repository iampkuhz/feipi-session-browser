"""Estimate-only normalizer。"""

from __future__ import annotations
from session_browser.attribution.core.models import UsageBreakdown


def normalize_estimate_usage(breakdown: UsageBreakdown) -> UsageBreakdown:
    """标准化 estimate-only UsageBreakdown。

    确保 precision 不能是 provider_reported。
    """
    if breakdown.usage_source == "unavailable":
        return breakdown
    precision = breakdown.precision
    if precision == "provider_reported":
        precision = "estimated"
    return UsageBreakdown(
        total_input=breakdown.total_input,
        fresh_input=breakdown.fresh_input,
        cache_read=breakdown.cache_read,
        cache_write=breakdown.cache_write,
        output=breakdown.output,
        hidden_reasoning=breakdown.hidden_reasoning,
        usage_source="local_reconstruction",
        precision=precision,
        note=breakdown.note or "Estimate-only usage normalized",
    )
