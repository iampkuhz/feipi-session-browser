"""OpenAI Chat Completions API usage parser.

OpenAI Chat usage 语义：
  fresh        = prompt_tokens（本次请求输入规模）
  cache_read   = prompt_tokens_details.cached_tokens
  total_input  = fresh + cache_read
  cache_write  = unavailable
  output       = completion_tokens
  hidden_reasoning = completion_tokens_details.reasoning_tokens
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown
from session_browser.attribution.mapping.usage_shape_detector import get_nested_int


def parse_openai_chat_usage(usage: dict | None) -> UsageBreakdown:
    """解析 OpenAI Chat Completions usage dict 为 UsageBreakdown。"""
    if not usage or not isinstance(usage, dict):
        return UsageBreakdown(
            usage_source="unavailable",
            precision="unavailable",
            note="无 OpenAI Chat usage 数据",
        )

    fresh = get_nested_int(usage, "prompt_tokens")
    cache_read = get_nested_int(usage, "prompt_tokens_details", "cached_tokens")
    output = get_nested_int(usage, "completion_tokens")
    hidden_reasoning = get_nested_int(usage, "completion_tokens_details", "reasoning_tokens")

    if fresh > 0:
        cache_read = min(cache_read, fresh)
    total_input = fresh + cache_read

    return UsageBreakdown(
        total_input=total_input if total_input > 0 else None,
        fresh_input=fresh if fresh > 0 else None,
        cache_read=cache_read if cache_read > 0 else (0 if fresh > 0 else None),
        cache_write=None,
        output=output if output > 0 else None,
        hidden_reasoning=hidden_reasoning if hidden_reasoning > 0 else None,
        usage_source="provider_reported" if fresh > 0 else "unavailable",
        precision="provider_reported" if fresh > 0 else "unavailable",
        note="OpenAI Chat usage：cache_write 不可用",
    )
