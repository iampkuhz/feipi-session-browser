"""说明：Anthropic Messages API usage parser.

Anthropic usage 语义：
  total_input = cache_read_input_tokens + cache_creation_input_tokens + input_tokens
  cache_read  = cache_read_input_tokens
  cache_write = cache_creation_input_tokens
  fresh       = input_tokens
  output      = output_tokens

注意：input_tokens 不是总输入，而是最后 cache breakpoint 之后没有被读缓存、
也没有用于写缓存的 tokens。
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown
from session_browser.attribution.mapping.usage_shape_detector import get_nested_int


def parse_anthropic_usage(usage: dict | None) -> UsageBreakdown:
    """解析 Anthropic usage dict 为 UsageBreakdown。

    Args:
        usage: provider usage dict，如包含 input_tokens, cache_read_input_tokens,
               cache_creation_input_tokens, output_tokens

    Returns:
        UsageBreakdown 带 total_input / fresh / cache_read / cache_write / output
    """
    if not usage or not isinstance(usage, dict):
        return UsageBreakdown(
            usage_source="unavailable",
            precision="unavailable",
            note="无 Anthropic usage 数据",
        )

    cache_read = get_nested_int(usage, "cache_read_input_tokens")
    cache_write = get_nested_int(usage, "cache_creation_input_tokens")
    fresh = get_nested_int(usage, "input_tokens")
    output = get_nested_int(usage, "output_tokens")
    total_input = cache_read + cache_write + fresh

    # 验证不变量：total = cache_read + cache_write + fresh
    reported_total = get_nested_int(usage, "total_tokens")
    if reported_total > 0 and reported_total != total_input:
        # 如果 provider 报告的 total 和计算不一致，以计算为准并记录 note
        note = (
            f"Anthropic total_input 计算值={total_input}，"
            f"provider total_tokens={reported_total}（可能含 overhead）"
        )
    else:
        note = "来自 Anthropic usage 字段"

    return UsageBreakdown(
        total_input=total_input,
        fresh_input=fresh,
        cache_read=cache_read,
        cache_write=cache_write,
        output=output,
        usage_source="provider_reported",
        precision="provider_reported",
        note=note,
    )
