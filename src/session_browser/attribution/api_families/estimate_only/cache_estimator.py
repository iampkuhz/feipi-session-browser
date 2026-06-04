"""Estimate-only cache estimator：本地 cache 估算（通常 unavailable）。"""

from __future__ import annotations


def estimate_cache_tokens(
    *,
    total_input: int = 0,
    has_prior_context: bool = False,
) -> dict:
    """估算本地 cache tokens（启发式）。

    返回 unavailable，因为本地无法确认 provider cache 行为。
    """
    return {
        "cache_read": None,
        "cache_write": None,
        "precision": "unavailable",
        "note": "本地无法确认 provider cache 行为",
    }
