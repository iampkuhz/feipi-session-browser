"""Tiktoken counter：使用 tiktoken 库进行精确 token 计数。

如果 tiktoken 未安装，自动 fallback 到 heuristic counter。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_tiktoken_encoder = None


def _get_tiktoken_encoder():
    """惰性加载 tiktoken。"""
    global _tiktoken_encoder
    if _tiktoken_encoder is not None:
        return _tiktoken_encoder

    try:
        import tiktoken
        _tiktoken_encoder = tiktoken.encoding_for_model("gpt-4o")
    except ImportError:
        logger.debug("tiktoken 未安装，将使用 heuristic counter")
        _tiktoken_encoder = False  # 标记为不可用
    except Exception as exc:
        logger.debug("tiktoken 加载失败: %s", exc)
        _tiktoken_encoder = False

    return _tiktoken_encoder


def count_tokens_tiktoken(text: str, model: str = "gpt-4o") -> int | None:
    """使用 tiktoken 精确计数。

    Args:
        text: 输入文本
        model: 模型名

    Returns:
        精确 token 数，如果 tiktoken 不可用则返回 None
    """
    if not text:
        return 0

    encoder = _get_tiktoken_encoder()
    if encoder is False:
        return None

    try:
        return len(encoder.encode(text))
    except Exception as exc:
        logger.debug("tiktoken 计数失败: %s", exc)
        return None
