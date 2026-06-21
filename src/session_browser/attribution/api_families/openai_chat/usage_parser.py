"""说明：OpenAI Chat Completions API usage parser.

OpenAI Chat usage 语义：
  provider_request_input = prompt_tokens
  cache_read   = prompt_tokens_details.cached_tokens
  fresh        = provider_request_input - cache_read
  input_side_component_total = fresh + cache_read
  cache_write  = unavailable
  output       = completion_tokens - hidden_reasoning（当 completion_tokens 含 hidden reasoning）
  hidden_reasoning = completion_tokens_details.reasoning_tokens
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown
from session_browser.attribution.mapping.usage_shape_detector import get_nested_int


def parse_openai_chat_usage(usage: dict | None) -> UsageBreakdown:
    """解析 OpenAI Chat Completions usage dict 为 UsageBreakdown。"""
    if not usage or not isinstance(usage, dict):
        return UsageBreakdown(
            usage_source='unavailable',
            precision='unavailable',
            note='无 OpenAI Chat usage 数据',
        )

    provider_request_input = get_nested_int(usage, 'prompt_tokens')
    cache_read = get_nested_int(usage, 'prompt_tokens_details', 'cached_tokens')
    provider_output_total = get_nested_int(usage, 'completion_tokens')
    hidden_reasoning = get_nested_int(usage, 'completion_tokens_details', 'reasoning_tokens')

    if provider_request_input > 0:
        cache_read = min(cache_read, provider_request_input)
    fresh = max(provider_request_input - cache_read, 0) if provider_request_input > 0 else 0
    input_side_component_total = fresh + cache_read
    output = provider_output_total
    if hidden_reasoning > 0 and provider_output_total >= hidden_reasoning:
        output = provider_output_total - hidden_reasoning

    return UsageBreakdown(
        total_input=input_side_component_total if input_side_component_total > 0 else None,
        fresh_input=fresh if fresh > 0 else None,
        cache_read=cache_read if cache_read > 0 else (0 if provider_request_input > 0 else None),
        cache_write=None,
        output=output if output > 0 else None,
        hidden_reasoning=hidden_reasoning if hidden_reasoning > 0 else None,
        usage_source='provider_reported' if provider_request_input > 0 else 'unavailable',
        precision='provider_reported' if provider_request_input > 0 else 'unavailable',
        note='OpenAI Chat usage：Fresh 已扣除 Cache Read；cache_write 不可用',
    )
