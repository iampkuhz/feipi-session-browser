"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from enum import Enum


class DomainStrEnum(str, Enum):
    """DomainStrEnum contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.
    """

    def __str__(self) -> str:
        """__str__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.value


class TokenPrecision(DomainStrEnum):
    """TokenPrecision contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        EXACT: Public contract field or enum value.
        PROVIDER_REPORTED: Public contract field or enum value.
        ESTIMATED: Public contract field or enum value.
        UNKNOWN: Public contract field or enum value.
        PROVIDER_REPORTED_NORMALIZED: Public contract field or enum value.
        PROVIDER_REPORTED_DELTA: Public contract field or enum value.
        SQLITE_TOKEN_INFO: Public contract field or enum value.
        ESTIMATED_PARTIAL: Public contract field or enum value.
        ZERO_FILLED_UNAVAILABLE: Public contract field or enum value.
        REPORTED_TOTAL_ONLY: Public contract field or enum value.
    """

    EXACT = 'exact'
    PROVIDER_REPORTED = 'provider_reported'
    ESTIMATED = 'estimated'
    UNKNOWN = 'unavailable'

    # Compatibility aliases for older normalizer call sites. They intentionally
    # share canonical enum values, so iteration still exposes only four states.
    PROVIDER_REPORTED_NORMALIZED = PROVIDER_REPORTED
    PROVIDER_REPORTED_DELTA = PROVIDER_REPORTED
    SQLITE_TOKEN_INFO = EXACT
    ESTIMATED_PARTIAL = ESTIMATED
    ZERO_FILLED_UNAVAILABLE = UNKNOWN
    REPORTED_TOTAL_ONLY = PROVIDER_REPORTED


class TokenTotalSemantics(DomainStrEnum):
    """TokenTotalSemantics contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        EXCLUSIVE_COMPONENT_SUM: Public contract field or enum value.
        REPORTED_TOTAL: Public contract field or enum value.
        REPORTED_CUMULATIVE_DELTA: Public contract field or enum value.
        PROMPT_TOTAL_PLUS_OUTPUT: Public contract field or enum value.
        ESTIMATED_COMPONENT_SUM: Public contract field or enum value.
        RECOMPUTED_DUE_TO_INCONSISTENT_RAW_TOTAL: Public contract field or enum value.
    """

    EXCLUSIVE_COMPONENT_SUM = 'exclusive_components_sum'
    REPORTED_TOTAL = 'reported_total'
    REPORTED_CUMULATIVE_DELTA = 'reported_cumulative_delta'
    PROMPT_TOTAL_PLUS_OUTPUT = 'prompt_total_plus_output'
    ESTIMATED_COMPONENT_SUM = 'estimated_components_sum'
    RECOMPUTED_DUE_TO_INCONSISTENT_RAW_TOTAL = 'recomputed_due_to_inconsistent_raw_total'


class TokenSourceKind(DomainStrEnum):
    """TokenSourceKind contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        CLAUDE_CODE_JSONL_USAGE: Public contract field or enum value.
        CODEX_ROLLOUT_TOKEN_COUNT: Public contract field or enum value.
        OPENAI_RESPONSES_USAGE: Public contract field or enum value.
        QODER_SEGMENT_MODEL_RESPONSE_COMPLETED: Public contract field or enum value.
        QODER_SQLITE_TOKEN_INFO: Public contract field or enum value.
        QODER_TURN_FINISHED_FALLBACK: Public contract field or enum value.
        QODER_TRANSCRIPT_ESTIMATED: Public contract field or enum value.
        SESSION_TOTAL_ONLY_FALLBACK: Public contract field or enum value.
        UNKNOWN: Public contract field or enum value.
    """

    CLAUDE_CODE_JSONL_USAGE = 'claude_code_jsonl_usage'
    CODEX_ROLLOUT_TOKEN_COUNT = 'codex_rollout_token_count'
    OPENAI_RESPONSES_USAGE = 'openai_responses_usage'
    QODER_SEGMENT_MODEL_RESPONSE_COMPLETED = 'qoder_segment_model_response_completed'
    QODER_SQLITE_TOKEN_INFO = 'qoder_sqlite_token_info'
    QODER_TURN_FINISHED_FALLBACK = 'qoder_turn_finished_fallback'
    QODER_TRANSCRIPT_ESTIMATED = 'qoder_transcript_estimated'
    SESSION_TOTAL_ONLY_FALLBACK = 'session_total_only_fallback'
    UNKNOWN = 'unknown'


class TokenProvider(DomainStrEnum):
    """TokenProvider contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        ANTHROPIC: Public contract field or enum value.
        OPENAI: Public contract field or enum value.
        CODEX: Public contract field or enum value.
        QWEN_ANTHROPIC_COMPATIBLE: Public contract field or enum value.
        QODER: Public contract field or enum value.
        UNKNOWN: Public contract field or enum value.
    """

    ANTHROPIC = 'anthropic'
    OPENAI = 'openai'
    CODEX = 'codex'
    QWEN_ANTHROPIC_COMPATIBLE = 'qwen-anthropic-compatible'
    QODER = 'qoder'
    UNKNOWN = 'unknown'


class CallScope(DomainStrEnum):
    """CallScope contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        MAIN: Public contract field or enum value.
        SUBAGENT: Public contract field or enum value.
    """

    MAIN = 'main'
    SUBAGENT = 'subagent'


class CallStatus(DomainStrEnum):
    """CallStatus contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        OK: Public contract field or enum value.
        ERROR: Public contract field or enum value.
        COMPLETED: Public contract field or enum value.
    """

    OK = 'ok'
    ERROR = 'error'
    COMPLETED = 'completed'
