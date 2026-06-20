"""Usage 字段形状识别。

通过分析 provider usage dict 中的字段名，推断该 call 使用的
API Family 语义（Anthropic-like / OpenAI-like / unknown）。
不依赖 agent string，只看 usage 数据结构本身。
"""

from __future__ import annotations


def detect_usage_shape(usage: dict | None) -> str:
    """识别 usage dict 的字段形状。

    返回值：
    - "anthropic_messages_like": 包含 cache_read_input_tokens / cache_creation_input_tokens
    - "openai_responses_like": 包含 input_tokens_details.cached_tokens / output_tokens_details.reasoning_tokens
    - "openai_chat_like": 包含 prompt_tokens_details.cached_tokens / completion_tokens_details.reasoning_tokens
    - "token_reported_unknown_cache": 只有 input_tokens/output_tokens，无 cache 信息
    - "unavailable": 无 usage 数据
    """
    if not usage or not isinstance(usage, dict):
        return "unavailable"

    # 说明：Anthropic-style fields
    has_anthropic_cache = (
        "cache_read_input_tokens" in usage
        or "cache_creation_input_tokens" in usage
    )
    if has_anthropic_cache:
        return "anthropic_messages_like"

    # 说明：OpenAI Responses-style fields
    input_details = usage.get("input_tokens_details")
    if isinstance(input_details, dict) and "cached_tokens" in input_details:
        return "openai_responses_like"

    # 说明：OpenAI Chat Completions-style fields
    prompt_details = usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict) and "cached_tokens" in prompt_details:
        return "openai_chat_like"

    # 检查 nested details，用于 reasoning tokens (OpenAI Responses indicator)
    output_details = usage.get("output_tokens_details")
    if isinstance(output_details, dict) and "reasoning_tokens" in output_details:
        return "openai_responses_like"

    completion_details = usage.get("completion_tokens_details")
    if isinstance(completion_details, dict) and "reasoning_tokens" in completion_details:
        return "openai_chat_like"

    # 说明：Has basic token fields but no cache info
    has_basic_tokens = (
        "input_tokens" in usage
        or "prompt_tokens" in usage
        or "output_tokens" in usage
        or "completion_tokens" in usage
    )
    if has_basic_tokens:
        return "token_reported_unknown_cache"

    return "unavailable"


def get_nested_int(d: dict, *keys: str) -> int:
    """安全获取嵌套 dict 中的 int 值。

    例如: get_nested_int(usage, "input_tokens_details", "cached_tokens")
    """
    current = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return 0
    try:
        return int(current) if current is not None else 0
    except (TypeError, ValueError):
        return 0
