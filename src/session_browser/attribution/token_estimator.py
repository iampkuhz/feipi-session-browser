"""Estimate token counts for attribution when provider totals are unavailable."""

from __future__ import annotations

import re

_CJK_RE = re.compile('[\\u4e00-\\u9fff\\u3040-\\u309f\\u30a0-\\u30ff\\uac00-\\ud7af]')
_ASCII_RE = re.compile(r'[\x20-\x7e]')
_CODE_PUNCT_RE = re.compile(r'[{}()\[\]\"\'\\;:,.<>+=~`/@#$%^&*|]')

_CJK_RATIO = 1.8
_ASCII_RATIO = 4.0
_CODE_PUNCT_RATIO = 3.0
_OTHER_UNICODE_RATIO = 2.5


def count_cjk(text: str) -> int:
    """Count Chinese, Japanese, Korean, and Hangul characters in text.

    The attribution estimator calls this helper before assigning heuristic token
    counts to prompt spans. CJK characters compress differently from ASCII prose, so
    they use a dedicated ratio.

    Args:
        text: Text preview extracted from an attribution evidence item.

    Returns:
        Number of CJK-range characters in the text.
    """
    return len(_CJK_RE.findall(text))


def count_ascii(text: str) -> int:
    """Count printable ASCII characters in text.

    Args:
        text: Text preview extracted from an attribution evidence item.

    Returns:
        Number of printable ASCII characters in the text.
    """
    return len(_ASCII_RE.findall(text))


def count_code_punctuation(text: str) -> int:
    """Count code-like punctuation characters in text.

    Args:
        text: Text preview extracted from an attribution evidence item.

    Returns:
        Number of punctuation characters commonly dense in code or JSON payloads.
    """
    return len(_CODE_PUNCT_RE.findall(text))


def estimate_tokens_from_text(text: str, model: str = '') -> int:
    """Estimate token count from plain text with auditable character ratios.

    Attribution builders call this when provider usage cannot identify exact span
    costs. The heuristic uses mutually exclusive CJK, code punctuation, ASCII prose,
    and other-Unicode buckets so estimates are stable across agents.

    Args:
        text: Input text that may contain mixed Chinese, English, or code.
        model: Optional model hint reserved for future model-specific heuristics.

    Returns:
        Estimated token count, with zero for empty text and at least one for non-empty
        text.
    """
    if not text or not text.strip():
        return 0

    chinese_chars = count_cjk(text)
    ascii_chars = count_ascii(text)
    code_punct = count_code_punctuation(text)

    ascii_non_code = max(0, ascii_chars - code_punct)
    total_len = len(text)
    other_unicode = max(0, total_len - chinese_chars - ascii_chars)

    estimated = (
        chinese_chars / _CJK_RATIO
        + code_punct / _CODE_PUNCT_RATIO
        + ascii_non_code / _ASCII_RATIO
        + other_unicode / _OTHER_UNICODE_RATIO
    )

    return max(1, round(estimated))


def estimate_tokens_from_list(texts: list[str], model: str = '') -> int:
    """Estimate total tokens for multiple text fragments.

    Args:
        texts: Text previews or fragments to estimate.
        model: Optional model hint passed through to each fragment estimate.

    Returns:
        Sum of token estimates for non-empty fragments.
    """
    return sum(estimate_tokens_from_text(text, model) for text in texts if text)
