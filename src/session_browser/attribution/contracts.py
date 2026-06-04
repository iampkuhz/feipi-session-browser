"""Stable contracts for LLM call attribution.

All dataclasses and enums used by the attribution layer are defined here
so that UI and test layers depend on a single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ─── Precision / Source enums ──────────────────────────────────────────


class ValuePrecision:
    EXACT = "exact"
    PROVIDER_REPORTED = "provider_reported"
    TRANSCRIPT_EXACT = "transcript_exact"
    ESTIMATED = "estimated"
    HEURISTIC = "heuristic"
    RESIDUAL = "residual"
    UNAVAILABLE = "unavailable"


class ValueSource:
    PROVIDER_USAGE = "provider_usage"
    TRANSCRIPT = "transcript"
    TOOL_LOGS = "tool_logs"
    SESSION_METADATA = "session_metadata"
    LOCAL_RULES = "local_rules"
    TOOL_LIST = "tool_list"
    HEURISTIC = "heuristic"
    RESIDUAL = "residual"


# ─── Core attributed value ─────────────────────────────────────────────


@dataclass
class AttributedValue:
    """A single numeric or string value with provenance."""
    value: int | float | str | None
    unit: str
    precision: str
    source: str
    fill_strategy: str = ""
    note: str = ""


# ─── Request bucket ────────────────────────────────────────────────────


@dataclass
class RequestAttributionBucket:
    """One request-side attribution bucket (e.g. history messages)."""
    key: str
    label: str
    tokens: int
    percent: float
    count_label: str = ""
    precision: str = ValuePrecision.ESTIMATED
    source: str = ValueSource.HEURISTIC
    confidence_label: str = ""
    summary: str = ""
    expandable: bool = False
    content_preview: str = ""
    contributes_to_total: bool = True
    parent_key: str = ""
    display_group: str = ""
    details: dict = field(default_factory=dict)


# ─── Response bucket ───────────────────────────────────────────────────


@dataclass
class ResponseAttributionBucket:
    """One response-side attribution bucket (e.g. assistant text)."""
    key: str
    label: str
    tokens: int
    percent: float
    count_label: str = ""
    precision: str = ValuePrecision.ESTIMATED
    source: str = ValueSource.HEURISTIC
    confidence_label: str = ""
    summary: str = ""
    block_refs: list[str] = field(default_factory=list)
    contributes_to_total: bool = True
    parent_key: str = ""
    display_group: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class AvailabilityRow:
    """One row in the parameter availability table for UI consumption."""
    field: str
    label: str
    exact: bool
    available: bool
    precision: str
    source: str
    fill_strategy: str
    note: str = ""


# ─── Request attribution result ────────────────────────────────────────


@dataclass
class LLMRequestAttribution:
    """Full request attribution for one LLM call."""
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


# ─── Response attribution result ───────────────────────────────────────


@dataclass
class LLMResponseAttribution:
    """Full response attribution for one LLM call."""
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


# ─── Re-exports from new core models (v2, backward compatible) ──────
# 新架构的核心数据模型通过 contracts.py 重新导出，保持旧 import 路径兼容。

from session_browser.attribution.core.models import (
    ContentRef,
    Evidence,
    PromptSpan,
    UsageBreakdown,
    AttributionResult,
    CallCreditSlice,
    CreditAttribution,
)

__all__ = [
    # Old public contracts
    "ValuePrecision",
    "ValueSource",
    "AttributedValue",
    "RequestAttributionBucket",
    "ResponseAttributionBucket",
    "AvailabilityRow",
    "LLMRequestAttribution",
    "LLMResponseAttribution",
    # New v2 core models
    "ContentRef",
    "Evidence",
    "PromptSpan",
    "UsageBreakdown",
    "AttributionResult",
    "CallCreditSlice",
    "CreditAttribution",
]