"""Reconstruct usage when no provider or broker usage payload exists.

This API-family estimator is triggered by estimate-only attribution paths after
prompt and output spans have been locally tokenized. It emits normalized usage
boundaries from local span totals: input span tokens plus optional residual
input, no cache-read or cache-write buckets, and visible output span tokens.
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown


def estimate_usage_from_spans(
    *,
    input_spans_token_sum: int = 0,
    output_spans_token_sum: int = 0,
    residual_estimate: int = 0,
) -> UsageBreakdown:
    """Estimate usage from reconstructed prompt and response spans.

    Args:
        input_spans_token_sum: Estimated token total across all input prompt
            spans.
        output_spans_token_sum: Estimated token total across visible output
            spans.
        residual_estimate: Extra input estimate for hidden system prompts,
            tokenizer overhead, or other residual provider-side input.

    Returns:
        A ``UsageBreakdown`` with estimated ``total_input`` and ``output`` when
        the corresponding local totals are positive. Cache buckets remain
        unavailable because no usage payload confirms provider cache behavior.
    """
    total_input = (
        input_spans_token_sum + residual_estimate
        if residual_estimate > 0
        else input_spans_token_sum
    )

    return UsageBreakdown(
        total_input=total_input if total_input > 0 else None,
        fresh_input=None,
        cache_read=None,
        cache_write=None,
        output=output_spans_token_sum if output_spans_token_sum > 0 else None,
        usage_source='local_reconstruction',
        precision='estimated',
        note=(
            f'本地重建: {input_spans_token_sum} input spans + {residual_estimate} residual'
            if residual_estimate > 0
            else f'本地重建: {input_spans_token_sum} input spans'
        ),
    )
