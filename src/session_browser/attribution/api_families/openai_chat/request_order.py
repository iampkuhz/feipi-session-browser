"""OpenAI Chat request order.

Chat Completions 推荐顺序：
  messages[]
  tools[]
  tool_choice
  response_format
  reasoning / prediction / metadata config
"""

from __future__ import annotations


def get_openai_chat_request_order() -> list[str]:
    return ["messages", "tools", "tool_choice", "response_format", "reasoning_config"]


def get_openai_chat_order_priority(kind: str) -> int:
    order = get_openai_chat_request_order()
    kind_to_label = {
        "user_text": "messages", "tool_result": "messages",
        "assistant_text": "messages", "tool_use": "messages",
        "tool_schema": "tools", "system_prompt": "messages",
    }
    label = kind_to_label.get(kind, "")
    return order.index(label) if label in order else 999
