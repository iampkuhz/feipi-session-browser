"""Base attribution builder for request and response token attribution.

This module is used when an agent-specific builder is unavailable. It reads
only normalized session context and provider token fields that are already
present on local domain objects, emits conservative attribution contracts for
UI rendering, and treats missing evidence as unavailable instead of inferring a
hidden request or response body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from session_browser.attribution.contracts import (
    AttributedValue,
    AvailabilityRow,
    LLMRequestAttribution,
    LLMResponseAttribution,
    RequestAttributionBucket,
    ResponseAttributionBucket,
    ValuePrecision,
    ValueSource,
)

if TYPE_CHECKING:
    from session_browser.domain.models import (
        ConversationRound,
        LLMCall,
        SessionSummary,
    )


_MIN_FRAGMENT_CHARS = 20


def _normalize_whitespace(text: str) -> str:
    """Collapse consecutive whitespace for conservative fragment comparison.

    Args:
        text: Text captured from a normalized source unit or tool result.

    Returns:
        Text with repeated whitespace replaced by one ASCII space.
    """
    return re.sub(r'\s+', ' ', text).strip()


@dataclass
class BaseAttributionBuilder:
    """Fallback attribution builder for unknown or unsupported agents.

    The builder is triggered by attribution code when no Claude Code, Codex, or
    Qoder builder can be selected. It uses only the local ``LLMCall`` token
    fields, optional ``session_context`` evidence, and the selected
    conversation round. Its output boundary is the ``LLMRequestAttribution``
    and ``LLMResponseAttribution`` contracts; it never claims raw body
    availability and reports unlocated evidence through residual or unavailable
    fields. Missing usage is a low-confidence attribution result, not an
    exception.

    Attributes:
        llm_call: Local model-call record containing provider usage fields,
            previews, finish reason, and call identifiers.
        round_obj: Conversation round that triggered this attribution pass.
        session_summary: Optional session metadata used by subclasses to locate
            normalized artifacts.
        session_context: Optional in-memory evidence such as prior tool
            results, normalized call payloads, or conversation history.
    """

    llm_call: LLMCall
    round_obj: ConversationRound
    session_summary: SessionSummary | None = None
    session_context: dict | None = None

    def __post_init__(self) -> None:
        """Normalize optional session context after dataclass initialization."""
        self.session_context = self.session_context or {}

    def _remove_known_fragments(self, text: str, fragments: list[str]) -> str:
        """Remove exact already-attributed fragments from a larger context.

        Args:
            text: Larger request or response context being prepared for a
                residual attribution bucket.
            fragments: Evidence strings already assigned to a more precise
                bucket.

        Returns:
            ``text`` with at most one exact occurrence of each stable fragment
            removed. Normalized matches are observed but not surgically removed
            because code and structured payloads are whitespace-sensitive.
        """
        if not text:
            return ''

        for frag in fragments:
            if not frag or len(frag.strip()) < _MIN_FRAGMENT_CHARS:
                continue
            frag_stripped = frag.strip()
            if frag_stripped in text:
                text = text.replace(frag_stripped, '', 1)

            normalized_frag = _normalize_whitespace(frag_stripped)
            normalized_text = _normalize_whitespace(text)
            if normalized_frag in normalized_text and len(normalized_frag) >= _MIN_FRAGMENT_CHARS:
                pass

        return text.strip()

    def _get_preceding_tool_result_texts(self) -> list[str]:
        """Return tool-result evidence that occurred before this LLM call.

        Returns:
            Tool result text values from ``session_context``. Items tied to a
            subagent are excluded so the parent call does not double count
            delegated output.
        """
        ctx = self.session_context or {}
        items = ctx.get('preceding_tool_results', [])
        result: list[str] = []
        for item in items:
            if hasattr(item, 'result') and item.result:
                if not getattr(item, 'subagent_id', ''):
                    result.append(item.result)
            elif isinstance(item, dict):
                text = (
                    item.get('result')
                    or item.get('content')
                    or item.get('text')
                    or item.get('output')
                )
                if text:
                    result.append(str(text))
            elif isinstance(item, str):
                result.append(item)
        return result

    def _avail(  # noqa: PLR0913
        self,
        field_name: str,
        label: str,
        available: bool,
        exact: bool = False,
        precision: str = '',
        source: str = '',
        fill_strategy: str = '',
        note: str = '',
    ) -> AvailabilityRow:
        """Build one availability row for the attribution detail table.

        Args:
            field_name: Stable attribution field key shown in diagnostics.
            label: Human-readable label for the UI parameter table.
            available: Whether local evidence is present for the field.
            exact: Whether the evidence is exact rather than estimated.
            precision: Optional explicit precision label.
            source: Optional explicit source label.
            fill_strategy: Optional explanation of how the value was filled.
            note: Optional note shown beside the availability row.

        Returns:
            Availability metadata that explains evidence presence, source, and
            failure semantics for one field.
        """
        if not precision:
            precision = (
                ValuePrecision.EXACT
                if exact
                else (ValuePrecision.UNAVAILABLE if not available else ValuePrecision.ESTIMATED)
            )
        if not source:
            source = ValueSource.HEURISTIC
        if not fill_strategy:
            fill_strategy = 'direct' if available else 'not available'
        return AvailabilityRow(
            field=field_name,
            label=label,
            exact=exact,
            available=available,
            precision=precision,
            source=source,
            fill_strategy=fill_strategy,
            note=note or ('available from ' + field_name if available else 'not available'),
        )

    def _request_id(self) -> str:
        """Return the best available request identifier for fallback output.

        Returns:
            The local call identifier, or ``unavailable`` when the source log
            did not expose a stable request id.
        """
        lc = self.llm_call
        return lc.id or 'unavailable'

    def build_request(self) -> LLMRequestAttribution:
        """Build low-confidence request attribution from local usage totals.

        Returns:
            Request attribution that assigns any provider-reported input tokens
            to one unknown bucket and marks fresh/cache splits unavailable.
        """
        lc = self.llm_call
        total = lc.input_tokens or 0

        total_input = AttributedValue(
            value=total,
            unit='tokens',
            precision=ValuePrecision.PROVIDER_REPORTED if total > 0 else ValuePrecision.UNAVAILABLE,
            source=ValueSource.PROVIDER_USAGE if total > 0 else ValueSource.HEURISTIC,
            fill_strategy='direct from llm_call.input_tokens' if total > 0 else 'unavailable',
        )

        buckets: list[RequestAttributionBucket] = []
        if total > 0:
            buckets.append(
                RequestAttributionBucket(
                    key='unknown_overhead',
                    label='未定位',
                    tokens=total,
                    percent=100.0,
                    precision=ValuePrecision.HEURISTIC,
                    source=ValueSource.HEURISTIC,
                    confidence_label='低',
                    summary='未区分 agent 时, 所有 token 归入未定位。',
                )
            )

        return LLMRequestAttribution(
            agent='unknown',
            model=lc.model or 'unknown',
            request_id=self._request_id(),
            call_id=lc.id,
            source_label='local logs',
            confidence_label='低',
            raw_body_available=False,
            total_input=total_input,
            fresh_input=AttributedValue(
                value=None,
                unit='tokens',
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                fill_strategy='unknown',
            ),
            cache_read=AttributedValue(
                value=None,
                unit='tokens',
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                fill_strategy='unknown',
            ),
            cache_write=AttributedValue(
                value=None,
                unit='tokens',
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                fill_strategy='unknown',
            ),
            coverage=AttributedValue(
                value=0.0,
                unit='ratio',
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                fill_strategy='no buckets',
            ),
            unknown=AttributedValue(
                value=total,
                unit='tokens',
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.RESIDUAL,
                fill_strategy='all unknown',
            ),
            buckets=buckets,
            captured_context_preview='',
            attribution_notes=['No agent-specific builder available.'],
            availability_rows=[
                self._avail(
                    'input_side_component_total',
                    'Input-side component total',
                    total > 0,
                    precision=ValuePrecision.PROVIDER_REPORTED
                    if total > 0
                    else ValuePrecision.UNAVAILABLE,
                    source=ValueSource.PROVIDER_USAGE if total > 0 else ValueSource.HEURISTIC,
                    fill_strategy='direct from llm_call.input_tokens'
                    if total > 0
                    else 'unavailable',
                ),
                self._avail(
                    'fresh_input',
                    'Fresh input tokens',
                    False,
                    precision=ValuePrecision.UNAVAILABLE,
                    source=ValueSource.HEURISTIC,
                    fill_strategy='unknown',
                ),
                self._avail(
                    'cache_read',
                    'Cache read tokens',
                    False,
                    precision=ValuePrecision.UNAVAILABLE,
                    source=ValueSource.HEURISTIC,
                    fill_strategy='unknown',
                ),
                self._avail(
                    'cache_write',
                    'Cache write tokens',
                    False,
                    precision=ValuePrecision.UNAVAILABLE,
                    source=ValueSource.HEURISTIC,
                    fill_strategy='unknown',
                ),
            ],
        )

    def build_response(self) -> LLMResponseAttribution:
        """Build low-confidence response attribution from local usage totals.

        Returns:
            Response attribution that assigns any provider-reported output
            tokens to one unknown bucket while preserving finish reason and
            preview evidence from the local call record.
        """
        lc = self.llm_call
        total = lc.output_tokens or 0

        total_output = AttributedValue(
            value=total,
            unit='tokens',
            precision=ValuePrecision.PROVIDER_REPORTED if total > 0 else ValuePrecision.UNAVAILABLE,
            source=ValueSource.PROVIDER_USAGE if total > 0 else ValueSource.HEURISTIC,
            fill_strategy='direct from llm_call.output_tokens' if total > 0 else 'unavailable',
        )

        buckets: list[ResponseAttributionBucket] = []
        if total > 0:
            buckets.append(
                ResponseAttributionBucket(
                    key='unknown',
                    label='Unknown',
                    tokens=total,
                    percent=100.0,
                    precision=ValuePrecision.HEURISTIC,
                    source=ValueSource.HEURISTIC,
                    confidence_label='低',
                    summary='未区分 agent 时, 所有 output token 归入 unknown。',
                )
            )

        finish_str = lc.finish_reason or ''
        return LLMResponseAttribution(
            agent='unknown',
            model=lc.model or 'unknown',
            request_id=self._request_id(),
            call_id=lc.id,
            source_label='local logs',
            confidence_label='低',
            raw_body_available=False,
            total_output=total_output,
            visible_text=AttributedValue(
                value=None,
                unit='tokens',
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                fill_strategy='unknown',
            ),
            tool_use=AttributedValue(
                value=None,
                unit='tokens',
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                fill_strategy='unknown',
            ),
            metadata=AttributedValue(
                value=None,
                unit='tokens',
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                fill_strategy='unknown',
            ),
            coverage=AttributedValue(
                value=0.0,
                unit='ratio',
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                fill_strategy='no buckets',
            ),
            unknown=AttributedValue(
                value=total,
                unit='tokens',
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.RESIDUAL,
                fill_strategy='all unknown',
            ),
            finish_reason=AttributedValue(
                value=finish_str,
                unit='str',
                precision=ValuePrecision.EXACT if finish_str else ValuePrecision.UNAVAILABLE,
                source=ValueSource.TRANSCRIPT,
                fill_strategy='from llm_call.finish_reason',
            ),
            buckets=buckets,
            blocks=lc.content_blocks or [],
            captured_output_preview=lc.response_preview or '',
            attribution_notes=['No agent-specific builder available.'],
            availability_rows=[
                self._avail(
                    'total_output',
                    'Total output tokens',
                    total > 0,
                    precision=ValuePrecision.PROVIDER_REPORTED
                    if total > 0
                    else ValuePrecision.UNAVAILABLE,
                    source=ValueSource.PROVIDER_USAGE if total > 0 else ValueSource.HEURISTIC,
                    fill_strategy='direct from llm_call.output_tokens'
                    if total > 0
                    else 'unavailable',
                ),
                self._avail(
                    'visible_text',
                    'Visible text tokens',
                    False,
                    precision=ValuePrecision.UNAVAILABLE,
                    source=ValueSource.HEURISTIC,
                    fill_strategy='unknown',
                ),
                self._avail(
                    'tool_call',
                    'Tool call tokens',
                    False,
                    precision=ValuePrecision.UNAVAILABLE,
                    source=ValueSource.HEURISTIC,
                    fill_strategy='unknown',
                ),
                self._avail(
                    'finish_reason',
                    'Finish reason',
                    bool(finish_str),
                    precision=ValuePrecision.EXACT if finish_str else ValuePrecision.UNAVAILABLE,
                    source=ValueSource.TRANSCRIPT,
                    fill_strategy='from llm_call.finish_reason',
                ),
            ],
        )
