"""Define the canonical Anthropic Messages request order.

Anthropic cache prefixes are built from request content in this order: tools,
system prompts, then message content blocks. The priority helpers are triggered
while creating ordered prompt spans, before provider usage parsing or cache
allocation maps usage payload totals onto normalized token buckets.
"""

from __future__ import annotations


def get_anthropic_request_order() -> list[str]:
    """Return the canonical Anthropic Messages request stages.

    Returns:
        Ordered stage labels used to build ``PromptSpan`` offsets for cache
        allocation and normalized usage attribution.
    """
    return [
        'tools',
        'system',
        'messages',
    ]


def get_anthropic_order_priority(kind: str) -> int:
    """Return the sort priority for an Anthropic semantic span kind.

    Args:
        kind: Semantic prompt-span kind, such as ``tool_schema``,
            ``system_prompt``, or message block kinds.

    Returns:
        Numeric priority where lower values sort earlier in the request. Unknown
        kinds return ``999`` so they remain after recognized Anthropic stages.
    """
    order = get_anthropic_request_order()
    kind_to_label = {
        'tool_schema': 'tools',
        'system_prompt': 'system',
        'user_text': 'messages',
        'tool_result': 'messages',
        'assistant_text': 'messages',
        'tool_use': 'messages',
    }
    label = kind_to_label.get(kind, '')
    if label in order:
        return order.index(label)
    return 999
