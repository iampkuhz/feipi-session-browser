"""OpenAI Responses API 请求顺序规范。

Responses 推荐顺序：
  instructions
  input[] / messages[]
  tools[]
  structured output schema / text.format / response_format
  reasoning config
  previous_response_id / server state placeholder
"""

from __future__ import annotations


def get_openai_responses_request_order() -> list[str]:
    """返回 OpenAI Responses API 的推荐请求顺序。"""
    return [
        "instructions",
        "input_messages",
        "tools",
        "structured_output_schema",
        "reasoning_config",
        "server_state",
    ]


def get_openai_responses_order_priority(kind: str) -> int:
    """获取 semantic_kind 在 OpenAI Responses 请求顺序中的优先级。"""
    order = get_openai_responses_request_order()
    kind_to_label = {
        "system_prompt": "instructions",
        "user_text": "input_messages",
        "tool_result": "input_messages",
        "assistant_text": "input_messages",
        "tool_schema": "tools",
        "tool_use": "input_messages",
        "repo_context": "input_messages",
    }
    label = kind_to_label.get(kind, "")
    if label in order:
        return order.index(label)
    return 999
