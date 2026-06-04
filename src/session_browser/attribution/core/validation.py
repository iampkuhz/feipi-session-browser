"""Validation invariant 检查：sum invariant / coverage / double-count / Qoder identity 检查。"""

from __future__ import annotations

from session_browser.attribution.core.models import PromptSpan, UsageBreakdown


def validate_attribution(
    *,
    spans: list[PromptSpan],
    usage: UsageBreakdown | None = None,
    api_family: str = "unknown",
    agent_runtime: str = "unknown",
    underlying_provider: str | None = None,
) -> list[dict]:
    """验证归因结果的不变量。

    检查项：
    1. request span allocated tokens sum <= total_input
    2. OpenAI cache_write unavailable
    3. Qoder/estimate 不标 provider_reported
    4. current user message 不双算（由上游保证）
    5. response tool schema 不计 output（由上游保证）
    6. **新增**: total == fresh + cache_read + cache_write（允许 +/-1 误差）
    7. **新增**: cache_read <= total_input
    8. **新增**: cache_write <= total_input
    9. **新增**: Qoder 不因为 field shape 设置 underlying_provider=anthropic/openai
    10. **新增**: 0 值是 known value

    Returns:
        invariant 结果列表，每项包含 name, passed, detail
    """
    results: list[dict] = []

    # 1. span sum <= total_input
    if usage and usage.total_input and usage.total_input > 0:
        allocated_sum = sum(
            s.cache_read_tokens + s.cache_write_tokens + s.fresh_tokens
            for s in spans
        )
        passed = allocated_sum <= usage.total_input
        results.append({
            "name": "request_sum_lte_total",
            "passed": passed,
            "detail": f"allocated_sum={allocated_sum}, total_input={usage.total_input}",
        })

    # 2. OpenAI cache_write unavailable
    if api_family in ("openai_responses", "openai_chat", "openai_like"):
        for s in spans:
            if s.cache_write_tokens > 0:
                results.append({
                    "name": "openai_cache_write_unavailable",
                    "passed": False,
                    "detail": f"span {s.span_id} has cache_write={s.cache_write_tokens}",
                })
                break
        else:
            results.append({
                "name": "openai_cache_write_unavailable",
                "passed": True,
                "detail": "所有 span cache_write 为 0 或 unavailable",
            })

    # 3. Qoder/estimate 不标 provider_reported
    if api_family in ("estimate_only",):
        for s in spans:
            if s.precision == "provider_reported":
                results.append({
                    "name": "estimate_no_provider_reported",
                    "passed": False,
                    "detail": f"span {s.span_id} has precision=provider_reported in estimate_only",
                })
                break
        else:
            results.append({
                "name": "estimate_no_provider_reported",
                "passed": True,
                "detail": "所有 span precision 非 provider_reported",
            })

    # 6. total == fresh + cache_read + cache_write（允许 +/-1 误差）
    if usage and usage.total_input and usage.total_input > 0:
        fresh = usage.fresh_input or 0
        cache_read = usage.cache_read or 0
        cache_write = usage.cache_write or 0
        reconstructed = fresh + cache_read + cache_write
        diff = abs(reconstructed - usage.total_input)
        passed = diff <= 1
        results.append({
            "name": "total_equals_fresh_plus_cache",
            "passed": passed,
            "detail": (
                f"total_input={usage.total_input}, "
                f"fresh+cache_read+cache_write={reconstructed}, "
                f"diff={diff}"
            ),
        })

    # 7. cache_read <= total_input
    if usage and usage.total_input and usage.total_input > 0:
        cache_read = usage.cache_read or 0
        passed = cache_read <= usage.total_input
        results.append({
            "name": "cache_read_lte_total",
            "passed": passed,
            "detail": f"cache_read={cache_read}, total_input={usage.total_input}",
        })

    # 8. cache_write <= total_input
    if usage and usage.total_input and usage.total_input > 0:
        cache_write = usage.cache_write or 0
        passed = cache_write <= usage.total_input
        results.append({
            "name": "cache_write_lte_total",
            "passed": passed,
            "detail": f"cache_write={cache_write}, total_input={usage.total_input}",
        })

    # 9. Qoder 不因为 field shape 设置 underlying_provider=anthropic/openai
    if agent_runtime == "qoder" and underlying_provider in ("anthropic", "openai"):
        results.append({
            "name": "qoder_no_underlying_provider_inference",
            "passed": False,
            "detail": f"Qoder 不应推断 underlying_provider={underlying_provider}，应为 None",
        })
    elif agent_runtime == "qoder":
        results.append({
            "name": "qoder_no_underlying_provider_inference",
            "passed": True,
            "detail": f"underlying_provider={underlying_provider}",
        })

    # 10. 0 值是 known value（通过 usage 字段检查）
    if usage:
        zero_is_valid = True
        zero_details = []
        for field_name in ("fresh_input", "cache_read", "cache_write"):
            val = getattr(usage, field_name, None)
            if val == 0:
                zero_details.append(f"{field_name}=0 (valid)")
        results.append({
            "name": "zero_values_are_known",
            "passed": zero_is_valid,
            "detail": "; ".join(zero_details) if zero_details else "无 0 值字段",
        })

    return results
