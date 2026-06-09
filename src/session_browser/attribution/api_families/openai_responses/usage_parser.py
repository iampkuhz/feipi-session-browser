"""OpenAI Responses API usage parser.

OpenAI Responses usage 语义：
  fresh        = input_tokens（本次请求输入规模）
  cache_read   = input_tokens_details.cached_tokens
  total_input  = fresh + cache_read
  cache_write  = unavailable（不报告 Anthropic-style cache_creation）
  output       = output_tokens
  hidden_reasoning = output_tokens_details.reasoning_tokens

注意：Fresh 不扣减 cached_tokens；cache_read 作为独立组件展示。
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown
from session_browser.attribution.mapping.usage_shape_detector import get_nested_int


def parse_openai_responses_usage(usage: dict | None) -> UsageBreakdown:
    """解析 OpenAI Responses usage dict 为 UsageBreakdown。

    Args:
        usage: provider usage dict

    Returns:
        UsageBreakdown
    """
    if not usage or not isinstance(usage, dict):
        return UsageBreakdown(
            usage_source="unavailable",
            precision="unavailable",
            note="无 OpenAI Responses usage 数据",
        )

    fresh = get_nested_int(usage, "input_tokens")
    cache_read = get_nested_int(usage, "input_tokens_details", "cached_tokens")
    output = get_nested_int(usage, "output_tokens")
    hidden_reasoning = get_nested_int(usage, "output_tokens_details", "reasoning_tokens")

    if fresh > 0:
        cache_read = min(cache_read, fresh)
    total_input = fresh + cache_read

    # cache_write: OpenAI 不报告，标记 unavailable
    note = "OpenAI Responses usage：cache_write 不可用（not_reported）"

    return UsageBreakdown(
        total_input=total_input if total_input > 0 else None,
        fresh_input=fresh if fresh > 0 else None,
        cache_read=cache_read if cache_read > 0 else (0 if fresh > 0 else None),
        cache_write=None,  # unavailable，不能用 0 exact
        output=output if output > 0 else None,
        hidden_reasoning=hidden_reasoning if hidden_reasoning > 0 else None,
        usage_source="provider_reported" if fresh > 0 else "unavailable",
        precision="provider_reported" if fresh > 0 else "unavailable",
        note=note,
    )
