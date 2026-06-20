"""API Family 枚举和能力表。

API Family 表示单次 LLM call 使用的 API 协议族：
- anthropic_messages: Anthropic Messages API
- anthropic_messages_like: 类似 Anthropic Messages 的用法
- openai_responses: OpenAI Responses API
- openai_chat: OpenAI Chat Completions API
- openai_like: 类似 OpenAI 的用法
- qoder_broker: Qoder Broker（动态识别 underlying family）
- estimate_only: 仅本地估算，无 provider usage
- unknown: 无法识别
"""

from __future__ import annotations

API_FAMILY_VALUES = frozenset({
    "anthropic_messages",
    "anthropic_messages_like",
    "openai_responses",
    "openai_chat",
    "openai_like",
    "qoder_broker",
    "estimate_only",
    "unknown",
})

# 各 API Family 的 cache 语义能力
# cache_write_available: 是否报告 Anthropic-style cache_creation_input_tokens
# cache_read_field: usage 中 cache read 的字段名
# 说明：provider_request_input_field: provider raw request input field
# 说明：fresh_formula: UI Fresh component formula
# 说明：input_side_component_total_formula: input-side component total formula

API_FAMILY_CAPABILITIES: dict[str, dict] = {
    "anthropic_messages": {
        "cache_write_available": True,
        "cache_read_field": "cache_read_input_tokens",
        "cache_write_field": "cache_creation_input_tokens",
        "provider_request_input_field": "input_tokens",
        "fresh_formula": "input_tokens",
        "input_side_component_total_formula": "fresh + cache_read + cache_write",
    },
    "anthropic_messages_like": {
        "cache_write_available": True,
        "cache_read_field": "cache_read_input_tokens",
        "cache_write_field": "cache_creation_input_tokens",
        "provider_request_input_field": "input_tokens",
        "fresh_formula": "input_tokens",
        "input_side_component_total_formula": "fresh + cache_read + cache_write",
    },
    "openai_responses": {
        "cache_write_available": False,
        "cache_read_field": "input_tokens_details.cached_tokens",
        "cache_write_field": None,
        "provider_request_input_field": "input_tokens",
        "fresh_formula": "input_tokens - input_tokens_details.cached_tokens",
        "input_side_component_total_formula": "fresh + cache_read",
    },
    "openai_chat": {
        "cache_write_available": False,
        "cache_read_field": "prompt_tokens_details.cached_tokens",
        "cache_write_field": None,
        "provider_request_input_field": "prompt_tokens",
        "fresh_formula": "prompt_tokens - prompt_tokens_details.cached_tokens",
        "input_side_component_total_formula": "fresh + cache_read",
    },
    "openai_like": {
        "cache_write_available": False,
        "cache_read_field": "cached_tokens",
        "cache_write_field": None,
        "provider_request_input_field": "input_tokens",
        "fresh_formula": "input_tokens - cached_tokens when cached is an input subset",
        "input_side_component_total_formula": "fresh + cache_read",
    },
    "qoder_broker": {
        "cache_write_available": True,  # 动态由 underlying family 决定
        "cache_read_field": "dynamic",
        "cache_write_field": "dynamic",
        "provider_request_input_field": "dynamic",
        "fresh_formula": "dynamic",
        "input_side_component_total_formula": "dynamic",
    },
    "estimate_only": {
        "cache_write_available": False,
        "cache_read_field": None,
        "cache_write_field": None,
        "provider_request_input_field": None,
        "fresh_formula": "reconstructed",
        "input_side_component_total_formula": "reconstructed",
    },
    "unknown": {
        "cache_write_available": False,
        "cache_read_field": None,
        "cache_write_field": None,
        "provider_request_input_field": None,
        "fresh_formula": "unavailable",
        "input_side_component_total_formula": "unavailable",
    },
}
