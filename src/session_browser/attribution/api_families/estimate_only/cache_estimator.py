"""Estimate cache boundaries when provider usage is unavailable.

This API-family helper is triggered for estimate-only attribution paths where
no provider or broker usage payload can confirm cache behavior. It deliberately
returns unavailable cache buckets instead of inventing cache reads or writes from
local prompt spans, keeping normalized usage boundaries explicit.
"""

from __future__ import annotations


def estimate_cache_tokens(
    *,
    total_input: int = 0,
    has_prior_context: bool = False,
) -> dict[str, str | None]:
    """Estimate cache token buckets for a locally reconstructed request.

    Args:
        total_input: Reconstructed input token total from prompt spans. The
            value is accepted for API-family symmetry but does not prove cache
            behavior.
        has_prior_context: Whether the local request appears to include prior
            context. This can explain cache possibility but not provider cache
            accounting.

    Returns:
        A mapping with ``cache_read`` and ``cache_write`` set to ``None``, plus
        unavailable precision and an explanatory note. The boundary is explicit:
        local reconstruction cannot emit normalized cache buckets.
    """
    return {
        'cache_read': None,
        'cache_write': None,
        'precision': 'unavailable',
        'note': '本地无法确认 provider cache 行为',
    }
