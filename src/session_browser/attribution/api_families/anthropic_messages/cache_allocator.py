"""Allocate Anthropic Messages cache buckets across ordered prompt spans.

This API-family helper is triggered after Anthropic request spans have been
ordered with the Messages request order and after provider usage has been
parsed into ``UsageBreakdown``. It maps the input usage payload boundaries to
per-span token buckets: cache reads first, cache writes second, and fresh input
last. The output stays within ``PromptSpan`` accounting fields; residual tokens
are represented as a synthetic span only when provider input exceeds the local
span total.
"""

from __future__ import annotations

from session_browser.attribution.core.models import PromptSpan, UsageBreakdown


def allocate_anthropic_cache(
    spans: list[PromptSpan],
    usage: UsageBreakdown,
) -> list[PromptSpan]:
    """Assign Anthropic-style cache token buckets to ordered spans.

    Args:
        spans: Prompt spans in Anthropic request order: tools, system, then
            message content blocks. The allocator mutates these spans in place.
        usage: Normalized Anthropic usage payload with ``total_input``,
            ``cache_read``, ``cache_write``, and fresh input boundaries.

    Returns:
        The same ordered span list with ``cache_read_tokens``,
        ``cache_write_tokens``, and ``fresh_tokens`` populated. If provider
        input exceeds local spans, the return value includes a residual span;
        if local spans exceed provider input, exact spans are not scaled down.
    """
    if not spans:
        return spans

    total_input = usage.total_input or 0
    cache_read = usage.cache_read or 0
    cache_write = usage.cache_write or 0

    if total_input == 0:
        # Without a provider total, cache boundaries cannot be trusted.
        for span in spans:
            span.precision = 'unavailable'
        return spans

    span_total = sum(s.token_estimate for s in spans)

    offset = 0
    for span in spans:
        est = span.token_estimate
        span_cache_read = 0
        span_cache_write = 0

        span_start = offset
        span_end = offset + est

        overlap_read_start = max(span_start, 0)
        overlap_read_end = min(span_end, cache_read)
        if overlap_read_end > overlap_read_start:
            span_cache_read = overlap_read_end - overlap_read_start

        write_start = cache_read
        write_end = cache_read + cache_write
        overlap_write_start = max(span_start, write_start)
        overlap_write_end = min(span_end, write_end)
        if overlap_write_end > overlap_write_start:
            span_cache_write = overlap_write_end - overlap_write_start

        span.cache_read_tokens = span_cache_read
        span.cache_write_tokens = span_cache_write
        span.fresh_tokens = max(0, est - span_cache_read - span_cache_write)

        offset += est

    if span_total < total_input:
        residual = total_input - span_total
        residual_span = PromptSpan(
            span_id=f'residual_{len(spans)}',
            order_index=len(spans),
            api_family='anthropic_messages',
            api_path='residual',
            semantic_kind='unknown_residual',
            token_estimate=residual,
            token_count_method='residual',
            precision='residual',
            confidence=0.3,
            fresh_tokens=residual,
        )
        spans.append(residual_span)

    return spans
