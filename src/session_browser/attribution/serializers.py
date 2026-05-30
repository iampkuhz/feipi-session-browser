"""Serializers for attribution data layer.

Converts internal dataclass objects to dict payloads for routes.py.
This avoids duplicating dict-construction logic in the route handler.
"""

from __future__ import annotations

from session_browser.attribution.contracts import (
    AttributedValue,
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
    }


def request_attribution_to_payload(attr: LLMRequestAttribution) -> dict:
    """Serialize a full LLMRequestAttribution to a route-ready payload dict."""
    return {
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
        "availability_rows": [dict(r) for r in attr.availability_rows],
    }


def response_attribution_to_payload(attr: LLMResponseAttribution) -> dict:
    """Serialize a full LLMResponseAttribution to a route-ready payload dict."""
    return {
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
        "availability_rows": [dict(r) for r in attr.availability_rows],
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
