"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from session_browser.domain._validation import coerce_enum, non_negative_int
from session_browser.domain.enums import TokenPrecision, TokenSourceKind, TokenTotalSemantics

_COMPONENT_SUM_SEMANTICS = {
    TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
    TokenTotalSemantics.ESTIMATED_COMPONENT_SUM,
    TokenTotalSemantics.RECOMPUTED_DUE_TO_INCONSISTENT_RAW_TOTAL,
}


@dataclass
class NormalizedTokenBreakdown:
    """NormalizedTokenBreakdown contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        fresh_input_tokens: Public contract field or enum value.
        cache_read_tokens: Public contract field or enum value.
        cache_write_tokens: Public contract field or enum value.
        output_tokens: Public contract field or enum value.
        total_tokens: Public contract field or enum value.
        precision: Public contract field or enum value.
        total_semantics: Public contract field or enum value.
        source_kind: Public contract field or enum value.
        raw_fields: Public contract field or enum value.
        notes: Public contract field or enum value.
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
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Raises:
                    ValueError: Raised when validation or file lookup rejects the input.
        """
        self.fresh_input_tokens = non_negative_int('fresh_input_tokens', self.fresh_input_tokens)
        self.cache_read_tokens = non_negative_int('cache_read_tokens', self.cache_read_tokens)
        self.cache_write_tokens = non_negative_int('cache_write_tokens', self.cache_write_tokens)
        self.output_tokens = non_negative_int('output_tokens', self.output_tokens)
        self.total_tokens = non_negative_int('total_tokens', self.total_tokens)
        self.precision = coerce_enum(TokenPrecision, self.precision, 'precision')
        self.total_semantics = coerce_enum(
            TokenTotalSemantics, self.total_semantics, 'total_semantics'
        )
        self.source_kind = coerce_enum(TokenSourceKind, self.source_kind, 'source_kind')

        component_total = self.component_total
        if self.total_tokens == 0 and component_total > 0:
            self.total_tokens = component_total
            self.notes.append('total_tokens recomputed from token components')
        elif (
            self.total_semantics in _COMPONENT_SUM_SEMANTICS
            and self.total_tokens != component_total
        ):
            self.total_tokens = component_total
            self.notes.append('total_tokens aligned to exclusive component sum')
        elif self.total_tokens < self.output_tokens:
            raise ValueError('total_tokens must be >= output_tokens')

    @property
    def component_total(self) -> int:
        """component_total method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return (
            self.fresh_input_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + self.output_tokens
        )
