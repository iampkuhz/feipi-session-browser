"""Qoder Broker usage parser.

Qoder 是 broker/runtime，不是固定 provider。usage shape 仅作字段形态分类，
不推断 underlying provider。

Qoder broker-reported usage 的关键语义：
- ``input_tokens`` 是 **inclusive total input**（包含缓存），不是 fresh。
- ``cache_read_input_tokens`` 和 ``cache_creation_input_tokens`` 是 provider/broker-reported。
- 如果存在 ``qoder_input_tokens_total``，说明该记录已被 normalizer 预处理过，
  ``input_tokens`` 已被改写为 fresh，total 以 marker 为准。
- fresh = total_input - cache_read - cache_write
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

    Qoder broker-reported usage 中 ``input_tokens`` 是 inclusive total input，
    不是 Anthropic 语义下的 fresh input。

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
        # Qoder broker: input_tokens 是 inclusive total
        cache_read = get_nested_int(usage, "cache_read_input_tokens")
        cache_write = get_nested_int(usage, "cache_creation_input_tokens")

        # 检查是否已被 normalizer 预处理（带有 qoder_input_tokens_total marker）
        qoder_total = usage.get("qoder_input_tokens_total")
        if qoder_total is not None:
            # 已标准化：input_tokens 已被改写为 fresh，total 以 marker 为准
            total_input = int(qoder_total)
            # 使用当前的 input_tokens 作为 fresh（normalizer 已改写）
            fresh = get_nested_int(usage, "input_tokens")
        else:
            # 原始 Qoder usage：input_tokens 是 inclusive total
            total_input = get_nested_int(usage, "input_tokens")
            fresh = max(0, total_input - cache_read - cache_write)

        output = get_nested_int(usage, "output_tokens")

        return UsageBreakdown(
            total_input=total_input if total_input > 0 else None,
            fresh_input=fresh,
            cache_read=cache_read,
            cache_write=cache_write,
            output=output if output > 0 else None,
            usage_source="qoder_broker_provider_reported",
            precision="provider_reported",
            note="Qoder broker: inclusive input with cache fields",
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
