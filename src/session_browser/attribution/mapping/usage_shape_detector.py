"""Detect API-family hints from provider usage payload shape.

The detector runs before model-string fallback when attribution has a usage payload. It
inspects only field names and nested detail objects, so it can classify Anthropic-like,
OpenAI Responses-like, OpenAI Chat-like, basic-token, or unavailable usage without
depending on agent runtime strings.
"""

from __future__ import annotations

from typing import Any


def detect_usage_shape(usage: dict[str, Any] | None) -> str:
    """Classify the API-family shape of a provider usage payload.

    Args:
        usage: Provider or broker usage payload for a single LLM call.

    Returns:
        Shape label such as ``anthropic_messages_like``, ``openai_responses_like``,
        ``openai_chat_like``, ``token_reported_unknown_cache``, or ``unavailable``.
    """
    usage_shape = 'unavailable'
    if not usage or not isinstance(usage, dict):
        return usage_shape

    has_anthropic_cache = (
        'cache_read_input_tokens' in usage or 'cache_creation_input_tokens' in usage
    )
    input_details = usage.get('input_tokens_details')
    prompt_details = usage.get('prompt_tokens_details')
    output_details = usage.get('output_tokens_details')
    completion_details = usage.get('completion_tokens_details')
    has_basic_tokens = (
        'input_tokens' in usage
        or 'prompt_tokens' in usage
        or 'output_tokens' in usage
        or 'completion_tokens' in usage
    )

    if has_anthropic_cache:
        usage_shape = 'anthropic_messages_like'
    elif isinstance(input_details, dict) and 'cached_tokens' in input_details:
        usage_shape = 'openai_responses_like'
    elif isinstance(prompt_details, dict) and 'cached_tokens' in prompt_details:
        usage_shape = 'openai_chat_like'
    elif isinstance(output_details, dict) and 'reasoning_tokens' in output_details:
        usage_shape = 'openai_responses_like'
    elif isinstance(completion_details, dict) and 'reasoning_tokens' in completion_details:
        usage_shape = 'openai_chat_like'
    elif has_basic_tokens:
        usage_shape = 'token_reported_unknown_cache'

    return usage_shape


def get_nested_int(data: dict[str, Any], *keys: str) -> int:
    """Return an integer value from a nested usage payload path.

    Args:
        data: Usage payload or nested detail dictionary to inspect.
        *keys: Ordered key path, for example ``input_tokens_details`` then
            ``cached_tokens``.

    Returns:
        Parsed integer when the full path exists and is numeric, otherwise ``0``.
    """
    current: Any = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return 0
    try:
        return int(current) if current is not None else 0
    except (TypeError, ValueError):
        return 0
