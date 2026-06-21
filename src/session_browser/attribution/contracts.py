"""Define stable attribution contracts shared by services, routes, and tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from session_browser.domain.enums import DomainStrEnum


class ValuePrecision(DomainStrEnum):
    """List precision states used by attributed values.

    Attribution builders attach these labels so serializers and UI surfaces can show
    whether a value came from provider usage, transcript reconstruction, estimation,
    residual allocation, or an unavailable source.

    Attributes:
        EXACT: Value is exactly reconstructed from a trusted source.
        PROVIDER_REPORTED: Value is reported by the provider or broker.
        TRANSCRIPT_EXACT: Value is exactly reconstructed from transcript content.
        ESTIMATED: Value is estimated from local rules or heuristics.
        HEURISTIC: Value uses a coarse fallback heuristic.
        RESIDUAL: Value is allocated as residual unexplained usage.
        UNAVAILABLE: Value is not available for the current call.
    """

    EXACT = 'exact'
    PROVIDER_REPORTED = 'provider_reported'
    TRANSCRIPT_EXACT = 'transcript_exact'
    ESTIMATED = 'estimated'
    HEURISTIC = 'heuristic'
    RESIDUAL = 'residual'
    UNAVAILABLE = 'unavailable'


class ValueSource(DomainStrEnum):
    """List source families used by attribution values.

    Attributes:
        PROVIDER_USAGE: Usage data returned by a provider or broker.
        TRANSCRIPT: Normalized transcript messages.
        TOOL_LOGS: Tool calls or tool result logs.
        SESSION_METADATA: Session-level metadata.
        LOCAL_RULES: Deterministic local attribution rules.
        TOOL_LIST: Runtime tool definition inventory.
        HEURISTIC: Local heuristic estimation.
        RESIDUAL: Residual allocation after known components are subtracted.
    """

    PROVIDER_USAGE = 'provider_usage'
    TRANSCRIPT = 'transcript'
    TOOL_LOGS = 'tool_logs'
    SESSION_METADATA = 'session_metadata'
    LOCAL_RULES = 'local_rules'
    TOOL_LIST = 'tool_list'
    HEURISTIC = 'heuristic'
    RESIDUAL = 'residual'


@dataclass
class AttributedValue:
    """Carry one value with attribution provenance.

    Builders use this object for request, response, and availability fields so every
    UI number can explain precision, source, fill strategy, and caveats.

    Attributes:
        value: Numeric or text value shown to users, or None when unavailable.
        unit: Display unit such as tokens, percent, count, or text.
        precision: Precision label from ValuePrecision.
        source: Source label from ValueSource.
        fill_strategy: Optional note about fallback or imputation strategy.
        note: Human-readable caveat for diagnostics and UI details.
    """

    value: int | float | str | None
    unit: str
    precision: str
    source: str
    fill_strategy: str = ''
    note: str = ''


@dataclass
class RequestAttributionBucket:
    """Describe one request-side attribution bucket for a model call.

    Request builders create buckets for history, current user input, tool results, tool
    definitions, local instructions, and residual usage before serializers normalize the
    payload for the detail UI.

    Attributes:
        key: Stable bucket key used by serializers and CSS hooks.
        label: Human-readable bucket label.
        tokens: Tokens assigned to this bucket.
        percent: Percent of the request-side denominator.
        count_label: Optional display count, such as message or tool count.
        precision: Precision label for the bucket token count.
        source: Source label for the bucket token count.
        confidence_label: Human-readable confidence label.
        summary: Short description rendered in the UI.
        expandable: Whether detailed content can be expanded.
        content_preview: Safe preview text for expandable buckets.
        contributes_to_total: Whether the bucket contributes to total input.
        parent_key: Optional parent group key.
        display_group: UI grouping key.
        details: Agent-specific diagnostic details.
    """

    key: str
    label: str
    tokens: int
    percent: float
    count_label: str = ''
    precision: str = ValuePrecision.ESTIMATED
    source: str = ValueSource.HEURISTIC
    confidence_label: str = ''
    summary: str = ''
    expandable: bool = False
    content_preview: str = ''
    contributes_to_total: bool = True
    parent_key: str = ''
    display_group: str = ''
    details: dict = field(default_factory=dict)


@dataclass
class ResponseAttributionBucket:
    """Describe one response-side attribution bucket for a model call.

    Response builders create these buckets for visible assistant text, tool use,
    metadata, hidden reasoning estimates, and residual output before payload
    serialization.

    Attributes:
        key: Stable bucket key used by serializers and CSS hooks.
        label: Human-readable bucket label.
        tokens: Tokens assigned to this bucket.
        percent: Percent of the response-side denominator.
        count_label: Optional display count.
        precision: Precision label for the bucket token count.
        source: Source label for the bucket token count.
        confidence_label: Human-readable confidence label.
        summary: Short description rendered in the UI.
        block_refs: Response block identifiers represented by this bucket.
        contributes_to_total: Whether the bucket contributes to total output.
        parent_key: Optional parent group key.
        display_group: UI grouping key.
        details: Agent-specific diagnostic details.
    """

    key: str
    label: str
    tokens: int
    percent: float
    count_label: str = ''
    precision: str = ValuePrecision.ESTIMATED
    source: str = ValueSource.HEURISTIC
    confidence_label: str = ''
    summary: str = ''
    block_refs: list[str] = field(default_factory=list)
    contributes_to_total: bool = True
    parent_key: str = ''
    display_group: str = ''
    details: dict = field(default_factory=dict)


@dataclass
class AvailabilityRow:
    """Describe one field in the attribution availability table.

    Builders add rows to explain whether important request or response values are exact,
    estimated, filled, or unavailable for the current runtime.

    Attributes:
        field: Machine-readable field name.
        label: Human-readable field label.
        exact: Whether the value is exact.
        available: Whether any value is available.
        precision: Precision label for the value.
        source: Source label for the value.
        fill_strategy: Fallback strategy used when the value is not exact.
        note: Optional user-facing caveat.
    """

    field: str
    label: str
    exact: bool
    available: bool
    precision: str
    source: str
    fill_strategy: str
    note: str = ''


@dataclass
class LLMRequestAttribution:
    """Describe complete request-side attribution for one LLM call.

    Agent-specific builders return this contract to the service layer before it is
    serialized into an API payload for the session detail attribution UI.

    Attributes:
        agent: Runtime that produced the call.
        model: Model label associated with the call.
        request_id: Provider or local request identifier.
        call_id: Stable call identifier in the session.
        source_label: Human-readable source description.
        confidence_label: Overall confidence label.
        raw_body_available: Whether raw provider request data can be inspected.
        total_input: Total input usage value.
        fresh_input: Fresh non-cache input usage value.
        cache_read: Cache-read input usage value.
        cache_write: Cache-write input usage value.
        coverage: Attribution coverage value.
        unknown: Unknown or residual input value.
        buckets: Request-side attribution buckets.
        captured_context_preview: Safe preview of reconstructed request context.
        attribution_notes: Notes and caveats from the builder.
        availability_rows: Availability table rows.
        timing: Optional timing metadata.
        accounting_attribution: Optional accounting-specific attribution details.
    """

    agent: str
    model: str
    request_id: str
    call_id: str
    source_label: str
    confidence_label: str
    raw_body_available: bool
    total_input: AttributedValue
    fresh_input: AttributedValue
    cache_read: AttributedValue
    cache_write: AttributedValue
    coverage: AttributedValue
    unknown: AttributedValue
    buckets: list[RequestAttributionBucket]
    captured_context_preview: str
    attribution_notes: list[str]
    availability_rows: list[AvailabilityRow | dict]
    timing: dict = field(default_factory=dict)
    accounting_attribution: dict = field(default_factory=dict)


@dataclass
class LLMResponseAttribution:
    """Describe complete response-side attribution for one LLM call.

    Agent-specific builders return this contract to the service layer before it is
    serialized into an API payload for the session detail attribution UI.

    Attributes:
        agent: Runtime that produced the call.
        model: Model label associated with the call.
        request_id: Provider or local request identifier.
        call_id: Stable call identifier in the session.
        source_label: Human-readable source description.
        confidence_label: Overall confidence label.
        raw_body_available: Whether raw provider response data can be inspected.
        total_output: Total output usage value.
        visible_text: Visible assistant text usage value.
        tool_use: Tool-call output usage value serialized as tool_call.
        metadata: Metadata token usage value.
        coverage: Attribution coverage value.
        unknown: Unknown or residual output value.
        finish_reason: Finish reason value with provenance.
        buckets: Response-side attribution buckets.
        blocks: Response block dictionaries for UI detail rendering.
        captured_output_preview: Safe preview of reconstructed response content.
        attribution_notes: Notes and caveats from the builder.
        availability_rows: Availability table rows.
        accounting_attribution: Optional accounting-specific attribution details.
    """

    agent: str
    model: str
    request_id: str
    call_id: str
    source_label: str
    confidence_label: str
    raw_body_available: bool
    total_output: AttributedValue
    visible_text: AttributedValue
    tool_use: AttributedValue
    metadata: AttributedValue
    coverage: AttributedValue
    unknown: AttributedValue
    finish_reason: AttributedValue
    buckets: list[ResponseAttributionBucket]
    blocks: list[dict]
    captured_output_preview: str
    attribution_notes: list[str]
    availability_rows: list[AvailabilityRow | dict]
    accounting_attribution: dict = field(default_factory=dict)


__all__ = [
    'AttributedValue',
    'AvailabilityRow',
    'LLMRequestAttribution',
    'LLMResponseAttribution',
    'RequestAttributionBucket',
    'ResponseAttributionBucket',
    'ValuePrecision',
    'ValueSource',
]
