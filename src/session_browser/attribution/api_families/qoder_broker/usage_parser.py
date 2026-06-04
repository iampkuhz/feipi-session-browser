"""Qoder Broker usage parser.

Qoder 是 broker，不是固定 provider。usage shape 决定 underlying family：
- 有 cache_read_input_tokens/cache_creation_input_tokens -> Anthropic-like
- 有 cached_tokens in input/prompt details -> OpenAI-like
- 只有 input_tokens/output_tokens -> token_reported_unknown_cache
- 无 usage -> estimate_only
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown
from session_browser.attribution.mapping.usage_shape_detector import (
    detect_usage_shape,
    get_nested_int,
)


def parse_qoder_broker_usage(usage: dict | None) -> UsageBreakdown:
    """解析 Qoder broker usage，按 shape 委托给对应 parser。

    Returns:
        UsageBreakdown，usage_source 包含 "qoder_broker" 标记。
    """
    if not usage or not isinstance(usage, dict):
        return UsageBreakdown(
            usage_source="unavailable",
            precision="unavailable",
            note="Qoder 无 usage 数据，需使用 estimate-only",
        )

    shape = detect_usage_shape(usage)

    if shape == "anthropic_messages_like":
        cache_read = get_nested_int(usage, "cache_read_input_tokens")
        cache_write = get_nested_int(usage, "cache_creation_input_tokens")
        fresh = get_nested_int(usage, "input_tokens")
        output = get_nested_int(usage, "output_tokens")
        total = cache_read + cache_write + fresh
        return UsageBreakdown(
            total_input=total if total > 0 else None,
            fresh_input=fresh,
            cache_read=cache_read,
            cache_write=cache_write,
            output=output if output > 0 else None,
            usage_source="qoder_broker_provider_reported",
            precision="provider_reported",
            note="Qoder broker: Anthropic-like usage",
        )

    elif shape in ("openai_responses_like", "openai_chat_like"):
        total_input = get_nested_int(usage, "input_tokens") or get_nested_int(usage, "prompt_tokens")
        cache_read = (
            get_nested_int(usage, "input_tokens_details", "cached_tokens")
            or get_nested_int(usage, "prompt_tokens_details", "cached_tokens")
        )
        output = get_nested_int(usage, "output_tokens") or get_nested_int(usage, "completion_tokens")
        hidden_reasoning = (
            get_nested_int(usage, "output_tokens_details", "reasoning_tokens")
            or get_nested_int(usage, "completion_tokens_details", "reasoning_tokens")
        )
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
            usage_source="qoder_broker_provider_reported",
            precision="provider_reported",
            note="Qoder broker: OpenAI-like usage",
        )

    elif shape == "token_reported_unknown_cache":
        total_input = get_nested_int(usage, "input_tokens") or get_nested_int(usage, "prompt_tokens")
        output = get_nested_int(usage, "output_tokens") or get_nested_int(usage, "completion_tokens")
        return UsageBreakdown(
            total_input=total_input if total_input > 0 else None,
            fresh_input=None,
            cache_read=None,
            cache_write=None,
            output=output if output > 0 else None,
            usage_source="qoder_broker_provider_reported",
            precision="provider_reported",
            note="Qoder broker: 只有 basic tokens，无 cache 信息",
        )

    return UsageBreakdown(
        usage_source="unavailable",
        precision="unavailable",
        note="Qoder broker: 无法识别 usage shape",
    )
