"""Token domain models.

The five token components are intentionally explicit because UI and indexing
need a stable vocabulary. ``total_tokens`` is authoritative only according to
``total_semantics``; for component-sum semantics it is recomputed from the four
exclusive components.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from session_browser.domain._validation import coerce_enum, enum_value, non_negative_int
from session_browser.domain.enums import TokenPrecision, TokenSourceKind, TokenTotalSemantics

_COMPONENT_SUM_SEMANTICS = {
    TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
    TokenTotalSemantics.ESTIMATED_COMPONENT_SUM,
    TokenTotalSemantics.RECOMPUTED_DUE_TO_INCONSISTENT_RAW_TOTAL,
}


@dataclass
class NormalizedTokenBreakdown:
    """Normalized five-field token accounting for a session or LLM call.

    fresh_input_tokens: input tokens that were not cache reads or writes.
    cache_read_tokens: provider-reported cached input tokens read this call.
    cache_write_tokens: provider-reported cache creation/write input tokens.
    output_tokens: provider-reported visible output tokens.
    total_tokens: total according to ``total_semantics``.
    precision/source_kind: provenance for the normalized value, not UI labels.
    raw_fields: original provider/parser fields used to derive this object.
    notes: machine/debug notes explaining repairs or uncertainty.
    """

    fresh_input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    precision: TokenPrecision = TokenPrecision.UNKNOWN
    total_semantics: TokenTotalSemantics = TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM
    source_kind: TokenSourceKind = TokenSourceKind.UNKNOWN
    raw_fields: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.fresh_input_tokens = non_negative_int("fresh_input_tokens", self.fresh_input_tokens)
        self.cache_read_tokens = non_negative_int("cache_read_tokens", self.cache_read_tokens)
        self.cache_write_tokens = non_negative_int("cache_write_tokens", self.cache_write_tokens)
        self.output_tokens = non_negative_int("output_tokens", self.output_tokens)
        self.total_tokens = non_negative_int("total_tokens", self.total_tokens)
        self.precision = coerce_enum(TokenPrecision, self.precision, "precision")
        self.total_semantics = coerce_enum(TokenTotalSemantics, self.total_semantics, "total_semantics")
        self.source_kind = coerce_enum(TokenSourceKind, self.source_kind, "source_kind")

        component_total = self.component_total
        if self.total_tokens == 0 and component_total > 0:
            self.total_tokens = component_total
            self.notes.append("total_tokens recomputed from token components")
        elif self.total_semantics in _COMPONENT_SUM_SEMANTICS and self.total_tokens != component_total:
            self.total_tokens = component_total
            self.notes.append("total_tokens aligned to exclusive component sum")
        elif self.total_tokens < self.output_tokens:
            raise ValueError("total_tokens must be >= output_tokens")

    @property
    def component_total(self) -> int:
        """Sum of the four mutually exclusive token components."""
        return (
            self.fresh_input_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + self.output_tokens
        )
