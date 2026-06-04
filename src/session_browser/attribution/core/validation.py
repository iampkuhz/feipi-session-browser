"""Validation invariant 检查：sum invariant / coverage / double-count 检查。"""

from __future__ import annotations

from session_browser.attribution.core.models import PromptSpan, UsageBreakdown


def validate_attribution(
    *,
    spans: list[PromptSpan],
    usage: UsageBreakdown | None = None,
    api_family: str = "unknown",
) -> list[dict]:
    """验证归因结果的不变量。

    检查项：
    1. request span allocated tokens sum <= total_input
    2. OpenAI cache_write unavailable
    3. Qoder no usage 不标 provider_reported
    4. current user message 不双算（由上游保证）
    5. response tool schema 不计 output（由上游保证）

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

    return results
