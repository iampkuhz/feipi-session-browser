"""Token usage normalizer for session-browser.

Maps provider-specific usage fields into a canonical TokenBreakdown.

Provider mappings:
- Anthropic: input_tokens, cache_read_input_tokens, cache_creation_input_tokens, output_tokens
- OpenAI: prompt_tokens, completion_tokens, prompt_tokens_details.cached_tokens, completion_tokens_details.reasoning_tokens
- qwen-anthropic-compatible: same as Anthropic
- Codex: tokens_used (total only, no breakdown)

Rules:
1. Missing fields are None, not 0.
2. Cache read is input-side, not output-side.
3. Estimated breakdowns (from content blocks) never override provider-reported usage.
4. No double counting: cache_read is separate from input_fresh.
"""

from __future__ import annotations

from typing import Optional

from session_browser.domain.models import TokenBreakdown, TokenPrecision, TokenProvider


def normalize_tokens(
    usage: dict,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> TokenBreakdown:
    """Normalize provider usage fields into TokenBreakdown.

    Args:
        usage: Raw usage dict from the provider.
        provider: Provider hint ("anthropic", "openai", "codex", "qwen-anthropic-compatible", "qoder").
        model: Model string for provider inference.

    Returns:
        TokenBreakdown with canonical fields.
    """
    if not usage or not isinstance(usage, dict):
        # Qoder with no usage is still "estimated" (not real data missing)
        if provider == TokenProvider.QODER:
            return TokenBreakdown(precision=TokenPrecision.ESTIMATED, provider=TokenProvider.QODER)
        return TokenBreakdown(precision=TokenPrecision.UNKNOWN)

    # Infer provider if not specified
    if provider is None:
        provider = _infer_provider(model)

    if provider == TokenProvider.ANTHROPIC or provider == TokenProvider.QWEN_ANTHROPIC_COMPATIBLE:
        return _normalize_anthropic(usage, provider)
    elif provider == TokenProvider.OPENAI:
        return _normalize_openai(usage)
    elif provider == TokenProvider.CODEX:
        return _normalize_codex(usage)
    elif provider == TokenProvider.QODER:
        return _normalize_qoder(usage)

    # Unknown provider — try generic extraction
    return _normalize_generic(usage)


def _infer_provider(model: Optional[str]) -> str:
    """Infer provider from model string."""
    if model is None:
        return TokenProvider.UNKNOWN

    model_lower = model.lower()

    # Qwen models via Anthropic-compatible API
    if "qwen" in model_lower:
        return TokenProvider.QWEN_ANTHROPIC_COMPATIBLE

    # Anthropic models
    if "claude" in model_lower:
        return TokenProvider.ANTHROPIC

    # OpenAI models
    if any(x in model_lower for x in ["gpt-", "o1", "o3", "davinci", "curie", "babbage", "ada"]):
        return TokenProvider.OPENAI

    return TokenProvider.UNKNOWN


def _normalize_anthropic(usage: dict, provider: str) -> TokenBreakdown:
    """Normalize Anthropic (or Anthropic-compatible) usage.

    Fields:
    - input_tokens: fresh input tokens
    - cache_read_input_tokens: tokens read from input cache
    - cache_creation_input_tokens: tokens written to input cache
    - output_tokens: output tokens
    """
    input_tokens = _get_or_none(usage, "input_tokens")
    cache_read = _get_or_none(usage, "cache_read_input_tokens")
    cache_write = _get_or_none(usage, "cache_creation_input_tokens")
    output_tokens = _get_or_none(usage, "output_tokens")

    breakdown = TokenBreakdown(
        input_fresh=input_tokens,
        input_cache_read=cache_read,
        input_cache_write=cache_write,
        output_visible=output_tokens,
        precision=TokenPrecision.PROVIDER_REPORTED,
        provider=provider,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )

    breakdown.compute_totals()
    return breakdown


def _normalize_openai(usage: dict) -> TokenBreakdown:
    """Normalize OpenAI usage.

    Fields:
    - prompt_tokens: total input tokens (includes cached)
    - completion_tokens: total output tokens (includes reasoning)
    - prompt_tokens_details.cached_tokens: cached input tokens
    - completion_tokens_details.reasoning_tokens: reasoning output tokens

    Or newer format:
    - input_tokens / output_tokens
    - input_tokens_details.cached_tokens
    - output_tokens_details.reasoning_tokens
    """
    # Try new format first
    input_tokens = _get_or_none(usage, "input_tokens")
    output_tokens = _get_or_none(usage, "output_tokens")
    prompt_tokens = _get_or_none(usage, "prompt_tokens")
    completion_tokens = _get_or_none(usage, "completion_tokens")

    if input_tokens is None:
        input_tokens = prompt_tokens
    if output_tokens is None:
        output_tokens = completion_tokens

    # Cached tokens
    cached = _get_nested_or_none(usage, "input_tokens_details", "cached_tokens")
    if cached is None:
        cached = _get_nested_or_none(usage, "prompt_tokens_details", "cached_tokens")

    # Reasoning tokens
    reasoning = _get_nested_or_none(usage, "output_tokens_details", "reasoning_tokens")
    if reasoning is None:
        reasoning = _get_nested_or_none(usage, "completion_tokens_details", "reasoning_tokens")

    # Calculate fresh input = input_tokens - cached_tokens
    input_fresh = None
    if input_tokens is not None and cached is not None:
        input_fresh = input_tokens - cached
    elif input_tokens is not None:
        input_fresh = input_tokens

    # Calculate visible output = output_tokens - reasoning_tokens
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


def _normalize_codex(usage: dict) -> TokenBreakdown:
    """Normalize Codex usage.

    Codex typically only reports total tokens_used.
    No breakdown available.
    """
    tokens_used = _get_or_none(usage, "tokens_used")
    if tokens_used is None:
        tokens_used = _get_or_none(usage, "total_tokens")

    precision = TokenPrecision.PROVIDER_REPORTED if tokens_used is not None else TokenPrecision.ESTIMATED

    return TokenBreakdown(
        total_input=tokens_used,
        precision=precision,
        provider=TokenProvider.CODEX,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )


def _normalize_qoder(usage: dict) -> TokenBreakdown:
    """Normalize Qoder usage.

    Qoder does not report real usage; token counts are local estimates
    computed via byte-length heuristic. All cache fields are 0.
    Precision is always ESTIMATED.
    """
    input_tokens = _get_or_none(usage, "input_tokens")
    output_tokens = _get_or_none(usage, "output_tokens")
    cache_read = _get_or_none(usage, "cache_read_input_tokens")
    cache_write = _get_or_none(usage, "cache_creation_input_tokens")

    breakdown = TokenBreakdown(
        input_fresh=input_tokens,
        input_cache_read=cache_read,
        input_cache_write=cache_write,
        output_visible=output_tokens,
        precision=TokenPrecision.ESTIMATED,
        provider=TokenProvider.QODER,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )
    breakdown.compute_totals()
    return breakdown


def _normalize_generic(usage: dict) -> TokenBreakdown:
    """Generic extraction for unknown providers.

    Try to extract common field names.
    """
    input_tokens = _get_or_none(usage, "input_tokens")
    output_tokens = _get_or_none(usage, "output_tokens")
    cache_read = _get_or_none(usage, "cache_read_input_tokens")
    cache_write = _get_or_none(usage, "cache_creation_input_tokens")
    cached = _get_or_none(usage, "cached_tokens")
    reasoning = _get_or_none(usage, "reasoning_tokens")
    prompt_tokens = _get_or_none(usage, "prompt_tokens")
    completion_tokens = _get_or_none(usage, "completion_tokens")
    total_tokens = _get_or_none(usage, "total_tokens")

    if input_tokens is None:
        input_tokens = prompt_tokens

    breakdown = TokenBreakdown(
        input_fresh=input_tokens,
        input_cache_read=cache_read or cached,
        input_cache_write=cache_write,
        output_visible=output_tokens or completion_tokens,
        output_reasoning=reasoning,
        precision=TokenPrecision.ESTIMATED,
        provider=TokenProvider.UNKNOWN,
        raw_fields={k: v for k, v in usage.items() if isinstance(v, (int, float))},
    )

    breakdown.compute_totals()
    return breakdown


# ─── Helpers ───────────────────────────────────────────────────────────────


def _get_or_none(d: dict, key: str) -> Optional[int]:
    """Get an int from dict, return None if missing or 0."""
    val = d.get(key)
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _get_nested_or_none(d: dict, outer_key: str, inner_key: str) -> Optional[int]:
    """Get a nested value from dict, return None if any level is missing."""
    outer = d.get(outer_key)
    if outer is None or not isinstance(outer, dict):
        return None
    val = outer.get(inner_key)
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


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
    }
    return labels.get(precision, "unknown")


def precision_color(precision: str) -> str:
    """Return a CSS color for precision level."""
    colors = {
        TokenPrecision.EXACT: "#10b981",
        TokenPrecision.PROVIDER_REPORTED: "#3b82f6",
        TokenPrecision.ESTIMATED: "#f59e0b",
        TokenPrecision.UNKNOWN: "#6b7280",
    }
    return colors.get(precision, "#6b7280")
