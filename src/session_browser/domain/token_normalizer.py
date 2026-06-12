"""Token usage normalizer for session-browser.

Maps provider-specific usage fields into a unified NormalizedTokenBreakdown
with a canonical 5-field breakdown.

Provider mappings:
- Claude Code: input_tokens=fresh request input, cache_read/cache_creation=separate buckets
- Codex/OpenAI: input_tokens is request input; cached_input_tokens is a subset
- Qoder: input_tokens is request input; cache read/write stay separate when reported

Rules:
1. Every session/LLM call gets 5 int fields: fresh_input, cache_read, cache_write, output, total.
2. No null/undefined/NaN — all fields default to 0.
3. Direct fields take priority; aliases are normalized.
4. Fresh input means the logical request input size. Do not subtract cache buckets.
5. Metadata records precision, source_kind, total_semantics, and notes.
"""

from __future__ import annotations

import math
from typing import Optional

from session_browser.domain.models import (
    NormalizedTokenBreakdown,
    TokenPrecision,
    TokenProvider,
    TokenTotalSemantics,
    TokenSourceKind,
)


# ─── Provider inference ──────────────────────────────────────────────────


def _infer_provider(model: Optional[str]) -> str:
    """Infer provider from model string."""
    if model is None:
        return TokenProvider.UNKNOWN

    model_lower = model.lower()

    if "qwen" in model_lower:
        return TokenProvider.QWEN_ANTHROPIC_COMPATIBLE

    if "claude" in model_lower:
        return TokenProvider.ANTHROPIC

    if any(x in model_lower for x in ["gpt-", "o1", "o3", "davinci", "curie", "babbage", "ada"]):
        return TokenProvider.OPENAI

    return TokenProvider.UNKNOWN


# ─── Alias extraction helpers ────────────────────────────────────────────


