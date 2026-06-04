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
# total_input_formula: total_input 计算公式

API_FAMILY_CAPABILITIES: dict[str, dict] = {
    "anthropic_messages": {
        "cache_write_available": True,
        "cache_read_field": "cache_read_input_tokens",
        "cache_write_field": "cache_creation_input_tokens",
        "fresh_field": "input_tokens",
        "total_input_formula": "cache_read + cache_write + fresh",
    },
    "anthropic_messages_like": {
        "cache_write_available": True,
        "cache_read_field": "cache_read_input_tokens",
        "cache_write_field": "cache_creation_input_tokens",
        "fresh_field": "input_tokens",
        "total_input_formula": "cache_read + cache_write + fresh",
    },
    "openai_responses": {
        "cache_write_available": False,
        "cache_read_field": "input_tokens_details.cached_tokens",
        "cache_write_field": None,
        "fresh_field": "input_tokens",
        "total_input_formula": "input_tokens (inclusive total)",
    },
    "openai_chat": {
        "cache_write_available": False,
        "cache_read_field": "prompt_tokens_details.cached_tokens",
        "cache_write_field": None,
        "fresh_field": "prompt_tokens",
        "total_input_formula": "prompt_tokens (inclusive total)",
    },
    "openai_like": {
        "cache_write_available": False,
        "cache_read_field": "cached_tokens",
        "cache_write_field": None,
        "fresh_field": "input_tokens",
        "total_input_formula": "input_tokens (inclusive total)",
    },
    "qoder_broker": {
        "cache_write_available": True,  # 动态由 underlying family 决定
        "cache_read_field": "dynamic",
        "cache_write_field": "dynamic",
        "fresh_field": "dynamic",
        "total_input_formula": "dynamic",
    },
    "estimate_only": {
        "cache_write_available": False,
        "cache_read_field": None,
        "cache_write_field": None,
        "fresh_field": None,
        "total_input_formula": "reconstructed",
    },
    "unknown": {
        "cache_write_available": False,
        "cache_read_field": None,
        "cache_write_field": None,
        "fresh_field": None,
        "total_input_formula": "unavailable",
    },
}
