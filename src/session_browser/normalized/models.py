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


_DIRECTION_VALUES = {"request", "response"}
_AGENT_VALUES = {"codex", "claude_code", "qoder"}


@dataclass(frozen=True)
class ByteRange:
    """Byte offsets into the originating source text/payload."""

    start: int = 0
    end: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", non_negative_int("byte_range.start", self.start))
        object.__setattr__(self, "end", non_negative_int("byte_range.end", self.end))
        if self.end < self.start:
            raise ValueError("byte_range.end must be >= byte_range.start")

    @classmethod
    def from_value(cls, value: Any) -> "ByteRange":
        if not isinstance(value, list | tuple) or len(value) != 2:
            raise ValueError("byte_range must be [start, end]")
        return cls(start=value[0], end=value[1])

    def to_list(self) -> list[int]:
        return [self.start, self.end]


@dataclass(frozen=True)
class NormalizedSourceFile:
    """One physical file that contributed to a normalized artifact."""

    role: str
    path: str
    subagent_id: str = ""
    parent_tool_use_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedSourceFile":
        return cls(
            role=str(data.get("role") or ""),
            path=str(data.get("path") or ""),
            subagent_id=str(data.get("subagent_id") or ""),
            parent_tool_use_id=str(data.get("parent_tool_use_id") or ""),
        )


@dataclass(frozen=True)
class NormalizedCallUsage:
    """Five-field token usage persisted for one normalized LLM call."""

    fresh: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0
    total: int = 0

    def __post_init__(self) -> None:
        fresh = non_negative_int("usage.fresh", self.fresh)
        cache_read = non_negative_int("usage.cache_read", self.cache_read)
        cache_write = non_negative_int("usage.cache_write", self.cache_write)
        output = non_negative_int("usage.output", self.output)
        total = non_negative_int("usage.total", self.total)
        expected = fresh + cache_read + cache_write + output
        if total != expected:
            raise ValueError(f"usage.total must equal component sum {expected}; got {total}")
        object.__setattr__(self, "fresh", fresh)
        object.__setattr__(self, "cache_read", cache_read)
        object.__setattr__(self, "cache_write", cache_write)
        object.__setattr__(self, "output", output)
        object.__setattr__(self, "total", total)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedCallUsage":
        return cls(
            fresh=data.get("fresh", 0),
            cache_read=data.get("cache_read", 0),
            cache_write=data.get("cache_write", 0),
            output=data.get("output", 0),
            total=data.get("total", 0),
        )


@dataclass(frozen=True)
class NormalizedCallRequest:
    """Request-side tool-result edges consumed by one call."""

    tool_result_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedCallRequest":
        return cls(tool_result_ids=_string_list(data.get("tool_result_ids")))


@dataclass(frozen=True)
class NormalizedCallResponse:
    """Response-side tool-call edges declared by one call."""

    tool_call_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedCallResponse":
        return cls(tool_call_ids=_string_list(data.get("tool_call_ids")))


@dataclass(frozen=True)
class SourceUnitRefRange:
    """Call-local reference to catalog units or a named source-unit sequence."""

    sequence: str = ""
    start: int = 0
    end: int = 0
    refs: list[str] = field(default_factory=list)
    role: str = ""

    def __post_init__(self) -> None:
        start = non_negative_int("source_unit_ref_range.start", self.start)
        end = non_negative_int("source_unit_ref_range.end", self.end)
        if end < start:
            raise ValueError("source_unit_ref_range.end must be >= start")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceUnitRefRange":
        return cls(
            sequence=str(data.get("sequence") or ""),
            start=data.get("start", 0),
            end=data.get("end", 0),
            refs=_string_list(data.get("refs")),
            role=str(data.get("role") or ""),
        )


@dataclass(frozen=True)
class SourceUnitCatalogEntry:
    """Call-independent catalog entry for visible attribution source content."""

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
    timestamp: str = ""
    label: str = ""
    priority: int = 50
    preview: str = ""
    text: str = ""
    payload: Any = None
    sub_source: str = ""
    source_candidate: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.direction not in _DIRECTION_VALUES:
            raise ValueError(f"source unit direction invalid: {self.direction!r}")
        object.__setattr__(self, "event_order", non_negative_int("source_unit.event_order", self.event_order))
        object.__setattr__(self, "part_index", non_negative_int("source_unit.part_index", self.part_index))
        object.__setattr__(self, "priority", non_negative_int("source_unit.priority", self.priority))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceUnitCatalogEntry":
        return cls(
            unit_key=str(data.get("unit_key") or ""),
            origin_path=str(data.get("origin_path") or ""),
            canonical_source_locator=str(data.get("canonical_source_locator") or ""),
            unit_type=str(data.get("unit_type") or ""),
            candidate=str(data.get("candidate") or ""),
            direction=str(data.get("direction") or ""),
            event_order=data.get("event_order", 0),
            part_index=data.get("part_index", 0),
            byte_range=ByteRange.from_value(data.get("byte_range")),
            content_hash=str(data.get("content_hash") or ""),
            timestamp=str(data.get("timestamp") or ""),
            label=str(data.get("label") or ""),
            priority=data.get("priority", 50),
            preview=str(data.get("preview") or ""),
            text=str(data.get("text") or ""),
            payload=data.get("payload"),
            sub_source=str(data.get("sub_source") or ""),
            source_candidate=str(data.get("source_candidate") or ""),
            diagnostics=list(data.get("diagnostics") or []),
        )


