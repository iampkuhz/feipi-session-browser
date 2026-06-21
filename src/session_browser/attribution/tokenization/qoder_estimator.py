"""Qoder token estimator:Qoder 专用 token 估算.

使用 qoder-fast-bytes-v1 策略或现有字节估算策略.
"""

from __future__ import annotations

import json

_BYTES_PER_TOKEN = 4  # 经验值


def estimate_qoder_tokens(text: str) -> int:
    """估算 Qoder 文本的 token 数.

    使用字节长度 / 4 的经验公式.

    Args:
        text: 需要估算的 Qoder 文本.

    Returns:
        基于 UTF-8 字节长度估算的 token 数.
    """
    if not text:
        return 0
    return max(0, len(text.encode('utf-8')) // _BYTES_PER_TOKEN)


def estimate_qoder_tokens_from_structured(data: dict) -> int:
    """从结构化数据估算 Qoder token 数.

    将数据结构化为 JSON 字符串后估算.

    Args:
        data: 需要估算的结构化 payload.

    Returns:
        序列化后文本的 Qoder token 估算值.
    """
    text = json.dumps(data, ensure_ascii=False)
    return estimate_qoder_tokens(text)
