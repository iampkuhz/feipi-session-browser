"""Fallback token counters based on local character estimates.

These counters run when provider exact usage, provider count APIs, and local tokenizers
are unavailable. They accept plain text or serialized request and response payloads and
return non-negative estimated token counts for attribution buckets.
"""

from __future__ import annotations

import json

_CHARS_PER_TOKEN = 4


def estimate_tokens_heuristic(text: str) -> int:
    """Estimate token count from text length.

    Args:
        text: Request, response, or bucket text to estimate.

    Returns:
        Non-negative token estimate using roughly four characters per token.
    """
    if not text:
        return 0
    return max(0, len(text) // _CHARS_PER_TOKEN)


def estimate_tokens_from_object(obj: object) -> int:
    """Estimate token count from text or structured payload data.

    Args:
        obj: Text, dict, list, or scalar payload captured for a call segment.

    Returns:
        Non-negative heuristic token estimate after stable JSON or string conversion.
    """
    if isinstance(obj, str):
        return estimate_tokens_heuristic(obj)
    if isinstance(obj, (dict, list)):
        text = json.dumps(obj, ensure_ascii=False)
        return estimate_tokens_heuristic(text)
    return estimate_tokens_heuristic(str(obj))
