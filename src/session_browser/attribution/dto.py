"""Wire DTOs for LLM attribution API payloads.

These DTOs keep route JSON assembly out of core domain objects. They are light
because bucket/detail contents are intentionally agent-specific dict payloads,
but the top-level API contract is explicit and validated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMRequestAttributionPayloadDTO:
    """Top-level JSON payload returned for request-side attribution."""

    schema_version: str
    call_identity: dict[str, Any]
    usage_summary: dict[str, Any]
    ordered_spans: list[dict[str, Any]]
    semantic_buckets: list[dict[str, Any]]
    coverage: dict[str, Any]
    credit_summary: dict[str, Any] | None
    diagnostics: dict[str, Any]
    accounting_attribution: dict[str, Any]
    kind: str
    agent: str
    model: str
    request_id: str
    call_id: str
    source_label: str
    confidence_label: str
    raw_body_available: bool
    usage: dict[str, Any]
    buckets: list[dict[str, Any]]
    captured_context_preview: str
    attribution_notes: list[str]
    availability_rows: list[dict[str, Any]]
    timing: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != "llm_attribution_v2":
            raise ValueError("request attribution payload schema_version must be llm_attribution_v2")
        if self.kind != "llm.request_attribution":
            raise ValueError("request attribution payload kind mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "call_identity": self.call_identity,
            "usage_summary": self.usage_summary,
            "ordered_spans": self.ordered_spans,
            "semantic_buckets": self.semantic_buckets,
            "coverage": self.coverage,
            "credit_summary": self.credit_summary,
            "diagnostics": self.diagnostics,
            "accounting_attribution": self.accounting_attribution,
            "kind": self.kind,
            "agent": self.agent,
            "model": self.model,
            "request_id": self.request_id,
            "call_id": self.call_id,
            "source_label": self.source_label,
            "confidence_label": self.confidence_label,
            "raw_body_available": self.raw_body_available,
            "usage": self.usage,
            "buckets": self.buckets,
            "captured_context_preview": self.captured_context_preview,
            "attribution_notes": self.attribution_notes,
            "availability_rows": self.availability_rows,
            "timing": self.timing,
        }


@dataclass(frozen=True)
class LLMResponseAttributionPayloadDTO:
    """Top-level JSON payload returned for response-side attribution."""

    schema_version: str
    call_identity: dict[str, Any]
    usage_summary: dict[str, Any]
    response_spans: list[dict[str, Any]]
    semantic_buckets: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    accounting_attribution: dict[str, Any]
    kind: str
    agent: str
    model: str
    request_id: str
    call_id: str
    source_label: str
    confidence_label: str
    raw_body_available: bool
    usage: dict[str, Any]
    buckets: list[dict[str, Any]]
    blocks: list[dict[str, Any]]
    captured_output_preview: str
    attribution_notes: list[str]
    availability_rows: list[dict[str, Any]]

    def __post_init__(self) -> None:
        if self.schema_version != "llm_attribution_v2":
            raise ValueError("response attribution payload schema_version must be llm_attribution_v2")
        if self.kind != "llm.response_attribution":
            raise ValueError("response attribution payload kind mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "call_identity": self.call_identity,
            "usage_summary": self.usage_summary,
            "response_spans": self.response_spans,
            "semantic_buckets": self.semantic_buckets,
            "diagnostics": self.diagnostics,
            "accounting_attribution": self.accounting_attribution,
            "kind": self.kind,
            "agent": self.agent,
            "model": self.model,
            "request_id": self.request_id,
            "call_id": self.call_id,
            "source_label": self.source_label,
            "confidence_label": self.confidence_label,
            "raw_body_available": self.raw_body_available,
            "usage": self.usage,
            "buckets": self.buckets,
            "blocks": self.blocks,
            "captured_output_preview": self.captured_output_preview,
            "attribution_notes": self.attribution_notes,
            "availability_rows": self.availability_rows,
        }


@dataclass(frozen=True)
class AttributionErrorPayloadDTO:
    """Minimal error payload for attribution failures."""

    kind: str
    agent: str
    call_id: str
    round_id: str
    error_type: str
    message: str
    fallback: str

    def __post_init__(self) -> None:
        if self.kind != "llm.attribution_error":
            raise ValueError("attribution error payload kind mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "agent": self.agent,
            "call_id": self.call_id,
            "round_id": self.round_id,
            "error_type": self.error_type,
            "message": self.message,
            "fallback": self.fallback,
        }
