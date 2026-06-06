"""Serializers for attribution data layer.

Converts internal dataclass objects to dict payloads for routes.py.
输出 route payload 字段与 v2 attribution 字段（schema_version,
call_identity, ordered_spans, semantic_buckets, coverage,
credit_summary, diagnostics）。
"""

from __future__ import annotations

from dataclasses import asdict

from session_browser.attribution.contracts import (
    AttributedValue,
    AvailabilityRow,
    RequestAttributionBucket,
    ResponseAttributionBucket,
    LLMRequestAttribution,
    LLMResponseAttribution,
)


def attributed_value_to_dict(v: AttributedValue) -> dict:
    """Convert an AttributedValue to a serializable dict."""
    return {
        "value": v.value,
        "unit": v.unit,
        "precision": v.precision,
        "source": v.source,
        "fill_strategy": v.fill_strategy,
        "note": v.note,
    }


def _request_bucket_to_dict(b: RequestAttributionBucket) -> dict:
    """Convert a request bucket to a serializable dict."""
    return {
        "key": b.key,
        "label": b.label,
        "tokens": b.tokens,
        "percent": b.percent,
        "count_label": b.count_label,
        "precision": b.precision,
        "source": b.source,
        "confidence_label": b.confidence_label,
        "summary": b.summary,
        "contributes_to_total": b.contributes_to_total,
        "parent_key": b.parent_key,
        "display_group": b.display_group,
        "expandable": b.expandable,
        "content_preview": b.content_preview,
        "details": b.details,
    }


def _response_bucket_to_dict(b: ResponseAttributionBucket) -> dict:
    """Convert a response bucket to a serializable dict."""
    return {
        "key": b.key,
        "label": b.label,
        "tokens": b.tokens,
        "percent": b.percent,
        "count_label": b.count_label,
        "precision": b.precision,
        "source": b.source,
        "confidence_label": b.confidence_label,
        "summary": b.summary,
        "contributes_to_total": b.contributes_to_total,
        "parent_key": b.parent_key,
        "display_group": b.display_group,
        "block_refs": b.block_refs,
        "details": b.details,
    }


def availability_row_to_dict(row: AvailabilityRow | dict) -> dict:
    """Convert an AvailabilityRow or legacy dict row to a serializable dict."""
    if isinstance(row, dict):
        return row
    return asdict(row)


def request_attribution_to_payload(attr: LLMRequestAttribution, v2_extra: dict | None = None) -> dict:
    """Serialize a full LLMRequestAttribution to a route-ready payload dict.

    包含 schema_version, call_identity, usage_summary (AttributedValue 格式),
    ordered_spans, semantic_buckets, coverage, credit_summary, diagnostics。
    """
    v2_extra = v2_extra or {}

    payload = {
        # ── v2 schema ──
        "schema_version": "llm_attribution_v2",

        # ── Call identity (v2) ──
        "call_identity": v2_extra.get("call_identity", _build_call_identity(attr)),

        # ── Usage summary with AttributedValue fields (v2) ──
        "usage_summary": {
            "total_input": attributed_value_to_dict(attr.total_input),
            "fresh_input": attributed_value_to_dict(attr.fresh_input),
            "cache_read": attributed_value_to_dict(attr.cache_read),
            "cache_write": attributed_value_to_dict(attr.cache_write),
            "output": attributed_value_to_dict(_get_output_from_notes(attr)),
        },

        # ── Ordered spans (v2) ──
        "ordered_spans": v2_extra.get("ordered_spans", []),

        # ── Semantic buckets (v2) ──
        "semantic_buckets": v2_extra.get("semantic_buckets", []),

        # ── Coverage (v2) ──
        "coverage": v2_extra.get("coverage", _build_coverage(attr)),

        # ── Credit summary (v2, Qoder) ──
        "credit_summary": v2_extra.get("credit_summary", None),

        # ── Diagnostics (v2) ──
        "diagnostics": v2_extra.get("diagnostics", _build_diagnostics(attr)),

        # ── Route payload fields ──
        "kind": "llm.request_attribution",
        "agent": attr.agent,
        "model": attr.model,
        "request_id": attr.request_id,
        "call_id": attr.call_id,
        "source_label": attr.source_label,
        "confidence_label": attr.confidence_label,
        "raw_body_available": attr.raw_body_available,
        "usage": {
            "total_input": attributed_value_to_dict(attr.total_input),
            "fresh_input": attributed_value_to_dict(attr.fresh_input),
            "cache_read": attributed_value_to_dict(attr.cache_read),
            "cache_write": attributed_value_to_dict(attr.cache_write),
            "coverage": attributed_value_to_dict(attr.coverage),
            "unknown": attributed_value_to_dict(attr.unknown),
        },
        "buckets": [_request_bucket_to_dict(b) for b in attr.buckets],
        "captured_context_preview": attr.captured_context_preview,
        "attribution_notes": list(attr.attribution_notes),
        "availability_rows": [availability_row_to_dict(r) for r in attr.availability_rows],
        "timing": {
            "request_at": attr.timing.get("request_at", "—") if hasattr(attr, "timing") and attr.timing else "—",
            "response_at": attr.timing.get("response_at", "—") if hasattr(attr, "timing") and attr.timing else "—",
            "duration": attr.timing.get("duration", "—") if hasattr(attr, "timing") and attr.timing else "—",
        },
    }
    return payload


