"""集中式 token 估算工具。

All token-count estimations go through this module so that heuristics
are consistent and auditable.  No heavy dependencies (tiktoken, etc.)
in phase 1 — we use character-class weighted estimation.
"""

from __future__ import annotations

import re


# 说明：─── Character classification helpers ──────────────────────────────────

# 说明：CJK (Chinese, Japanese, Korean) characters
_CJK_RE = re.compile(r'[一-鿿぀-ゟ゠-ヿ가-힯]')
# 说明：ASCII printable (letters, digits, common punctuation, spaces)
_ASCII_RE = re.compile(r'[\x20-\x7e]')
# 说明：Code-like punctuation (braces, brackets, quotes used in code/JSON)
_CODE_PUNCT_RE = re.compile(r'[{}()\[\]\"\'\\;:,.<>+=~`/@#$%^&*|]')


def count_cjk(text: str) -> int:
    """统计 CJK characters in text."""
    return len(_CJK_RE.findall(text))


def count_ascii(text: str) -> int:
    """统计 ASCII characters in text."""
    return len(_ASCII_RE.findall(text))


def count_code_punctuation(text: str) -> int:
    """统计 code-like punctuation characters."""
    return len(_CODE_PUNCT_RE.findall(text))


# 说明：─── Core estimator ────────────────────────────────────────────────────

# Heuristic ratios tuned，用于 common LLM tokenisers (cl100k_base style):
# 说明：CJK: ~1.8 chars per token (Chinese characters are often 1 token each,
# 说明：but some multi-char terms compress)
# 说明：ASCII: ~4.0 chars per token
# 说明：Code punctuation: ~3.0 chars per token (denser than prose)
_CJK_RATIO = 1.8
_ASCII_RATIO = 4.0
_CODE_PUNCT_RATIO = 3.0


def estimate_tokens_from_text(text: str, model: str = "") -> int:
    """Estimate token count，来源于 plain text.

    Uses mutually exclusive character-class weighted heuristic:
      - CJK chars / 1.8
      - Code punctuation / 3.0
      - ASCII non-code chars / 4.0  (ASCII minus code punctuation)
      - Other unicode / 2.5

    Code punctuation characters are also ASCII, so we subtract them
    from the ASCII count to avoid double counting.

    Args:
        text: Input text (may be mixed Chinese/English/code).
        model: Optional model hint (reserved for future model-specific
               heuristics; currently ignored).

    Returns:
        Estimated token count (int, >= 1 for non-empty text, 0 for empty).
    """
    if not text or not text.strip():
        return 0

    chinese_chars = count_cjk(text)
    ascii_chars = count_ascii(text)
    code_punct = count_code_punctuation(text)

    # Mutually exclusive: subtract code punctuation，来源于 ASCII
    ascii_non_code = max(0, ascii_chars - code_punct)

    # Other unicode: total length minus CJK, ASCII, 和 other unicode
    # 说明：(non-ASCII, non-CJK characters like emoji, mathematical symbols, etc.)
    total_len = len(text)
    other_unicode = max(0, total_len - chinese_chars - ascii_chars)

    estimated = (chinese_chars / _CJK_RATIO
                 + code_punct / _CODE_PUNCT_RATIO
                 + ascii_non_code / _ASCII_RATIO
                 + other_unicode / 2.5)

    return max(1, int(round(estimated)))


def estimate_tokens_from_list(texts: list[str], model: str = "") -> int:
    """Estimate total tokens，来源于 一个 list of text fragments."""
    return sum(estimate_tokens_from_text(t, model) for t in texts if t)
