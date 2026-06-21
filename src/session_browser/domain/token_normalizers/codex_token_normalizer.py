"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from typing import Any

from session_browser.domain.models import (
    NormalizedTokenBreakdown,
    TokenPrecision,
    TokenSourceKind,
    TokenTotalSemantics,
)

CODEX_USAGE_FIELDS = (
    'input_tokens',
    'cached_input_tokens',
    'output_tokens',
    'reasoning_output_tokens',
    'total_tokens',
)


def int_or_zero(value: Any) -> int:
    """int_or_zero function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        value: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def nested_int(d: dict, outer: str, inner: str) -> int:
    """nested_int function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        d: Input value supplied by the caller for this pipeline step.
        outer: Input value supplied by the caller for this pipeline step.
        inner: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    child = d.get(outer)
    if isinstance(child, dict):
        return int_or_zero(child.get(inner))
    return 0


def extract_codex_usage(raw: dict) -> dict:
    """extract_codex_usage function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        raw: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not isinstance(raw, dict):
        return {}

    candidates: list[tuple[dict, str]] = []
    candidates.append((raw, 'direct'))
    if isinstance(raw.get('usage'), dict):
        candidates.append((raw['usage'], 'usage'))
    if isinstance(raw.get('response'), dict) and isinstance(raw['response'].get('usage'), dict):
        candidates.append((raw['response']['usage'], 'response.usage'))
    if isinstance(raw.get('data'), dict) and isinstance(raw['data'].get('usage'), dict):
        candidates.append((raw['data']['usage'], 'data.usage'))

    payload = raw.get('payload')
    if isinstance(payload, dict):
        if isinstance(payload.get('usage'), dict):
            candidates.append((payload['usage'], 'payload.usage'))
        info = payload.get('info')
        if isinstance(info, dict):
            if isinstance(info.get('last_token_usage'), dict):
                candidates.append((info['last_token_usage'], 'payload.info.last_token_usage'))
            if isinstance(info.get('total_token_usage'), dict):
                candidates.append((info['total_token_usage'], 'payload.info.total_token_usage'))

    for usage, source in candidates:
        if not isinstance(usage, dict):
            continue
        has_any = any(
            k in usage
            for k in (
                'input_tokens',
                'prompt_tokens',
                'output_tokens',
                'completion_tokens',
                'cached_input_tokens',
                'cache_read_input_tokens',
                'cached_tokens',
                'total_tokens',
                'total_token_usage',
                'tokens_used',
                'input_tokens_details',
                'output_tokens_details',
                'prompt_tokens_details',
                'completion_tokens_details',
            )
        )
        if not has_any:
            continue
        input_tokens = int_or_zero(usage.get('input_tokens') or usage.get('prompt_tokens'))
        cached = (
            int_or_zero(usage.get('cached_input_tokens'))
            or int_or_zero(usage.get('cache_read_input_tokens'))
            or int_or_zero(usage.get('cached_tokens'))
            or nested_int(usage, 'input_tokens_details', 'cached_tokens')
            or nested_int(usage, 'prompt_tokens_details', 'cached_tokens')
        )
        output_tokens = int_or_zero(usage.get('output_tokens') or usage.get('completion_tokens'))
        reasoning = (
            int_or_zero(usage.get('reasoning_output_tokens'))
            or int_or_zero(usage.get('reasoning_tokens'))
            or int_or_zero(usage.get('thinking_tokens'))
            or nested_int(usage, 'output_tokens_details', 'reasoning_tokens')
            or nested_int(usage, 'completion_tokens_details', 'reasoning_tokens')
        )
        total = (
            int_or_zero(usage.get('total_tokens'))
            or int_or_zero(usage.get('total_token_usage'))
            or int_or_zero(usage.get('tokens_used'))
        )
        result = {
            'input_tokens': input_tokens,
            'cached_input_tokens': min(cached, input_tokens) if input_tokens else cached,
            'output_tokens': output_tokens if output_tokens else reasoning,
            'reasoning_output_tokens': reasoning,
            'total_tokens': total,
            '_usage_source': source,
        }
        if 'total_token_usage' in source:
            result['_is_cumulative'] = True
        return result
    return {}


def normalize_codex_usage(usage: dict) -> NormalizedTokenBreakdown:
    """normalize_codex_usage function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        usage: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    extracted = extract_codex_usage(usage) or (usage if isinstance(usage, dict) else {})
    raw_input_total = int_or_zero(extracted.get('input_tokens'))
    raw_cache_read = int_or_zero(extracted.get('cached_input_tokens'))
    raw_output = int_or_zero(extracted.get('output_tokens'))
    raw_total = int_or_zero(extracted.get('total_tokens'))
    raw_reasoning = int_or_zero(extracted.get('reasoning_output_tokens'))

    cache_read = min(raw_cache_read, raw_input_total) if raw_input_total else raw_cache_read
    fresh = max(raw_input_total - cache_read, 0) if raw_input_total else 0
    cache_write = 0

    output = raw_output
    if output == 0 and raw_reasoning > 0:
        output = raw_reasoning

    component_sum = fresh + cache_read + cache_write + output
    total = component_sum
    semantics = TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM
    notes: list[str] = []

    if component_sum == 0 and raw_total > 0:
        total = raw_total
        semantics = TokenTotalSemantics.REPORTED_TOTAL
    elif raw_total > 0 and component_sum != raw_total:
        notes.append(
            f'provider total ({raw_total}) 与四字段合计 ({component_sum}) 不一致;'
            '展示层使用互斥 accounting fields 合计.'
        )
        semantics = TokenTotalSemantics.RECOMPUTED_DUE_TO_INCONSISTENT_RAW_TOTAL

    return NormalizedTokenBreakdown(
        fresh_input_tokens=fresh,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        output_tokens=output,
        total_tokens=total,
        precision=TokenPrecision.PROVIDER_REPORTED,
        total_semantics=semantics,
        source_kind=TokenSourceKind.CODEX_ROLLOUT_TOKEN_COUNT,
        raw_fields={k: v for k, v in extracted.items() if isinstance(v, (int, float))},
        notes=notes,
    )


def codex_usage_delta(current: dict, previous: dict | None = None) -> dict:
    """codex_usage_delta function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        current: Input value supplied by the caller for this pipeline step.
        previous: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    current_usage = extract_codex_usage(current) or (current if isinstance(current, dict) else {})
    previous_usage = extract_codex_usage(previous) if isinstance(previous, dict) else {}
    return {
        field: int_or_zero(current_usage.get(field)) - int_or_zero(previous_usage.get(field))
        for field in CODEX_USAGE_FIELDS
    }


def codex_is_duplicate_cumulative(current: dict, previous: dict | None) -> bool:
    """codex_is_duplicate_cumulative function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        current: Input value supplied by the caller for this pipeline step.
        previous: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not isinstance(previous, dict):
        return False
    delta = codex_usage_delta(current, previous)
    return all(delta[field] == 0 for field in CODEX_USAGE_FIELDS)


def normalize_codex_from_delta(
    current: dict,
    previous: dict | None = None,
) -> NormalizedTokenBreakdown:
    """normalize_codex_from_delta function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        current: Input value supplied by the caller for this pipeline step.
        previous: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if previous and isinstance(previous, dict):
        delta = {
            field: max(value, 0) for field, value in codex_usage_delta(current, previous).items()
        }
        result = normalize_codex_usage(delta)
        result.precision = TokenPrecision.PROVIDER_REPORTED_DELTA
        result.total_semantics = TokenTotalSemantics.REPORTED_CUMULATIVE_DELTA
        return result
    return normalize_codex_usage(current)
