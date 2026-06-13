"""Request attribution builder for Claude Code.

Contains the `build_request` logic extracted as a standalone function
that takes the builder instance as a parameter.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from session_browser.domain.models import LLMCall, ConversationRound, SessionSummary
from session_browser.attribution.contracts import (
    AttributedValue,
    RequestAttributionBucket,
    LLMRequestAttribution,
    ValuePrecision,
    ValueSource,
)
from session_browser.attribution.token_estimator import estimate_tokens_from_text
from session_browser.attribution.agents.claude_code_tool_schemas import (
    ALL_CLAUDE_CODE_TOOLS,
    get_cached_schemas,
    get_all_tool_schema_tokens,
    get_tool_schema_tokens,
)
from session_browser.attribution.agents.claude_code_parts.constants import (
    NORMALIZATION_NOTE,
)
from session_browser.attribution.agents.claude_code_parts.utils import (
    _pct,
    extract_tool_name,
    mask_sensitive_keys,
    tool_description,
    truncate_preview,
)
from session_browser.attribution.agents.claude_code_parts.normalizer import (
    normalize_request_reconstruction_buckets,
)

if TYPE_CHECKING:
    from session_browser.attribution.agents.base import BaseAttributionBuilder


def _extract_prior_messages(self: "BaseAttributionBuilder") -> list[dict]:
    """Extract prior messages from session_context if available.

    Returns a list of message dicts with 'role' and 'content' keys.
    If session_context does not provide prior_messages, returns [].
    """
    ctx = self.session_context or {}
    prior = ctx.get("prior_messages", ctx.get("conversation_history", []))
    if isinstance(prior, list):
        return prior
    # Also check round-level data: interactions from previous rounds
    if hasattr(self.round_obj, "round_index") and self.round_obj.round_index > 0:
        # In multi-round sessions, prior rounds' messages could be accessed
        # via session_context. For now, return empty — we don't guess.
        pass
    return []


def _get_available_tools(self: "BaseAttributionBuilder") -> list[str]:
    """Get available tool schemas from session_context or metadata.

    Returns a list of tool names (strings).  Empty list means we
    cannot determine available tools from local logs.

    IMPORTANT: This does NOT use observed tool_calls.  Tool schemas
    refers to the tools available to the model, not the tools called.
    """
    ctx = self.session_context or {}
    available = ctx.get("available_tools", ctx.get("available_tool_schemas", []))
    if isinstance(available, list):
        # Normalize to list of tool name strings
        result = []
        for item in available:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                name = item.get("name", item.get("tool_name", ""))
                if name:
                    result.append(name)
        return result
    return []


def build_request(self: "BaseAttributionBuilder") -> LLMRequestAttribution:
    """Build request attribution for a Claude Code LLM call."""
    lc = self.llm_call
    ro = self.round_obj

    # ── Step 1: provider usage (authoritative) ─────────────────────
    # Claude Code fields:
    #   input_tokens  = non-cache input (fresh)
    #   cache_read_input_tokens / cached_input_tokens = cache read
    #   cache_creation_input_tokens = cache write
    #   total = input + cache_read + cache_write (exclusive accounting components)
    # Request attribution distribution uses input + cache_read; cache_write is
    # shown as provider accounting, not as an additional request source bucket.
    total_input_val = lc.input_tokens or 0
    cache_read_val = lc.cache_read_tokens or 0
    cache_write_val = lc.cache_write_tokens or 0

    # input_tokens in Claude Code JSONL usage is the fresh (non-cache)
    # input — it does NOT include cache_read.  So fresh_input == input_tokens.
    fresh_input_val = total_input_val

    request_distribution_input = total_input_val + cache_read_val
    total_call_input = request_distribution_input + cache_write_val

    total_input = AttributedValue(
        value=total_call_input,
        unit="tokens",
        precision=ValuePrecision.PROVIDER_REPORTED,
        source=ValueSource.PROVIDER_USAGE,
        fill_strategy="input_tokens + cache_read_tokens + cache_write_tokens",
    )
    fresh_input = AttributedValue(
        value=fresh_input_val,
        unit="tokens",
        precision=ValuePrecision.PROVIDER_REPORTED,
        source=ValueSource.PROVIDER_USAGE,
        fill_strategy="input_tokens is non-cache fresh input",
    )
    cache_read = AttributedValue(
        value=cache_read_val,
        unit="tokens",
        precision=ValuePrecision.PROVIDER_REPORTED,
        source=ValueSource.PROVIDER_USAGE,
        fill_strategy="cache_read_input_tokens",
    )
    cache_write = AttributedValue(
        value=cache_write_val,
        unit="tokens",
        precision=ValuePrecision.PROVIDER_REPORTED,
        source=ValueSource.PROVIDER_USAGE,
        fill_strategy="cache_creation_input_tokens",
    )

    # ── Step 2: visible text token estimation ─────────────────────
    # Current user message
    user_msg_content = ro.user_msg.content if ro.user_msg else ""
    current_user_msg_tokens = estimate_tokens_from_text(user_msg_content)

    # Tool results: ONLY preceding ones from session_context, NOT the
    # entire round's tool_calls.  Tool results typically feed the NEXT
    # LLM call, not the current one.
    tool_result_texts = self._get_preceding_tool_result_texts()
    tool_results_tokens = estimate_tokens_from_text("\n".join(tool_result_texts))

    # Prior conversation messages: extract from session_context.
    # NOTE: this replaces the old history_messages bucket to avoid
    # double-counting with current_user_message.
    prior_messages = _extract_prior_messages(self)
    prior_message_texts = []
    for pm in prior_messages:
        if isinstance(pm, dict):
            prior_message_texts.append(pm.get("content", ""))
        else:
            prior_message_texts.append(str(pm))
    prior_msg_count = len(prior_messages)
    prior_conversation_tokens = 0
    if prior_messages:
        prior_conversation_tokens = estimate_tokens_from_text("\n".join(prior_message_texts))

    # full_messages_array: Anthropic API-style messages (replaces prior_conversation_messages)
    ctx = self.session_context or {}
    full_messages_array = ctx.get("full_messages_array", [])
    full_msg_count = len(full_messages_array) if full_messages_array else 0
    full_messages_tokens = 0
    if full_messages_array:
        full_messages_tokens = sum(
            max(0, int(fm.get("content_token_estimate") or 0))
            for fm in full_messages_array
            if isinstance(fm, dict)
        )

    # Tool schemas: use real JSON Schema definitions extracted from
    # Claude Code npm package (sdk-tools.d.ts) for accurate token
    # counting, instead of the old per-tool heuristic.
    available_tools = _get_available_tools(self)
    available_tools_source_kind = str(ctx.get("available_tools_source") or "")
    available_tools_agent_name = str(ctx.get("available_tools_agent_name") or "")
    available_tools_definition_path = str(ctx.get("available_tools_definition_path") or "")
    available_tools_reason = str(ctx.get("available_tools_reason") or "")
    # When available_tools is empty (e.g. tool_calls_raw not parseable),
    # fall back to the full Claude Code SDK tool registry so that the
    # token count and bucket details use the same comprehensive list.
    tools_for_schema = available_tools if available_tools else ALL_CLAUDE_CODE_TOOLS
    tool_schema_tokens = 0
    tool_schemas_availability = ValuePrecision.UNAVAILABLE
    tool_schemas_source = ValueSource.HEURISTIC
    tool_schemas_summary = (
        "无法从本地日志获取可用工具定义列表；不能用实际 tool calls 代替 tool schemas。"
    )
    # Always compute tokens against the list that will be displayed.
    schemas = get_cached_schemas()
    tool_schema_tokens = get_all_tool_schema_tokens(tools_for_schema, schemas)
    if available_tools:
        tool_schemas_availability = ValuePrecision.ESTIMATED
        if available_tools_source_kind == "agent_definition":
            tool_schemas_source = ValueSource.LOCAL_RULES
        elif available_tools_source_kind == "default_builtin":
            tool_schemas_source = ValueSource.HEURISTIC
        else:
            tool_schemas_source = ValueSource.TOOL_LIST
    tool_schemas_summary = (
        f"基于 Claude Code SDK 真实 tool schema 定义，"
        f"{len(tools_for_schema)} 个工具共 {tool_schema_tokens} tokens。"
    )
    if available_tools_source_kind == "agent_definition" and available_tools_agent_name:
        tool_schemas_summary = (
            f"基于 Claude agent `{available_tools_agent_name}` 的显式 tools 配置和 "
            f"Claude Code SDK 真实 tool schema 定义，"
            f"{len(tools_for_schema)} 个工具共 {tool_schema_tokens} tokens。"
        )
    elif available_tools_source_kind == "default_builtin":
        tool_schemas_summary = (
            f"未检测到可证明的自定义 agent tools 配置，按 Claude Code 默认内置工具集计算："
            f"{len(tools_for_schema)} 个工具共 {tool_schema_tokens} tokens。"
        )

    # Local instruction context: look for system-reminder content in
    # session_context or round user_msg.
    local_instruction_tokens = 0
    local_instruction_text = ""
    local_instruction_availability = ValuePrecision.UNAVAILABLE
    local_instruction_summary = "未检测到本地指令上下文。"
    local_text = (
        ctx.get("local_instructions")
        or ctx.get("system_reminder_content")
        or ""
    )
    if local_text:
        local_instruction_text = local_text[:3000]
        local_instruction_tokens = estimate_tokens_from_text(local_instruction_text)
        local_instruction_availability = ValuePrecision.HEURISTIC
        local_instruction_summary = (
            f"从 session_context 中提取本地指令，{len(local_text)} 字符估算。"
        )

    # Agent/Subagent prompt: check session_context for prompt file or text.
    agent_subagent_tokens = 0
    agent_subagent_text = ""
    agent_subagent_availability = ValuePrecision.UNAVAILABLE
    agent_subagent_summary = "未检测到 Agent/Subagent 提示。"
    agent_prompt = (
        ctx.get("agent_prompt_file")
        or ctx.get("subagent_prompt")
        or ""
    )
    if agent_prompt:
        agent_subagent_text = agent_prompt[:3000]
        agent_subagent_tokens = estimate_tokens_from_text(agent_subagent_text)
        agent_subagent_availability = ValuePrecision.HEURISTIC
        agent_subagent_summary = (
            f"从 session_context 中提取 Agent 提示，{len(agent_prompt)} 字符估算。"
        )

    # MCP tool metadata: count items * ~50 tokens each.
    mcp_metadata_tokens = 0
    mcp_metadata_availability = ValuePrecision.UNAVAILABLE
    mcp_metadata_summary = "未检测到 MCP 工具元数据。"
    mcp_tools = ctx.get("mcp_tools", ctx.get("mcp_servers", []))
    if isinstance(mcp_tools, list) and mcp_tools:
        mcp_metadata_tokens = len(mcp_tools) * 50
        mcp_metadata_availability = ValuePrecision.HEURISTIC
        mcp_metadata_summary = (
            f"按 {len(mcp_tools)} 个 MCP 工具/服务器 × 50 tokens 估算。"
        )

    # Top-level system estimate: if cache_read > 0 and full messages array is
    # small, some tokens are likely system-level.
    top_level_system_tokens = 0
    if cache_read_val > 0 and full_messages_tokens < cache_read_val:
        # Some cache tokens are likely system-level content.
        known_before_system = (
            current_user_msg_tokens + tool_results_tokens
            + full_messages_tokens + tool_schema_tokens
            + local_instruction_tokens + agent_subagent_tokens
            + mcp_metadata_tokens
        )
        top_level_system_tokens = min(500, max(0, request_distribution_input - known_before_system))
        # Clamp: don't exceed cache_read
        top_level_system_tokens = min(top_level_system_tokens, cache_read_val)
    if top_level_system_tokens > 0:
        pass  # heuristic estimate
    else:
        top_level_system_tokens = 0

    # Hidden builtin system estimate: Claude Code builtin prompt not public.
    # If system_reminder_content is available in session_context, use actual token count.
    hidden_builtin_tokens = 0
    system_reminder_text = ctx.get("system_reminder_content", "")
    if system_reminder_text:
        hidden_builtin_tokens = estimate_tokens_from_text(system_reminder_text)
        hidden_builtin_tokens = max(hidden_builtin_tokens, 100)  # floor
    else:
        # Typical range: 300-800 tokens for Claude Code wrapper.
        hidden_builtin_tokens = 500  # midpoint heuristic
    # This is always a heuristic; mark as such.

    # Provider wrapper estimate: ~50-200 tokens for framing.
    # Not shown as a separate bucket — noted in attribution_notes instead.
    provider_wrapper_tokens = 100  # midpoint heuristic

    # ── Step 3: assemble buckets and normalize ─────────────────────
    # Sum of all known buckets EXCEPT unlocated_residual.
    # Note: provider_wrapper_tokens is NOT included — it's absorbed into residual.
    known_sum = (
        current_user_msg_tokens + tool_results_tokens
        + full_messages_tokens + tool_schema_tokens
        + local_instruction_tokens + agent_subagent_tokens
        + mcp_metadata_tokens + top_level_system_tokens
        + hidden_builtin_tokens
    )

    unlocated_residual = (
        max(request_distribution_input - known_sum, 0)
        if request_distribution_input > 0 else 0
    )

    buckets = []

    # 1. current_user_message — 当前用户输入
    if current_user_msg_tokens > 0:
        masked_user_content = mask_sensitive_keys(user_msg_content or "")
        current_user_details = {
            "kind": "current_user_message",
            "preview": truncate_preview(masked_user_content, 1000),
            "full_content": masked_user_content,
            "tokens": current_user_msg_tokens,
        }
        buckets.append(RequestAttributionBucket(
            key="current_user_message",
            label="当前用户输入",
            tokens=current_user_msg_tokens,
            percent=_pct(current_user_msg_tokens, request_distribution_input),
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TRANSCRIPT,
            confidence_label="中高",
            summary="用户消息内容完整可用，token 通过文本估算。",
            content_preview=(user_msg_content or "")[:120],
            details=current_user_details,
        ))

    # 2. preceding_tool_results — 前序工具结果
    if tool_results_tokens > 0:
        preceding_tool_details = {
            "kind": "tool_results",
            "items": [
                {
                    "tool_name": extract_tool_name(rt),
                    "summary": truncate_preview(mask_sensitive_keys(rt), 180),
                    "full_content": mask_sensitive_keys(rt),
                    "exit_status": 0,  # unknown from text
                    "tokens": estimate_tokens_from_text(rt),
                }
                for rt in tool_result_texts
            ],
            "total_items": len(tool_result_texts),
            "truncated": False,
        }
        buckets.append(RequestAttributionBucket(
            key="preceding_tool_results",
            label="前序工具结果",
            tokens=tool_results_tokens,
            percent=_pct(tool_results_tokens, request_distribution_input),
            count_label=f"{len(tool_result_texts)} results" if tool_result_texts else "",
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TOOL_LOGS,
            confidence_label="中",
            summary="前序 Tool result 内容可从 tool logs 获取，token 通过文本估算。",
            details=preceding_tool_details,
        ))

    # 3. full_messages_array — Anthropic API 完整 messages 数组
    # This replaces prior_conversation_messages with a structured array
    # that mirrors the real Anthropic API messages field.
    # (full_messages_array and full_messages_tokens already extracted from ctx above)
    prior_details = {
        "kind": "full_messages_array",
        "explanation": [
            "这里对应发送给模型的 Anthropic API `messages` 字段，而不是 UI 上的 round 列表。",
            "每一行是一段输入消息内容：user_text 是用户文本，tool_result 是工具结果，assistant_text 是历史助手文本，tool_use 是历史工具调用。",
            "当前 assistant response 属于输出，不计入这个 request-side messages 数组。",
        ],
        "items": [
            {
                "message_index": fm.get("message_index", i),
                "role": fm.get("role", "unknown"),
                "content_type": fm.get("content_type", "unknown"),
                "tool_name": fm.get("tool_name", ""),
                "tool_use_id": fm.get("tool_use_id", ""),
                "summary": fm.get("content_preview", ""),
                "full_content": (
                    fm.get("full_content")
                    or fm.get("content")
                    or fm.get("content_preview", "")
                ),
                "tokens": fm.get("content_token_estimate", 0),
                "has_full_content": fm.get("has_full_content", False),
            }
            for i, fm in enumerate(full_messages_array)
        ],
        "total_items": full_msg_count,
        "truncated": False,
    }
    buckets.append(RequestAttributionBucket(
        key="full_messages_array",
        label="API messages 数组",
        tokens=full_messages_tokens,
        percent=_pct(full_messages_tokens, request_distribution_input),
        count_label=f"{full_msg_count} messages" if full_messages_array else "",
        precision=ValuePrecision.ESTIMATED,
        source=ValueSource.TRANSCRIPT,
        confidence_label="中",
        summary=(
            f"Anthropic API messages 数组完整结构，共 {full_msg_count} 条消息，"
            f"包含 user_text、tool_result、assistant_text、tool_use 四种类型，"
            f"token 通过文本估算。"
        ),
        content_preview="",
        details=prior_details,
    ))

    # 4. tool_schemas — 工具定义
    # Import schema extractor for per-tool token counts
    schemas_for_detail = get_cached_schemas()

    detail_item_source = "available_tools"
    if available_tools_source_kind == "agent_definition":
        detail_item_source = "agent_definition"
    elif available_tools_source_kind == "default_builtin" or not available_tools:
        detail_item_source = "default_fallback"

    tool_schemas_details = {
        "kind": "tools",
        "source": available_tools_source_kind or ("available_tools" if available_tools else "default_fallback"),
        "agent_name": available_tools_agent_name,
        "definition_path": available_tools_definition_path,
        "reason": available_tools_reason,
        "items": [
            {
                "name": tool_name,
                "source": detail_item_source,
                "enabled": True,
                "description_preview": tool_description(tool_name),
                "estimated_tokens": get_tool_schema_tokens(tool_name, schemas_for_detail),
                "precision": "extracted_from_sdk",
                "description": tool_description(tool_name),
                "input_schema": json.dumps(
                    schemas_for_detail.get(tool_name, {}).get("input_schema", {}),
                    ensure_ascii=False, indent=2,
                ) if tool_name in schemas_for_detail else "",
            }
            for tool_name in sorted(available_tools or ALL_CLAUDE_CODE_TOOLS)
        ],
        "total_items": len(available_tools or ALL_CLAUDE_CODE_TOOLS),
        "truncated": False,
    }
    buckets.append(RequestAttributionBucket(
        key="tool_schemas",
        label="工具定义",
        tokens=tool_schema_tokens,
        percent=_pct(tool_schema_tokens, request_distribution_input),
        count_label=f"{len(tools_for_schema)} tools",
        precision=tool_schemas_availability if tool_schema_tokens > 0 else ValuePrecision.UNAVAILABLE,
        source=tool_schemas_source,
        confidence_label="中低" if tool_schema_tokens > 0 else "低",
        summary=tool_schemas_summary,
        details=tool_schemas_details,
    ))

    # 5. local_instruction_context — 本地指令上下文
    local_instruction_details = {"kind": "system_sources", "items": []}
    if ctx.get("local_instructions"):
        masked_text = mask_sensitive_keys(ctx["local_instructions"])
        local_instruction_details["items"].append({
            "file_path": "CLAUDE.md",
            "source_type": "project_instructions",
            "preview": truncate_preview(masked_text, 500),
            "full_content": masked_text,
            "tokens": local_instruction_tokens,
            "precision": "heuristic",
        })
    if ctx.get("system_reminder_content"):
        masked_reminder = mask_sensitive_keys(ctx["system_reminder_content"])
        local_instruction_details["items"].append({
            "file_path": "system-reminder",
            "source_type": "transcript_system_reminder",
            "preview": truncate_preview(masked_reminder, 500),
            "full_content": masked_reminder,
            "tokens": estimate_tokens_from_text(ctx["system_reminder_content"]),
            "precision": "heuristic",
        })
    buckets.append(RequestAttributionBucket(
        key="local_instruction_context",
        label="本地指令上下文",
        tokens=local_instruction_tokens,
        percent=_pct(local_instruction_tokens, request_distribution_input),
        precision=local_instruction_availability,
        source=ValueSource.LOCAL_RULES,
        confidence_label="中低" if local_instruction_tokens > 0 else "低",
        summary=local_instruction_summary,
        content_preview=local_instruction_text[:120] if local_instruction_text else "",
        details=local_instruction_details,
    ))

    # 6. agent_subagent_prompt — Agent/Subagent 提示
    agent_subagent_details = {"kind": "system_sources", "items": []}
    if ctx.get("agent_prompt_file") and ctx.get("subagent_prompt"):
        agent_name_for_path = ""
        if hasattr(self.round_obj, "agent_name"):
            agent_name_for_path = getattr(self.round_obj, "agent_name", "")
        if not agent_name_for_path:
            # Try to extract from prompt file path
            prompt_file = ctx.get("agent_prompt_file", "")
            if prompt_file:
                agent_name_for_path = prompt_file.rsplit("/", 1)[-1].replace(".md", "")
        masked_agent = mask_sensitive_keys(ctx["subagent_prompt"])
        agent_subagent_details["items"].append({
            "file_path": f".claude/agents/{agent_name_for_path or 'unknown'}.md",
            "source_type": "agent_prompt",
            "preview": truncate_preview(masked_agent, 500),
            "full_content": masked_agent,
            "tokens": agent_subagent_tokens,
            "precision": "heuristic",
        })
    buckets.append(RequestAttributionBucket(
        key="agent_subagent_prompt",
        label="Agent/Subagent 提示",
        tokens=agent_subagent_tokens,
        percent=_pct(agent_subagent_tokens, request_distribution_input),
        precision=agent_subagent_availability,
        source=ValueSource.LOCAL_RULES,
        confidence_label="中低" if agent_subagent_tokens > 0 else "低",
        summary=agent_subagent_summary,
        content_preview=agent_subagent_text[:120] if agent_subagent_text else "",
        details=agent_subagent_details,
    ))

    # 7. mcp_tool_metadata — MCP 工具元数据
    mcp_details = {"kind": "mcp_metadata", "items": []}
    if isinstance(mcp_tools, list) and mcp_tools:
        mcp_details["items"] = [
            {"name": str(t), "estimated_tokens": 50, "precision": "heuristic"}
            for t in mcp_tools
        ]
        mcp_details["total_items"] = len(mcp_tools)
    buckets.append(RequestAttributionBucket(
        key="mcp_tool_metadata",
        label="MCP 工具元数据",
        tokens=mcp_metadata_tokens,
        percent=_pct(mcp_metadata_tokens, request_distribution_input),
        precision=mcp_metadata_availability,
        source=ValueSource.SESSION_METADATA,
        confidence_label="中低" if mcp_metadata_tokens > 0 else "低",
        summary=mcp_metadata_summary,
        details=mcp_details,
    ))

    # 8. top_level_system_estimate — 顶层系统提示估算
    if top_level_system_tokens > 0:
        top_level_details = {
            "kind": "hidden_estimate",
            "explanation": [
                f"cache_read ({cache_read_val} tokens) 大于前序消息总量，"
                f"部分缓存 token 可能来自顶层系统提示。",
                "通过 cache_read 分析启发式估算。",
            ],
        }
        buckets.append(RequestAttributionBucket(
            key="top_level_system_estimate",
            label="顶层系统提示估算",
            tokens=top_level_system_tokens,
            percent=_pct(top_level_system_tokens, request_distribution_input),
            precision=ValuePrecision.HEURISTIC,
            source=ValueSource.HEURISTIC,
            confidence_label="低",
            summary="根据 cache_read 和前序消息量估算的顶层系统提示。",
            details=top_level_details,
        ))

    # 9. hidden_builtin_system_estimate — 内置系统提示
    hidden_builtin_precision = ValuePrecision.HEURISTIC
    hidden_builtin_source = ValueSource.HEURISTIC
    hidden_builtin_summary = (
        "Claude Code 内置 prompt 未在本地 transcript 中捕获，此处为 300-800 tokens "
        "典型值估算，非真实内容。"
    )
    if system_reminder_text:
        masked_reminder_text = mask_sensitive_keys(system_reminder_text)
        hidden_builtin_precision = ValuePrecision.ESTIMATED
        hidden_builtin_source = ValueSource.TRANSCRIPT
        hidden_builtin_summary = (
            "从本地 transcript 捕获到可见 <system-reminder> 内容，下面展示脱敏预览；"
            "它仍不代表 Claude Code 完整隐藏内置 prompt。"
        )
        hidden_builtin_details = {
            "kind": "hidden_estimate",
            "explanation": [
                f"从会话 transcript 中提取 <system-reminder> 内容，共 {len(system_reminder_text)} 字符",
                f"token 数 {hidden_builtin_tokens} 通过文本估算",
            ],
            "preview": truncate_preview(masked_reminder_text, 2000),
            "full_content": masked_reminder_text,
        }
    else:
        hidden_builtin_details = {
            "kind": "hidden_estimate",
            "explanation": [
                "Claude Code 内置隐藏 system prompt 未在本地 transcript 中捕获",
                "按 300-800 tokens 典型值估算",
            ],
        }
    buckets.append(RequestAttributionBucket(
        key="hidden_builtin_system_estimate",
        label="内置系统提示",
        tokens=hidden_builtin_tokens,
        percent=_pct(hidden_builtin_tokens, request_distribution_input),
        precision=hidden_builtin_precision,
        source=hidden_builtin_source,
        confidence_label="低",
        summary=hidden_builtin_summary,
        details=hidden_builtin_details,
    ))

    # 10. provider_wrapper_estimate — absorbed into unlocated_residual,
    # noted in attribution_notes instead of shown as a separate bucket.

    # 11. unlocated_residual — 未定位 (always LAST)
    unlocated_details = {
        "kind": "unlocated",
        "explanation": [
            "Claude Code 隐藏内置 prompt 不公开",
            "Provider 包装字段不可见",
            "Tokenizer overhead 未计入",
            "未能安全读取的本地配置",
            "raw HTTP 不可见字段",
        ],
    }
    buckets.append(RequestAttributionBucket(
        key="unlocated_residual",
        label="未定位",
        tokens=unlocated_residual,
        percent=_pct(unlocated_residual, request_distribution_input),
        precision=ValuePrecision.RESIDUAL,
        source=ValueSource.RESIDUAL,
        confidence_label="中",
        summary="Total input 减去已知所有 bucket 后的剩余部分。",
        details=unlocated_details,
    ))

    # ── Step 3b: normalize heuristic buckets ─────────────────────
    buckets = normalize_request_reconstruction_buckets(
        buckets,
        total_input=request_distribution_input,
        fresh_input=fresh_input_val,
    )

    # Extract normalized residual for unknown value.
    normalized_residual = next(
        (b.tokens for b in buckets if b.key == "unlocated_residual"),
        unlocated_residual,
    )

    # ── Step 4: coverage ───────────────────────────────────────────
    known_bucket_sum = sum(
        b.tokens for b in buckets
        if b.key not in ("unlocated_residual",) and b.contributes_to_total
    )
    if request_distribution_input > 0:
        coverage_val = min(known_bucket_sum / request_distribution_input, 1.0)
    else:
        coverage_val = 0.0

    # ── Step 5: availability rows ──────────────────────────────────
    avail_rows = [
        self._avail("total_input", "Total input tokens", True,
                    precision=ValuePrecision.PROVIDER_REPORTED,
                    source=ValueSource.PROVIDER_USAGE,
                    fill_strategy="input_tokens + cache_read_tokens + cache_write_tokens"),
        self._avail("fresh_input", "Fresh input tokens", True,
                    precision=ValuePrecision.PROVIDER_REPORTED,
                    source=ValueSource.PROVIDER_USAGE,
                    fill_strategy="input_tokens is non-cache"),
        self._avail("cache_read", "Cache read tokens", True,
                    precision=ValuePrecision.PROVIDER_REPORTED,
                    source=ValueSource.PROVIDER_USAGE,
                    fill_strategy="cache_read_input_tokens"),
        self._avail("cache_write", "Cache write tokens", True,
                    precision=ValuePrecision.PROVIDER_REPORTED,
                    source=ValueSource.PROVIDER_USAGE,
                    fill_strategy="cache_creation_input_tokens"),
        self._avail("prior_conversation_count", "Prior conversation message count",
                    prior_msg_count > 0, exact=False,
                    precision=ValuePrecision.ESTIMATED if prior_msg_count > 0 else ValuePrecision.UNAVAILABLE,
                    source=ValueSource.TRANSCRIPT if prior_msg_count > 0 else ValueSource.HEURISTIC,
                    fill_strategy="count of prior messages" if prior_msg_count > 0 else "no prior messages"),
        self._avail("prior_conversation_tokens", "Prior conversation tokens",
                    prior_conversation_tokens > 0, exact=False,
                    precision=ValuePrecision.ESTIMATED if prior_conversation_tokens > 0 else ValuePrecision.UNAVAILABLE,
                    source=ValueSource.TRANSCRIPT if prior_conversation_tokens > 0 else ValueSource.HEURISTIC,
                    fill_strategy="estimated from prior message text" if prior_conversation_tokens > 0 else "no prior messages"),
        self._avail("current_user_message_content", "Current user message content",
                    bool(user_msg_content), exact=True,
                    precision=ValuePrecision.EXACT if user_msg_content else ValuePrecision.UNAVAILABLE,
                    source=ValueSource.TRANSCRIPT,
                    fill_strategy="direct from round user_msg"),
        self._avail("current_user_message_tokens", "Current user message tokens",
                    current_user_msg_tokens > 0, exact=False,
                    precision=ValuePrecision.ESTIMATED,
                    source=ValueSource.TRANSCRIPT,
                    fill_strategy="estimated from text"),
        self._avail("tool_results_content", "Tool results content",
                    bool(tool_result_texts), exact=True,
                    precision=ValuePrecision.TRANSCRIPT_EXACT if tool_result_texts else ValuePrecision.UNAVAILABLE,
                    source=ValueSource.TOOL_LOGS,
                    fill_strategy="from tool result text"),
        self._avail("tool_results_tokens", "Tool results tokens",
                    tool_results_tokens > 0, exact=False,
                    precision=ValuePrecision.ESTIMATED,
                    source=ValueSource.TOOL_LOGS,
                    fill_strategy="estimated from text"),
        self._avail("tool_schemas_tokens", "Tool schemas tokens",
                    True, exact=False,
                    precision=tool_schemas_availability,
                    source=tool_schemas_source,
                    fill_strategy="available_tools count × real SDK schema tokens" if available_tools else "fallback to default Claude Code tool list"),
        self._avail("local_instruction_tokens", "Local instruction tokens",
                    local_instruction_tokens > 0, exact=False,
                    precision=local_instruction_availability,
                    source=ValueSource.LOCAL_RULES,
                    fill_strategy="from local_instructions or system_reminder_content"),
        self._avail("agent_subagent_tokens", "Agent/Subagent prompt tokens",
                    agent_subagent_tokens > 0, exact=False,
                    precision=agent_subagent_availability,
                    source=ValueSource.LOCAL_RULES,
                    fill_strategy="from agent_prompt_file or subagent_prompt"),
        self._avail("mcp_metadata_tokens", "MCP metadata tokens",
                    mcp_metadata_tokens > 0, exact=False,
                    precision=mcp_metadata_availability,
                    source=ValueSource.SESSION_METADATA,
                    fill_strategy="mcp_tools count × 50"),
        self._avail("unknown", "Unknown / residual", True, exact=False,
                    precision=ValuePrecision.RESIDUAL,
                    source=ValueSource.RESIDUAL,
                    fill_strategy="residual = fresh + cache_read - all_known"),
    ]

    notes = []
    if cache_read_val > 0:
        notes.append(f"Cache read {cache_read_val:,} tokens — 主要来自历史消息和系统提示，但无法逐块确认。")
    notes.append(f"Tool schemas 基于 Claude Code SDK 真实定义，{len(tools_for_schema)} 个工具共 {tool_schema_tokens} tokens。")
    if not available_tools or available_tools_source_kind == "default_builtin":
        notes.append("注意：无法从本地日志获取可用工具定义列表，使用默认工具列表代替。")
    notes.append(
        "采用 request reconstruction 方法：将原先归入 unknown 的 token 拆分为多个解释性 bucket，"
        "包括本地指令、Agent 提示、MCP 元数据、系统提示估算等。"
        "heuristic/hidden bucket 不含真实内容，仅解释 token 来源。"
    )
    notes.append(
        "Provider 包装层（元数据/thinking/output_config 等）约 50-200 tokens，"
        "不计入单独 bucket，已包含在未定位余项中。"
    )
    notes.append(NORMALIZATION_NOTE)

    # Timing extraction from llm_call.timestamp
    timing = {
        "request_at": lc.timestamp or "—",
        "response_at": "—",
        "duration": "—",
    }

    return LLMRequestAttribution(
        agent="claude_code",
        model=lc.model or "unknown",
        request_id=lc.id or "unavailable",
        call_id=lc.id,
        source_label="local logs",
        confidence_label="中高",
        raw_body_available=False,
        total_input=total_input,
        fresh_input=fresh_input,
        cache_read=cache_read,
        cache_write=cache_write,
        coverage=AttributedValue(
            value=coverage_val,
            unit="ratio",
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.HEURISTIC,
            fill_strategy="known_buckets / (fresh_input + cache_read)",
        ),
        unknown=AttributedValue(
            value=normalized_residual,
            unit="tokens",
            precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
            fill_strategy="fresh_input + cache_read - sum(all_known_buckets)",
        ),
        buckets=buckets,
        captured_context_preview="",
        attribution_notes=notes,
        availability_rows=avail_rows,
        timing=timing,
    )
