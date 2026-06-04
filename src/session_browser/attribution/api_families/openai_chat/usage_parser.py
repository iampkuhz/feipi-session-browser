"""OpenAI Chat Completions API usage parser.

OpenAI Chat usage 语义：
  total_input  = prompt_tokens（inclusive total）
  cache_read   = prompt_tokens_details.cached_tokens
  fresh        = total_input - cache_read
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

    total_input = get_nested_int(usage, "prompt_tokens")
    cache_read = get_nested_int(usage, "prompt_tokens_details", "cached_tokens")
    output = get_nested_int(usage, "completion_tokens")
    hidden_reasoning = get_nested_int(usage, "completion_tokens_details", "reasoning_tokens")

    if total_input > 0:
        cache_read = min(cache_read, total_input)
    fresh = max(0, total_input - cache_read)

    return UsageBreakdown(
        total_input=total_input if total_input > 0 else None,
        fresh_input=fresh if total_input > 0 else None,
        cache_read=cache_read if cache_read > 0 else (0 if total_input > 0 else None),
        cache_write=None,
        output=output if output > 0 else None,
        hidden_reasoning=hidden_reasoning if hidden_reasoning > 0 else None,
        usage_source="provider_reported" if total_input > 0 else "unavailable",
        precision="provider_reported" if total_input > 0 else "unavailable",
        note="OpenAI Chat usage：cache_write 不可用",
    )
