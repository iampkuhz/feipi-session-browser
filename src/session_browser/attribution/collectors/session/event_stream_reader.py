"""事件流读取器:按事件类型过滤和定位 LLM call 相关事件."""

from __future__ import annotations

# 事件类型常量
LLM_REQUEST = 'llm_request'
LLM_RESPONSE = 'llm_response'
TOOL_USE = 'tool_use'
TOOL_RESULT = 'tool_result'
USER_MESSAGE = 'user_message'
ASSISTANT_MESSAGE = 'assistant_message'
SYSTEM_MESSAGE = 'system_message'


def filter_events_by_type(events: list[dict], event_type: str) -> list[dict]:
    """按事件类型过滤 session 事件.

    匹配规则:
    - 检查 event["type"] 字段
    - 检查 event["kind"] 字段
    - 检查 event 中是否包含 event_type 作为 key

    Args:
        events: 原始 session 事件列表.
        event_type: 需要匹配的事件类型或 key.

    Returns:
        与事件类型匹配的事件列表, 保持原始顺序.
    """
    results = []
    for ev in events:
        ev_type = ev.get('type', '') or ''
        ev_kind = ev.get('kind', '') or ''
        if event_type in (ev_type, ev_kind) or event_type in ev:
            results.append(ev)
    return results


def locate_llm_call_events(events: list[dict]) -> list[dict]:
    """定位所有 LLM call 请求和响应事件.

    Args:
        events: 原始 session 事件列表.

    Returns:
        LLM request 与 LLM response 事件列表.
    """
    return filter_events_by_type(events, LLM_REQUEST) + filter_events_by_type(events, LLM_RESPONSE)


def locate_tool_events(events: list[dict]) -> list[dict]:
    """定位所有工具调用和工具结果事件.

    Args:
        events: 原始 session 事件列表.

    Returns:
        Tool use 与 tool result 事件列表.
    """
    tool_uses = filter_events_by_type(events, TOOL_USE)
    tool_results = filter_events_by_type(events, TOOL_RESULT)
    return tool_uses + tool_results
