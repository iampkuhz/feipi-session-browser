"""说明：Qoder Broker usage parser.

Qoder 是 broker/runtime，不是固定 provider。usage shape 仅作字段形态分类，
不推断 underlying provider。

Qoder broker-reported usage 的关键语义：
- ``input_tokens`` 是本次请求输入规模，作为 Fresh。
- ``cache_read_input_tokens`` 和 ``cache_creation_input_tokens`` 是 provider/broker-reported。
- 如果存在 ``qoder_input_tokens_total``，它仅用于追溯原始 ``input_tokens``，
  不覆盖组件合计。
- total_input = fresh + cache_read + cache_write
- 0 是有效值，不能变成 unavailable。
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown
from session_browser.attribution.mapping.usage_shape_detector import (
    detect_usage_shape,
    get_nested_int,
)


def parse_qoder_broker_usage(usage: dict | None) -> UsageBreakdown:
    """解析 Qoder broker usage。

    Qoder broker-reported usage 中 ``input_tokens`` 是本次请求输入规模，
    cache read/write 是单独组件。

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
        # Qoder broker: input_tokens 是 Fresh request input。
        fresh = get_nested_int(usage, "input_tokens")
        cache_read = get_nested_int(usage, "cache_read_input_tokens")
        cache_write = get_nested_int(usage, "cache_creation_input_tokens")
        total_input = fresh + cache_read + cache_write
        output = get_nested_int(usage, "output_tokens")

        return UsageBreakdown(
            total_input=total_input if total_input > 0 else None,
            fresh_input=fresh,
            cache_read=cache_read,
            cache_write=cache_write,
            output=output if output > 0 else None,
            usage_source="qoder_broker_provider_reported",
            precision="provider_reported",
            note="Qoder broker: request input plus separate cache fields",
        )

    elif shape in ("openai_responses_like", "openai_chat_like"):
        fresh = get_nested_int(usage, "input_tokens") or get_nested_int(usage, "prompt_tokens")
        cache_read = (
            get_nested_int(usage, "input_tokens_details", "cached_tokens")
            or get_nested_int(usage, "prompt_tokens_details", "cached_tokens")
        )
        output = get_nested_int(usage, "output_tokens") or get_nested_int(usage, "completion_tokens")
        hidden_reasoning = (
            get_nested_int(usage, "output_tokens_details", "reasoning_tokens")
            or get_nested_int(usage, "completion_tokens_details", "reasoning_tokens")
        )
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
            usage_source="qoder_broker_provider_reported",
            precision="provider_reported",
            note="Qoder broker: OpenAI-like request input plus cache read",
        )

    elif shape == "token_reported_unknown_cache":
        fresh = get_nested_int(usage, "input_tokens") or get_nested_int(usage, "prompt_tokens")
        output = get_nested_int(usage, "output_tokens") or get_nested_int(usage, "completion_tokens")
        return UsageBreakdown(
            total_input=fresh if fresh > 0 else None,
            fresh_input=fresh if fresh > 0 else None,
            cache_read=None,
            cache_write=None,
            output=output if output > 0 else None,
            usage_source="qoder_broker_provider_reported",
            precision="provider_reported",
            note="Qoder broker: 只有 basic tokens，无 cache 信息；Fresh 使用 input_tokens",
        )

    return UsageBreakdown(
        usage_source="unavailable",
        precision="unavailable",
        note="Qoder broker: 无法识别 usage shape",
    )