def normalize_tokens(
    usage: dict,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> NormalizedTokenBreakdown:
    """Normalize provider usage into a unified 5-field breakdown.

    Every return has all 5 int fields set (never None/NaN).
    """
    if not usage or not isinstance(usage, dict):
        if provider == TokenProvider.QODER:
            return NormalizedTokenBreakdown(
                precision=TokenPrecision.ESTIMATED,
                source_kind=TokenSourceKind.QODER_TRANSCRIPT_ESTIMATED,
                notes=["No usage data; zero-filled."],
            )
        return NormalizedTokenBreakdown(
            precision=TokenPrecision.UNKNOWN,
            source_kind=TokenSourceKind.UNKNOWN,
            notes=["No usage data; zero-filled."],
        )

    if provider is None:
        provider = _infer_provider(model)

    if provider in (TokenProvider.ANTHROPIC, TokenProvider.QWEN_ANTHROPIC_COMPATIBLE):
        return _normalize_claude_code(usage)
    elif provider == TokenProvider.CODEX:
        return _normalize_codex(usage)
    elif provider == TokenProvider.QODER:
        return _normalize_qoder(usage)
    elif provider == TokenProvider.OPENAI:
        return _normalize_openai(usage)

    return _normalize_generic(usage)


# ─── Alias extraction helpers ────────────────────────────────────────────


def _get_int(d: dict, *keys: str) -> int:
    """Return the first int found among keys; 0 if none."""
    for k in keys:
        val = d.get(k)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return 0


def _get_int_or_none(d: dict, *keys: str) -> Optional[int]:
    """Return the first int found among keys; None if none."""
    for k in keys:
        val = d.get(k)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None


def _get_nested_int(d: dict, outer: str, inner: str) -> int:
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
    """Estimate tokens from text using ceil(utf8_byte_len / 3.5)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text.encode("utf-8")) / 3.5))


# ─── Claude Code unified normalizer ──────────────────────────────────────


def _normalize_claude_code(usage: dict) -> NormalizedTokenBreakdown:
    """Claude Code: input_tokens = fresh; cache buckets are separate.

    total = fresh + cache_read + cache_write + output (exclusive_components_sum).
    """
    fresh = _get_int(usage, "input_tokens")
    cache_read = _get_int(usage, "cache_read_input_tokens")
    cache_write = _get_int(usage, "cache_creation_input_tokens")
    output = _get_int(usage, "output_tokens")
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


# ─── Codex unified normalizer ────────────────────────────────────────────


def _normalize_codex(usage: dict) -> NormalizedTokenBreakdown:
    """Codex: input_tokens is the logical request input size.

    Supports both flat Codex aliases and OpenAI Responses nested aliases.
    OpenAI/Codex cached input is a subset of input_tokens, so UI token
    composition uses mutually exclusive components: Fresh = input - cache read.
    Cache Write always 0.
    """
    raw_input_total = _get_int(usage, "input_tokens", "prompt_tokens", "input")
    raw_cache_read = (
        _get_int(usage, "cached_input_tokens", "cache_read_input_tokens", "cached_tokens")
        or _get_nested_int(usage, "input_tokens_details", "cached_tokens")
        or _get_nested_int(usage, "prompt_tokens_details", "cached_tokens")
    )
    raw_output = _get_int(usage, "output_tokens", "completion_tokens", "output")
    raw_total = _get_int(usage, "total_tokens", "total_token_usage", "tokens_used")
    raw_reasoning = (
        _get_int(usage, "reasoning_output_tokens", "reasoning_tokens", "thinking_tokens")
        or _get_nested_int(usage, "output_tokens_details", "reasoning_tokens")
        or _get_nested_int(usage, "completion_tokens_details", "reasoning_tokens")
    )

    cache_read = min(raw_cache_read, raw_input_total) if raw_input_total else raw_cache_read
    fresh = max(raw_input_total - cache_read, 0) if raw_input_total else 0
    cache_write = 0

    # If only reasoning tokens and no output tokens, use reasoning as output fallback
    output = raw_output
    if raw_output == 0 and raw_reasoning > 0:
        output = raw_reasoning

    component_sum = fresh + cache_read + cache_write + output
    total = component_sum
    semantics = TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM
    notes: list[str] = []

    if component_sum == 0 and raw_total > 0:
        total = raw_total
        semantics = TokenTotalSemantics.REPORTED_TOTAL

    if component_sum > 0 and raw_total > 0 and component_sum != raw_total:
        notes.append(
            f"Raw reported total ({raw_total}) differs from component sum ({component_sum}); "
            "using mutually exclusive component sum for UI token composition."
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
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
        notes=notes,
    )


def _normalize_codex_from_delta(
    current: dict,
    previous: Optional[dict] = None,
) -> NormalizedTokenBreakdown:
    """Codex: recover delta from cumulative totals.

    If previous cumulative is provided, subtract to get delta,
    then normalize the delta normally.
    """
    if previous and isinstance(previous, dict):
        delta = {}
        for key in ("input_tokens", "prompt_tokens", "cached_input_tokens",
                     "cache_read_input_tokens", "cached_tokens",
                     "output_tokens", "completion_tokens",
                     "total_tokens", "total_token_usage", "tokens_used"):
            cur_val = _get_int(current, key)
            prev_val = _get_int(previous, key)
            delta[key] = max(cur_val - prev_val, 0)

        result = _normalize_codex(delta)
        result.precision = TokenPrecision.PROVIDER_REPORTED_DELTA
        result.total_semantics = TokenTotalSemantics.REPORTED_CUMULATIVE_DELTA
        return result

    return _normalize_codex(current)


# ─── Qoder unified normalizer ────────────────────────────────────────────


def _normalize_qoder(usage: dict) -> NormalizedTokenBreakdown:
    """Qoder structured logs: input_tokens is the logical request input size.

    Fresh must remain the request input size. Cache read/write fields are
    reported separately and are not subtracted from Fresh.
    """
    raw_input = _get_int(usage, "input_tokens", "prompt_tokens")
    raw_cache_read = _get_int(usage, "cache_read_input_tokens", "cache_read_tokens", "cached_tokens")
    raw_cache_write = _get_int(usage, "cache_creation_input_tokens", "cache_write_input_tokens", "cache_write_tokens")
    raw_output = _get_int(usage, "output_tokens", "completion_tokens")
    raw_thinking = _get_int(usage, "thinking_tokens", "reasoning_tokens", "reasoning_output_tokens")
    raw_total = _get_int(usage, "total_tokens", "total_token_usage")

    cache_read = raw_cache_read
    cache_write = raw_cache_write

    fresh = raw_input
    precision = TokenPrecision.PROVIDER_REPORTED

    # Output: include thinking tokens unless it would bloat the total
    output = raw_output
    if raw_thinking > 0:
        if raw_total > 0 and (raw_output + raw_thinking) > raw_total:
            # Don't double-add thinking; keep in raw_fields only
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
    """Qoder SQLite token_info: prompt_tokens is the request input size.

    cached_tokens is tracked separately as cache read. UI total is the component
    sum so the tokenbar uses the same semantics as JSONL-derived Qoder usage.
    """
    raw_prompt = _get_int(token_info, "prompt_tokens")
    raw_cached = _get_int(token_info, "cached_tokens")
    raw_completion = _get_int(token_info, "completion_tokens")

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
            "Qoder SQLite prompt_tokens is used as Fresh request input size.",
            "Cache Write unavailable in Qoder SQLite; zero-filled.",
        ],
    )


def _normalize_qoder_with_text(
    usage: dict,
    assistant_text: str = "",
    request_text: str = "",
) -> NormalizedTokenBreakdown:
    """Qoder fallback: use text estimation for missing fields."""
    bd = _normalize_qoder(usage)

    # Fill output from text if missing
    if bd.output_tokens == 0 and assistant_text:
        bd.output_tokens = _estimate_tokens(assistant_text)
        bd.precision = TokenPrecision.ESTIMATED_PARTIAL
        bd.total_tokens = bd.fresh_input_tokens + bd.cache_read_tokens + bd.cache_write_tokens + bd.output_tokens
        bd.notes.append("Output estimated from assistant text.")

    # Fill input from text if missing
    if bd.fresh_input_tokens == 0 and request_text:
        bd.fresh_input_tokens = _estimate_tokens(request_text)
        bd.cache_read_tokens = 0
        bd.cache_write_tokens = 0
        bd.precision = TokenPrecision.ESTIMATED_PARTIAL
        bd.total_tokens = bd.fresh_input_tokens + bd.cache_read_tokens + bd.cache_write_tokens + bd.output_tokens
        bd.notes.append("Fresh Input estimated from request text.")

    return bd


# ─── OpenAI unified normalizer ───────────────────────────────────────────


def _normalize_openai(usage: dict) -> NormalizedTokenBreakdown:
    """OpenAI: cached input is a subset of prompt/input tokens."""
    input_tokens = _get_int(usage, "input_tokens") or _get_int(usage, "prompt_tokens")
    output_tokens = _get_int(usage, "output_tokens") or _get_int(usage, "completion_tokens")

    cached = (_get_nested_int(usage, "input_tokens_details", "cached_tokens")
              or _get_nested_int(usage, "prompt_tokens_details", "cached_tokens"))
    reasoning = (_get_nested_int(usage, "output_tokens_details", "reasoning_tokens")
                 or _get_nested_int(usage, "completion_tokens_details", "reasoning_tokens"))

    cached = min(cached, input_tokens) if input_tokens else cached
    fresh = max(input_tokens - cached, 0) if input_tokens else 0

    cache_write = 0
    total = fresh + cached + cache_write + output_tokens

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
    )


# ─── Generic unified normalizer ──────────────────────────────────────────


def _normalize_generic(usage: dict) -> NormalizedTokenBreakdown:
    """Generic fallback for unknown providers."""
    total_only = _get_int(usage, "total_tokens", "total_token_usage", "tokens_used")

    # Extract breakdown fields
    raw_input = _get_int(usage, "input_tokens", "prompt_tokens", "input")
    raw_cache_read = _get_int(usage, "cache_read_input_tokens", "cached_input_tokens", "cache_read_tokens", "cached_tokens")
    raw_cache_write = _get_int(usage, "cache_creation_input_tokens", "cache_write_input_tokens", "cache_write_tokens")
    raw_output = _get_int(usage, "output_tokens", "completion_tokens", "output")

    if raw_input or raw_cache_read or raw_cache_write or raw_output:
        # Has some breakdown — compute from components
        fresh = raw_input
        total = fresh + raw_cache_read + raw_cache_write + raw_output
        notes = []
        if total_only > 0 and total_only != total:
            notes.append(
                f"Raw reported total ({total_only}) differs from component sum ({total}); "
                "using component sum for UI token composition."
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
        # Total-only fallback
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
            notes=["Only total token value is available; assigned to Fresh Input as fallback."],
        )

    return NormalizedTokenBreakdown(
        precision=TokenPrecision.UNKNOWN,
        source_kind=TokenSourceKind.UNKNOWN,
        notes=["No token source available."],
    )


# ─── Helpers ───────────────────────────────────────────────────────────────


def format_tokens(n: Optional[int]) -> str:
    """Format token count for display. Unknown/None returns '—'."""
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def precision_label(precision: str) -> str:
    """Return a human-readable precision label."""
    labels = {
        TokenPrecision.EXACT: "exact",
        TokenPrecision.PROVIDER_REPORTED: "provider-reported",
        TokenPrecision.ESTIMATED: "estimated",
        TokenPrecision.UNKNOWN: "unknown",
        TokenPrecision.PROVIDER_REPORTED_NORMALIZED: "provider-reported (normalized)",
        TokenPrecision.PROVIDER_REPORTED_DELTA: "provider-reported (delta)",
        TokenPrecision.SQLITE_TOKEN_INFO: "SQLite token_info",
        TokenPrecision.ESTIMATED_PARTIAL: "estimated (partial)",
        TokenPrecision.REPORTED_TOTAL_ONLY: "reported total only",
    }
    return labels.get(precision, "unknown")


def precision_color(precision: str) -> str:
    """Return a CSS color for precision level."""
    colors = {
        TokenPrecision.EXACT: "#10b981",
        TokenPrecision.PROVIDER_REPORTED: "#3b82f6",
        TokenPrecision.ESTIMATED: "#f59e0b",
        TokenPrecision.UNKNOWN: "#6b7280",
        TokenPrecision.PROVIDER_REPORTED_NORMALIZED: "#3b82f6",
        TokenPrecision.PROVIDER_REPORTED_DELTA: "#60a5fa",
        TokenPrecision.SQLITE_TOKEN_INFO: "#8b5cf6",
        TokenPrecision.ESTIMATED_PARTIAL: "#f59e0b",
        TokenPrecision.REPORTED_TOTAL_ONLY: "#9ca3af",
    }
    return colors.get(precision, "#6b7280")
