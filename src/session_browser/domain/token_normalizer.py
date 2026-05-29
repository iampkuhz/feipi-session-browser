"""Token usage normalizer for session-browser.

Maps provider-specific usage fields into a canonical TokenBreakdown (legacy)
and NormalizedTokenBreakdown (unified 5-field breakdown).

Provider mappings:
- Claude Code: input_tokens=fresh, cache_read/cache_creation=separate buckets, total=sum of 4
- Codex: input_tokens is inclusive total, cached_input_tokens is subset, total != sum
- Qoder: structured logs / SQLite / transcript estimation with inclusive input handling

Rules:
1. Every session/LLM call gets 5 int fields: fresh_input, cache_read, cache_write, output, total.
2. No null/undefined/NaN — all fields default to 0.
3. Direct fields take priority; aliases are normalized.
4. Inclusive inputs are decomposed: fresh = raw_input - cache_read - cache_write.
5. Metadata records precision, source_kind, total_semantics, and notes.
"""

from __future__ import annotations

import math
from typing import Optional

from session_browser.domain.models import (
    TokenBreakdown,
    NormalizedTokenBreakdown,
    TokenPrecision,
    TokenProvider,
    TokenTotalSemantics,
    TokenSourceKind,
)


# ─── Legacy: TokenBreakdown normalizer (backward compat) ─────────────────


