"""Qoder token estimator：Qoder 专用 token 估算。

使用 qoder-fast-bytes-v1 策略或现有字节估算策略。
"""

from __future__ import annotations

_BYTES_PER_TOKEN = 4  # 经验值


def estimate_qoder_tokens(text: str) -> int:
    """估算 Qoder 文本的 token 数。

    使用字节长度 / 4 的经验公式。
    """
    if not text:
        return 0
    return max(0, len(text.encode("utf-8")) // _BYTES_PER_TOKEN)


def estimate_qoder_tokens_from_structured(data: dict) -> int:
    """从结构化数据估算 Qoder token 数。

    将数据结构化为 JSON 字符串后估算。
    """
    import json
    text = json.dumps(data, ensure_ascii=False)
    return estimate_qoder_tokens(text)
