"""Define core data models for LLM attribution results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContentRef:
    """Reference attribution content without exposing unsafe full payloads.

    Attribution collectors attach this object when evidence can point to inline text,
    a session event, or a file slice. Consumers use it to render safe previews and to
    decide whether a separate full-content loader can be called.

    Attributes:
        kind: Reference type such as inline, file_slice, session_event, or unavailable.
        pointer: Optional file path, event id, or byte range locator.
        preview: Redacted or truncated text safe for UI display.
        can_load_full: Whether a caller may request the full referenced content.
        redaction_applied: Whether sensitive content was redacted before storage.
    """

    kind: str
    pointer: str | None = None
    preview: str = ''
    can_load_full: bool = False
    redaction_applied: bool = False


@dataclass(frozen=True)
class Evidence:
    """Record one attribution fact extracted from a session or runtime source.

    Collectors create evidence before API-family normalizers build ordered prompt spans.
    Each fact captures source scope, semantic kind, optional content reference, and the
    confidence level used later by bucket aggregation and validation.

    Attributes:
        evidence_id: Stable identifier used by spans and UI payloads.
        scope: Source scope, for example current_session, prior_session, project_repo,
            agent_app, provider_usage, or inferred.
        kind: Semantic evidence kind such as user_message, tool_result, tool_schema, or
            system_prompt.
        source_path: Optional source file path for evidence loaded from disk.
        source_event_id: Optional session event id for trace correlation.
        content_ref: Optional safe locator for full or preview content.
        text_preview: Short text used for token estimation and UI display.
        raw_value: Optional provider or collector value kept for diagnostics.
        precision: Precision label such as exact, estimated, heuristic, or residual.
        confidence: Confidence score between 0.0 and 1.0.
        redaction_state: Redaction note attached by the collector.
    """

    evidence_id: str
    scope: str
    kind: str
    source_path: str | None = None
    source_event_id: str | None = None
    content_ref: ContentRef | None = None
    text_preview: str = ''
    raw_value: Any = None
    precision: str = 'heuristic'
    confidence: float = 0.5
    redaction_state: str = ''


@dataclass
class PromptSpan:
    """Represent one ordered request or response fragment for attribution.

    API-family normalizers create spans after collectors emit evidence. A span preserves
    API ordering, semantic meaning, token estimates, cache allocation, and whether the
    tokens contribute to request or response totals.

    Attributes:
        span_id: Stable span identifier for buckets and UI payloads.
        order_index: Zero-based API order after normalizer sorting.
        api_family: API family that owns the path semantics.
        api_path: Provider-specific path such as tools[3].input_schema.
        semantic_kind: Semantic kind such as tool_schema, user_text, or tool_result.
        evidence_ids: Evidence identifiers that produced this span.
        content_ref: Optional safe content reference for this span.
        text_preview: Safe text preview used by rendering and token estimation.
        raw_json_preview: Optional redacted JSON preview for provider payloads.
        token_estimate: Token count assigned to this span.
        token_count_method: Counting method, for example heuristic or tiktoken.
        precision: Precision label inherited from evidence or provider usage.
        confidence: Confidence score for the span.
        contributes_to_input: Whether the span contributes to input tokens.
        contributes_to_output: Whether the span contributes to output tokens.
        cache_read_tokens: Cache-read tokens assigned to the span.
        cache_write_tokens: Cache-write tokens assigned to the span.
        fresh_tokens: Fresh input tokens assigned to the span.
    """

    span_id: str
    order_index: int
    api_family: str
    api_path: str
    semantic_kind: str
    evidence_ids: list[str] = field(default_factory=list)
    content_ref: ContentRef | None = None
    text_preview: str = ''
    raw_json_preview: str | None = None
    token_estimate: int = 0
    token_count_method: str = 'heuristic'
    precision: str = 'heuristic'
    confidence: float = 0.5
    contributes_to_input: bool = True
    contributes_to_output: bool = False
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    fresh_tokens: int = 0


@dataclass(frozen=True)
class UsageBreakdown:
    """Describe provider or broker usage values for one model call.

    API-family parsers fill this structure from provider payloads or local
    reconstruction. Validators compare it with spans to detect allocation drift and
    unsupported cache semantics.

    Attributes:
        total_input: Total input tokens reported or reconstructed.
        fresh_input: Non-cache input tokens.
        cache_read: Cache-read tokens when the provider exposes them.
        cache_write: Cache-write tokens when the provider exposes them.
        output: Output tokens.
        hidden_reasoning: Hidden reasoning tokens when available.
        usage_source: Source label such as provider_reported or local_reconstruction.
        precision: Precision label for the usage payload.
        note: Human-readable diagnostic note.
    """

    total_input: int | None = None
    fresh_input: int | None = None
    cache_read: int | None = None
    cache_write: int | None = None
    output: int | None = None
    hidden_reasoning: int | None = None
    usage_source: str = 'unknown'
    precision: str = 'unavailable'
    note: str = ''


@dataclass
class AttributionResult:
    """Hold the complete attribution result for one LLM call.

    The attribution service returns this object after collectors, normalizers, bucket
    aggregation, and invariant checks finish. UI serializers read it to render request
    and response attribution with supporting evidence.

    Attributes:
        request_spans: Ordered input spans for the call.
        response_spans: Ordered output spans for the call.
        request_buckets: Aggregated request buckets for display.
        response_buckets: Aggregated response buckets for display.
        usage_breakdown: Optional provider or broker usage values.
        evidence_map: Evidence indexed by evidence id.
        invariants: Validation results emitted by the core validator.
        warnings: Recoverable attribution warnings.
    """

    request_spans: list[PromptSpan] = field(default_factory=list)
    response_spans: list[PromptSpan] = field(default_factory=list)
    request_buckets: list[dict] = field(default_factory=list)
    response_buckets: list[dict] = field(default_factory=list)
    usage_breakdown: UsageBreakdown | None = None
    evidence_map: dict[str, Evidence] = field(default_factory=dict)
    invariants: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CallCreditSlice:
    """Represent credit usage attributed to one model call.

    Qoder broker attribution creates these slices when credits, rather than token-only
    usage, are available. The slice keeps precision and source metadata for UI display.

    Attributes:
        call_id: Model call identifier receiving the credit allocation.
        credits: Credits attributed to the call, or None when unavailable.
        precision: Precision label such as exact, estimated, or unavailable.
        source: Broker or estimator source for the credit value.
    """

    call_id: str
    credits: float | None
    precision: str
    source: str = ''


@dataclass
class CreditAttribution:
    """Describe broker credit attribution for runtimes that bill by credits.

    Qoder-specific parsers attach this object when provider token usage is incomplete
    but broker credit fields can still explain the model call cost.

    Attributes:
        total_credits: Total credits reported for the request.
        precision: Precision label for credit attribution.
        credit_source: Source field or extractor that produced the credits.
        by_model_call: Per-call credit slices.
        effective_rates: Derived token-to-credit rates keyed by model or family.
        notes: Diagnostic notes for missing or estimated credit fields.
    """

    total_credits: float | None = None
    precision: str = 'unavailable'
    credit_source: str = ''
    by_model_call: list[CallCreditSlice] = field(default_factory=list)
    effective_rates: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
