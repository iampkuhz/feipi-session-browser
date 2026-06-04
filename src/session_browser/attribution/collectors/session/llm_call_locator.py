"""LLM call 定位器：在 session 事件中定位特定 LLM call 的边界。"""

from __future__ import annotations


def locate_call_boundary(
    events: list[dict],
    call_id: str,
) -> tuple[int, int]:
    """定位特定 call_id 的起始和结束事件索引。

    Args:
        events: 事件列表
        call_id: 目标 LLM call 的 ID

    Returns:
        (start_index, end_index)，未找到时返回 (-1, -1)
    """
    start = -1
    end = -1
    for i, ev in enumerate(events):
        ev_id = ev.get("id", "") or ev.get("call_id", "") or ev.get("request_id", "")
        if ev_id == call_id:
            if start == -1:
                start = i
            end = i
    return start, end


def find_preceding_events(
    events: list[dict],
    call_id: str,
) -> list[dict]:
    """返回特定 call_id 之前的所有事件（不包含当前 call 的事件）。

    用于双算防护：prior messages 只能包含当前 LLM call 之前的事件。
    """
    start, _ = locate_call_boundary(events, call_id)
    if start <= 0:
        return []
    return events[:start]


def find_current_call_events(
    events: list[dict],
    call_id: str,
) -> list[dict]:
    """返回特定 call_id 相关的所有事件。"""
    _, end = locate_call_boundary(events, call_id)
    if end == -1:
        return []
    results = []
    for ev in events:
        ev_id = ev.get("id", "") or ev.get("call_id", "") or ev.get("request_id", "")
        if ev_id == call_id:
            results.append(ev)
    return results
