"""当前用户消息提取器：从 session 事件中提取当前 LLM call 对应的用户输入。"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence
from session_browser.attribution.collectors.session.llm_call_locator import locate_call_boundary


def extract_current_user_message(
    events: list[dict],
    call_id: str,
    evidence_counter: int = 0,
) -> Evidence | None:
    """提取当前 LLM call 对应的用户消息。

    双算防护：只取当前 call 对应的用户消息，不包含 prior messages。
    """
    start, end = locate_call_boundary(events, call_id)
    if start < 0:
        return None

    for i in range(max(0, start - 5), end + 1):
        ev = events[i]
        role = ev.get("role", "")
        content = ev.get("content", "") or ""

        if role in ("user", "human") and content:
            content_str = str(content)
            preview = content_str[:200]

            return Evidence(
                evidence_id=f"session_user_msg_{evidence_counter}",
                scope="current_session",
                kind="user_message",
                source_event_id=ev.get("id", ""),
                content_ref=ContentRef(
                    kind="session_event",
                    pointer=f"line_{ev.get('_line', i)}",
                    preview=preview,
                    can_load_full=True,
                ),
                text_preview=preview,
                precision="extracted",
                confidence=0.9,
            )

    return None
