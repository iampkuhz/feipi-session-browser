"""OpenAI Responses API usage parser.

OpenAI Responses usage 语义：
  provider_request_input = input_tokens
  cache_read   = input_tokens_details.cached_tokens
  fresh        = provider_request_input - cache_read
  input_side_component_total = fresh + cache_read
  cache_write  = unavailable（不报告 Anthropic-style cache_creation）
  output       = output_tokens（reasoning 是 output 的 breakdown/subset）
  hidden_reasoning = output_tokens_details.reasoning_tokens

注意：OpenAI/Codex 的 cached_tokens 是 provider request input 的子集；
Fresh 必须扣减 Cache Read，避免 tokenbar 重复计入。
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

    provider_request_input = get_nested_int(usage, "input_tokens")
    cache_read = get_nested_int(usage, "input_tokens_details", "cached_tokens")
    provider_output_total = get_nested_int(usage, "output_tokens")
    hidden_reasoning = get_nested_int(usage, "output_tokens_details", "reasoning_tokens")

    if provider_request_input > 0:
        cache_read = min(cache_read, provider_request_input)
    fresh = max(provider_request_input - cache_read, 0) if provider_request_input > 0 else 0
    input_side_component_total = fresh + cache_read
    output = provider_output_total

    # cache_write: OpenAI 不报告，标记 unavailable
    note = (
        "OpenAI Responses usage：input_tokens 是 Provider Request Input；"
        "Fresh 已扣除 Cache Read；cache_write 不可用（not_reported）"
    )

    return UsageBreakdown(
        total_input=input_side_component_total if input_side_component_total > 0 else None,
        fresh_input=fresh if fresh > 0 else None,
        cache_read=cache_read if cache_read > 0 else (0 if provider_request_input > 0 else None),
        cache_write=None,  # unavailable，不能用 0 exact
        output=output if output > 0 else None,
        hidden_reasoning=hidden_reasoning if hidden_reasoning > 0 else None,
        usage_source="provider_reported" if provider_request_input > 0 else "unavailable",
        precision="provider_reported" if provider_request_input > 0 else "unavailable",
        note=note,
    )
