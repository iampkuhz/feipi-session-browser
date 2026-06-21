"""Extract completed prior-session tool results for attribution evidence.

History collectors call this module with earlier conversation messages and a
call boundary. It returns Evidence rows for tool_result blocks before that
boundary without reading files or mutating the message payload.
"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence


def extract_prior_tool_results(
    all_messages: list[dict] | list,
    call_boundary_index: int = 0,
    evidence_counter: int = 0,
) -> list[Evidence]:
    """Extract tool-result blocks that appear before the current LLM call.

    History evidence collection calls this with all available messages and the
    index where the target call begins. Non-dictionary messages and non-tool
    blocks are ignored.

    Args:
        all_messages: Conversation messages from the historical session payload.
        call_boundary_index: Exclusive upper bound for messages visible to the
            target call; non-positive values yield no prior evidence.
        evidence_counter: Offset used to generate deterministic Evidence IDs.

    Returns:
        Evidence rows ordered by their appearance before the boundary.
    """
    results = []
    messages = all_messages[:call_boundary_index] if call_boundary_index > 0 else []
    idx = evidence_counter

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = msg.get('role', '')
        content = msg.get('content', '')

        if role == 'user' and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'tool_result':
                    tr_text = _tool_result_to_text(block)
                    tool_use_id = block.get('tool_use_id', '')
                    results.append(
                        Evidence(
                            evidence_id=f'prior_tool_result_{idx}',
                            scope='prior_session',
                            kind='tool_result',
                            source_event_id=tool_use_id,
                            content_ref=ContentRef(
                                kind='session_event',
                                preview=tr_text[:200],
                                can_load_full=True,
                            ),
                            text_preview=tr_text[:200],
                            precision='extracted',
                            confidence=0.9,
                        )
                    )
                    idx += 1

    return results


def _tool_result_to_text(block: dict) -> str:
    """Normalize a tool_result content block into preview text.

    The prior-results extractor calls this for each matching block. It accepts
    both list-of-text fragments and scalar content values, and it has no side
    effects.

    Args:
        block: Message content block whose ``type`` is ``tool_result``.

    Returns:
        Joined text fragments, scalar content converted to text, or an empty
        string when the block has no content.
    """
    content = block.get('content', '')
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get('text', ''))
        return '\n'.join(parts)
    return str(content) if content else ''
