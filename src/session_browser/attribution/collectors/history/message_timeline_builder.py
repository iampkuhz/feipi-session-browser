"""消息时间线构建器：从全量 session 消息中构建按时间排序的消息列表。"""

from __future__ import annotations


def build_message_timeline(
    all_messages: list[dict] | list,
    max_messages: int = 100,
) -> list[dict]:
    """构建消息时间线。

    Args:
        all_messages: 全量消息列表（dict 或对象）
        max_messages: 最大返回数量，避免超大上下文

    Returns:
        按原始顺序的消息 dict 列表，每条包含 role、content、timestamp 等字段
    """
    timeline = []
    for msg in all_messages:
        if isinstance(msg, dict):
            timeline.append(msg)
        elif hasattr(msg, 'role'):
            timeline.append(
                {
                    'role': getattr(msg, 'role', ''),
                    'content': getattr(msg, 'content', '') or '',
                    'timestamp': getattr(msg, 'timestamp', None),
                }
            )

    return timeline[:max_messages]


def split_at_boundary(
    timeline: list[dict],
    boundary_index: int,
) -> tuple[list[dict], list[dict]]:
    """在指定边界处拆分时间线。

    Args:
        timeline: 完整消息时间线
        boundary_index: 当前 LLM call 在时间线中的位置

    Returns:
        (prior_messages, subsequent_messages)
    """
    prior = timeline[:boundary_index]
    subsequent = timeline[boundary_index:]
    return prior, subsequent