@dataclass(frozen=True)
class NormalizedCall:
    """One normalized logical LLM call and its lightweight edge references."""

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
        object.__setattr__(self, "call_index", non_negative_int("call.call_index", self.call_index))
        if self.call_index <= 0:
            raise ValueError("call.call_index must start at 1")
        if self.call_key != f"C{self.call_index}":
            raise ValueError("call.call_key must match call_index")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedCall":
        return cls(
            call_id=str(data.get("call_id") or ""),
            call_index=data.get("call_index", 0),
            call_key=str(data.get("call_key") or ""),
            scope=str(data.get("scope") or "main"),
            parent_call_id=str(data.get("parent_call_id") or ""),
            parent_tool_call_id=str(data.get("parent_tool_call_id") or ""),
            turn_id=str(data.get("turn_id") or ""),
            model=str(data.get("model") or ""),
            timestamp=str(data.get("timestamp") or ""),
            usage=NormalizedCallUsage.from_dict(data.get("usage") if isinstance(data.get("usage"), dict) else {}),
            request=NormalizedCallRequest.from_dict(data.get("request") if isinstance(data.get("request"), dict) else {}),
            response=NormalizedCallResponse.from_dict(data.get("response") if isinstance(data.get("response"), dict) else {}),
            source_unit_ref_ranges=[
                SourceUnitRefRange.from_dict(item)
                for item in data.get("source_unit_ref_ranges") or []
                if isinstance(item, dict)
            ],
            source_units=list(data.get("source_units") or []),
            attribution_candidates=data.get("attribution_candidates") if isinstance(data.get("attribution_candidates"), dict) else {},
            usage_source=data.get("usage_source") if isinstance(data.get("usage_source"), dict) else {},
        )


@dataclass(frozen=True)
class NormalizedToolExecution:
    """Edge-table row for a tool call declared by one call and consumed by another."""

    tool_call_id: str
    name: str
    scope: str
    declared_by_call_id: str
    result_consumed_by_call_id: str = ""
    status: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    files_touched: list[str] = field(default_factory=list)
    subagent_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "duration_ms", non_negative_int("tool.duration_ms", self.duration_ms))
        if self.exit_code is not None:
            object.__setattr__(self, "exit_code", int(self.exit_code))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedToolExecution":
        return cls(
            tool_call_id=str(data.get("tool_call_id") or ""),
            name=str(data.get("name") or ""),
            scope=str(data.get("scope") or "main"),
            declared_by_call_id=str(data.get("declared_by_call_id") or ""),
            result_consumed_by_call_id=str(data.get("result_consumed_by_call_id") or ""),
            status=str(data.get("status") or ""),
            exit_code=data.get("exit_code"),
            duration_ms=data.get("duration_ms", 0),
            files_touched=list(data.get("files_touched") or []),
            subagent_id=str(data.get("subagent_id") or ""),
        )


@dataclass(frozen=True)
class NormalizedSessionArtifact:
    """Top-level normalized session artifact persisted beside the SQLite index."""

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
        if self.schema_version != NORMALIZED_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {NORMALIZED_SCHEMA_VERSION}")
        if self.agent not in _AGENT_VALUES:
            raise ValueError(f"invalid normalized agent: {self.agent!r}")
        call_ids = [call.call_id for call in self.calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("normalized call_id values must be unique")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedSessionArtifact":
        source = data.get("source") if isinstance(data.get("source"), dict) else {}
        catalog_data = data.get("source_unit_catalog") if isinstance(data.get("source_unit_catalog"), dict) else {}
        return cls(
            schema_version=str(data.get("schema_version") or ""),
            agent=str(data.get("agent") or ""),
            source_files=[
                NormalizedSourceFile.from_dict(item)
                for item in source.get("files") or []
                if isinstance(item, dict)
            ],
            session=data.get("session") if isinstance(data.get("session"), dict) else {},
            calls=[
                NormalizedCall.from_dict(item)
                for item in data.get("calls") or []
                if isinstance(item, dict)
            ],
            tool_executions=[
                NormalizedToolExecution.from_dict(item)
                for item in data.get("tool_executions") or []
                if isinstance(item, dict)
            ],
            diagnostics=list(data.get("diagnostics") or []),
            source_unit_catalog={
                str(key): SourceUnitCatalogEntry.from_dict(value)
                for key, value in catalog_data.items()
                if isinstance(value, dict)
            },
            source_unit_sequences={
                str(key): _string_list(value)
                for key, value in (data.get("source_unit_sequences") or {}).items()
            } if isinstance(data.get("source_unit_sequences"), dict) else {},
        )


def validate_normalized_artifact_model(data: dict[str, Any]) -> None:
    """Validate normalized artifact dict through POJO construction."""
    NormalizedSessionArtifact.from_dict(data)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]
