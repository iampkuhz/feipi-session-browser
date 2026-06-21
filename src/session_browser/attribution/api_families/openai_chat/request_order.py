"""Define canonical OpenAI Chat request ordering for attribution rendering.

Attribution serializers and UI presenters load this module when they need a
stable display order for Chat Completions payload sections. Inputs are local
bucket kinds, and outputs are ordered field labels or numeric priorities.
"""

from __future__ import annotations


def get_openai_chat_request_order() -> list[str]:
    """Return the canonical OpenAI Chat request field order.

    The attribution request-order resolver calls this helper before sorting
    reconstructed request sections. It has no inputs and no side effects.

    Returns:
        Field labels ordered as they should appear in OpenAI Chat payload views.
    """
    return ['messages', 'tools', 'tool_choice', 'response_format', 'reasoning_config']


def get_openai_chat_order_priority(kind: str) -> int:
    """Map an attribution bucket kind to its OpenAI Chat sort priority.

    Sorting code calls this helper for each reconstructed request bucket. Unknown
    kinds are placed after known Chat payload sections.

    Args:
        kind: Attribution bucket kind emitted by request collectors or builders.

    Returns:
        Zero-based priority within the OpenAI Chat order, or 999 for unknown
        kinds.
    """
    order = get_openai_chat_request_order()
    kind_to_label = {
        'user_text': 'messages',
        'tool_result': 'messages',
        'assistant_text': 'messages',
        'tool_use': 'messages',
        'tool_schema': 'tools',
        'system_prompt': 'messages',
    }
    label = kind_to_label.get(kind, '')
    return order.index(label) if label in order else 999
