"""事件流读取器：按事件类型过滤和定位 LLM call 相关事件。"""

from __future__ import annotations

from session_browser.attribution.collectors.session.jsonl_reader import read_jsonl_events


# 事件类型常量
LLM_REQUEST = "llm_request"
LLM_RESPONSE = "llm_response"
TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
USER_MESSAGE = "user_message"
ASSISTANT_MESSAGE = "assistant_message"
SYSTEM_MESSAGE = "system_message"


def filter_events_by_type(events: list[dict], event_type: str) -> list[dict]:
    """按事件类型过滤。

    匹配规则：
    - 检查 event["type"] 字段
    - 检查 event["kind"] 字段
    - 检查 event 中是否包含 event_type 作为 key
    """
    results = []
    for ev in events:
        ev_type = ev.get("type", "") or ""
        ev_kind = ev.get("kind", "") or ""
        if event_type in (ev_type, ev_kind) or event_type in ev:
            results.append(ev)
    return results


def locate_llm_call_events(events: list[dict]) -> list[dict]:
    """定位所有 LLM call 相关事件（request + response）。"""
    return filter_events_by_type(events, LLM_REQUEST) + filter_events_by_type(events, LLM_RESPONSE)


def locate_tool_events(events: list[dict]) -> list[dict]:
    """定位所有工具相关事件（tool_use + tool_result）。"""
    tool_uses = filter_events_by_type(events, TOOL_USE)
    tool_results = filter_events_by_type(events, TOOL_RESULT)
    return tool_uses + tool_results
