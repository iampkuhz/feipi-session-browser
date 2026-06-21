"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

import math

from session_browser.domain.models import (
    NormalizedTokenBreakdown,
    TokenPrecision,
    TokenProvider,
    TokenSourceKind,
    TokenTotalSemantics,
)
from session_browser.domain.token_normalizers.codex_token_normalizer import (
    normalize_codex_from_delta,
    normalize_codex_usage,
)

# 说明:─── Provider inference ──────────────────────────────────────────────────


def _infer_provider(model: str | None) -> str:
    """_infer_provider function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        model: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if model is None:
        return TokenProvider.UNKNOWN

    model_lower = model.lower()

    if 'qwen' in model_lower:
        return TokenProvider.QWEN_ANTHROPIC_COMPATIBLE

    if 'claude' in model_lower:
        return TokenProvider.ANTHROPIC

    if any(x in model_lower for x in ['gpt-', 'o1', 'o3', 'davinci', 'curie', 'babbage', 'ada']):
        return TokenProvider.OPENAI

    return TokenProvider.UNKNOWN


# 说明:─── Alias extraction helpers ────────────────────────────────────────────


def normalize_tokens(
    usage: dict,
    provider: str | None = None,
    model: str | None = None,
) -> NormalizedTokenBreakdown:
    """normalize_tokens function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        usage: Input value supplied by the caller for this pipeline step.
        provider: Input value supplied by the caller for this pipeline step.
        model: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not usage or not isinstance(usage, dict):
        if provider == TokenProvider.QODER:
            return NormalizedTokenBreakdown(
                precision=TokenPrecision.ESTIMATED,
                source_kind=TokenSourceKind.QODER_TRANSCRIPT_ESTIMATED,
                notes=['No usage data; zero-filled.'],
            )
        return NormalizedTokenBreakdown(
            precision=TokenPrecision.UNKNOWN,
            source_kind=TokenSourceKind.UNKNOWN,
            notes=['No usage data; zero-filled.'],
        )

    if provider is None:
        provider = _infer_provider(model)

    if provider in (TokenProvider.ANTHROPIC, TokenProvider.QWEN_ANTHROPIC_COMPATIBLE):
        return _normalize_claude_code(usage)
    if provider == TokenProvider.CODEX:
        return _normalize_codex(usage)
    if provider == TokenProvider.QODER:
        return _normalize_qoder(usage)
    if provider == TokenProvider.OPENAI:
        return _normalize_openai(usage)

    return _normalize_generic(usage)


# 说明:─── Alias extraction helpers ────────────────────────────────────────────


def _get_int(d: dict, *keys: str) -> int:
    """_get_int function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        d: Input value supplied by the caller for this pipeline step.
        *keys: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    for k in keys:
        val = d.get(k)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return 0


def _get_int_or_none(d: dict, *keys: str) -> int | None:
    """_get_int_or_none function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        d: Input value supplied by the caller for this pipeline step.
        *keys: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    for k in keys:
        val = d.get(k)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None


def _get_nested_int(d: dict, outer: str, inner: str) -> int:
    """_get_nested_int function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        d: Input value supplied by the caller for this pipeline step.
        outer: Input value supplied by the caller for this pipeline step.
        inner: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    outer_d = d.get(outer)
    if isinstance(outer_d, dict):
        val = outer_d.get(inner)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return 0


def _estimate_tokens(text: str) -> int:
    """_estimate_tokens function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        text: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text.encode('utf-8')) / 3.5))


# 说明:─── Claude Code unified normalizer ──────────────────────────────────────


def _normalize_claude_code(usage: dict) -> NormalizedTokenBreakdown:
    """_normalize_claude_code function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        usage: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    fresh = _get_int(usage, 'input_tokens')
    cache_read = _get_int(usage, 'cache_read_input_tokens')
    cache_write = _get_int(usage, 'cache_creation_input_tokens')
    output = _get_int(usage, 'output_tokens')
    total = fresh + cache_read + cache_write + output

    return NormalizedTokenBreakdown(
        fresh_input_tokens=fresh,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        output_tokens=output,
        total_tokens=total,
        precision=TokenPrecision.PROVIDER_REPORTED,
        total_semantics=TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
        source_kind=TokenSourceKind.CLAUDE_CODE_JSONL_USAGE,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )


# 说明:─── Codex unified normalizer ────────────────────────────────────────────


def _normalize_codex(usage: dict) -> NormalizedTokenBreakdown:
    """_normalize_codex function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        usage: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return normalize_codex_usage(usage)


