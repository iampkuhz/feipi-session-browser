"""Qoder underlying family resolver：动态识别 Qoder call 的底层 API Family。"""

from __future__ import annotations

from session_browser.attribution.mapping.usage_shape_detector import detect_usage_shape


def resolve_qoder_underlying_family(usage: dict | None) -> str:
    """根据 Qoder usage shape 决定 underlying API Family。

    Returns:
        "anthropic_messages_like" / "openai_like" / "estimate_only" / "unknown"
    """
    shape = detect_usage_shape(usage)
    if shape == "anthropic_messages_like":
        return "anthropic_messages_like"
    elif shape in ("openai_responses_like", "openai_chat_like"):
        return "openai_like"
    elif shape == "token_reported_unknown_cache":
        return "token_reported_unknown_cache"
    return "estimate_only"


def resolve_qoder_cache_allocator(api_family: str) -> str:
    """为 Qoder call 选择合适的 cache allocator。

    Returns:
        allocator 模块名称
    """
    if api_family == "anthropic_messages_like":
        return "anthropic_messages"
    elif api_family == "openai_like":
        return "openai_responses"
    return "estimate_only"
