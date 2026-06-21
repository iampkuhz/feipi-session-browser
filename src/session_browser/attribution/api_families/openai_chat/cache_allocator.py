"""OpenAI Chat cache allocator — 与 Responses 相同语义。"""

from __future__ import annotations

from session_browser.attribution.core.models import PromptSpan, UsageBreakdown


def allocate_openai_chat_cache(
    spans: list[PromptSpan],
    usage: UsageBreakdown,
) -> list[PromptSpan]:
    """为 ordered spans 分配 OpenAI Chat-style cache tokens。

    仅标注已有 request-content span 的 cache/fresh 区间，
    不创建独立的 provider cache-hit 来源 bucket。
    """
    if not spans:
        return spans

    total_input = usage.total_input or 0
    cache_read = usage.cache_read or 0

    if total_input == 0:
        for span in spans:
            span.precision = 'unavailable'
        return spans

    span_total = sum(s.token_estimate for s in spans)
    offset = 0
    for span in spans:
        est = span.token_estimate
        span_start = offset
        span_end = offset + est
        overlap = max(0, min(span_end, cache_read) - max(span_start, 0))
        span.cache_read_tokens = overlap
        span.cache_write_tokens = 0
        span.fresh_tokens = max(0, est - overlap)
        offset += est

    if span_total < total_input:
        residual = total_input - span_total
        spans.append(
            PromptSpan(
                span_id=f'residual_{len(spans)}',
                order_index=len(spans),
                api_family='openai_chat',
                api_path='residual',
                semantic_kind='unknown_residual',
                token_estimate=residual,
                token_count_method='residual',
                precision='residual',
                confidence=0.3,
                fresh_tokens=residual,
            )
        )
    return spans
