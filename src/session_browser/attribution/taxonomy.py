"""Canonical token-attribution taxonomy.

Agent builders may use runtime-specific raw bucket keys while extracting data.
This module owns the stable request-side classification tree used by API
payloads and UI color/ordering.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestTokenCategory:
    """One canonical request-side token attribution category."""

    key: str
    label: str
    parent_key: str
    parent_label: str
    order: int
    color_key: str
    description: str


REQUEST_TOKEN_CATEGORY_TREE: tuple[RequestTokenCategory, ...] = (
    RequestTokenCategory(
        key="current_user_input",
        label="当前用户输入",
        parent_key="conversation_context",
        parent_label="对话上下文",
        order=10,
        color_key="current_user_input",
        description="当前轮用户直接输入的 request-side 文本。",
    ),
    RequestTokenCategory(
        key="conversation_messages",
        label="对话消息上下文",
        parent_key="conversation_context",
        parent_label="对话上下文",
        order=20,
        color_key="conversation_messages",
        description="发送给模型的历史消息、API messages 数组或对话历史。",
    ),
    RequestTokenCategory(
        key="tool_result_context",
        label="工具结果上下文",
        parent_key="conversation_context",
        parent_label="对话上下文",
        order=30,
        color_key="tool_result_context",
        description="历史工具输出、tool result 或 function_call_output。",
    ),
    RequestTokenCategory(
        key="captured_runtime_context",
        label="运行上下文片段",
        parent_key="conversation_context",
        parent_label="对话上下文",
        order=50,
        color_key="captured_runtime_context",
        description="可见但无法更精确归入对话/工具结果的上下文片段。",
    ),
    RequestTokenCategory(
        key="tool_definitions",
        label="工具定义",
        parent_key="tooling_context",
        parent_label="工具上下文",
        order=40,
        color_key="tool_definitions",
        description="工具 schema、函数定义、参数结构和描述。",
    ),
    RequestTokenCategory(
        key="mcp_tool_metadata",
        label="MCP 工具元数据",
        parent_key="tooling_context",
        parent_label="工具上下文",
        order=45,
        color_key="mcp_tool_metadata",
        description="MCP 工具列表或 MCP server 暴露的工具元信息。",
    ),
    RequestTokenCategory(
        key="instruction_context",
        label="系统/开发者指令",
        parent_key="instruction_context",
        parent_label="指令上下文",
        order=60,
        color_key="instruction_context",
        description="系统提示、developer 指令或 agent runtime 指令。",
    ),
    RequestTokenCategory(
        key="local_instruction_context",
        label="本地指令上下文",
        parent_key="instruction_context",
        parent_label="指令上下文",
        order=70,
        color_key="local_instruction_context",
        description="CLAUDE.md、AGENTS.md、Qoder rules 等本地项目指令。",
    ),
    RequestTokenCategory(
        key="agent_subagent_prompt",
        label="Agent/Subagent 提示",
        parent_key="instruction_context",
        parent_label="指令上下文",
        order=80,
        color_key="agent_subagent_prompt",
        description="agent/subagent 专用提示词或角色说明。",
    ),
    RequestTokenCategory(
        key="builtin_system_prompt",
        label="内置系统提示",
        parent_key="instruction_context",
        parent_label="指令上下文",
        order=90,
        color_key="builtin_system_prompt",
        description="agent 内置或隐藏 system prompt 的可见片段/估算。",
    ),
    RequestTokenCategory(
        key="provider_cache_read_context",
        label="Provider 缓存命中上下文",
        parent_key="provider_context",
        parent_label="Provider 上下文",
        order=110,
        color_key="provider_cache_read_context",
        description="provider reported cache read / cached input tokens。",
    ),
    RequestTokenCategory(
        key="provider_conversation_state",
        label="Provider 会话状态",
        parent_key="provider_context",
        parent_label="Provider 上下文",
        order=120,
        color_key="provider_conversation_state",
        description="previous_response_id 等服务端会话状态引用。",
    ),
    RequestTokenCategory(
        key="reasoning_config",
        label="推理配置",
        parent_key="provider_context",
        parent_label="Provider 上下文",
        order=130,
        color_key="reasoning_config",
        description="reasoning effort、budget 或 provider 推理配置开销。",
    ),
    RequestTokenCategory(
        key="runtime_wrapper_overhead",
        label="运行时封装开销",
        parent_key="provider_context",
        parent_label="Provider 上下文",
        order=140,
        color_key="runtime_wrapper_overhead",
        description="JSON wrapper、broker/runtime 包装字段等估算开销。",
    ),
    RequestTokenCategory(
        key="unlocated_residual",
        label="未定位",
        parent_key="residual",
        parent_label="残差",
        order=900,
        color_key="unlocated_residual",
        description="已知 bucket 外仍无法安全定位的剩余 token。",
    ),
)


CATEGORY_BY_KEY = {category.key: category for category in REQUEST_TOKEN_CATEGORY_TREE}


_DEFAULT_BUCKET_CATEGORY_MAP = {
    "current_user_message": "current_user_input",
    "current_user_instruction": "current_user_input",
    "full_messages_array": "conversation_messages",
    "conversation_history": "conversation_messages",
    "history_messages": "conversation_messages",
    "prior_conversation_messages": "conversation_messages",
    "preceding_tool_results": "tool_result_context",
    "tool_results": "tool_result_context",
    "tool_outputs": "tool_result_context",
    "captured_context_fragment": "captured_runtime_context",
    "repository_file_context": "captured_runtime_context",
    "instructions": "instruction_context",
    "local_instruction_context": "local_instruction_context",
    "agent_subagent_prompt": "agent_subagent_prompt",
    "top_level_system_estimate": "builtin_system_prompt",
    "hidden_builtin_system_estimate": "builtin_system_prompt",
    "tool_schemas": "tool_definitions",
    "mcp_tool_metadata": "mcp_tool_metadata",
    "provider_cached_context": "provider_cache_read_context",
    "provider_cache_read_context": "provider_cache_read_context",
    "previous_response_state": "provider_conversation_state",
    "reasoning_config": "reasoning_config",
    "provider_wrapper_overhead": "runtime_wrapper_overhead",
    "qoder_runtime_context_estimate": "runtime_wrapper_overhead",
    "unknown_overhead": "unlocated_residual",
    "unlocated_residual": "unlocated_residual",
    "unknown": "unlocated_residual",
}


def request_bucket_category(agent: str, bucket_key: str) -> RequestTokenCategory:
    """Resolve an agent raw bucket key to a canonical category."""
    category_key = _agent_bucket_map(agent).get(
        bucket_key,
        _DEFAULT_BUCKET_CATEGORY_MAP.get(bucket_key, "unlocated_residual"),
    )
    return CATEGORY_BY_KEY.get(category_key, CATEGORY_BY_KEY["unlocated_residual"])


def normalize_request_bucket_payload(agent: str, bucket: dict) -> dict:
    """Attach canonical taxonomy metadata and unified label to a bucket payload."""
    raw_key = str(bucket.get("key") or "")
    category = request_bucket_category(agent, raw_key)
    normalized = dict(bucket)
    normalized["agent_bucket_key"] = raw_key
    normalized["agent_label"] = bucket.get("label", "")
    normalized["canonical_key"] = category.key
    normalized["canonical_label"] = category.label
    normalized["category_key"] = category.parent_key
    normalized["category_label"] = category.parent_label
    normalized["color_key"] = category.color_key
    normalized["display_order"] = category.order
    normalized["taxonomy_description"] = category.description
    normalized["label"] = category.label
    return normalized


def sort_request_buckets(agent: str, buckets: list[dict]) -> list[dict]:
    """Sort request buckets by canonical taxonomy while keeping agent order ties stable."""
    indexed = list(enumerate(buckets))
    indexed.sort(
        key=lambda item: (
            int(item[1].get("display_order", request_bucket_category(agent, item[1].get("key", "")).order)),
            item[0],
        )
    )
    return [bucket for _, bucket in indexed]


def request_color_index(color_key: str) -> int:
    """Stable color slot for the current CSS palette."""
    order = [
        "current_user_input",
        "conversation_messages",
        "tool_result_context",
        "tool_definitions",
        "local_instruction_context",
        "agent_subagent_prompt",
        "mcp_tool_metadata",
        "builtin_system_prompt",
        "unlocated_residual",
    ]
    if color_key in order:
        return order.index(color_key)
    return 8 if color_key == "unlocated_residual" else 7


def _agent_bucket_map(agent: str) -> dict[str, str]:
    if agent == "claude_code":
        from session_browser.attribution.agents.claude_code_parts.request_taxonomy import (
            REQUEST_BUCKET_CATEGORY_MAP,
        )
        return REQUEST_BUCKET_CATEGORY_MAP
    if agent == "codex":
        from session_browser.attribution.agents.codex_request_taxonomy import (
            REQUEST_BUCKET_CATEGORY_MAP,
        )
        return REQUEST_BUCKET_CATEGORY_MAP
    if agent == "qoder":
        from session_browser.attribution.agents.qoder_request_taxonomy import (
            REQUEST_BUCKET_CATEGORY_MAP,
        )
        return REQUEST_BUCKET_CATEGORY_MAP
    return {}


__all__ = [
    "RequestTokenCategory",
    "REQUEST_TOKEN_CATEGORY_TREE",
    "CATEGORY_BY_KEY",
    "normalize_request_bucket_payload",
    "request_bucket_category",
    "request_color_index",
    "sort_request_buckets",
]