def response_attribution_to_payload(attr: LLMResponseAttribution, v2_extra: dict | None = None) -> dict:
    """Serialize a full LLMResponseAttribution to a route-ready payload dict."""
    v2_extra = v2_extra or {}

    payload = {
        # ── v2 schema ──
        "schema_version": "llm_attribution_v2",

        # ── Call identity (v2) ──
        "call_identity": v2_extra.get("call_identity", _build_call_identity(attr)),

        # ── Usage summary (v2) ──
        "usage_summary": {
            "total_output": attributed_value_to_dict(attr.total_output),
            "visible_text": attributed_value_to_dict(attr.visible_text),
            "tool_use": attributed_value_to_dict(attr.tool_use),
            "hidden_reasoning": attributed_value_to_dict(_get_hidden_reasoning(attr)),
            "metadata": attributed_value_to_dict(attr.metadata),
            "residual": attributed_value_to_dict(attr.unknown),
        },

        # ── Response spans (v2) ──
        "response_spans": v2_extra.get("response_spans", []),

        # ── Semantic buckets (v2) ──
        "semantic_buckets": v2_extra.get("semantic_buckets", []),

        # ── Diagnostics (v2) ──
        "diagnostics": v2_extra.get("diagnostics", _build_response_diagnostics(attr)),

        # ── Route payload fields ──
        "kind": "llm.response_attribution",
        "agent": attr.agent,
        "model": attr.model,
        "request_id": attr.request_id,
        "call_id": attr.call_id,
        "source_label": attr.source_label,
        "confidence_label": attr.confidence_label,
        "raw_body_available": attr.raw_body_available,
        "usage": {
            "total_output": attributed_value_to_dict(attr.total_output),
            "visible_text": attributed_value_to_dict(attr.visible_text),
            "tool_use": attributed_value_to_dict(attr.tool_use),
            "metadata": attributed_value_to_dict(attr.metadata),
            "coverage": attributed_value_to_dict(attr.coverage),
            "unknown": attributed_value_to_dict(attr.unknown),
            "finish_reason": attributed_value_to_dict(attr.finish_reason),
        },
        "buckets": [_response_bucket_to_dict(b) for b in attr.buckets],
        "blocks": list(attr.blocks),
        "captured_output_preview": attr.captured_output_preview,
        "attribution_notes": list(attr.attribution_notes),
        "availability_rows": [availability_row_to_dict(r) for r in attr.availability_rows],
    }
    return payload


# ─── v2 helper functions ─────────────────────────────────────────────


def _build_call_identity(attr) -> dict:
    """构建 call_identity v2 字段。"""
    agent_runtime = attr.agent if attr.agent else "unknown"
    return {
        "agent_runtime": agent_runtime,
        "api_family": _infer_api_family_from_agent(agent_runtime),
        "provider_or_broker": _infer_provider_from_agent(agent_runtime),
        "underlying_provider": None,
        "model": attr.model if attr.model and attr.model != "unknown" else None,
        "billing_units": ["tokens"] + (["credits"] if agent_runtime == "qoder" else []),
        "mapping_confidence": 0.5,
        "mapping_reasons": [f"agent={agent_runtime}"],
    }


def _infer_api_family_from_agent(agent: str) -> str:
    """从 agent 字符串推断默认 API Family。"""
    mapping = {
        "claude_code": "anthropic_messages",
        "codex": "openai_responses",
        "qoder": "qoder_broker",
    }
    return mapping.get(agent, "estimate_only")


def _infer_provider_from_agent(agent: str) -> str:
    """从 agent 字符串推断默认 Provider/Broker。"""
    mapping = {
        "claude_code": "anthropic",
        "codex": "openai",
        "qoder": "qoder",
    }
    return mapping.get(agent, "unknown")


def _get_output_from_notes(attr) -> AttributedValue:
    """从 notes 或 bucket 中尝试推断 output tokens。"""
    return AttributedValue(
        value=None, unit="tokens", precision="unavailable",
        source="heuristic", fill_strategy="not available in request",
    )


def _get_hidden_reasoning(attr) -> AttributedValue:
    """推断 hidden reasoning tokens。"""
    return AttributedValue(
        value=None, unit="tokens", precision="unavailable",
        source="heuristic", fill_strategy="not detected",
    )


def _build_coverage(attr) -> dict:
    """构建 coverage v2 对象。"""
    total_val = (attr.total_input.value if hasattr(attr, 'total_input') and attr.total_input else 0) or 0
    unknown_val = (attr.unknown.value if hasattr(attr, 'unknown') and attr.unknown else 0) or 0
    reconstructed = max(0, total_val - unknown_val) if total_val > 0 else 0
    return {
        "provider_total_input": total_val,
        "reconstructed_total": reconstructed,
        "coverage_ratio": round(reconstructed / total_val, 3) if total_val > 0 else 0.0,
        "residual_tokens": unknown_val,
        "residual_likely_sources": ["unclassified overhead"],
    }


def _build_diagnostics(attr) -> dict:
    """构建 diagnostics v2 对象。"""
    return {
        "invariants": [{"name": "legacy_mode", "passed": True}],
        "warnings": [],
    }


def _build_response_diagnostics(attr) -> dict:
    """构建 response diagnostics v2 对象。"""
    return {
        "tool_schema_counted_as_output": False,
        "invariants": [{"name": "legacy_mode", "passed": True}],
        "warnings": [],
    }


def attribution_error_to_payload(
    agent: str,
    call_id: str,
    round_id: str,
    error_type: str,
    message: str,
) -> dict:
    """Create a diagnostic error payload when attribution building fails.

    This payload is intentionally minimal — it does NOT include full
    tracebacks to avoid leaking sensitive data into the UI.
    """
    return {
        "kind": "llm.attribution_error",
        "agent": agent,
        "call_id": call_id,
        "round_id": round_id,
        "error_type": error_type,
        "message": message,
        "fallback": "Attribution unavailable; base LLM context/output payloads are still available.",
    }
