"""Serialize attribution dataclasses into route payload dictionaries.

Attribution routes call these helpers after request and response builders finish.
Inputs are attribution dataclasses plus optional v2 overlays; outputs are DTO
validated dictionaries for the UI. The module has no I/O side effects.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from session_browser.attribution.contracts import (
    AttributedValue,
    AvailabilityRow,
    LLMRequestAttribution,
    LLMResponseAttribution,
    RequestAttributionBucket,
    ResponseAttributionBucket,
)
from session_browser.attribution.dto import (
    AttributionErrorPayloadDTO,
    LLMRequestAttributionPayloadDTO,
    LLMResponseAttributionPayloadDTO,
)
from session_browser.attribution.taxonomy import (
    normalize_request_bucket_payload,
    sort_request_buckets,
)


def attributed_value_to_dict(v: AttributedValue) -> dict:
    """Serialize one measured attribution value for route payloads.

    DTO builders call this for usage, coverage, and accounting fields.

    Args:
        v: Attribution value carrying units, precision, source, and notes.

    Returns:
        JSON-compatible dictionary preserving all AttributedValue fields.
    """
    return {
        'value': v.value,
        'unit': v.unit,
        'precision': v.precision,
        'source': v.source,
        'fill_strategy': v.fill_strategy,
        'note': v.note,
    }


def _request_bucket_to_dict(b: RequestAttributionBucket) -> dict:
    """Serialize one request-side attribution bucket.

    Request payload assembly calls this before taxonomy normalization and
    display percent recalculation.

    Args:
        b: Request attribution bucket emitted by the request builder.

    Returns:
        JSON-compatible bucket dictionary for route payloads.
    """
    return {
        'key': b.key,
        'label': b.label,
        'tokens': b.tokens,
        'percent': b.percent,
        'count_label': b.count_label,
        'precision': b.precision,
        'source': b.source,
        'confidence_label': b.confidence_label,
        'summary': b.summary,
        'contributes_to_total': b.contributes_to_total,
        'parent_key': b.parent_key,
        'display_group': b.display_group,
        'expandable': b.expandable,
        'content_preview': b.content_preview,
        'details': b.details,
    }


def _response_bucket_to_dict(b: ResponseAttributionBucket) -> dict:
    """Serialize one response-side attribution bucket.

    Response payload assembly calls this before display normalization.

    Args:
        b: Response attribution bucket emitted by the response builder.

    Returns:
        JSON-compatible bucket dictionary for route payloads.
    """
    return {
        'key': b.key,
        'label': b.label,
        'tokens': b.tokens,
        'percent': b.percent,
        'count_label': b.count_label,
        'precision': b.precision,
        'source': b.source,
        'confidence_label': b.confidence_label,
        'summary': b.summary,
        'contributes_to_total': b.contributes_to_total,
        'parent_key': b.parent_key,
        'display_group': b.display_group,
        'block_refs': b.block_refs,
        'details': b.details,
    }


def _num(value: object) -> float:
    """Convert optional numeric payload values for UI calculations.

    Percent and coverage helpers call this on dataclass values and dict fields.
    Invalid values are treated as zero without raising.

    Args:
        value: Raw numeric, string, ``None``, or missing-like value.

    Returns:
        Floating-point value suitable for token arithmetic.
    """
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_bucket_percents_for_display(buckets: list[dict]) -> list[dict]:
    """Normalize bucket percentages for attribution bars and legends.

    Response payload assembly calls this after bucket serialization. It mutates
    the supplied bucket dictionaries to preserve route payload shape.

    Args:
        buckets: Serialized bucket dictionaries with tokens and optional percent
            values.

    Returns:
        The same list with ``raw_percent`` stored and display ``percent`` values
        recalculated for contributing buckets.
    """
    contributing = [b for b in buckets if b.get('contributes_to_total', True)]
    total_tokens = sum(max(_num(b.get('tokens')), 0.0) for b in contributing)
    if total_tokens <= 0:
        for b in buckets:
            b['raw_percent'] = b.get('percent', 0.0)
            if b.get('contributes_to_total', True):
                b['percent'] = 0.0
        return buckets

    running = 0.0
    for idx, b in enumerate(contributing):
        b['raw_percent'] = b.get('percent', 0.0)
        tokens = max(_num(b.get('tokens')), 0.0)
        if idx == len(contributing) - 1:
            percent = max(0.0, 100.0 - running)
        else:
            percent = round((tokens / total_tokens) * 100.0, 1)
            running += percent
        b['percent'] = round(min(percent, 100.0), 1)

    for b in buckets:
        if 'raw_percent' not in b:
            b['raw_percent'] = b.get('percent', 0.0)
    return buckets


def _request_distribution_denominator(attr: LLMRequestAttribution) -> float:
    """Return the request-content denominator used by UI distribution.

    Request serialization calls this for bucket percentages, coverage, and
    residual calculations. Cache read/write are provider accounting components,
    not request-content buckets.

    Args:
        attr: Request attribution dataclass with fresh/cache token values.

    Returns:
        Fresh input tokens when available, otherwise the input-side component
        total.
    """
    fresh = _num(attr.fresh_input.value)
    if fresh > 0:
        return fresh
    return _input_side_component_total(attr)


def _provider_request_input(attr: LLMRequestAttribution) -> float:
    """Infer provider request-input tokens for legacy route fields.

    Request payload builders call this when filling usage summaries. Codex
    counts cache-read tokens in the provider input total; other agents keep
    fresh input only.

    Args:
        attr: Request attribution dataclass with agent and input token values.

    Returns:
        Provider-facing request input token count.
    """
    fresh = _num(attr.fresh_input.value)
    cache_read = _num(attr.cache_read.value)
    if attr.agent == 'codex':
        return fresh + cache_read
    return fresh


def _input_side_component_total(attr: LLMRequestAttribution) -> float:
    """Sum fresh, cache-read, and cache-write input components.

    Coverage and usage serializers call this to expose additive input-side
    accounting without changing source dataclasses.

    Args:
        attr: Request attribution dataclass with input-side component values.

    Returns:
        Total input-side component tokens as a float.
    """
    return _num(attr.fresh_input.value) + _num(attr.cache_read.value) + _num(attr.cache_write.value)


def _input_side_component_value(attr: LLMRequestAttribution) -> dict:
    """Build an AttributedValue-shaped payload for input-side totals.

    Request usage serialization calls this to keep the route schema consistent
    with other measured values.

    Args:
        attr: Request attribution dataclass supplying source and precision.

    Returns:
        Serialized AttributedValue dictionary for the component total.
    """
    return attributed_value_to_dict(
        AttributedValue(
            value=_input_side_component_total(attr),
            unit='tokens',
            precision=attr.fresh_input.precision,
            source=attr.fresh_input.source,
            fill_strategy='Fresh + Cache Read + Cache Write',
            note='Fresh + Cache Read + Cache Write。',
        )
    )


def _normalize_request_bucket_percents_for_display(
    buckets: list[dict],
    denominator: float,
) -> list[dict]:
    """Recalculate request bucket percentages from the display denominator.

    Request payload assembly calls this after taxonomy ordering. The function
    mutates serialized bucket dictionaries in place.

    Args:
        buckets: Serialized request bucket dictionaries.
        denominator: Request-content token denominator used for display.

    Returns:
        The same bucket list with updated ``raw_percent`` and ``percent`` keys.
    """
    for b in buckets:
        b['raw_percent'] = b.get('percent', 0.0)
        if not b.get('contributes_to_total', True):
            continue
        tokens = max(_num(b.get('tokens')), 0.0)
        b['percent'] = round((tokens / denominator) * 100.0, 1) if denominator > 0 else 0.0
    return buckets


def _request_candidate_for_bucket(bucket: dict) -> str | None:
    """Map request bucket metadata to the shared candidate vocabulary.

    Accounting attribution calls this while collapsing legacy buckets into
    field-first candidate entries.

    Args:
        bucket: Serialized request bucket with ``key`` or ``canonical_key``.

    Returns:
        Shared candidate key, or ``None`` when the bucket is unattributed.
    """
    key = str(bucket.get('canonical_key') or bucket.get('key') or '')
    mapping = {
        'current_user_input': 'user_input',
        'user_attachments': 'user_input',
        'conversation_messages': 'conversation_history',
        'tool_result_context': 'tool_results',
        'repository_file_context': 'repo_context',
        'tool_definitions': 'tool_definitions',
        'mcp_tool_metadata': 'tool_definitions',
        'skill_plugin_catalog': 'skill_definitions',
        'instruction_context': 'system_instructions',
        'platform_default_instructions': 'system_instructions',
        'session_injected_instructions': 'system_instructions',
        'project_instruction_files': 'system_instructions',
        'local_instruction_context': 'system_instructions',
        'agent_subagent_prompt': 'system_instructions',
        'custom_agent_profile': 'system_instructions',
        'builtin_system_prompt': 'system_instructions',
        'hidden_instruction_estimate': 'system_instructions',
        'captured_runtime_context': 'runtime_context',
        'permission_sandbox_policy': 'runtime_context',
        'client_app_context': 'runtime_context',
        'collaboration_mode_policy': 'runtime_context',
        'runtime_environment_context': 'runtime_context',
        'task_goal_context': 'runtime_context',
        'provider_conversation_state': 'reasoning_state',
        'reasoning_config': 'reasoning_state',
        'runtime_wrapper_overhead': 'runtime_context',
    }
    return mapping.get(key)


def _response_candidate_for_bucket(bucket: dict) -> str | None:
    """Map response bucket keys to the shared response candidate vocabulary.

    Response accounting attribution calls this while grouping visible text,
    reasoning, tool call, and structured-output buckets.

    Args:
        bucket: Serialized response bucket with a response-side ``key``.

    Returns:
        Shared response candidate key, or ``None`` when no mapping exists.
    """
    key = str(bucket.get('key') or '')
    if key in {'assistant_text', 'visible_text'}:
        return 'assistant_output'
    if key in {'assistant_thinking', 'hidden_reasoning', 'reasoning_output_tokens'}:
        return 'reasoning_output'
    if key in {'tool_call', 'tool_use'} or key.startswith('tool_call:'):
        return 'tool_calls'
    if key in {'structured_response_block', 'structured_items'}:
        return 'structured_output'
    return None


def _candidate_entry(candidate: str) -> dict:
    """Create an empty accounting candidate accumulator.

    Candidate aggregation calls this when a mapped candidate appears for the
    first time in serialized bucket input.

    Args:
        candidate: Shared attribution candidate key.

    Returns:
        Mutable accumulator with zero tokens, zero percent, and source list.
    """
    return {
        'candidate': candidate,
        'tokens': 0,
        'percent': 0.0,
        'sources': [],
    }


def _candidate_sources_from_buckets(
    buckets: list[dict],
    candidate_resolver: Callable[[dict], str | None],
    denominator: float,
) -> tuple[list[dict], int]:
    """Aggregate legacy buckets into shared Attribution Candidate entries.

    Request and response accounting builders call this compatibility layer after
    bucket serialization. It exposes a field-first view without inventing cache
    allocation per candidate.

    Args:
        buckets: Serialized buckets from request or response attribution.
        candidate_resolver: Function mapping each bucket to a shared candidate.
        denominator: Token total used to compute candidate percentages.

    Returns:
        Sorted candidate entries and rounded unattributed token count.
    """
    by_candidate: dict[str, dict] = {}
    unattributed = 0.0
    for bucket in buckets:
        if not bucket.get('contributes_to_total', True):
            continue
        tokens = max(_num(bucket.get('tokens')), 0.0)
        candidate = candidate_resolver(bucket)
        if not candidate:
            unattributed += tokens
            continue
        entry = by_candidate.setdefault(candidate, _candidate_entry(candidate))
        entry['tokens'] += tokens
        entry['sources'].append(
            {
                'bucket_key': bucket.get('key', ''),
                'canonical_key': bucket.get('canonical_key', bucket.get('key', '')),
                'label': bucket.get('label', ''),
                'tokens': tokens,
                'precision': bucket.get('precision', ''),
                'source': bucket.get('source', ''),
                'summary': bucket.get('summary', ''),
            }
        )

    result = []
    for entry in by_candidate.values():
        tokens = round(entry['tokens'])
        entry['tokens'] = tokens
        entry['percent'] = round((tokens / denominator) * 100.0, 1) if denominator > 0 else 0.0
        result.append(entry)
    result.sort(key=lambda item: item['candidate'])
    return result, round(unattributed)


def _accounting_field_payload(
    field: str,
    value: AttributedValue,
    candidates: list[dict] | None = None,
    *,
    unattributed_tokens: int = 0,
    notes: list[str] | None = None,
) -> dict:
    """Build one additive v2 token-accounting field group.

    Request and response accounting serializers call this for each canonical
    accounting field.

    Args:
        field: Canonical token accounting field name.
        value: AttributedValue backing the field total.
        candidates: Candidate entries contributing to this field.
        unattributed_tokens: Tokens not mapped to a shared candidate.
        notes: Explanatory notes for UI display.

    Returns:
        JSON-compatible accounting field payload.
    """
    value_dict = attributed_value_to_dict(value)
    return {
        'field': field,
        'tokens': _num(value.value),
        'value': value_dict,
        'candidates': candidates or [],
        'candidate_total_tokens': sum(_num(item.get('tokens')) for item in (candidates or [])),
        'unattributed_tokens': unattributed_tokens,
        'notes': notes or [],
    }


def _zero_accounting_value(note: str = '') -> AttributedValue:
    """Create a zero-token placeholder for unavailable accounting fields.

    Accounting serializers call this when a request payload lacks response
    fields, or a response payload lacks request fields.

    Args:
        note: Explanation attached to the placeholder value.

    Returns:
        AttributedValue with zero tokens and unavailable precision.
    """
    return AttributedValue(
        value=0,
        unit='tokens',
        precision='unavailable',
        source='heuristic',
        fill_strategy='not applicable',
        note=note,
    )


def _build_request_accounting_attribution(
    attr: LLMRequestAttribution,
    request_buckets: list[dict],
) -> dict:
    """Expose request attribution as TokenAccountingField to candidates.

    Request payload serialization calls this when no v2 accounting overlay is
    supplied by upstream builders.

    Args:
        attr: Request attribution dataclass with usage values.
        request_buckets: Serialized and normalized request buckets.

    Returns:
        Additive accounting-attribution dictionary for request payloads.
    """
    fresh_total = _num(attr.fresh_input.value)
    fresh_candidates, unattributed = _candidate_sources_from_buckets(
        request_buckets,
        _request_candidate_for_bucket,
        fresh_total,
    )
    return {
        'schema': 'token_accounting_fields.v1',
        'field_order': [
            'fresh_input_tokens',
            'cache_read_tokens',
            'cache_write_tokens',
            'output_tokens',
        ],
        'fresh_input_tokens': _accounting_field_payload(
            'fresh_input_tokens',
            attr.fresh_input,
            fresh_candidates,
            unattributed_tokens=unattributed,
            notes=[
                '现有 request buckets 在这里按统一 Attribution Candidates 暴露。',
                '当前本地重建无法提供 candidate-level cache 分配。',
            ],
        ),
        'cache_read_tokens': _accounting_field_payload(
            'cache_read_tokens',
            attr.cache_read,
            [],
            notes=[
                'Provider 上报的 cache read accounting;不推断 per-candidate split。',
            ],
        ),
        'cache_write_tokens': _accounting_field_payload(
            'cache_write_tokens',
            attr.cache_write,
            [],
            notes=[
                'Provider 上报的 cache write accounting 可用时展示;不推断 per-candidate split。',
            ],
        ),
        'output_tokens': _accounting_field_payload(
            'output_tokens',
            _zero_accounting_value(
                'Request attribution payload 不包含 response output allocation。'
            ),
            [],
        ),
    }


def _build_response_accounting_attribution(
    attr: LLMResponseAttribution,
    response_buckets: list[dict],
) -> dict:
    """Expose response attribution as TokenAccountingField to candidates.

    Response payload serialization calls this when no v2 accounting overlay is
    supplied by upstream builders.

    Args:
        attr: Response attribution dataclass with usage values.
        response_buckets: Serialized and normalized response buckets.

    Returns:
        Additive accounting-attribution dictionary for response payloads.
    """
    output_total = _num(attr.total_output.value)
    output_candidates, unattributed = _candidate_sources_from_buckets(
        response_buckets,
        _response_candidate_for_bucket,
        output_total,
    )
    return {
        'schema': 'token_accounting_fields.v1',
        'field_order': [
            'fresh_input_tokens',
            'cache_read_tokens',
            'cache_write_tokens',
            'output_tokens',
        ],
        'fresh_input_tokens': _accounting_field_payload(
            'fresh_input_tokens',
            _zero_accounting_value(
                'Response attribution payload 不包含 request input allocation。'
            ),
            [],
        ),
        'cache_read_tokens': _accounting_field_payload(
            'cache_read_tokens',
            _zero_accounting_value(
                'Response attribution payload 不包含 request cache-read allocation。'
            ),
            [],
        ),
        'cache_write_tokens': _accounting_field_payload(
            'cache_write_tokens',
            _zero_accounting_value(
                'Response attribution payload 不包含 request cache-write allocation。'
            ),
            [],
        ),
        'output_tokens': _accounting_field_payload(
            'output_tokens',
            attr.total_output,
            output_candidates,
            unattributed_tokens=unattributed,
            notes=[
                '现有 response buckets 在这里按统一 response-side Attribution Candidates 暴露。',
            ],
        ),
    }


def availability_row_to_dict(row: AvailabilityRow | dict) -> dict:
    """Serialize an availability row for attribution payloads.

    Request and response serializers call this for each diagnostic availability
    entry. Existing dictionaries are preserved for compatibility.

    Args:
        row: Availability dataclass or an already serialized dictionary.

    Returns:
        JSON-compatible availability-row dictionary.
    """
    if isinstance(row, dict):
        return row
    return asdict(row)


def request_attribution_to_payload(
    attr: LLMRequestAttribution, v2_extra: dict | None = None
) -> dict:
    """Serialize a full request attribution dataclass for the route layer.

    Routes call this after request attribution builders finish. The helper
    preserves legacy route fields while adding v2 schema, identity, coverage,
    diagnostics, and field-first accounting sections.

    Args:
        attr: Complete request attribution dataclass for one LLM call.
        v2_extra: Optional upstream v2 sections that override locally inferred
            identity, spans, buckets, coverage, diagnostics, or accounting.

    Returns:
        DTO-validated request attribution payload dictionary.
    """
    v2_extra = v2_extra or {}

    request_buckets = [
        normalize_request_bucket_payload(attr.agent, _request_bucket_to_dict(b))
        for b in attr.buckets
    ]
    request_buckets = sort_request_buckets(attr.agent, request_buckets)
    request_buckets = _normalize_request_bucket_percents_for_display(
        request_buckets,
        _request_distribution_denominator(attr),
    )
    accounting_attribution = (
        getattr(attr, 'accounting_attribution', None)
        or v2_extra.get('accounting_attribution')
        or _build_request_accounting_attribution(attr, request_buckets)
    )

    payload = {
        # v2 schema.
        'schema_version': 'llm_attribution_v2',
        # Call identity (v2).
        'call_identity': v2_extra.get('call_identity', _build_call_identity(attr)),
        # Usage summary keeps AttributedValue-shaped fields (v2).
        'usage_summary': {
            'provider_request_input': {
                **attributed_value_to_dict(attr.fresh_input),
                'value': _provider_request_input(attr),
                'note': '可推导时的 provider request input 原始计量值。',
            },
            'input_side_component_total': {
                **_input_side_component_value(attr),
                'value': _input_side_component_total(attr),
                'note': 'Fresh + Cache Read + Cache Write。',
            },
            'request_content_denominator': {
                **attributed_value_to_dict(attr.fresh_input),
                'value': _request_distribution_denominator(attr),
                'note': 'request content bucket 覆盖率与残差使用的 Fresh 分母。',
            },
            'fresh': attributed_value_to_dict(attr.fresh_input),
            'cache_read': attributed_value_to_dict(attr.cache_read),
            'cache_write': attributed_value_to_dict(attr.cache_write),
            'output': attributed_value_to_dict(_get_output_from_notes(attr)),
        },
        # Ordered spans (v2).
        'ordered_spans': v2_extra.get('ordered_spans', []),
        # Semantic buckets (v2).
        'semantic_buckets': v2_extra.get('semantic_buckets', []),
        # Coverage (v2).
        'coverage': v2_extra.get('coverage', _build_coverage(attr)),
        # Credit summary (v2, Qoder).
        'credit_summary': v2_extra.get('credit_summary', None),
        # Diagnostics (v2).
        'diagnostics': v2_extra.get('diagnostics', _build_diagnostics(attr)),
        # Field-first attribution (v2 additive).
        'accounting_attribution': accounting_attribution,
        # Route payload fields.
        'kind': 'llm.request_attribution',
        'agent': attr.agent,
        'model': attr.model,
        'request_id': attr.request_id,
        'call_id': attr.call_id,
        'source_label': attr.source_label,
        'confidence_label': attr.confidence_label,
        'raw_body_available': attr.raw_body_available,
        'usage': {
            'provider_request_input': {
                **attributed_value_to_dict(attr.fresh_input),
                'value': _provider_request_input(attr),
                'note': '可推导时的 provider request input 原始计量值。',
            },
            'input_side_component_total': {
                **_input_side_component_value(attr),
                'value': _input_side_component_total(attr),
                'note': 'Fresh + Cache Read + Cache Write。',
            },
            'request_content_denominator': {
                **attributed_value_to_dict(attr.fresh_input),
                'value': _request_distribution_denominator(attr),
                'note': 'request content bucket 覆盖率与残差使用的 Fresh 分母。',
            },
            'fresh': attributed_value_to_dict(attr.fresh_input),
            'cache_read': attributed_value_to_dict(attr.cache_read),
            'cache_write': attributed_value_to_dict(attr.cache_write),
            'coverage': attributed_value_to_dict(attr.coverage),
            'unknown': attributed_value_to_dict(attr.unknown),
        },
        'buckets': request_buckets,
        'captured_context_preview': attr.captured_context_preview,
        'attribution_notes': list(attr.attribution_notes),
        'availability_rows': [availability_row_to_dict(r) for r in attr.availability_rows],
        'timing': {
            'request_at': attr.timing.get('request_at', '—')
            if hasattr(attr, 'timing') and attr.timing
            else '—',
            'response_at': attr.timing.get('response_at', '—')
            if hasattr(attr, 'timing') and attr.timing
            else '—',
            'duration': attr.timing.get('duration', '—')
            if hasattr(attr, 'timing') and attr.timing
            else '—',
        },
    }
    return LLMRequestAttributionPayloadDTO(**payload).to_dict()


def response_attribution_to_payload(
    attr: LLMResponseAttribution, v2_extra: dict | None = None
) -> dict:
    """Serialize a full response attribution dataclass for the route layer.

    Routes call this after response attribution builders finish. The helper
    preserves legacy response fields while adding v2 identity, spans, semantic
    buckets, diagnostics, and field-first accounting sections.

    Args:
        attr: Complete response attribution dataclass for one LLM call.
        v2_extra: Optional upstream v2 sections that override locally inferred
            identity, spans, buckets, diagnostics, or accounting.

    Returns:
        DTO-validated response attribution payload dictionary.
    """
    v2_extra = v2_extra or {}
    response_buckets = _normalize_bucket_percents_for_display(
        [_response_bucket_to_dict(b) for b in attr.buckets]
    )
    accounting_attribution = (
        getattr(attr, 'accounting_attribution', None)
        or v2_extra.get('accounting_attribution')
        or _build_response_accounting_attribution(attr, response_buckets)
    )

    payload = {
        # v2 schema.
        'schema_version': 'llm_attribution_v2',
        # Call identity (v2).
        'call_identity': v2_extra.get('call_identity', _build_call_identity(attr)),
        # Usage summary (v2).
        'usage_summary': {
            'total_output': attributed_value_to_dict(attr.total_output),
            'visible_text': attributed_value_to_dict(attr.visible_text),
            'tool_call': attributed_value_to_dict(attr.tool_use),
            'tool_use': attributed_value_to_dict(attr.tool_use),
            'hidden_reasoning': attributed_value_to_dict(_get_hidden_reasoning(attr)),
            'metadata': attributed_value_to_dict(attr.metadata),
            'residual': attributed_value_to_dict(attr.unknown),
        },
        # Response spans (v2).
        'response_spans': v2_extra.get('response_spans', []),
        # Semantic buckets (v2).
        'semantic_buckets': v2_extra.get('semantic_buckets', []),
        # Diagnostics (v2).
        'diagnostics': v2_extra.get('diagnostics', _build_response_diagnostics(attr)),
        # Field-first attribution (v2 additive).
        'accounting_attribution': accounting_attribution,
        # Route payload fields.
        'kind': 'llm.response_attribution',
        'agent': attr.agent,
        'model': attr.model,
        'request_id': attr.request_id,
        'call_id': attr.call_id,
        'source_label': attr.source_label,
        'confidence_label': attr.confidence_label,
        'raw_body_available': attr.raw_body_available,
        'usage': {
            'total_output': attributed_value_to_dict(attr.total_output),
            'visible_text': attributed_value_to_dict(attr.visible_text),
            'tool_call': attributed_value_to_dict(attr.tool_use),
            'tool_use': attributed_value_to_dict(attr.tool_use),
            'metadata': attributed_value_to_dict(attr.metadata),
            'coverage': attributed_value_to_dict(attr.coverage),
            'unknown': attributed_value_to_dict(attr.unknown),
            'finish_reason': attributed_value_to_dict(attr.finish_reason),
        },
        'buckets': response_buckets,
        'blocks': list(attr.blocks),
        'captured_output_preview': attr.captured_output_preview,
        'attribution_notes': list(attr.attribution_notes),
        'availability_rows': [availability_row_to_dict(r) for r in attr.availability_rows],
    }
    return LLMResponseAttributionPayloadDTO(**payload).to_dict()


# v2 helper functions.


def _build_call_identity(attr: LLMRequestAttribution | LLMResponseAttribution) -> dict:
    """Build the v2 call_identity section from attribution metadata.

    Request and response serializers call this when upstream v2 identity data is
    absent. It performs deterministic inference only and has no side effects.

    Args:
        attr: Request or response attribution dataclass for one LLM call.

    Returns:
        Mapping with runtime, API family, provider, model, billing units, and
        confidence metadata.
    """
    agent_runtime = attr.agent if attr.agent else 'unknown'
    return {
        'agent_runtime': agent_runtime,
        'api_family': _infer_api_family_from_agent(agent_runtime),
        'provider_or_broker': _infer_provider_from_agent(agent_runtime),
        'underlying_provider': None,
        'model': attr.model if attr.model and attr.model != 'unknown' else None,
        'billing_units': ['tokens'] + (['credits'] if agent_runtime == 'qoder' else []),
        'mapping_confidence': 0.5,
        'mapping_reasons': [f'agent={agent_runtime}'],
    }


def _infer_api_family_from_agent(agent: str) -> str:
    """Infer the default API family label for an agent runtime.

    Call-identity construction uses this local mapping when richer provider
    metadata is unavailable.

    Args:
        agent: Agent runtime label from an attribution dataclass.

    Returns:
        API-family label, or ``estimate_only`` for unknown agents.
    """
    mapping = {
        'claude_code': 'anthropic_messages',
        'codex': 'openai_responses',
        'qoder': 'qoder_broker',
    }
    return mapping.get(agent, 'estimate_only')


def _infer_provider_from_agent(agent: str) -> str:
    """Infer the provider or broker label for an agent runtime.

    Call-identity construction uses this local mapping when provider metadata is
    not supplied by upstream attribution builders.

    Args:
        agent: Agent runtime label from an attribution dataclass.

    Returns:
        Provider or broker label, or ``unknown`` for unrecognized agents.
    """
    mapping = {
        'claude_code': 'anthropic',
        'codex': 'openai',
        'qoder': 'qoder',
    }
    return mapping.get(agent, 'unknown')


def _get_output_from_notes(attr: LLMRequestAttribution) -> AttributedValue:
    """Return a request-side placeholder for unavailable output tokens.

    Request usage serialization calls this because request attribution payloads
    do not own response output allocation.

    Args:
        attr: Request attribution dataclass; accepted for signature symmetry with
            future inference hooks.

    Returns:
        Unavailable AttributedValue placeholder for output tokens.
    """
    return AttributedValue(
        value=None,
        unit='tokens',
        precision='unavailable',
        source='heuristic',
        fill_strategy='not available in request',
    )


def _get_hidden_reasoning(attr: LLMResponseAttribution) -> AttributedValue:
    """Return a response-side placeholder for hidden reasoning tokens.

    Response usage serialization calls this when no explicit hidden-reasoning
    bucket is available in the current dataclass.

    Args:
        attr: Response attribution dataclass; accepted for future inference from
            response notes or buckets.

    Returns:
        Unavailable AttributedValue placeholder for hidden reasoning tokens.
    """
    return AttributedValue(
        value=None,
        unit='tokens',
        precision='unavailable',
        source='heuristic',
        fill_strategy='not detected',
    )


def _build_coverage(attr: LLMRequestAttribution) -> dict:
    """Build the v2 request coverage object.

    Request serialization calls this when upstream coverage is absent. It uses
    request-content denominator semantics and local bucket reconstruction totals.

    Args:
        attr: Request attribution dataclass with usage, unknown, and buckets.

    Returns:
        Coverage dictionary with denominator, reconstructed total, ratio,
        residual tokens, and cache-read accounting.
    """
    input_side_component_total = _input_side_component_total(attr)
    cache_read_val = (
        attr.cache_read.value if hasattr(attr, 'cache_read') and attr.cache_read else 0
    ) or 0
    request_content_denominator = _request_distribution_denominator(attr)
    provider_request_input = _provider_request_input(attr)
    unknown_val = (attr.unknown.value if hasattr(attr, 'unknown') and attr.unknown else 0) or 0
    reconstructed = sum(
        max(_num(getattr(bucket, 'tokens', 0)), 0)
        for bucket in getattr(attr, 'buckets', []) or []
        if getattr(bucket, 'contributes_to_total', True)
        and getattr(bucket, 'key', '')
        not in {
            'unknown_overhead',
            'unlocated_residual',
            'unknown',
            'provider_cached_context',
        }
    )
    if reconstructed <= 0 and input_side_component_total > 0:
        reconstructed = max(0, request_content_denominator - unknown_val)
    return {
        'provider_request_input': provider_request_input,
        'input_side_component_total': input_side_component_total,
        'request_content_denominator': request_content_denominator,
        'accounting_cache_read_tokens': cache_read_val,
        'reconstructed_total': int(reconstructed),
        'coverage_ratio': round(reconstructed / request_content_denominator, 3)
        if request_content_denominator > 0
        else 0.0,
        'residual_tokens': unknown_val,
        'residual_likely_sources': [],
    }


def _build_diagnostics(attr: LLMRequestAttribution) -> dict:
    """Build default request diagnostics for v2 payloads.

    Request serialization calls this when no upstream diagnostics are supplied.
    The current default records the contract invariant and no warnings.

    Args:
        attr: Request attribution dataclass for signature symmetry with richer
            diagnostics builders.

    Returns:
        Diagnostics dictionary containing invariants and warnings.
    """
    return {
        'invariants': [{'name': 'current_contract', 'passed': True}],
        'warnings': [],
    }


def _build_response_diagnostics(attr: LLMResponseAttribution) -> dict:
    """Build default response diagnostics for v2 payloads.

    Response serialization calls this when no upstream diagnostics are supplied.
    The current default records output-accounting invariants and no warnings.

    Args:
        attr: Response attribution dataclass for signature symmetry with richer
            diagnostics builders.

    Returns:
        Diagnostics dictionary containing invariants and warnings.
    """
    return {
        'tool_schema_counted_as_output': False,
        'invariants': [{'name': 'current_contract', 'passed': True}],
        'warnings': [],
    }


def attribution_error_to_payload(
    agent: str,
    call_id: str,
    round_id: str,
    error_type: str,
    message: str,
) -> dict:
    """Create a diagnostic route payload when attribution construction fails.

    Routes call this from exception handling around attribution builders. The
    payload intentionally excludes tracebacks to avoid leaking sensitive UI data.

    Args:
        agent: Agent runtime associated with the failed attribution attempt.
        call_id: LLM call identifier for the failed payload.
        round_id: Conversation round identifier used by the UI.
        error_type: Stable error category from the exception handler.
        message: Human-readable failure message safe for route output.

    Returns:
        DTO-validated attribution error payload dictionary.
    """
    return AttributionErrorPayloadDTO(
        kind='llm.attribution_error',
        agent=agent,
        call_id=call_id,
        round_id=round_id,
        error_type=error_type,
        message=message,
        fallback='归因数据不可用;基础 LLM 上下文和输出 payload 仍可查看。',
    ).to_dict()
