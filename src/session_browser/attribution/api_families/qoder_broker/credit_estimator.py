"""Qoder credit estimator：基于 token 估算 credit。

当无法获得 exact credit delta 时：
- 如果没有本地显式校准费率（calibration rates），不输出看似精确的 numeric credit。
- 返回 ``credits=None``，``precision="unavailable"``，并附说明 note。
- 只有传入显式 calibration rates 时，才进行估算并标注来源。
"""

from __future__ import annotations


def estimate_qoder_credits(
    *,
    input_tokens: int,
    output_tokens: int = 0,
    model_tier: str = "unknown",
    calibration_rates: dict[str, float] | None = None,
) -> dict:
    """基于 token 数估算 Qoder credit。

    Args:
        input_tokens: 输入 token 数
        output_tokens: 输出 token 数
        model_tier: model tier 标识
        calibration_rates: 显式校准费率 {model_tier: credits_per_token}。
            如果不提供，不输出 pseudo-precise 估算值。

    Returns:
        {"total_credits": float|None, "precision": str, "source": str, "note": str}
    """
    # 有显式校准费率时才估算
    if calibration_rates and isinstance(calibration_rates, dict):
        rate = calibration_rates.get(model_tier)
        if rate is not None and rate > 0:
            total_tokens = input_tokens + output_tokens
            estimated_credits = total_tokens * rate
            return {
                "total_credits": estimated_credits,
                "precision": "estimated",
                "source": f"estimated_from_calibrated_rates_{model_tier}",
                "note": f"使用本地校准费率 {rate} credits/token，共 {total_tokens} tokens",
            }

    # 无校准费率时：不输出伪精确值
    return {
        "total_credits": None,
        "precision": "unavailable",
        "source": "unavailable",
        "note": "Qoder credit 与 token/model tier 相关，但当前缺少 exact credit delta 或本地校准费率",
    }
