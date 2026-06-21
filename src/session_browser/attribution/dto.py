"""Define wire DTOs for LLM attribution API payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMRequestAttributionPayloadDTO:
    """Represent the top-level JSON payload for request-side attribution.

    Routes instantiate this DTO after request attribution has been serialized from
    domain contracts. It keeps the API schema explicit while allowing agent-specific
    dictionaries inside spans, buckets, diagnostics, and accounting details.

    Attributes:
        schema_version: Payload schema version, currently llm_attribution_v2.
        call_identity: Stable call identity and inferred provider metadata.
        usage_summary: Compact usage summary for header cards.
        ordered_spans: Request spans in provider or reconstructed order.
        semantic_buckets: Normalized semantic bucket payloads.
        coverage: Attribution coverage summary.
        credit_summary: Optional broker credit attribution summary.
        diagnostics: Validation and reconstruction diagnostics.
        accounting_attribution: Accounting field attribution payloads.
        kind: Payload kind, expected to be llm.request_attribution.
        agent: Runtime that produced the call.
        model: Model label associated with the call.
        request_id: Provider or local request identifier.
        call_id: Stable call identifier in the session.
        source_label: Human-readable source description.
        confidence_label: Overall confidence label.
        raw_body_available: Whether raw provider request data can be inspected.
        usage: Detailed usage payload.
        buckets: Legacy request bucket payloads.
        captured_context_preview: Safe reconstructed context preview.
        attribution_notes: Notes and caveats from builders.
        availability_rows: Availability table rows.
        timing: Optional timing metadata.
    """

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
        """Validate fixed discriminator fields after dataclass initialization.

        Raises:
            ValueError: Raised when schema version or kind does not match the request
                attribution API contract.
        """
        if self.schema_version != 'llm_attribution_v2':
            raise ValueError(
                'request attribution payload schema_version must be llm_attribution_v2'
            )
        if self.kind != 'llm.request_attribution':
            raise ValueError('request attribution payload kind mismatch')

    def to_dict(self) -> dict[str, Any]:
        """Serialize the request attribution DTO to a JSON-ready dictionary.

        Returns:
            Dictionary preserving the public request attribution API schema.
        """
        return {
            'schema_version': self.schema_version,
            'call_identity': self.call_identity,
            'usage_summary': self.usage_summary,
            'ordered_spans': self.ordered_spans,
            'semantic_buckets': self.semantic_buckets,
            'coverage': self.coverage,
            'credit_summary': self.credit_summary,
            'diagnostics': self.diagnostics,
            'accounting_attribution': self.accounting_attribution,
            'kind': self.kind,
            'agent': self.agent,
            'model': self.model,
            'request_id': self.request_id,
            'call_id': self.call_id,
            'source_label': self.source_label,
            'confidence_label': self.confidence_label,
            'raw_body_available': self.raw_body_available,
            'usage': self.usage,
            'buckets': self.buckets,
            'captured_context_preview': self.captured_context_preview,
            'attribution_notes': self.attribution_notes,
            'availability_rows': self.availability_rows,
            'timing': self.timing,
        }


@dataclass(frozen=True)
class LLMResponseAttributionPayloadDTO:
    """Represent the top-level JSON payload for response-side attribution.

    Routes instantiate this DTO after response attribution has been serialized from
    domain contracts. It keeps the top-level API stable while response blocks and
    semantic buckets remain agent-specific dictionaries.

    Attributes:
        schema_version: Payload schema version, currently llm_attribution_v2.
        call_identity: Stable call identity and inferred provider metadata.
        usage_summary: Compact usage summary for header cards.
        response_spans: Response spans in provider or reconstructed order.
        semantic_buckets: Normalized semantic bucket payloads.
        diagnostics: Validation and reconstruction diagnostics.
        accounting_attribution: Accounting field attribution payloads.
        kind: Payload kind, expected to be llm.response_attribution.
        agent: Runtime that produced the call.
        model: Model label associated with the call.
        request_id: Provider or local request identifier.
        call_id: Stable call identifier in the session.
        source_label: Human-readable source description.
        confidence_label: Overall confidence label.
        raw_body_available: Whether raw provider response data can be inspected.
        usage: Detailed usage payload.
        buckets: Legacy response bucket payloads.
        blocks: Response block dictionaries used by the detail UI.
        captured_output_preview: Safe reconstructed output preview.
        attribution_notes: Notes and caveats from builders.
        availability_rows: Availability table rows.
    """

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
        """Validate fixed discriminator fields after dataclass initialization.

        Raises:
            ValueError: Raised when schema version or kind does not match the response
                attribution API contract.
        """
        if self.schema_version != 'llm_attribution_v2':
            raise ValueError(
                'response attribution payload schema_version must be llm_attribution_v2'
            )
        if self.kind != 'llm.response_attribution':
            raise ValueError('response attribution payload kind mismatch')

    def to_dict(self) -> dict[str, Any]:
        """Serialize the response attribution DTO to a JSON-ready dictionary.

        Returns:
            Dictionary preserving the public response attribution API schema.
        """
        return {
            'schema_version': self.schema_version,
            'call_identity': self.call_identity,
            'usage_summary': self.usage_summary,
            'response_spans': self.response_spans,
            'semantic_buckets': self.semantic_buckets,
            'diagnostics': self.diagnostics,
            'accounting_attribution': self.accounting_attribution,
            'kind': self.kind,
            'agent': self.agent,
            'model': self.model,
            'request_id': self.request_id,
            'call_id': self.call_id,
            'source_label': self.source_label,
            'confidence_label': self.confidence_label,
            'raw_body_available': self.raw_body_available,
            'usage': self.usage,
            'buckets': self.buckets,
            'blocks': self.blocks,
            'captured_output_preview': self.captured_output_preview,
            'attribution_notes': self.attribution_notes,
            'availability_rows': self.availability_rows,
        }


@dataclass(frozen=True)
class AttributionErrorPayloadDTO:
    """Represent a structured error payload for attribution failures.

    Routes use this DTO when request or response attribution cannot be produced but
    the API still needs to return a structured fallback response.

    Attributes:
        kind: Payload kind, expected to be llm.attribution_error.
        agent: Runtime that produced the failed call.
        call_id: Stable call identifier when available.
        round_id: Conversation round identifier for the failed request.
        error_type: Machine-readable error class.
        message: User-facing failure message.
        fallback: Fallback UI or payload strategy.
    """

    kind: str
    agent: str
    call_id: str
    round_id: str
    error_type: str
    message: str
    fallback: str

    def __post_init__(self) -> None:
        """Validate the fixed error payload kind after initialization.

        Raises:
            ValueError: Raised when kind does not match the attribution error contract.
        """
        if self.kind != 'llm.attribution_error':
            raise ValueError('attribution error payload kind mismatch')

    def to_dict(self) -> dict[str, Any]:
        """Serialize the error DTO to a JSON-ready dictionary.

        Returns:
            Dictionary preserving the attribution error API schema.
        """
        return {
            'kind': self.kind,
            'agent': self.agent,
            'call_id': self.call_id,
            'round_id': self.round_id,
            'error_type': self.error_type,
            'message': self.message,
            'fallback': self.fallback,
        }
