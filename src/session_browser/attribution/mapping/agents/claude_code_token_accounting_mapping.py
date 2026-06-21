"""Claude Code call mapping resolver and token accounting mapper."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import ClassVar

from session_browser.attribution.contracts import AttributedValue
from session_browser.attribution.mapping.call_mapping_resolver import CallMappingDecision
from session_browser.attribution.mapping.usage_shape_detector import detect_usage_shape
from session_browser.attribution.token_estimator import estimate_tokens_from_text


@dataclass(frozen=True)
class ClaudeCodeCallMappingResolver:
    """Resolve Claude Code calls into provider and billing mapping decisions."""

    def resolve(
        self,
        *,
        usage: dict | None = None,
        model: str | None = None,
        raw_request: dict | None = None,
        raw_response: dict | None = None,
    ) -> CallMappingDecision:
        """Map one Claude Code call to the attribution call-mapping contract.

        The resolver is invoked after a Claude Code session row is normalized. It
        only trusts Anthropic Messages-shaped usage as provider reported token
        accounting; otherwise it keeps the call billable in tokens but marks the
        usage source as local reconstruction from visible source units. Raw
        request and response payloads are accepted to keep the resolver interface
        stable, but this mapper does not inspect them.

        Args:
            usage: Optional provider usage object from the normalized call.
            model: Model name reported for the call, if available.
            raw_request: Raw request payload reserved for future shape checks.
            raw_response: Raw response payload reserved for future shape checks.

        Returns:
            A decision with Claude Code as runtime, Anthropic as provider, token
            billing units, confidence, reasons, and fallback warnings.
        """
        _ = (raw_request, raw_response)
        usage_shape = detect_usage_shape(usage)
        reasons = ['agent is claude_code -> provider anthropic']
        warnings: list[str] = []
        confidence = 0.4
        usage_source = 'local_reconstruction'
        api_family = 'estimate_only'
        if usage_shape == 'anthropic_messages_like':
            api_family = 'anthropic_messages'
            confidence = 0.95
            usage_source = 'provider_reported'
            reasons.append('Claude Code usage 形状为 Anthropic Messages')
        else:
            warnings.append('Claude Code 无 Anthropic usage, 使用本地可见 source_units')
        return CallMappingDecision(
            agent_runtime='claude_code',
            api_family=api_family,
            provider_or_broker='anthropic',
            underlying_provider=None,
            model=model,
            billing_units=['tokens'],
            usage_source=usage_source,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
        )


class ClaudeCodeTokenAccountingMapper:
    """Build field-first accounting payloads from Claude Code source units.

    The attribution assembly calls this mapper after request or response source
    units are normalized. Input units are dictionaries grouped by ``direction``
    and ``candidate``; text, payload, or preview content is estimated locally.
    The output always preserves the ``token_accounting_fields.v1`` schema and the
    fixed field order, keeps cache read/write as accounting fields instead of
    content candidates, and never allocates response output in request payloads or
    request input/cache fields in response payloads.

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

    def build_request_accounting(
        self,
        *,
        source_units: list[dict],
        fresh_input: AttributedValue,
        cache_read: AttributedValue,
        cache_write: AttributedValue,
    ) -> dict:
        """Build request-side token accounting for a Claude Code call.

        The request attribution path calls this with request source units and the
        provider or reconstructed request accounting fields. Candidate allocation
        is limited to fresh input tokens, while cache read and cache write remain
        top-level accounting fields. The method returns zero output allocation to
        keep request and response accounting independent.

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
                    'Claude Code request candidates 来自 normalized source_units.',
                    'cache read/write 是 Anthropic accounting fields, '
                    '不创建 provider cache 来源 candidate.',
                ],
            ),
            'cache_read_tokens': self._field_payload(
                'cache_read_tokens',
                cache_read,
                [],
                notes=[
                    'Anthropic cache_read_input_tokens 只作为 accounting field 展示, '
                    '不做 per-candidate 拆分.'
                ],
            ),
            'cache_write_tokens': self._field_payload(
                'cache_write_tokens',
                cache_write,
                [],
                notes=[
                    'Anthropic cache_creation_input_tokens 只作为 accounting field 展示, '
                    '不变成 content candidate.'
                ],
            ),
            'output_tokens': self._field_payload(
                'output_tokens',
                _zero_value('Request attribution payload 不包含 response output allocation.'),
                [],
            ),
        }

    def build_response_accounting(
        self, *, source_units: list[dict], total_output: AttributedValue
    ) -> dict:
        """Build response-side token accounting for a Claude Code call.

        The response attribution path calls this with response source units and
        the total output token field. Candidate estimates are scaled down when
        local content estimates exceed the provider denominator. Request-side
        fields are emitted as explicit zero placeholders so consumers can rely on
        a stable schema shape.

        Args:
            source_units: Normalized source units from the call response side.
            total_output: Total output token value for the response.

        Returns:
            A field-first payload with zero request fields, output candidates,
            totals, notes, and unattributed output token mass.
        """
        output_total = _num(total_output.value)
        candidates, unattributed = self._candidate_entries(
            self.source_units_for_direction(source_units, 'response'),
            denominator=output_total,
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
                notes=['Claude Code response candidates 来自 normalized source_units.'],
            ),
        }

    def _candidate_entries(
        self, units: list[dict], *, denominator: float
    ) -> tuple[list[dict], int]:
        """Aggregate source units into candidate accounting entries.

        Args:
            units: Direction-filtered source units with optional candidate keys.
            denominator: Provider or reconstructed token total for this field.

        Returns:
            Candidate entries sorted by candidate name and the positive residual
            token count that could not be attributed to known candidates.
        """
        entries: dict[str, dict[str, object]] = {}
        for unit in units:
            candidate = str(unit.get('candidate') or '')
            if not candidate:
                continue
            tokens = _unit_tokens(unit)
            entry = entries.setdefault(
                candidate, {'candidate': candidate, 'tokens': 0, 'percent': 0.0, 'sources': []}
            )
            entry['tokens'] = int(entry['tokens']) + tokens
            sources = entry['sources']
            if isinstance(sources, list):
                sources.append(
                    {
                        'source_id': unit.get('source_id', ''),
                        'origin_path': unit.get('origin_path', ''),
                        'unit_type': unit.get('unit_type', ''),
                        'label': unit.get('label', ''),
                        'tokens': tokens,
                        'preview': unit.get('preview', ''),
                    }
                )
        total = sum(float(entry['tokens']) for entry in entries.values())
        scale = (
            denominator / total if denominator > 0 and total > denominator and total > 0 else 1.0
        )
        result: list[dict] = []
        for entry in entries.values():
            tokens = int(float(entry['tokens']) * scale)
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
        return estimate_tokens_from_text(_stable_payload_text(unit.get('payload')))
    return estimate_tokens_from_text(str(unit.get('preview') or ''))


def _stable_payload_text(payload: object) -> str:
    """Serialize payload content deterministically for local token estimates.

    Args:
        payload: Arbitrary payload captured in a normalized source unit.

    Returns:
        Sorted-key JSON text when possible, otherwise the Python string form.
    """
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(payload)


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
