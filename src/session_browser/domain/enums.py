"""Type-safe domain enums.

These enums replace historical string-constant classes while remaining JSON
friendly: each enum member is also a ``str`` and serializes to its value when
used by the DTO layer.
"""

from __future__ import annotations

from enum import Enum


class DomainStrEnum(str, Enum):
    """Base class for finite string values used in domain models."""

    def __str__(self) -> str:
        return self.value


class TokenPrecision(DomainStrEnum):
    """How trustworthy a token value is.

    EXACT: counted from a deterministic local source.
    PROVIDER_REPORTED: reported by provider/broker usage data.
    ESTIMATED: locally estimated from visible content.
    UNKNOWN: unavailable or deliberately zero-filled.
    """

    EXACT = "exact"
    PROVIDER_REPORTED = "provider_reported"
    ESTIMATED = "estimated"
    UNKNOWN = "unavailable"

    # Compatibility aliases for older normalizer call sites. They intentionally
    # share canonical enum values, so iteration still exposes only four states.
    PROVIDER_REPORTED_NORMALIZED = PROVIDER_REPORTED
    PROVIDER_REPORTED_DELTA = PROVIDER_REPORTED
    SQLITE_TOKEN_INFO = EXACT
    ESTIMATED_PARTIAL = ESTIMATED
    ZERO_FILLED_UNAVAILABLE = UNKNOWN
    REPORTED_TOTAL_ONLY = PROVIDER_REPORTED


class TokenTotalSemantics(DomainStrEnum):
    """What ``total_tokens`` means relative to token components."""

    EXCLUSIVE_COMPONENT_SUM = "exclusive_components_sum"
    REPORTED_TOTAL = "reported_total"
    REPORTED_CUMULATIVE_DELTA = "reported_cumulative_delta"
    PROMPT_TOTAL_PLUS_OUTPUT = "prompt_total_plus_output"
    ESTIMATED_COMPONENT_SUM = "estimated_components_sum"
    RECOMPUTED_DUE_TO_INCONSISTENT_RAW_TOTAL = "recomputed_due_to_inconsistent_raw_total"


class TokenSourceKind(DomainStrEnum):
    """Source of token data before normalization."""

    CLAUDE_CODE_JSONL_USAGE = "claude_code_jsonl_usage"
    CODEX_ROLLOUT_TOKEN_COUNT = "codex_rollout_token_count"
    OPENAI_RESPONSES_USAGE = "openai_responses_usage"
    QODER_SEGMENT_MODEL_RESPONSE_COMPLETED = "qoder_segment_model_response_completed"
    QODER_SQLITE_TOKEN_INFO = "qoder_sqlite_token_info"
    QODER_TURN_FINISHED_FALLBACK = "qoder_turn_finished_fallback"
    QODER_TRANSCRIPT_ESTIMATED = "qoder_transcript_estimated"
    SESSION_TOTAL_ONLY_FALLBACK = "session_total_only_fallback"
    UNKNOWN = "unknown"


class TokenProvider(DomainStrEnum):
    """Provider or broker family inferred from model/runtime context."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    CODEX = "codex"
    QWEN_ANTHROPIC_COMPATIBLE = "qwen-anthropic-compatible"
    QODER = "qoder"
    UNKNOWN = "unknown"


class CallScope(DomainStrEnum):
    """Execution scope of an LLM call or tool call."""

    MAIN = "main"
    SUBAGENT = "subagent"


class CallStatus(DomainStrEnum):
    """Common success/error status for LLM and tool events."""

    OK = "ok"
    ERROR = "error"
    COMPLETED = "completed"
