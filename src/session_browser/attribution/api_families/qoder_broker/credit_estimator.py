"""Qoder credit estimator：基于 token 估算 credit。

当无法获得 exact credit delta 时，根据 tokens 和 model tier 估算。
"""

from __future__ import annotations

# Qoder model tier 估算费率（tokens -> credits）
_QODER_TIER_RATES = {
    "performance-tier": 0.0003,  # 示例费率
    "standard-tier": 0.0001,
    "unknown": 0.0002,
}


def estimate_qoder_credits(
    *,
    input_tokens: int,
    output_tokens: int = 0,
    model_tier: str = "unknown",
) -> dict:
    """基于 token 数估算 Qoder credit。

    Returns:
        {"total_credits": float, "precision": "estimated", "source": str, "note": str}
    """
    rate = _QODER_TIER_RATES.get(model_tier, _QODER_TIER_RATES["unknown"])
    total_tokens = input_tokens + output_tokens
    estimated_credits = total_tokens * rate

    return {
        "total_credits": estimated_credits,
        "precision": "estimated",
        "source": f"estimated_from_tokens_and_{model_tier}",
        "note": f"按 {rate} credits/token 估算，共 {total_tokens} tokens",
    }
