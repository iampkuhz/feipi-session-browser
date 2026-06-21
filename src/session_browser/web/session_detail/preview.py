"""Presenter-owned preview helpers for Session Detail trace rows."""

from __future__ import annotations

import re
from html import escape


def compact_preview_text(text: str | None, limit: int = 120) -> str:
    """Collapse whitespace and truncate text for trace row summaries.

    Args:
        text: Source text to compact.
        limit: Maximum number of characters to keep before adding an ellipsis.

    Returns:
        Compacted preview text.
    """
    if not text:
        return ''
    compacted = re.sub(r'\s+', ' ', str(text)).strip()
    if len(compacted) > limit:
        return compacted[:limit].rstrip() + '…'
    return compacted


def format_tool_counts(tools: list[object]) -> str:
    """Build HTML-safe tool count chips for a trace row view model.

    Args:
        tools: Tool call objects with optional ``name`` attributes.

    Returns:
        HTML snippet containing tool count chips.
    """
    if not tools:
        return ''
    tool_counts: dict[str, int] = {}
    for tool in tools:
        name = str(getattr(tool, 'name', '') or 'tool')
        tool_counts[name] = tool_counts.get(name, 0) + 1
    return ' · '.join(
        f'<span class="preview-tool">{escape(name)}</span>&times;{count}'
        for name, count in tool_counts.items()
    )


def build_round_preview(round_obj: object) -> dict[str, str]:
    """Return presenter preview fields for a ConversationRound-like object.

    Args:
        round_obj: ConversationRound-like object.

    Returns:
        Dict containing ``preview_text`` and ``tool_summary_html``.
    """
    all_tools = list(getattr(round_obj, 'tool_calls', []) or [])
    tool_summary_html = format_tool_counts(all_tools)

    interactions = list(getattr(round_obj, 'interactions', []) or [])
    has_subagent = any(getattr(ix, 'scope', '') == 'subagent' for ix in interactions)
    subagent_response = ''
    for ix in interactions:
        if (
            getattr(ix, 'scope', '') == 'subagent'
            and getattr(ix, 'response_preview', '')
            and not subagent_response
        ):
            subagent_response = str(getattr(ix, 'response_preview', ''))

    user_msg = getattr(round_obj, 'user_msg', None)
    assistant_msg = getattr(round_obj, 'assistant_msg', None)
    user_content = str(getattr(user_msg, 'content', '') or '')
    assistant_content = str(getattr(assistant_msg, 'content', '') or '')

    if has_subagent:
        if subagent_response:
            preview_text = compact_preview_text(subagent_response, 100)
        else:
            sub_desc = ''
            for ix in interactions:
                if getattr(ix, 'scope', '') == 'subagent' and getattr(ix, 'parent_tool_name', ''):
                    sub_desc = str(getattr(ix, 'parent_tool_name', ''))
                    break
            preview_text = f'Subagent({sub_desc})' if sub_desc else 'Subagent'
    elif assistant_content:
        preview_text = compact_preview_text(assistant_content, 100)
    elif user_content:
        preview_text = compact_preview_text(user_content, 120)
    else:
        preview_text = ''

    return {
        'preview_text': preview_text,
        'tool_summary_html': tool_summary_html,
    }


def apply_round_preview(round_obj: object) -> object:
    """Compatibility shim for tests and older callers that expect round attrs.

    Args:
        round_obj: ConversationRound-like object to mutate.

    Returns:
        The same object with preview attributes attached.
    """
    preview = build_round_preview(round_obj)
    round_obj.preview_text = preview['preview_text']
    round_obj.tool_summary_html = preview['tool_summary_html']
    return round_obj
