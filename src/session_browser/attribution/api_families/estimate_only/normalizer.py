"""Normalize estimate-only usage without provider-reported precision.

This API-family normalizer is triggered after local reconstruction estimates
input and output usage without a provider payload. It preserves estimated token
boundaries, converts impossible provider-reported precision to estimated, and
marks the output usage source as local reconstruction.
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown


def normalize_estimate_usage(breakdown: UsageBreakdown) -> UsageBreakdown:
    """Normalize locally reconstructed usage for attribution output.

    Args:
        breakdown: Usage reconstructed from prompt spans, output spans, and
            residual estimates rather than from a provider ``usage`` payload.

    Returns:
        A ``UsageBreakdown`` with the same token buckets and local reconstruction
        provenance. Unavailable usage is returned unchanged, and
        provider-reported precision is downgraded to estimated.
    """
    if breakdown.usage_source == 'unavailable':
        return breakdown
    precision = breakdown.precision
    if precision == 'provider_reported':
        precision = 'estimated'
    return UsageBreakdown(
        total_input=breakdown.total_input,
        fresh_input=breakdown.fresh_input,
        cache_read=breakdown.cache_read,
        cache_write=breakdown.cache_write,
        output=breakdown.output,
        hidden_reasoning=breakdown.hidden_reasoning,
        usage_source='local_reconstruction',
        precision=precision,
        note=breakdown.note or 'Estimate-only usage normalized',
    )
