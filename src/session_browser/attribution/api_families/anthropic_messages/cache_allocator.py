"""说明：Anthropic Messages API cache allocator.

按 ordered token offsets 分配 cache_read / cache_write / fresh：
  [0, cache_read)                         => cache_read
  [cache_read, cache_read + cache_write)  => cache_write
  [cache_read + cache_write, total)       => fresh

输入：ordered PromptSpan 列表 + UsageBreakdown
输出：每个 span 被分配 cache_read_tokens / cache_write_tokens / fresh_tokens
"""

from __future__ import annotations

from session_browser.attribution.core.models import PromptSpan, UsageBreakdown


def allocate_anthropic_cache(
    spans: list[PromptSpan],
    usage: UsageBreakdown,
) -> list[PromptSpan]:
    """为 ordered spans 分配 Anthropic-style cache tokens。

    如果 span total 小于 provider total，差额插入 residual span。
    如果 span total 大于 provider total，不对 exact spans 做粗暴缩放。
    """
    if not spans:
        return spans

    total_input = usage.total_input or 0
    cache_read = usage.cache_read or 0
    cache_write = usage.cache_write or 0

    if total_input == 0:
        # 无 provider total，只能标记 unavailable
        for span in spans:
            span.precision = "unavailable"
        return spans

    # 计算所有 spans 的 token estimate 总和
    span_total = sum(s.token_estimate for s in spans)

    # 分配：按 offset 累加
    offset = 0
    for span in spans:
        est = span.token_estimate
        span_cache_read = 0
        span_cache_write = 0
        span_fresh = 0

        span_start = offset
        span_end = offset + est

        # 区间映射：[0, cache_read) => cache_read
        overlap_read_start = max(span_start, 0)
        overlap_read_end = min(span_end, cache_read)
        if overlap_read_end > overlap_read_start:
            span_cache_read = overlap_read_end - overlap_read_start

        # 区间映射：[cache_read, cache_read + cache_write) => cache_write
        write_start = cache_read
        write_end = cache_read + cache_write
        overlap_write_start = max(span_start, write_start)
        overlap_write_end = min(span_end, write_end)
        if overlap_write_end > overlap_write_start:
            span_cache_write = overlap_write_end - overlap_write_start

        # 剩余 = fresh
        span_fresh = max(0, est - span_cache_read - span_cache_write)

        span.cache_read_tokens = span_cache_read
        span.cache_write_tokens = span_cache_write
        span.fresh_tokens = span_fresh

        offset += est

    # 如果 span_total < total_input，插入 residual span
    if span_total < total_input:
        residual = total_input - span_total
        residual_span = PromptSpan(
            span_id=f"residual_{len(spans)}",
            order_index=len(spans),
            api_family="anthropic_messages",
            api_path="residual",
            semantic_kind="unknown_residual",
            token_estimate=residual,
            token_count_method="residual",
            precision="residual",
            confidence=0.3,
            fresh_tokens=residual,
        )
        spans.append(residual_span)

    return spans
