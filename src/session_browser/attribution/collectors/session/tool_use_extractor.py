"""工具使用提取器：从 session 事件中提取 tool_use 事件。"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence
from session_browser.attribution.collectors.session.event_stream_reader import filter_events_by_type, TOOL_USE


def extract_tool_uses(
    events: list[dict],
    call_id: str,
    evidence_counter: int = 0,
) -> list[Evidence]:
    """提取当前 LLM call 输出的 tool_use 事件。每个 tool 单独返回一个 Evidence。"""
    tool_events = filter_events_by_type(events, TOOL_USE)
    results = []

    for idx, ev in enumerate(tool_events):
        ev_id = ev.get("id", "") or ev.get("call_id", "") or ev.get("request_id", "")
        if ev_id and ev_id != call_id:
            continue

        tool_name = ev.get("tool_name", ev.get("name", "unknown"))
        tool_params = ev.get("parameters", ev.get("input", {}))
        params_str = str(tool_params)[:200] if tool_params else ""
        preview = f"{tool_name}({params_str[:80]}...)" if params_str else tool_name

        results.append(Evidence(
            evidence_id=f"session_tool_use_{evidence_counter + idx}",
            scope="current_session",
            kind="tool_use",
            source_event_id=ev.get("id", ""),
            content_ref=ContentRef(
                kind="session_event",
                pointer=f"line_{ev.get('_line', idx)}",
                preview=preview,
                can_load_full=False,
            ),
            text_preview=preview,
            precision="extracted",
            confidence=0.85,
        ))

    return results
