"""前序消息提取器：提取当前 LLM call 之前的所有消息作为 Evidence。"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence


def extract_prior_messages(
    all_messages: list[dict] | list,
    call_boundary_index: int = 0,
    max_messages: int = 50,
    evidence_counter: int = 0,
) -> list[Evidence]:
    """提取当前 LLM call 之前的所有消息。"""
    results = []
    messages = all_messages[:call_boundary_index] if call_boundary_index > 0 else []

    if len(messages) > max_messages:
        messages = messages[-max_messages:]

    for idx, msg in enumerate(messages):
        role = ''
        content = ''
        if isinstance(msg, dict):
            role = msg.get('role', '')
            content = msg.get('content', '') or ''
        elif hasattr(msg, 'role'):
            role = getattr(msg, 'role', '')
            content = getattr(msg, 'content', '') or ''

        if not role:
            continue

        content_str = str(content)
        preview = content_str[:200]

        results.append(
            Evidence(
                evidence_id=f'prior_msg_{evidence_counter + idx}',
                scope='prior_session',
                kind='conversation_history',
                content_ref=ContentRef(
                    kind='session_event',
                    preview=preview,
                    can_load_full=True,
                ),
                text_preview=preview,
                precision='extracted',
                confidence=0.8,
                raw_value={'role': role, 'original_index': idx},
            )
        )

    return results
