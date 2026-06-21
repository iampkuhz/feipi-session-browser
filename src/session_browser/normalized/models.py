"""POJO models for normalized session artifacts.

The normalized artifact is persisted as JSON, but these models document and
validate the contract before serializer/hydration code consumes plain dicts.
Open provider payload fragments remain ``dict`` because their schemas are
runtime-owned; artifact edges and source-unit metadata are modeled here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from session_browser.domain._validation import non_negative_int
from session_browser.normalized.constants import NORMALIZED_SCHEMA_VERSION

_DIRECTION_VALUES = {'request', 'response'}
_AGENT_VALUES = {'codex', 'claude_code', 'qoder'}
_BYTE_RANGE_LENGTH = 2


@dataclass(frozen=True)
class ByteRange:
    """Byte offsets into the originating source text or payload.

    Normalized source-unit validators create this immutable value object while
    hydrating artifact dictionaries. Offsets are always non-negative and
    ``end`` must be greater than or equal to ``start``.

    Attributes:
        start: Inclusive byte offset in the originating source payload.
        end: Exclusive byte offset in the originating source payload.
    """

    start: int = 0
    end: int = 0

    def __post_init__(self) -> None:
        """Validate dataclass construction for byte-range invariants.

        Dataclasses call this protocol hook immediately after object creation.
        It normalizes both offsets with the shared non-negative validator and
        preserves immutable instances by assigning through ``object``.

        Raises:
            ValueError: Raised when ``end`` is smaller than ``start`` or either
                offset is negative.
        """
        object.__setattr__(self, 'start', non_negative_int('byte_range.start', self.start))
        object.__setattr__(self, 'end', non_negative_int('byte_range.end', self.end))
        if self.end < self.start:
            raise ValueError('byte_range.end must be >= byte_range.start')

    @classmethod
    def from_value(cls, value: object) -> ByteRange:
        """Hydrate a byte range from an artifact list-like value.

        Model construction calls this when reading source-unit catalog entries.
        It accepts only the public JSON representation and delegates invariant
        checks to ``ByteRange`` construction.

        Args:
            value: Candidate ``[start, end]`` value from the normalized JSON.

        Returns:
            Immutable byte range for downstream model validation.

        Raises:
            ValueError: Raised when ``value`` is not a two-item list or tuple,
                or when the resulting offsets violate range invariants.
        """
        if not isinstance(value, list | tuple) or len(value) != _BYTE_RANGE_LENGTH:
            raise ValueError('byte_range must be [start, end]')
        return cls(start=value[0], end=value[1])

    def to_list(self) -> list[int]:
        """Serialize the range back to the normalized JSON representation.

        Artifact serialization callers use this protocol-shaped helper when a
        model instance must be converted to plain JSON data.

        Returns:
            Two-item ``[start, end]`` list preserving byte-offset order.
        """
        return [self.start, self.end]


@dataclass(frozen=True)
class NormalizedSourceFile:
    """One physical file that contributed to a normalized artifact.

    Source adapters create these records during scan normalization. Instances
    are immutable metadata transfer objects and keep optional subagent lineage
    fields empty when the source file belongs to the main session.

    Attributes:
        role: Source role such as transcript or companion metadata.
        path: Filesystem path recorded for provenance.
        subagent_id: Optional subagent instance that produced this source.
        parent_tool_use_id: Optional parent tool-call edge for subagent sources.
    """

    role: str
    path: str
    subagent_id: str = ''
    parent_tool_use_id: str = ''

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedSourceFile:
        """Hydrate source-file metadata from a normalized artifact mapping.

        Artifact model validation calls this for every ``source.files`` entry.
        Missing optional fields are converted to empty strings to preserve the
        JSON contract and avoid mutating the input mapping.

        Args:
            data: Source file object from the normalized JSON payload.

        Returns:
            Immutable source-file metadata instance.
        """
        return cls(
            role=str(data.get('role') or ''),
            path=str(data.get('path') or ''),
            subagent_id=str(data.get('subagent_id') or ''),
            parent_tool_use_id=str(data.get('parent_tool_use_id') or ''),
        )


@dataclass(frozen=True)
class NormalizedCallUsage:
    """Five-field token usage persisted for one normalized LLM call.

    The semantic builder and artifact validator create this immutable value
    object for each call. Component counts are non-negative and ``total`` must
    equal the sum of fresh, cache, and output counts.

    Attributes:
        fresh: Fresh input tokens attributed to the call.
        cache_read: Cache-read input tokens attributed to the call.
        cache_write: Cache-write input tokens attributed to the call.
        output: Output tokens attributed to the call.
        total: Sum of all persisted token components.
    """

    fresh: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0
    total: int = 0

    def __post_init__(self) -> None:
        """Validate token counters after dataclass construction.

        Dataclasses call this hook for artifact hydration and direct tests. It
        coerces all counters with the shared non-negative validator and updates
        the frozen instance only after the total is proven consistent.

        Raises:
            ValueError: Raised when any token count is negative or ``total`` is
                not equal to the component sum.
        """
        fresh = non_negative_int('usage.fresh', self.fresh)
        cache_read = non_negative_int('usage.cache_read', self.cache_read)
        cache_write = non_negative_int('usage.cache_write', self.cache_write)
        output = non_negative_int('usage.output', self.output)
        total = non_negative_int('usage.total', self.total)
        expected = fresh + cache_read + cache_write + output
        if total != expected:
            raise ValueError(f'usage.total must equal component sum {expected}; got {total}')
        object.__setattr__(self, 'fresh', fresh)
        object.__setattr__(self, 'cache_read', cache_read)
        object.__setattr__(self, 'cache_write', cache_write)
        object.__setattr__(self, 'output', output)
        object.__setattr__(self, 'total', total)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedCallUsage:
        """Hydrate token usage from one normalized call mapping.

        Artifact validation calls this while walking ``calls``. Missing token
        fields default to zero and the constructor enforces the persisted total.

        Args:
            data: ``usage`` object from a normalized call.

        Returns:
            Validated token usage value object.
        """
        return cls(
            fresh=data.get('fresh', 0),
            cache_read=data.get('cache_read', 0),
            cache_write=data.get('cache_write', 0),
            output=data.get('output', 0),
            total=data.get('total', 0),
        )


@dataclass(frozen=True)
class NormalizedCallRequest:
    """Request-side tool-result edges consumed by one call.

    The semantic builder stores only lightweight edge identifiers here. The
    artifact model treats the object as immutable call input metadata.

    Attributes:
        tool_result_ids: Tool-call identifiers whose results were consumed by
            this LLM request, in normalized source order.
    """

    tool_result_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedCallRequest:
        """Hydrate request edge metadata from a normalized call mapping.

        Artifact validation calls this for each call request. Non-list input is
        normalized to an empty edge list and each truthy item is stringified.

        Args:
            data: ``request`` object from a normalized call.

        Returns:
            Immutable request edge metadata.
        """
        return cls(tool_result_ids=_string_list(data.get('tool_result_ids')))


@dataclass(frozen=True)
class NormalizedCallResponse:
    """Response-side tool-call edges declared by one call.

    The semantic builder stores only tool-call identifiers here. The model is a
    short-lived immutable transfer object used during artifact validation.

    Attributes:
        tool_call_ids: Tool-call identifiers declared by this LLM response, in
            normalized response order.
    """

    tool_call_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedCallResponse:
        """Hydrate response edge metadata from a normalized call mapping.

        Artifact validation calls this for each call response. Non-list input is
        normalized to an empty edge list and each truthy item is stringified.

        Args:
            data: ``response`` object from a normalized call.

        Returns:
            Immutable response edge metadata.
        """
        return cls(tool_call_ids=_string_list(data.get('tool_call_ids')))


@dataclass(frozen=True)
class SourceUnitRefRange:
    """Call-local reference to catalog units or a named source-unit sequence.

    Normalized calls use this immutable record to point at source-unit catalog
    entries without duplicating payload content. The range indices are
    non-negative and preserve the adapter-provided order for the named sequence.

    Attributes:
        sequence: Optional source-unit sequence name used by the reference.
        start: Inclusive index into the referenced sequence.
        end: Exclusive index into the referenced sequence.
        refs: Explicit catalog unit keys referenced by the call.
        role: Optional display role assigned by the adapter.
    """

    sequence: str = ''
    start: int = 0
    end: int = 0
    refs: list[str] = field(default_factory=list)
    role: str = ''

    def __post_init__(self) -> None:
        """Validate sequence index invariants after dataclass construction.

        Dataclasses call this hook when artifact dictionaries are hydrated. It
        normalizes range indices and preserves immutable assignment semantics.

        Raises:
            ValueError: Raised when either index is negative or ``end`` is
                smaller than ``start``.
        """
        start = non_negative_int('source_unit_ref_range.start', self.start)
        end = non_negative_int('source_unit_ref_range.end', self.end)
        if end < start:
            raise ValueError('source_unit_ref_range.end must be >= start')
        object.__setattr__(self, 'start', start)
        object.__setattr__(self, 'end', end)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceUnitRefRange:
        """Hydrate a call-local source-unit reference range.

        Artifact validation calls this for entries under
        ``source_unit_ref_ranges``. It keeps missing optional text fields empty
        and normalizes explicit references through the shared string-list helper.

        Args:
            data: Reference-range object from a normalized call.

        Returns:
            Immutable reference range for model validation.
        """
        return cls(
            sequence=str(data.get('sequence') or ''),
            start=data.get('start', 0),
            end=data.get('end', 0),
            refs=_string_list(data.get('refs')),
            role=str(data.get('role') or ''),
        )


@dataclass(frozen=True)
class SourceUnitCatalogEntry:
    """Call-independent catalog entry for visible attribution source content.

    Adapters populate the source-unit catalog during normalization, and the
    artifact validator hydrates entries as immutable records. The catalog key,
    direction, event order, byte range, and content hash form the stable
    provenance contract used by UI attribution features.

    Attributes:
        unit_key: Stable key used by calls and sequences to reference the unit.
        origin_path: Source file path that produced the unit.
        canonical_source_locator: Adapter-specific locator for the source span.
        unit_type: Category of source unit stored in the catalog.
        candidate: Attribution candidate bucket for UI grouping.
        direction: Request or response side of the conversation.
        event_order: Non-negative event order in the source transcript.
        part_index: Non-negative index within the source event.
        byte_range: Byte offsets for the unit inside the source payload.
        content_hash: Stable content hash used for deduplication.
        timestamp: Optional source timestamp associated with the unit.
        label: Optional display label for the unit.
        priority: Non-negative ranking priority for attribution display.
        preview: Optional short preview text.
        text: Optional full text when safe to persist.
        payload: Optional provider-owned payload fragment.
        sub_source: Optional nested source label from the adapter.
        source_candidate: Optional original candidate label before normalization.
        diagnostics: Adapter diagnostics associated with this unit.
    """

    unit_key: str
    origin_path: str
    canonical_source_locator: str
    unit_type: str
    candidate: str
    direction: str
    event_order: int
    part_index: int
    byte_range: ByteRange
    content_hash: str
    timestamp: str = ''
    label: str = ''
    priority: int = 50
    preview: str = ''
    text: str = ''
    payload: Any = None
    sub_source: str = ''
    source_candidate: str = ''
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate catalog entry invariants after dataclass construction.

        Dataclasses call this hook while hydrating catalog entries. It enforces
        request/response direction and non-negative ordering fields without
        mutating provider-owned payload fragments.

        Raises:
            ValueError: Raised when direction is unknown or numeric ordering
                fields are negative.
        """
        if self.direction not in _DIRECTION_VALUES:
            raise ValueError(f'source unit direction invalid: {self.direction!r}')
        object.__setattr__(
            self, 'event_order', non_negative_int('source_unit.event_order', self.event_order)
        )
        object.__setattr__(
            self, 'part_index', non_negative_int('source_unit.part_index', self.part_index)
        )
        object.__setattr__(
            self, 'priority', non_negative_int('source_unit.priority', self.priority)
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceUnitCatalogEntry:
        """Hydrate one source-unit catalog entry from normalized JSON.

        Artifact validation calls this for each catalog value. Required fields
        are stringified or delegated to value objects, while optional provider
        payloads are carried through unchanged.

        Args:
            data: Catalog entry object from ``source_unit_catalog``.

        Returns:
            Immutable catalog entry for validation and downstream consumers.
        """
        return cls(
            unit_key=str(data.get('unit_key') or ''),
            origin_path=str(data.get('origin_path') or ''),
            canonical_source_locator=str(data.get('canonical_source_locator') or ''),
            unit_type=str(data.get('unit_type') or ''),
            candidate=str(data.get('candidate') or ''),
            direction=str(data.get('direction') or ''),
            event_order=data.get('event_order', 0),
            part_index=data.get('part_index', 0),
            byte_range=ByteRange.from_value(data.get('byte_range')),
            content_hash=str(data.get('content_hash') or ''),
            timestamp=str(data.get('timestamp') or ''),
            label=str(data.get('label') or ''),
            priority=data.get('priority', 50),
            preview=str(data.get('preview') or ''),
            text=str(data.get('text') or ''),
            payload=data.get('payload'),
            sub_source=str(data.get('sub_source') or ''),
            source_candidate=str(data.get('source_candidate') or ''),
            diagnostics=list(data.get('diagnostics') or []),
        )


@dataclass(frozen=True)
class NormalizedCall:
    """One normalized logical LLM call and its lightweight edge references.

    The semantic builder creates these records for main and subagent turns, and
    artifact validation hydrates them from JSON. Calls are immutable transfer
    objects whose index and key must stay sequential within the artifact.

    Attributes:
        call_id: Stable adapter-provided or generated call identifier.
        call_index: One-based call position in normalized traversal order.
        call_key: Display key matching ``C{call_index}``.
        scope: Main or subagent scope label for the call.
        parent_call_id: Parent LLM call for subagent calls, otherwise empty.
        parent_tool_call_id: Tool-call edge that triggered a subagent call.
        turn_id: Provider turn identifier associated with the call.
        model: Model name reported by the provider.
        timestamp: Provider timestamp for the call.
        usage: Token usage attributed to the call.
        request: Request-side edge identifiers consumed by the call.
        response: Response-side edge identifiers declared by the call.
        source_unit_ref_ranges: References into catalog sequences.
        source_units: Legacy inline source units kept for compatibility.
        attribution_candidates: Adapter-owned attribution metadata.
        usage_source: Metadata describing estimated usage when applicable.
    """

    call_id: str
    call_index: int
    call_key: str
    scope: str
    parent_call_id: str
    parent_tool_call_id: str
    turn_id: str
    model: str
    timestamp: str
    usage: NormalizedCallUsage
    request: NormalizedCallRequest
    response: NormalizedCallResponse
    source_unit_ref_ranges: list[SourceUnitRefRange] = field(default_factory=list)
    source_units: list[dict[str, Any]] = field(default_factory=list)
    attribution_candidates: dict[str, Any] = field(default_factory=dict)
    usage_source: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate call ordering invariants after dataclass construction.

        Dataclasses call this hook during artifact hydration. It ensures call
        indices are one-based and that display keys cannot drift from persisted
        order.

        Raises:
            ValueError: Raised when ``call_index`` is not positive or
                ``call_key`` does not match it.
        """
        object.__setattr__(self, 'call_index', non_negative_int('call.call_index', self.call_index))
        if self.call_index <= 0:
            raise ValueError('call.call_index must start at 1')
        if self.call_key != f'C{self.call_index}':
            raise ValueError('call.call_key must match call_index')

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedCall:
        """Hydrate one normalized call from an artifact mapping.

        Top-level artifact validation calls this for every item in ``calls``.
        Nested request, response, usage, and source-unit references are
        converted through their dedicated value objects while adapter-owned
        metadata remains dictionary based.

        Args:
            data: Call object from a normalized session artifact.

        Returns:
            Immutable normalized call instance.
        """
        return cls(
            call_id=str(data.get('call_id') or ''),
            call_index=data.get('call_index', 0),
            call_key=str(data.get('call_key') or ''),
            scope=str(data.get('scope') or 'main'),
            parent_call_id=str(data.get('parent_call_id') or ''),
            parent_tool_call_id=str(data.get('parent_tool_call_id') or ''),
            turn_id=str(data.get('turn_id') or ''),
            model=str(data.get('model') or ''),
            timestamp=str(data.get('timestamp') or ''),
            usage=NormalizedCallUsage.from_dict(
                data.get('usage') if isinstance(data.get('usage'), dict) else {}
            ),
            request=NormalizedCallRequest.from_dict(
                data.get('request') if isinstance(data.get('request'), dict) else {}
            ),
            response=NormalizedCallResponse.from_dict(
                data.get('response') if isinstance(data.get('response'), dict) else {}
            ),
            source_unit_ref_ranges=[
                SourceUnitRefRange.from_dict(item)
                for item in data.get('source_unit_ref_ranges') or []
                if isinstance(item, dict)
            ],
            source_units=list(data.get('source_units') or []),
            attribution_candidates=data.get('attribution_candidates')
            if isinstance(data.get('attribution_candidates'), dict)
            else {},
            usage_source=data.get('usage_source')
            if isinstance(data.get('usage_source'), dict)
            else {},
        )


@dataclass(frozen=True)
class NormalizedToolExecution:
    """Edge-table row for a tool call declared by one call and consumed by another.

    The semantic builder emits these records while walking tool batches. The
    artifact validator hydrates them as immutable edge metadata and keeps
    optional execution details absent or empty when providers did not report
    them.

    Attributes:
        tool_call_id: Stable tool-call identifier declared by an LLM response.
        name: Tool name reported by the provider.
        scope: Main or subagent scope where the tool executed.
        declared_by_call_id: Call identifier that declared the tool call.
        result_consumed_by_call_id: Later call that consumed the tool result.
        status: Optional non-completed tool status.
        exit_code: Optional process-style exit code for command tools.
        duration_ms: Non-negative execution duration in milliseconds.
        files_touched: Files reported by the tool execution.
        subagent_id: Optional subagent instance associated with the tool.
    """

    tool_call_id: str
    name: str
    scope: str
    declared_by_call_id: str
    result_consumed_by_call_id: str = ''
    status: str = ''
    exit_code: int | None = None
    duration_ms: int = 0
    files_touched: list[str] = field(default_factory=list)
    subagent_id: str = ''

    def __post_init__(self) -> None:
        """Normalize execution counters after dataclass construction.

        Dataclasses call this hook while hydrating tool edges. It validates the
        duration and coerces optional exit codes without changing the caller's
        transaction or source data.
        """
        object.__setattr__(
            self, 'duration_ms', non_negative_int('tool.duration_ms', self.duration_ms)
        )
        if self.exit_code is not None:
            object.__setattr__(self, 'exit_code', int(self.exit_code))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedToolExecution:
        """Hydrate a normalized tool-execution edge from JSON.

        Artifact validation calls this for every ``tool_executions`` item. The
        method stringifies identifiers, preserves optional status details, and
        delegates numeric duration validation to the dataclass hook.

        Args:
            data: Tool execution object from the normalized artifact.

        Returns:
            Immutable tool execution edge.
        """
        return cls(
            tool_call_id=str(data.get('tool_call_id') or ''),
            name=str(data.get('name') or ''),
            scope=str(data.get('scope') or 'main'),
            declared_by_call_id=str(data.get('declared_by_call_id') or ''),
            result_consumed_by_call_id=str(data.get('result_consumed_by_call_id') or ''),
            status=str(data.get('status') or ''),
            exit_code=data.get('exit_code'),
            duration_ms=data.get('duration_ms', 0),
            files_touched=list(data.get('files_touched') or []),
            subagent_id=str(data.get('subagent_id') or ''),
        )


@dataclass(frozen=True)
class NormalizedSessionArtifact:
    """Top-level normalized session artifact persisted beside the SQLite index.

    Index scans create this data-transfer root before JSON persistence, and
    query or validation paths hydrate it to enforce the public artifact
    contract. The artifact is immutable, schema-versioned, and requires unique
    call identifiers.

    Attributes:
        schema_version: Normalized artifact schema version.
        agent: Source adapter name that produced the artifact.
        source_files: Physical source files contributing to the artifact.
        session: Session metadata object preserved as public JSON data.
        calls: Normalized LLM calls in traversal order.
        tool_executions: Tool-call edges declared and consumed by calls.
        diagnostics: Non-fatal parser diagnostics surfaced with the artifact.
        source_unit_catalog: Catalog entries keyed by source-unit ID.
        source_unit_sequences: Named source-unit key sequences used by calls.
    """

    schema_version: str
    agent: str
    source_files: list[NormalizedSourceFile]
    session: dict[str, Any]
    calls: list[NormalizedCall]
    tool_executions: list[NormalizedToolExecution]
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    source_unit_catalog: dict[str, SourceUnitCatalogEntry] = field(default_factory=dict)
    source_unit_sequences: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate top-level artifact invariants after dataclass construction.

        Dataclasses call this hook after nested model hydration. It protects the
        schema version, supported agent names, and uniqueness of call IDs before
        callers trust the artifact shape.

        Raises:
            ValueError: Raised when the schema version, agent, or call ID set is
                invalid.
        """
        if self.schema_version != NORMALIZED_SCHEMA_VERSION:
            raise ValueError(f'schema_version must be {NORMALIZED_SCHEMA_VERSION}')
        if self.agent not in _AGENT_VALUES:
            raise ValueError(f'invalid normalized agent: {self.agent!r}')
        call_ids = [call.call_id for call in self.calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError('normalized call_id values must be unique')

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedSessionArtifact:
        """Hydrate the full normalized artifact model from a JSON object.

        Schema validation calls this after lightweight semantic checks pass.
        The method converts nested lists and catalog mappings into immutable
        value objects while preserving public dictionary fields such as
        ``session`` and adapter diagnostics.

        Args:
            data: Top-level normalized session artifact object.

        Returns:
            Immutable normalized artifact root.
        """
        source = data.get('source') if isinstance(data.get('source'), dict) else {}
        catalog_data = (
            data.get('source_unit_catalog')
            if isinstance(data.get('source_unit_catalog'), dict)
            else {}
        )
        return cls(
            schema_version=str(data.get('schema_version') or ''),
            agent=str(data.get('agent') or ''),
            source_files=[
                NormalizedSourceFile.from_dict(item)
                for item in source.get('files') or []
                if isinstance(item, dict)
            ],
            session=data.get('session') if isinstance(data.get('session'), dict) else {},
            calls=[
                NormalizedCall.from_dict(item)
                for item in data.get('calls') or []
                if isinstance(item, dict)
            ],
            tool_executions=[
                NormalizedToolExecution.from_dict(item)
                for item in data.get('tool_executions') or []
                if isinstance(item, dict)
            ],
            diagnostics=list(data.get('diagnostics') or []),
            source_unit_catalog={
                str(key): SourceUnitCatalogEntry.from_dict(value)
                for key, value in catalog_data.items()
                if isinstance(value, dict)
            },
            source_unit_sequences={
                str(key): _string_list(value)
                for key, value in (data.get('source_unit_sequences') or {}).items()
            }
            if isinstance(data.get('source_unit_sequences'), dict)
            else {},
        )


def validate_normalized_artifact_model(data: dict[str, Any]) -> None:
    """Validate a normalized artifact dictionary through model construction.

    ``schema.validate_normalized_session`` calls this after semantic checks to
    reuse dataclass invariants. The function has no side effects and returns
    only by not raising.

    Args:
        data: Top-level normalized session artifact object.
    """
    NormalizedSessionArtifact.from_dict(data)


def _string_list(value: object) -> list[str]:
    """Normalize optional JSON arrays into string identifier lists.

    Model ``from_dict`` helpers call this for edge and sequence identifiers.
    Non-list values become empty lists, and falsy items are omitted to preserve
    the normalized contract for references.

    Args:
        value: Candidate list value from a normalized artifact mapping.

    Returns:
        Stringified truthy items in their original order.
    """
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]