def _normalize_codex_from_delta(
    current: dict,
    previous: dict | None = None,
) -> NormalizedTokenBreakdown:
    """_normalize_codex_from_delta function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        current: Input value supplied by the caller for this pipeline step.
        previous: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return normalize_codex_from_delta(current, previous)


# 说明:─── Qoder unified normalizer ────────────────────────────────────────────


def _normalize_qoder(usage: dict) -> NormalizedTokenBreakdown:
    """_normalize_qoder function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        usage: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    raw_input = _get_int(usage, 'input_tokens', 'prompt_tokens')
    raw_cache_read = _get_int(
        usage, 'cache_read_input_tokens', 'cache_read_tokens', 'cached_tokens'
    )
    raw_cache_write = _get_int(
        usage, 'cache_creation_input_tokens', 'cache_write_input_tokens', 'cache_write_tokens'
    )
    raw_output = _get_int(usage, 'output_tokens', 'completion_tokens')
    raw_thinking = _get_int(usage, 'thinking_tokens', 'reasoning_tokens', 'reasoning_output_tokens')
    raw_total = _get_int(usage, 'total_tokens', 'total_token_usage')

    cache_read = raw_cache_read
    cache_write = raw_cache_write

    fresh = raw_input
    precision = TokenPrecision.PROVIDER_REPORTED

    # Output: include thinking tokens unless it would bloat 该 total
    output = raw_output
    if raw_thinking > 0:
        if raw_total > 0 and (raw_output + raw_thinking) > raw_total:
            # 说明:Don't double-add thinking; keep in raw_fields only
            pass
        else:
            output = raw_output + raw_thinking

    total = fresh + cache_read + cache_write + output

    return NormalizedTokenBreakdown(
        fresh_input_tokens=fresh,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        output_tokens=output,
        total_tokens=total,
        precision=precision,
        total_semantics=TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
        source_kind=TokenSourceKind.QODER_SEGMENT_MODEL_RESPONSE_COMPLETED,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )


def normalize_qoder_sqlite_unified(token_info: dict) -> NormalizedTokenBreakdown:
    """normalize_qoder_sqlite_unified function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        token_info: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    raw_prompt = _get_int(token_info, 'prompt_tokens')
    raw_cached = _get_int(token_info, 'cached_tokens')
    raw_completion = _get_int(token_info, 'completion_tokens')

    cache_read = min(raw_cached, raw_prompt)
    fresh = raw_prompt
    cache_write = 0
    output = raw_completion
    total = fresh + cache_read + cache_write + output

    return NormalizedTokenBreakdown(
        fresh_input_tokens=fresh,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        output_tokens=output,
        total_tokens=total,
        precision=TokenPrecision.SQLITE_TOKEN_INFO,
        total_semantics=TokenTotalSemantics.PROMPT_TOTAL_PLUS_OUTPUT,
        source_kind=TokenSourceKind.QODER_SQLITE_TOKEN_INFO,
        raw_fields={k: v for k, v in token_info.items() if isinstance(v, (int, float))},
        notes=[
            'Qoder SQLite prompt_tokens is used as Fresh request input size.',
            'Cache Write unavailable in Qoder SQLite; zero-filled.',
        ],
    )


def _normalize_qoder_with_text(
    usage: dict,
    assistant_text: str = '',
    request_text: str = '',
) -> NormalizedTokenBreakdown:
    """_normalize_qoder_with_text function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        usage: Input value supplied by the caller for this pipeline step.
        assistant_text: Input value supplied by the caller for this pipeline step.
        request_text: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    bd = _normalize_qoder(usage)

    # Fill output,来源于 text,如果 missing
    if bd.output_tokens == 0 and assistant_text:
        bd.output_tokens = _estimate_tokens(assistant_text)
        bd.precision = TokenPrecision.ESTIMATED_PARTIAL
        bd.total_tokens = (
            bd.fresh_input_tokens + bd.cache_read_tokens + bd.cache_write_tokens + bd.output_tokens
        )
        bd.notes.append('Output estimated from assistant text.')

    # Fill input,来源于 text,如果 missing
    if bd.fresh_input_tokens == 0 and request_text:
        bd.fresh_input_tokens = _estimate_tokens(request_text)
        bd.cache_read_tokens = 0
        bd.cache_write_tokens = 0
        bd.precision = TokenPrecision.ESTIMATED_PARTIAL
        bd.total_tokens = (
            bd.fresh_input_tokens + bd.cache_read_tokens + bd.cache_write_tokens + bd.output_tokens
        )
        bd.notes.append('Fresh Input estimated from request text.')

    return bd


# 说明:─── OpenAI unified normalizer ───────────────────────────────────────────


