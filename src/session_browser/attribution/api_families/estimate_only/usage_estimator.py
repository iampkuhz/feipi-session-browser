"""Estimate-only usage estimator：无 provider/broker usage 时的本地重建。

当无 provider 数据时：
  total_input = reconstructed_prompt_span_tokens + residual_estimate
  fresh/cache_read/cache_write = unavailable 或 heuristic-inferred
  output = reconstructed visible text/tool_use/reasoning metadata estimate
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown


def estimate_usage_from_spans(
    *,
    input_spans_token_sum: int = 0,
    output_spans_token_sum: int = 0,
    residual_estimate: int = 0,
) -> UsageBreakdown:
    """从 reconstructed spans 估算 usage。

    Args:
        input_spans_token_sum: 所有 input spans 的 token 估算总和
        output_spans_token_sum: 所有 output spans 的 token 估算总和
        residual_estimate: 额外残差估算（hidden system prompt、tokenizer overhead 等）

    Returns:
        UsageBreakdown，precision=estimated/heuristic
    """
    total_input = input_spans_token_sum + residual_estimate if residual_estimate > 0 else input_spans_token_sum

    return UsageBreakdown(
        total_input=total_input if total_input > 0 else None,
        fresh_input=None,
        cache_read=None,
        cache_write=None,
        output=output_spans_token_sum if output_spans_token_sum > 0 else None,
        usage_source="local_reconstruction",
        precision="estimated",
        note=(
            f"本地重建：{input_spans_token_sum} input spans + {residual_estimate} residual"
            if residual_estimate > 0
            else f"本地重建：{input_spans_token_sum} input spans"
        ),
    )
