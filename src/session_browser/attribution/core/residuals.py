"""Compute residual token gaps between provider totals and reconstructed spans."""

from __future__ import annotations

from typing import Any


def compute_residual(
    *,
    provider_total: int = 0,
    reconstructed_total: int = 0,
    likely_sources: list[str] | None = None,
) -> dict[str, Any]:
    """Compute residual tokens and explain likely missing sources.

    Attribution normalizers call this when provider totals exceed locally reconstructed
    prompt spans. The result becomes an unknown residual bucket or diagnostic note.

    Args:
        provider_total: Provider or broker reported total input tokens.
        reconstructed_total: Sum of locally reconstructed span tokens.
        likely_sources: Optional source labels that may explain the residual.

    Returns:
        Dictionary with residual token count, likely source labels, and a note.
    """
    if provider_total <= 0:
        return {
            'residual_tokens': 0,
            'likely_sources': likely_sources or [],
            'note': 'No provider total is available; residual cannot be computed.',
        }

    residual = max(0, provider_total - reconstructed_total)

    default_sources = [
        'hidden system prompt',
        'tokenizer overhead',
        'provider wrapper overhead',
    ]
    sources = likely_sources or default_sources

    if residual == 0:
        note = 'Local reconstruction covers all provider tokens.'
    elif residual < provider_total * 0.1:
        percent = residual / provider_total * 100
        note = f'Residual {residual} tokens ({percent:.1f}%) is within the expected range.'
    else:
        percent = residual / provider_total * 100
        note = f'Residual {residual} tokens ({percent:.1f}%) may come from: {", ".join(sources)}'

    return {
        'residual_tokens': residual,
        'likely_sources': sources,
        'note': note,
    }
