"""Residuals：residual/unknown 插入与解释。"""

from __future__ import annotations


def compute_residual(
    *,
    provider_total: int = 0,
    reconstructed_total: int = 0,
    likely_sources: list[str] | None = None,
) -> dict:
    """计算 residual tokens 并解释可能来源。

    Args:
        provider_total: provider/broker 报告的 total input
        reconstructed_total: 本地重建的 spans token 总和
        likely_sources: 可能的缺失来源列表

    Returns:
        {"residual_tokens": int, "likely_sources": list, "note": str}
    """
    if provider_total <= 0:
        return {
            "residual_tokens": 0,
            "likely_sources": likely_sources or [],
            "note": "无 provider total，无法计算 residual",
        }

    residual = max(0, provider_total - reconstructed_total)

    default_sources = [
        "hidden system prompt",
        "tokenizer overhead",
        "provider wrapper overhead",
    ]
    sources = likely_sources or default_sources

    if residual == 0:
        note = "本地重建已覆盖全部 provider tokens"
    elif residual < provider_total * 0.1:
        note = f"残差 {residual} tokens（{residual/provider_total*100:.1f}%），在可接受范围内"
    else:
        note = f"残差 {residual} tokens（{residual/provider_total*100:.1f}%），可能来源：{', '.join(sources)}"

    return {
        "residual_tokens": residual,
        "likely_sources": sources,
        "note": note,
    }
