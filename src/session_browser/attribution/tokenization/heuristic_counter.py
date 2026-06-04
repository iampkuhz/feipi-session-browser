"""Heuristic token counter：基于字符数的 fallback token 估算。

当 tiktoken 不可用时使用此策略。
估算公式：~4 字符/token（英文文本的经验值）。
"""

from __future__ import annotations

_CHARS_PER_TOKEN = 4


def estimate_tokens_heuristic(text: str) -> int:
    """基于字符数的 heuristic token 估算。

    Args:
        text: 输入文本

    Returns:
        估算 token 数，至少为 0
    """
    if not text:
        return 0
    return max(0, len(text) // _CHARS_PER_TOKEN)


def estimate_tokens_from_object(obj: object) -> int:
    """从任意对象估算 token 数。

    策略：
    - str: 直接估算
    - dict/list: 转为 JSON 字符串后估算
    - 其他: 转为字符串后估算
    """
    if isinstance(obj, str):
        return estimate_tokens_heuristic(obj)
    elif isinstance(obj, (dict, list)):
        import json
        text = json.dumps(obj, ensure_ascii=False)
        return estimate_tokens_heuristic(text)
    else:
        return estimate_tokens_heuristic(str(obj))
