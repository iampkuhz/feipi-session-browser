"""Codex call mapping resolver and token accounting mapper."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import ClassVar

from session_browser.attribution.contracts import AttributedValue
from session_browser.attribution.mapping.call_mapping_resolver import CallMappingDecision
from session_browser.attribution.mapping.usage_shape_detector import detect_usage_shape
from session_browser.attribution.token_estimator import estimate_tokens_from_text


@dataclass(frozen=True)
class CodexCallMappingResolver:
    """Resolve Codex calls into OpenAI API family and billing decisions."""

    def resolve(
        self,
        *,
        usage: dict | None = None,
        model: str | None = None,
        raw_request: dict | None = None,
        raw_response: dict | None = None,
    ) -> CallMappingDecision:
        """Map one Codex call to the attribution call-mapping contract.

        The resolver is invoked after a Codex session row is normalized. It
        distinguishes OpenAI Responses, OpenAI Chat, basic token usage, and local
        reconstruction fallback shapes. Raw request and response payloads are
        accepted to keep the common resolver interface stable, but this mapper
        does not inspect them.

        Args:
            usage: Optional provider usage object from the normalized call.
            model: Model name reported for the call, if available.
            raw_request: Raw request payload reserved for future shape checks.
            raw_response: Raw response payload reserved for future shape checks.

        Returns:
            A decision with Codex as runtime, OpenAI as provider, token billing
            units, API family, confidence, reasons, and fallback warnings.
        """
        _ = (raw_request, raw_response)
        usage_shape = detect_usage_shape(usage)
        reasons = ['agent is codex -> provider openai']
        warnings: list[str] = []
        api_family = 'openai_responses'
        confidence = 0.7
        usage_source = (
            'provider_reported' if usage_shape != 'unavailable' else 'local_reconstruction'
        )

        if usage_shape == 'openai_responses_like':
            confidence = 0.95
            reasons.append('codex with OpenAI Responses usage -> openai_responses')
        elif usage_shape == 'openai_chat_like':
            api_family = 'openai_chat'
            confidence = 0.9
            reasons.append('codex with OpenAI Chat usage -> openai_chat')
        elif usage_shape == 'token_reported_unknown_cache':
            confidence = 0.7
            reasons.append('codex with basic token usage -> openai_responses')
        else:
            api_family = 'estimate_only'
            confidence = 0.4
            warnings.append('Codex 无预期 OpenAI usage, 使用本地估算')

        return CallMappingDecision(
            agent_runtime='codex',
            api_family=api_family,
            provider_or_broker='openai',
            underlying_provider=None,
            model=model,
            billing_units=['tokens'],
            usage_source=usage_source,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
        )


class CodexTokenAccountingMapper:
    """Build field-first accounting payloads from Codex source units.

    Attribution assembly calls this mapper after Codex request or response source
    units are normalized. Input units are dictionaries grouped by ``direction``
    and ``candidate``; text, payload, or preview content is estimated locally.
    The output always preserves the ``token_accounting_fields.v1`` schema and the
    fixed field order. Cache read/write remain provider accounting fields, while
    response reasoning output can be assigned exactly when provider usage reports
    it.

    Attributes:
        FIELD_ORDER: Stable order for fresh input, cache read, cache write, and
            output token fields in every accounting payload.
    """

    FIELD_ORDER: ClassVar[list[str]] = [
        'fresh_input_tokens',
        'cache_read_tokens',
        'cache_write_tokens',
        'output_tokens',
    ]

    def source_units_for_direction(self, source_units: list[dict], direction: str) -> list[dict]:
        """Select normalized source units that belong to one traffic direction.

        Args:
            source_units: Normalized attribution source unit dictionaries.
            direction: Expected direction, usually ``request`` or ``response``.

        Returns:
            Source units whose ``direction`` value exactly matches the requested
            direction; malformed non-dict entries are ignored.
        """
        return [
            u for u in source_units or [] if isinstance(u, dict) and u.get('direction') == direction
        ]

    def candidate_groups(self, source_units: list[dict], direction: str) -> dict[str, list[dict]]:
        """Group source units by candidate within one direction.

        This helper is used by callers that need the raw normalized units before
        accounting field payloads are built. It preserves each unit unchanged and
        only drops entries without a candidate key.

        Args:
            source_units: Normalized attribution source unit dictionaries.
            direction: Direction to filter before grouping.

        Returns:
            Mapping from candidate name to the source units that contributed to
            that candidate in the requested direction.
        """
        groups: dict[str, list[dict]] = {}
        for unit in self.source_units_for_direction(source_units, direction):
            candidate = str(unit.get('candidate') or '')
            if candidate:
                groups.setdefault(candidate, []).append(unit)
        return groups

    def build_request_accounting(
        self,
        *,
        source_units: list[dict],
        fresh_input: AttributedValue,
        cache_read: AttributedValue,
        cache_write: AttributedValue,
    ) -> dict:
        """Build request-side token accounting for a Codex call.

        The request attribution path calls this with request source units and the
        provider or reconstructed request accounting fields. Candidate allocation
        is limited to fresh input tokens. Cache read and cache write remain
        top-level provider accounting fields because local source units cannot
        identify provider-cached context reliably.

        Args:
            source_units: Normalized source units from the call request side.
            fresh_input: Fresh input token value to allocate across candidates.
            cache_read: Provider cache-read token field to expose without splits.
            cache_write: Provider cache-write token field to expose without splits.

        Returns:
            A field-first payload with request candidates, cache fields, output
            placeholder, totals, notes, and unattributed token mass.
        """
        fresh_total = _num(fresh_input.value)
        candidates, unattributed = self._candidate_entries(
            self.source_units_for_direction(source_units, 'request'),
            denominator=fresh_total,
        )
        return {
            'schema': 'token_accounting_fields.v1',
            'field_order': list(self.FIELD_ORDER),
            'fresh_input_tokens': self._field_payload(
                'fresh_input_tokens',
                fresh_input,
                candidates,
                unattributed_tokens=unattributed,
                notes=[
                    'Codex mapping 根据 normalized source_units 暴露 request-side candidates.',
                    '本地数据无法可靠拆分 candidate-level cache read; '
                    'cache read 单独作为 provider accounting 展示.',
                ],
            ),
            'cache_read_tokens': self._field_payload(
                'cache_read_tokens',
                cache_read,
                [],
                notes=[
                    'Provider reported cached_input_tokens; 不创建 provider_cached_context 来源.'
                ],
            ),
            'cache_write_tokens': self._field_payload(
                'cache_write_tokens',
                cache_write,
                [],
                notes=['Codex/OpenAI Responses cache_write unavailable; 不从 residual 推断.'],
            ),
            'output_tokens': self._field_payload(
                'output_tokens',
                _zero_value('Request attribution payload 不包含 response output allocation.'),
                [],
            ),
        }

    def build_response_accounting(
        self,
        *,
        source_units: list[dict],
        total_output: AttributedValue,
        reasoning_output_tokens: int = 0,
    ) -> dict:
        """Build response-side token accounting for a Codex call.

        The response attribution path calls this with response source units,
        provider total output, and optional exact reasoning output. Exact
        reasoning output is assigned only to the ``reasoning_output`` candidate;
        other response candidates keep unknown token mass. Request-side fields are
        emitted as explicit zero placeholders for stable consumer parsing.

        Args:
            source_units: Normalized source units from the call response side.
            total_output: Total output token value for the response.
            reasoning_output_tokens: Provider-reported reasoning output tokens.

        Returns:
            A field-first payload with zero request fields, output candidates,
            totals, notes, and unattributed output token mass.
        """
        output_total = _num(total_output.value)
        candidates, unattributed = self._candidate_entries(
            self.source_units_for_direction(source_units, 'response'),
            denominator=output_total,
            exact_candidate_tokens={
                'reasoning_output': max(int(reasoning_output_tokens or 0), 0),
            }
            if reasoning_output_tokens
            else None,
        )
        return {
            'schema': 'token_accounting_fields.v1',
            'field_order': list(self.FIELD_ORDER),
            'fresh_input_tokens': self._field_payload(
                'fresh_input_tokens',
                _zero_value('Response attribution payload 不包含 request input allocation.'),
                [],
            ),
            'cache_read_tokens': self._field_payload(
                'cache_read_tokens',
                _zero_value('Response attribution payload 不包含 request cache-read allocation.'),
                [],
            ),
            'cache_write_tokens': self._field_payload(
                'cache_write_tokens',
                _zero_value('Response attribution payload 不包含 request cache-write allocation.'),
                [],
            ),
            'output_tokens': self._field_payload(
                'output_tokens',
                total_output,
                candidates,
                unattributed_tokens=unattributed,
                notes=[
                    'Codex mapping 根据 normalized response source_units 暴露 output candidates.'
                ],
            ),
        }

    def _candidate_entries(
        self,
        units: list[dict],
        *,
        denominator: float,
        exact_candidate_tokens: dict[str, int] | None = None,
    ) -> tuple[list[dict], int]:
        """Aggregate Codex source units into candidate accounting entries.

        Args:
            units: Direction-filtered source units with optional candidate keys.
            denominator: Provider or reconstructed token total for this field.
            exact_candidate_tokens: Candidate token totals reported by provider
                usage, keyed by candidate name.

        Returns:
            Candidate entries sorted by candidate name and the positive residual
            token count that could not be attributed to known exact candidates.
        """
        entries: dict[str, dict[str, object]] = {}
        exact_candidate_tokens = exact_candidate_tokens or {}
        for unit in units:
            candidate = str(unit.get('candidate') or '')
            if not candidate:
                continue
            content_estimate = _unit_tokens(unit)
            entry = entries.setdefault(
                candidate,
                {
                    'candidate': candidate,
                    'tokens': 0,
                    'percent': 0.0,
                    'token_status': 'unknown_mass',
                    'token_precision': 'unknown_mass',
                    'sources': [],
                },
            )
            if candidate in exact_candidate_tokens:
                entry['tokens'] = exact_candidate_tokens[candidate]
                entry['token_status'] = 'exact_provider'
                entry['token_precision'] = 'provider_reported'
            sources = entry['sources']
            if isinstance(sources, list):
                sources.append(
                    {
                        'source_id': unit.get('source_id', ''),
                        'origin_path': unit.get('origin_path', ''),
                        'unit_type': unit.get('unit_type', ''),
                        'label': unit.get('label', ''),
                        'tokens': 0,
                        'token_status': entry['token_status'],
                        'content_token_estimate': content_estimate,
                        'preview': unit.get('preview', ''),
                    }
                )

        result: list[dict] = []
        for entry in entries.values():
            tokens = (
                min(int(entry['tokens']), int(denominator))
                if denominator > 0
                else int(entry['tokens'])
            )
            entry['tokens'] = tokens
            entry['percent'] = round((tokens / denominator) * 100.0, 1) if denominator > 0 else 0.0
            result.append(entry)
        result.sort(key=lambda item: item['candidate'])
        known = sum(int(item['tokens']) for item in result)
        return result, max(int(denominator) - known, 0) if denominator > 0 else 0

    def _field_payload(
        self,
        field: str,
        value: AttributedValue,
        candidates: list[dict],
        *,
        unattributed_tokens: int = 0,
        notes: list[str] | None = None,
    ) -> dict:
        """Wrap one accounting field in the shared payload structure.

        Args:
            field: Accounting field name from ``FIELD_ORDER``.
            value: Token value and provenance metadata for the field.
            candidates: Candidate allocation entries for this field.
            unattributed_tokens: Residual tokens not assigned to candidates.
            notes: Human-readable mapping notes for consumers.

        Returns:
            A serializable dictionary containing field metadata, candidates,
            candidate totals, residual tokens, and notes.
        """
        return {
            'field': field,
            'tokens': _num(value.value),
            'value': {
                'value': value.value,
                'unit': value.unit,
                'precision': value.precision,
                'source': value.source,
                'fill_strategy': value.fill_strategy,
                'note': value.note,
            },
            'candidates': candidates,
            'candidate_total_tokens': sum(_num(item.get('tokens')) for item in candidates),
            'unattributed_tokens': unattributed_tokens,
            'notes': notes or [],
        }


def _unit_tokens(unit: dict) -> int:
    """Estimate tokens for one source unit using stable content precedence.

    Args:
        unit: Normalized source unit that may contain text, payload, or preview.

    Returns:
        Estimated token count from text first, then stable payload JSON, then
        preview text. Missing content contributes zero-estimate text.
    """
    if unit.get('text'):
        return estimate_tokens_from_text(str(unit.get('text') or ''))
    if 'payload' in unit:
        return estimate_tokens_from_text(
            json.dumps(unit.get('payload'), ensure_ascii=False, sort_keys=True)
        )
    return estimate_tokens_from_text(str(unit.get('preview') or ''))


def _num(value: object) -> float:
    """Convert optional numeric field values into float token counts.

    Args:
        value: Provider or reconstructed value that should represent tokens.

    Returns:
        Float token count, or ``0.0`` when the value is missing or invalid.
    """
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _zero_value(note: str) -> AttributedValue:
    """Create a zero-token placeholder with explicit non-applicable provenance.

    Args:
        note: Explanation attached to the placeholder field.

    Returns:
        An ``AttributedValue`` representing a zero-token non-applicable field.
    """
    return AttributedValue(
        value=0,
        unit='tokens',
        precision='unavailable',
        source='heuristic',
        fill_strategy='not applicable',
        note=note,
    )