def normalize_tokens(
    usage: dict,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> TokenBreakdown:
    """Normalize provider usage fields into TokenBreakdown (legacy).

    Args:
        usage: Raw usage dict from the provider.
        provider: Provider hint ("anthropic", "openai", "codex", "qwen-anthropic-compatible", "qoder").
        model: Model string for provider inference.

    Returns:
        TokenBreakdown with canonical fields.
    """
    if not usage or not isinstance(usage, dict):
        if provider == TokenProvider.QODER:
            return TokenBreakdown(precision=TokenPrecision.ESTIMATED, provider=TokenProvider.QODER)
        return TokenBreakdown(precision=TokenPrecision.UNKNOWN)

    if provider is None:
        provider = _infer_provider(model)

    if provider == TokenProvider.ANTHROPIC or provider == TokenProvider.QWEN_ANTHROPIC_COMPATIBLE:
        result = _normalize_anthropic(usage, provider)
    elif provider == TokenProvider.OPENAI:
        result = _normalize_openai(usage)
    elif provider == TokenProvider.CODEX:
        result = _normalize_codex_legacy(usage)
    elif provider == TokenProvider.QODER:
        result = _normalize_qoder_legacy(usage)
    else:
        result = _normalize_generic(usage)

    result.compute_totals()
    return result


# ─── New: Unified NormalizedTokenBreakdown normalizer ────────────────────


def normalize_tokens_unified(
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
        return _normalize_claude_code_unified(usage)
    elif provider == TokenProvider.CODEX:
        return _normalize_codex_unified(usage)
    elif provider == TokenProvider.QODER:
        return _normalize_qoder_unified(usage)
    elif provider == TokenProvider.OPENAI:
        return _normalize_openai_unified(usage)

    return _normalize_generic_unified(usage)


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


def _normalize_claude_code_unified(usage: dict) -> NormalizedTokenBreakdown:
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


def _normalize_codex_unified(usage: dict) -> NormalizedTokenBreakdown:
    """Codex: input_tokens is inclusive total; cached_input_tokens is a subset.

    fresh = raw_input_total - cache_read
    total = raw_total if > 0 else raw_input_total + output
    Cache Write always 0.
    """
    raw_input_total = _get_int(usage, "input_tokens", "prompt_tokens", "input")
    raw_cache_read = _get_int(usage, "cached_input_tokens", "cache_read_input_tokens", "cached_tokens")
    raw_output = _get_int(usage, "output_tokens", "completion_tokens", "output")
    raw_total = _get_int(usage, "total_tokens", "total_token_usage", "tokens_used")
    raw_reasoning = _get_int(usage, "reasoning_output_tokens", "reasoning_tokens", "thinking_tokens")

    cache_read = min(raw_cache_read, raw_input_total)
    fresh = max(raw_input_total - cache_read, 0)
    cache_write = 0
    output = raw_output

    if raw_total > 0:
        total = raw_total
    else:
        total = raw_input_total + output

    # Consistency check: if component sum != reported total
    component_sum = fresh + cache_read + cache_write + output
    semantics = TokenTotalSemantics.REPORTED_CUMULATIVE_DELTA if raw_total == 0 else TokenTotalSemantics.REPORTED_TOTAL
    notes: list[str] = []

    if raw_total > 0 and component_sum != raw_total:
        # Use reported total but note the inconsistency
        notes.append(
            f"Component sum ({component_sum}) differs from reported total ({raw_total}); "
            f"using reported total."
        )

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


def _normalize_codex_unified_from_delta(
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

        result = _normalize_codex_unified(delta)
        result.precision = TokenPrecision.PROVIDER_REPORTED_DELTA
        result.total_semantics = TokenTotalSemantics.REPORTED_CUMULATIVE_DELTA
        return result

    return _normalize_codex_unified(current)


# ─── Qoder unified normalizer ────────────────────────────────────────────


def _normalize_qoder_unified(usage: dict) -> NormalizedTokenBreakdown:
    """Qoder structured logs: input_tokens is often inclusive total.

    fresh = raw_input - cache_read - cache_write (if raw_input >= cache_read + cache_write)
    total = fresh + cache_read + cache_write + output
    """
    raw_input = _get_int(usage, "input_tokens", "prompt_tokens")
    raw_cache_read = _get_int(usage, "cache_read_input_tokens", "cache_read_tokens", "cached_tokens")
    raw_cache_write = _get_int(usage, "cache_creation_input_tokens", "cache_write_input_tokens", "cache_write_tokens")
    raw_output = _get_int(usage, "output_tokens", "completion_tokens")
    raw_thinking = _get_int(usage, "thinking_tokens", "reasoning_tokens", "reasoning_output_tokens")
    raw_total = _get_int(usage, "total_tokens", "total_token_usage")

    cache_read = raw_cache_read
    cache_write = raw_cache_write

    if raw_input >= raw_cache_read + raw_cache_write:
        fresh = raw_input - raw_cache_read - raw_cache_write
        precision = TokenPrecision.PROVIDER_REPORTED_NORMALIZED
    else:
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
    """Qoder SQLite token_info: prompt_tokens includes cached_tokens.

    fresh = prompt_tokens - cached_tokens
    total = prompt_tokens + completion_tokens
    """
    raw_prompt = _get_int(token_info, "prompt_tokens")
    raw_cached = _get_int(token_info, "cached_tokens")
    raw_completion = _get_int(token_info, "completion_tokens")

    cache_read = min(raw_cached, raw_prompt)
    fresh = max(raw_prompt - cache_read, 0)
    cache_write = 0
    output = raw_completion
    total = raw_prompt + raw_completion

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
            "Qoder SQLite prompt_tokens includes cached_tokens; Fresh Input is prompt_tokens - cached_tokens.",
            "Cache Write unavailable in Qoder SQLite; zero-filled.",
        ],
    )


def _normalize_qoder_unified_with_text(
    usage: dict,
    assistant_text: str = "",
    request_text: str = "",
) -> NormalizedTokenBreakdown:
    """Qoder fallback: use text estimation for missing fields."""
    bd = _normalize_qoder_unified(usage)

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


def _normalize_openai_unified(usage: dict) -> NormalizedTokenBreakdown:
    """OpenAI: prompt_tokens is inclusive; cached_tokens is a subset."""
    input_tokens = _get_int(usage, "input_tokens") or _get_int(usage, "prompt_tokens")
    output_tokens = _get_int(usage, "output_tokens") or _get_int(usage, "completion_tokens")

    cached = (_get_nested_int(usage, "input_tokens_details", "cached_tokens")
              or _get_nested_int(usage, "prompt_tokens_details", "cached_tokens"))
    reasoning = (_get_nested_int(usage, "output_tokens_details", "reasoning_tokens")
                 or _get_nested_int(usage, "completion_tokens_details", "reasoning_tokens"))

    fresh = input_tokens - cached if cached > 0 else input_tokens
    if fresh < 0:
        fresh = 0

    cache_write = 0
    total = input_tokens + output_tokens

    return NormalizedTokenBreakdown(
        fresh_input_tokens=fresh,
        cache_read_tokens=cached,
        cache_write_tokens=cache_write,
        output_tokens=output_tokens,
        total_tokens=total,
        precision=TokenPrecision.PROVIDER_REPORTED,
        total_semantics=TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
        source_kind=TokenSourceKind.CLAUDE_CODE_JSONL_USAGE,  # reuse; not OpenAI-specific yet
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )


# ─── Generic unified normalizer ──────────────────────────────────────────


def _normalize_generic_unified(usage: dict) -> NormalizedTokenBreakdown:
    """Generic fallback for unknown providers."""
    total_only = _get_int(usage, "total_tokens", "total_token_usage", "tokens_used")

    # Extract breakdown fields
    raw_input = _get_int(usage, "input_tokens", "prompt_tokens", "input")
    raw_cache_read = _get_int(usage, "cache_read_input_tokens", "cached_input_tokens", "cache_read_tokens", "cached_tokens")
    raw_cache_write = _get_int(usage, "cache_creation_input_tokens", "cache_write_input_tokens", "cache_write_tokens")
    raw_output = _get_int(usage, "output_tokens", "completion_tokens", "output")

    if raw_input or raw_cache_read or raw_cache_write or raw_output:
        # Has some breakdown — compute from components
        fresh = max(raw_input - raw_cache_read - raw_cache_write, 0)
        total = total_only if total_only > 0 else (fresh + raw_cache_read + raw_cache_write + raw_output)
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


# ─── Legacy normalizers (kept for backward compat) ───────────────────────


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


def _normalize_anthropic(usage: dict, provider: str) -> TokenBreakdown:
    """Normalize Anthropic (or Anthropic-compatible) usage."""
    input_tokens = _get_int(usage, "input_tokens")
    cache_read = _get_int(usage, "cache_read_input_tokens")
    cache_write = _get_int(usage, "cache_creation_input_tokens")
    output_tokens = _get_int(usage, "output_tokens")

    # Only use None for fields that are truly absent (not explicitly 0)
    has_cache_read = "cache_read_input_tokens" in usage
    has_cache_write = "cache_creation_input_tokens" in usage
    has_output = "output_tokens" in usage

    breakdown = TokenBreakdown(
        input_fresh=input_tokens,
        input_cache_read=cache_read if has_cache_read else None,
        input_cache_write=cache_write if has_cache_write else None,
        output_visible=output_tokens if has_output else None,
        precision=TokenPrecision.PROVIDER_REPORTED,
        provider=provider,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )

    breakdown.compute_totals()
    return breakdown


def _normalize_openai(usage: dict) -> TokenBreakdown:
    """Normalize OpenAI usage."""
    input_tokens = _get_int(usage, "input_tokens") or _get_int(usage, "prompt_tokens") or None
    output_tokens = _get_int(usage, "output_tokens") or _get_int(usage, "completion_tokens") or None

    cached = _get_int(usage, "cached_tokens") or None
    if cached is None:
        cached = _get_nested_int(usage, "input_tokens_details", "cached_tokens") or None
        if cached is None:
            cached = _get_nested_int(usage, "prompt_tokens_details", "cached_tokens") or None

    reasoning = _get_int(usage, "reasoning_tokens") or None
    if reasoning is None:
        reasoning = _get_nested_int(usage, "output_tokens_details", "reasoning_tokens") or None
        if reasoning is None:
            reasoning = _get_nested_int(usage, "completion_tokens_details", "reasoning_tokens") or None

    input_fresh = None
    if input_tokens is not None and cached is not None:
        input_fresh = input_tokens - cached
    elif input_tokens is not None:
        input_fresh = input_tokens

    output_visible = None
    if output_tokens is not None and reasoning is not None:
        output_visible = output_tokens - reasoning
    elif output_tokens is not None:
        output_visible = output_tokens

    breakdown = TokenBreakdown(
        input_fresh=input_fresh,
        input_cache_read=cached,
        output_visible=output_visible,
        output_reasoning=reasoning,
        precision=TokenPrecision.PROVIDER_REPORTED,
        provider=TokenProvider.OPENAI,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )

    breakdown.compute_totals()
    return breakdown


def _normalize_codex_legacy(usage: dict) -> TokenBreakdown:
    """Codex usage — legacy, typically only total."""
    tokens_used = _get_int_or_none(usage, "tokens_used", "total_tokens")
    precision = TokenPrecision.PROVIDER_REPORTED if tokens_used is not None else TokenPrecision.ESTIMATED

    return TokenBreakdown(
        total_input=tokens_used,
        precision=precision,
        provider=TokenProvider.CODEX,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )


def _normalize_qoder_legacy(usage: dict) -> TokenBreakdown:
    """Qoder usage — legacy, estimated."""
    input_tokens = _get_int_or_none(usage, "input_tokens")
    output_tokens = _get_int_or_none(usage, "output_tokens")
    cache_read = _get_int_or_none(usage, "cache_read_input_tokens")
    cache_write = _get_int_or_none(usage, "cache_creation_input_tokens")

    return TokenBreakdown(
        input_fresh=input_tokens,
        input_cache_read=cache_read,
        input_cache_write=cache_write,
        output_visible=output_tokens,
        precision=TokenPrecision.ESTIMATED,
        provider=TokenProvider.QODER,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )


def _normalize_generic(usage: dict) -> TokenBreakdown:
    """Generic extraction for unknown providers."""
    input_tokens = _get_int_or_none(usage, "input_tokens", "prompt_tokens")
    output_tokens = _get_int_or_none(usage, "output_tokens", "completion_tokens")
    cache_read = _get_int_or_none(usage, "cache_read_input_tokens", "cached_tokens")
    cache_write = _get_int_or_none(usage, "cache_creation_input_tokens")
    reasoning = _get_int_or_none(usage, "reasoning_tokens")

    breakdown = TokenBreakdown(
        input_fresh=input_tokens,
        input_cache_read=cache_read,
        input_cache_write=cache_write,
        output_visible=output_tokens,
        output_reasoning=reasoning,
        precision=TokenPrecision.ESTIMATED,
        provider=TokenProvider.UNKNOWN,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )

    breakdown.compute_totals()
    return breakdown


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
