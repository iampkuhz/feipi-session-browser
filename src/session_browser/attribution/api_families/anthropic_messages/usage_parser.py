"""Parse Anthropic Messages provider usage into normalized boundaries.

This API-family parser is triggered when an Anthropic Messages response exposes
a provider ``usage`` payload. Anthropic reports cache reads, cache creation, and
fresh input separately: ``cache_read_input_tokens``,
``cache_creation_input_tokens``, and ``input_tokens``. The parser converts those
fields into attribution token buckets and leaves cache ordering to the allocator.
"""

from __future__ import annotations

from session_browser.attribution.core.models import UsageBreakdown
from session_browser.attribution.mapping.usage_shape_detector import get_nested_int


def parse_anthropic_usage(usage: dict | None) -> UsageBreakdown:
    """Parse an Anthropic usage dictionary into ``UsageBreakdown``.

    Args:
        usage: Provider usage payload containing Anthropic token fields such as
            ``input_tokens``, ``cache_read_input_tokens``,
            ``cache_creation_input_tokens``, and ``output_tokens``.

    Returns:
        A ``UsageBreakdown`` with ``total_input``, ``fresh_input``,
        ``cache_read``, ``cache_write``, and ``output`` populated from provider
        usage. Missing or non-dictionary input returns an unavailable breakdown.
    """
    if not usage or not isinstance(usage, dict):
        return UsageBreakdown(
            usage_source='unavailable',
            precision='unavailable',
            note='无 Anthropic usage 数据',
        )

    cache_read = get_nested_int(usage, 'cache_read_input_tokens')
    cache_write = get_nested_int(usage, 'cache_creation_input_tokens')
    fresh = get_nested_int(usage, 'input_tokens')
    output = get_nested_int(usage, 'output_tokens')
    total_input = cache_read + cache_write + fresh

    reported_total = get_nested_int(usage, 'total_tokens')
    if reported_total > 0 and reported_total != total_input:
        note = (
            f'Anthropic total_input 计算值={total_input}, '
            f'provider total_tokens={reported_total} (可能含 overhead)'
        )
    else:
        note = '来自 Anthropic usage 字段'

    return UsageBreakdown(
        total_input=total_input,
        fresh_input=fresh,
        cache_read=cache_read,
        cache_write=cache_write,
        output=output,
        usage_source='provider_reported',
        precision='provider_reported',
        note=note,
    )
