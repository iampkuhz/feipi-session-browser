"""Infer provider hints from captured model strings.

These helpers run when a mapping resolver has a model name but weak or missing usage
payload evidence. They never choose an API family alone; they only return provider and
reasoning-model hints that can raise confidence for later resolver decisions.
"""

from __future__ import annotations

import re


def detect_model_family(model_string: str) -> dict[str, str]:
    """Infer provider and normalized model hints from a model string.

    Args:
        model_string: Raw model string captured from request, response, or metadata.

    Returns:
        Dictionary with ``provider_hint`` set to ``anthropic``, ``openai``, ``qoder``,
        or ``unknown``, and ``model_hint`` preserving the usable model value.
    """
    if not model_string:
        return {'provider_hint': 'unknown', 'model_hint': ''}

    s = model_string.lower()

    if 'claude' in s:
        return {'provider_hint': 'anthropic', 'model_hint': model_string}

    if 'gpt' in s or 'o1' in s or 'o3' in s or 'o4' in s:
        return {'provider_hint': 'openai', 'model_hint': model_string}

    if 'performance' in s or 'standard' in s or 'qoder' in s:
        return {'provider_hint': 'qoder', 'model_hint': model_string}

    return {'provider_hint': 'unknown', 'model_hint': model_string}


def is_reasoning_model(model_string: str) -> bool:
    """Return whether a model string may include hidden reasoning tokens.

    Args:
        model_string: Raw model string captured for a call.

    Returns:
        ``True`` for known OpenAI reasoning prefixes or Claude Sonnet/Opus families.
    """
    if not model_string:
        return False
    s = model_string.lower()
    return bool(re.search(r'^(o1|o3|o4|claude.*sonnet|claude.*opus)', s))
