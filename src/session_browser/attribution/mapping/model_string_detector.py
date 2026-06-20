"""Model 字符串辅助识别。

用于从 model 字符串中推断 provider 和 model family 信息。
"""

from __future__ import annotations

import re


def detect_model_family(model_string: str) -> dict[str, str]:
    """从 model 字符串推断 provider 和 model family。

    Returns:
        {"provider_hint": "anthropic" | "openai" | "qoder" | "unknown",
         "model_hint": cleaned model string or ""}
    """
    if not model_string:
        return {"provider_hint": "unknown", "model_hint": ""}

    s = model_string.lower()

    # 说明：Anthropic models
    if "claude" in s:
        return {"provider_hint": "anthropic", "model_hint": model_string}

    # 说明：OpenAI models
    if "gpt" in s or "o1" in s or "o3" in s or "o4" in s:
        return {"provider_hint": "openai", "model_hint": model_string}

    # 说明：Qoder models (performance/standard, etc.)
    if "performance" in s or "standard" in s or "qoder" in s:
        return {"provider_hint": "qoder", "model_hint": model_string}

    return {"provider_hint": "unknown", "model_hint": model_string}


def is_reasoning_model(model_string: str) -> bool:
    """判断 model 是否为 reasoning model（可能有 hidden reasoning tokens）。"""
    if not model_string:
        return False
    s = model_string.lower()
    return bool(re.search(r'^(o1|o3|o4|claude.*sonnet|claude.*opus)', s))