def _normalize_openai(usage: dict) -> NormalizedTokenBreakdown:
    """_normalize_openai function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        usage: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    input_tokens = _get_int(usage, 'input_tokens') or _get_int(usage, 'prompt_tokens')
    provider_output_total = _get_int(usage, 'output_tokens') or _get_int(usage, 'completion_tokens')

    cached = _get_nested_int(usage, 'input_tokens_details', 'cached_tokens') or _get_nested_int(
        usage, 'prompt_tokens_details', 'cached_tokens'
    )
    reasoning = _get_nested_int(
        usage, 'output_tokens_details', 'reasoning_tokens'
    ) or _get_nested_int(usage, 'completion_tokens_details', 'reasoning_tokens')

    cached = min(cached, input_tokens) if input_tokens else cached
    fresh = max(input_tokens - cached, 0) if input_tokens else 0

    output_tokens = provider_output_total

    cache_write = 0
    total = fresh + cached + cache_write + output_tokens
    notes: list[str] = []
    if reasoning > 0:
        notes.append(
            'Hidden reasoning tokens are retained as an output breakdown; '
            'Output keeps the provider reported output_tokens total.'
        )

    return NormalizedTokenBreakdown(
        fresh_input_tokens=fresh,
        cache_read_tokens=cached,
        cache_write_tokens=cache_write,
        output_tokens=output_tokens,
        total_tokens=total,
        precision=TokenPrecision.PROVIDER_REPORTED,
        total_semantics=TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
        source_kind=TokenSourceKind.OPENAI_RESPONSES_USAGE,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
        notes=notes,
    )


# 说明:─── Generic unified normalizer ──────────────────────────────────────────


def _normalize_generic(usage: dict) -> NormalizedTokenBreakdown:
    """_normalize_generic function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        usage: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    total_only = _get_int(usage, 'total_tokens', 'total_token_usage', 'tokens_used')

    # 提取 breakdown fields
    raw_input = _get_int(usage, 'input_tokens', 'prompt_tokens', 'input')
    raw_cache_read = _get_int(
        usage,
        'cache_read_input_tokens',
        'cached_input_tokens',
        'cache_read_tokens',
        'cached_tokens',
    )
    raw_cache_write = _get_int(
        usage, 'cache_creation_input_tokens', 'cache_write_input_tokens', 'cache_write_tokens'
    )
    raw_output = _get_int(usage, 'output_tokens', 'completion_tokens', 'output')

    if raw_input or raw_cache_read or raw_cache_write or raw_output:
        # Has some breakdown — compute,来源于 components
        fresh = raw_input
        total = fresh + raw_cache_read + raw_cache_write + raw_output
        notes = []
        if total_only > 0 and total_only != total:
            notes.append(
                f'Raw reported total ({total_only}) differs from component sum ({total}); '
                'using component sum for UI token composition.'
            )
        return NormalizedTokenBreakdown(
            fresh_input_tokens=fresh,
            cache_read_tokens=raw_cache_read,
            cache_write_tokens=raw_cache_write,
            output_tokens=raw_output,
            total_tokens=total,
            precision=TokenPrecision.ESTIMATED,
            total_semantics=TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
            source_kind=TokenSourceKind.UNKNOWN,
            raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
            notes=notes,
        )

    if total_only > 0:
        # 说明:Total-only fallback
        return NormalizedTokenBreakdown(
            fresh_input_tokens=total_only,
            cache_read_tokens=0,
            cache_write_tokens=0,
            output_tokens=0,
            total_tokens=total_only,
            precision=TokenPrecision.REPORTED_TOTAL_ONLY,
            total_semantics=TokenTotalSemantics.REPORTED_TOTAL,
            source_kind=TokenSourceKind.SESSION_TOTAL_ONLY_FALLBACK,
            raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
            notes=['Only total token value is available; assigned to Fresh Input as fallback.'],
        )

    return NormalizedTokenBreakdown(
        precision=TokenPrecision.UNKNOWN,
        source_kind=TokenSourceKind.UNKNOWN,
        notes=['No token source available.'],
    )


# 说明:─── Helpers ───────────────────────────────────────────────────────────────


def format_tokens(n: int | None) -> str:
    """format_tokens function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        n: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if n is None:
        return '—'
    if n >= 1_000_000:
        return f'{n / 1_000_000:.1f}M'
    if n >= 1_000:
        return f'{n / 1_000:.1f}K'
    return str(n)


def precision_label(precision: str) -> str:
    """precision_label function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        precision: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    labels = {
        TokenPrecision.EXACT: 'exact',
        TokenPrecision.PROVIDER_REPORTED: 'provider_reported',
        TokenPrecision.ESTIMATED: 'estimated',
        TokenPrecision.UNKNOWN: 'unavailable',
        TokenPrecision.ZERO_FILLED_UNAVAILABLE: 'unavailable',
    }
    return labels.get(precision, 'unavailable')


def precision_color(precision: str) -> str:
    """precision_color function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        precision: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    colors = {
        TokenPrecision.EXACT: '#10b981',
        TokenPrecision.PROVIDER_REPORTED: '#3b82f6',
        TokenPrecision.ESTIMATED: '#f59e0b',
        TokenPrecision.UNKNOWN: '#6b7280',
        TokenPrecision.ZERO_FILLED_UNAVAILABLE: '#6b7280',
    }
    return colors.get(precision, '#6b7280')
