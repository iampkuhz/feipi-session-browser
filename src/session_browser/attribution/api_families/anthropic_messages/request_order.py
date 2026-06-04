"""Anthropic Messages API 请求顺序规范。

Anthropic request canonical order：
  tools[]
  system[]
  messages[0].content[]
  messages[1].content[]
  ...

Prompt cache prefix 也是按这个顺序建立。
"""

from __future__ import annotations


def get_anthropic_request_order() -> list[str]:
    """返回 Anthropic Messages API 的推荐请求顺序。

    Returns:
        有序的阶段标签列表，用于构建 ordered PromptSpan。
    """
    return [
        "tools",
        "system",
        "messages",
    ]


def get_anthropic_order_priority(kind: str) -> int:
    """获取某个 semantic_kind 在 Anthropic 请求顺序中的优先级。

    数字越小越靠前。未识别的 kind 返回 999（排最后）。
    """
    order = get_anthropic_request_order()
    # 映射 semantic_kind -> order 标签
    kind_to_label = {
        "tool_schema": "tools",
        "system_prompt": "system",
        "user_text": "messages",
        "tool_result": "messages",
        "assistant_text": "messages",
        "tool_use": "messages",
    }
    label = kind_to_label.get(kind, "")
    if label in order:
        return order.index(label)
    return 999
