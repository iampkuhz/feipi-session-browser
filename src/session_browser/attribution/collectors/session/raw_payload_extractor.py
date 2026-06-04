"""原始载荷提取器：提取 LLM call 的原始 request/response payload。"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence


def extract_raw_payload(
    request_full: str | None = None,
    response_full: str | None = None,
    call_id: str = "",
    evidence_counter: int = 0,
) -> list[Evidence]:
    """提取原始 request/response payload。

    Args:
        request_full: 完整 request 文本（可能包含 JSON）
        response_full: 完整 response 文本
        call_id: LLM call ID
        evidence_counter: evidence ID 起始计数器

    Returns:
        Evidence 列表，scope=provider_usage
    """
    results = []
    idx = evidence_counter

    if request_full:
        # 尝试脱敏敏感字段
        safe_text = _redact_sensitive(request_full)
        results.append(Evidence(
            evidence_id=f"raw_request_{idx}",
            scope="provider_usage",
            kind="request_payload",
            content_ref=ContentRef(
                kind="inline",
                preview=safe_text[:300],
                can_load_full=True,
                redaction_applied=True,
            ),
            content_preview=safe_text[:200],
            token_estimate=len(safe_text) // 4,
            precision="extracted",
            confidence=0.95,
        ))

    if response_full:
        safe_text = _redact_sensitive(response_full)
        results.append(Evidence(
            evidence_id=f"raw_response_{idx + 1}",
            scope="provider_usage",
            kind="response_payload",
            content_ref=ContentRef(
                kind="inline",
                preview=safe_text[:300],
                can_load_full=True,
                redaction_applied=True,
            ),
            content_preview=safe_text[:200],
            token_estimate=len(safe_text) // 4,
            precision="extracted",
            confidence=0.95,
        ))

    return results


def extract_usage_metadata(
    usage: dict | None = None,
    call_id: str = "",
    evidence_counter: int = 0,
) -> Evidence | None:
    """提取 usage 元数据（token counts）。

    Args:
        usage: usage dict，如 {"input_tokens": 100, "output_tokens": 50}
        call_id: LLM call ID
        evidence_counter: evidence ID 起始计数器

    Returns:
        Evidence 对象，scope=provider_usage, kind=usage_metadata
    """
    if not usage:
        return None

    return Evidence(
        evidence_id=f"usage_meta_{evidence_counter}",
        scope="provider_usage",
        kind="usage_metadata",
        content_ref=ContentRef(
            kind="inline",
            preview=str(usage)[:200],
            can_load_full=False,
        ),
        content_preview=str(usage)[:200],
        token_estimate=0,
        precision="provider_reported",
        confidence=1.0,
        extra={"usage": usage},
    )


def _redact_sensitive(text: str) -> str:
    """脱敏敏感字段。"""
    import re
    sensitive_keys = frozenset({
        "api_key", "apikey", "token", "secret", "password",
        "authorization", "credential", "bearer",
    })
    for key in sensitive_keys:
        pattern = re.compile(
            rf'("{key}"\s*:\s*)"([^"]*)"',
            re.IGNORECASE,
        )
        text = pattern.sub(r'\1"***REDACTED***"', text)
    return text
