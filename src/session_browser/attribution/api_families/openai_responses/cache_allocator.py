"""OpenAI Responses API cache allocator.

OpenAI cache 分配语义：
  [0, cached_tokens)       => cache_read
  [cached_tokens, total)   => fresh
  cache_write              => unavailable（不是 exact 0）
"""

from __future__ import annotations

from session_browser.attribution.core.models import PromptSpan, UsageBreakdown


def allocate_openai_responses_cache(
    spans: list[PromptSpan],
    usage: UsageBreakdown,
) -> list[PromptSpan]:
    """为 ordered spans 分配 OpenAI-style cache tokens。

    OpenAI 只有 cache_read（cached_tokens）和 fresh。
    cache_write 始终 unavailable。
    本函数只标注已有 request-content span 的 cache/fresh 区间，
    不创建独立的 provider cache-hit 来源 bucket。
    """
    if not spans:
        return spans

    total_input = usage.total_input or 0
    cache_read = usage.cache_read or 0

    if total_input == 0:
        for span in spans:
            span.precision = "unavailable"
        return spans

    span_total = sum(s.token_estimate for s in spans)

    offset = 0
    for span in spans:
        est = span.token_estimate
        span_start = offset
        span_end = offset + est

        # [0, cache_read) => cache_read
        overlap_start = max(span_start, 0)
        overlap_end = min(span_end, cache_read)
        span_cache_read = max(0, overlap_end - overlap_start)
        span_fresh = max(0, est - span_cache_read)

        span.cache_read_tokens = span_cache_read
        span.cache_write_tokens = 0  # OpenAI 不报告
        span.fresh_tokens = span_fresh

        offset += est

    # residual 插入
    if span_total < total_input:
        residual = total_input - span_total
        spans.append(PromptSpan(
            span_id=f"residual_{len(spans)}",
            order_index=len(spans),
            api_family="openai_responses",
            api_path="residual",
            semantic_kind="unknown_residual",
            token_estimate=residual,
            token_count_method="residual",
            precision="residual",
            confidence=0.3,
            fresh_tokens=residual,
        ))

    return spans
