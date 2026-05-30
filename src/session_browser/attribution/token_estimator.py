"""Centralised token estimation utilities.

All token-count estimations go through this module so that heuristics
are consistent and auditable.  No heavy dependencies (tiktoken, etc.)
in phase 1 — we use character-class weighted estimation.
"""

from __future__ import annotations

import re


# ─── Character classification helpers ──────────────────────────────────

# CJK (Chinese, Japanese, Korean) characters
_CJK_RE = re.compile(r'[一-鿿぀-ゟ゠-ヿ가-힯]')
# ASCII printable (letters, digits, common punctuation, spaces)
_ASCII_RE = re.compile(r'[\x20-\x7e]')
# Code-like punctuation (braces, brackets, quotes used in code/JSON)
_CODE_PUNCT_RE = re.compile(r'[{}()\[\]\"\'\\;:,.<>+=~`/@#$%^&*|]')


def count_cjk(text: str) -> int:
    """Count CJK characters in text."""
    return len(_CJK_RE.findall(text))


def count_ascii(text: str) -> int:
    """Count ASCII characters in text."""
    return len(_ASCII_RE.findall(text))


def count_code_punctuation(text: str) -> int:
    """Count code-like punctuation characters."""
    return len(_CODE_PUNCT_RE.findall(text))


# ─── Core estimator ────────────────────────────────────────────────────

# Heuristic ratios tuned for common LLM tokenisers (cl100k_base style):
#   CJK: ~1.8 chars per token (Chinese characters are often 1 token each,
#          but some multi-char terms compress)
#   ASCII: ~4.0 chars per token
#   Code punctuation: ~3.0 chars per token (denser than prose)
_CJK_RATIO = 1.8
_ASCII_RATIO = 4.0
_CODE_PUNCT_RATIO = 3.0


def estimate_tokens_from_text(text: str, model: str = "") -> int:
    """Estimate token count from plain text.

    Uses character-class weighted heuristic:
      - CJK chars / 1.8
      - ASCII chars / 4.0
      - Code punctuation / 3.0

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

    estimated = (chinese_chars / _CJK_RATIO
                 + ascii_chars / _ASCII_RATIO
                 + code_punct / _CODE_PUNCT_RATIO)

    return max(1, int(round(estimated)))


def estimate_tokens_from_list(texts: list[str], model: str = "") -> int:
    """Estimate total tokens from a list of text fragments."""
    return sum(estimate_tokens_from_text(t, model) for t in texts if t)
