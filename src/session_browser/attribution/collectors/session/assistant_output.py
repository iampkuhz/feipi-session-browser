"""助手输出提取器：从 session 事件中提取 LLM 的 response 内容。"""

from __future__ import annotations

from session_browser.attribution.collectors.session.llm_call_locator import locate_call_boundary
from session_browser.attribution.core.models import ContentRef, Evidence


def extract_assistant_output(
    events: list[dict],
    call_id: str,
    evidence_counter: int = 0,
) -> Evidence | None:
    """提取当前 LLM call 对应的助手输出。"""
    start, end = locate_call_boundary(events, call_id)
    if end < 0:
        return None

    for i in range(start, min(len(events), end + 5)):
        ev = events[i]
        role = ev.get('role', '')
        content = ev.get('content', '') or ''

        if role in ('assistant', 'ai') and content:
            content_str = str(content)
            preview = content_str[:200]

            return Evidence(
                evidence_id=f'session_assistant_out_{evidence_counter}',
                scope='current_session',
                kind='assistant_output',
                source_event_id=ev.get('id', ''),
                content_ref=ContentRef(
                    kind='session_event',
                    pointer=f'line_{ev.get("_line", i)}',
                    preview=preview,
                    can_load_full=True,
                ),
                text_preview=preview,
                precision='extracted',
                confidence=0.9,
            )

    return None
