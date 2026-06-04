"""工具结果提取器：从 session 事件中提取 tool_result 事件。"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence
from session_browser.attribution.collectors.session.event_stream_reader import filter_events_by_type, TOOL_RESULT


def extract_tool_results(
    events: list[dict],
    call_id: str,
    preceding_only: bool = True,
    evidence_counter: int = 0,
) -> list[Evidence]:
    """提取工具结果事件。preceding_only=True 时只取当前 call 之前完成的工具结果。"""
    tool_events = filter_events_by_type(events, TOOL_RESULT)
    results = []

    for idx, ev in enumerate(tool_events):
        result_text = ev.get("content", ev.get("result", "")) or ""
        tool_use_id = ev.get("tool_use_id", ev.get("id", ""))
        tool_name = ev.get("tool_name", _extract_tool_name(result_text))

        content_str = str(result_text)
        preview = content_str[:200]

        results.append(Evidence(
            evidence_id=f"session_tool_result_{evidence_counter + idx}",
            scope="current_session",
            kind="tool_result",
            source_event_id=ev.get("id", ""),
            content_ref=ContentRef(
                kind="session_event",
                pointer=f"line_{ev.get('_line', idx)}",
                preview=preview,
                can_load_full=True,
            ),
            text_preview=preview,
            precision="extracted",
            confidence=0.9,
            source_path=tool_use_id,
        ))

    return results


def _extract_tool_name(text: str) -> str:
    if not text:
        return "unknown"
    import re
    m = re.search(r'(?:Tool|tool)[\s_]*(?:Call|Result|Output)?[:\s]+(\w+)', text)
    if m:
        return m.group(1)
    first = text.split()[0] if text.split() else "unknown"
    return first[:30]
