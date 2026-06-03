"""Claude Code attribution builder.

Claude Code provides the richest signal set: provider usage with
fresh/cache_read/cache_write split, transcript messages, tool results,
and content blocks.
"""

from __future__ import annotations

import json
from typing import Optional

from session_browser.domain.models import (
    LLMCall,
    ConversationRound,
    SessionSummary,
)
from session_browser.attribution.contracts import (
    AttributedValue,
    RequestAttributionBucket,
    ResponseAttributionBucket,
    LLMRequestAttribution,
    LLMResponseAttribution,
    ValuePrecision,
    ValueSource,
)
from session_browser.attribution.token_estimator import estimate_tokens_from_text
from session_browser.attribution.agents.base import BaseAttributionBuilder
from session_browser.attribution.agents.claude_code_tool_schemas import (
    _BINARY_TOOL_DESCRIPTIONS,
)

# Built-in tool descriptions for Claude Code common tools.
_TOOL_DESCRIPTIONS = {
    "Read": "读取文件内容。",
    "Write": "写入文件内容，创建新文件。",
    "Edit": "对文件进行精确的局部修改。",
    "Bash": "执行 shell 命令。",
    "Grep": "在文件中搜索文本。",
    "Glob": "按模式匹配查找文件。",
    "LS": "列出目录内容。",
    "Agent": "启动子 agent 执行任务。",
    "TodoWrite": "创建/更新任务列表。",
    "WebFetch": "获取网页内容。",
}


def _tool_description(name: str) -> str:
    """Return description for a tool.

    Uses _BINARY_TOOL_DESCRIPTIONS (full descriptions from Claude Code binary)
    as primary source, then falls back to _TOOL_DESCRIPTIONS (short Chinese),
    then to a generic fallback.
    """
    return _BINARY_TOOL_DESCRIPTIONS.get(
        name, _TOOL_DESCRIPTIONS.get(name, "工具说明未知。")
    )


def _extract_tool_name(result_text: str) -> str:
    """Attempt to extract tool name from a tool result text.

    Looks for common patterns like 'Tool Call: Name', '### Name', etc.
    Falls back to first word or 'unknown'.
    """
    if not result_text:
        return "unknown"
    # Try common header patterns
    import re as _re
    m = _re.search(r'(?:Tool|tool)[\s_]*(?:Call|Result|Output)?[:\s]+(\w+)', result_text)
    if m:
        return m.group(1)
    m = _re.search(r'^###\s+(\w+)', result_text, _re.MULTILINE)
    if m:
        return m.group(1)
    # Fallback: first word
    first = result_text.split()[0] if result_text.split() else "unknown"
    return first[:30]  # cap length


def _mask_sensitive_keys(text: str) -> str:
    """Mask sensitive key values in text for safe display."""
    # Inline implementation to avoid circular import from context.py
    sensitive_keys = frozenset({
        "api_key", "apikey", "token", "secret", "password",
        "authorization", "bearer", "credential", "env",
    })
    if not text:
        return ""
    result = text
    for key in sensitive_keys:
        # Match "key": "value" or key: value patterns
        import re as _re2
        pattern = _re2.compile(
            r'(["\']?' + _re2.escape(key) + r'["\']?\s*[:=]\s*)'
            r'(["][^"]*["]|[\'"][^\']*[\'"]|[^\n,}]+)',
            _re2.IGNORECASE,
        )
        result = pattern.sub(lambda m: m.group(1) + '***MASKED***', result)
    return result


def _truncate_preview(text: str, max_len: int = 200) -> str:
    """Truncate text to max_len characters with ellipsis."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


# Bucket classification keys for normalization.
_MEASURED_BUCKET_KEYS = {
    "current_user_message",
    "preceding_tool_results",
    "prior_conversation_messages",
}
_ESTIMATED_BUCKET_KEYS = {
    "local_instruction_context",
    "agent_subagent_prompt",
    "mcp_tool_metadata",
}
_HEURISTIC_FIXED_KEYS = {
    "hidden_builtin_system_estimate",
    "tool_schemas",
}
_HEURISTIC_SCALED_KEYS = {
    "top_level_system_estimate",
}
_NORMALIZATION_NOTE = (
    "定位率包含推断 bucket；不是 raw request 精确还原。"
)


def _scale_bucket_and_details(bucket: "RequestAttributionBucket", scale: float) -> None:
    """Scale a bucket's tokens and its details.items tokens proportionally."""
    original_tokens = bucket.tokens
    bucket.tokens = max(0, int(bucket.tokens * scale))
    if bucket.tokens == 0 and original_tokens > 0 and scale > 0:
        # Preserve a floor of 1 token if the bucket had content but scale is very small
        bucket.tokens = 1
    # Scale inner detail items proportionally
    if bucket.details and "items" in bucket.details:
        for item in bucket.details["items"]:
            if isinstance(item, dict) and "tokens" in item:
                item_tokens = item.get("tokens", 0)
                item["tokens"] = max(0, int(item_tokens * scale))
                # Preserve floor for items too
                if item["tokens"] == 0 and item_tokens > 0 and scale > 0:
                    item["tokens"] = 1


def _zero_bucket_preserve_floor(bucket: "RequestAttributionBucket") -> None:
    """Zero out a bucket but preserve a floor token if it has actual content."""
    original_tokens = bucket.tokens
    has_content = bool(
        bucket.content_preview
        or (bucket.details and bucket.details.get("items"))
    )
    if has_content and original_tokens > 0:
        # Preserve 1 token minimum for buckets with actual content
        bucket.tokens = 1
    else:
        bucket.tokens = 0
    # Also zero out detail items but preserve floor
    if bucket.details and "items" in bucket.details:
        for item in bucket.details["items"]:
            if isinstance(item, dict) and "tokens" in item:
                item_tokens = item.get("tokens", 0)
                if item_tokens > 0 and has_content:
                    item["tokens"] = 1
                else:
                    item["tokens"] = 0


def normalize_request_reconstruction_buckets(
    buckets: list["RequestAttributionBucket"],
    *,
    total_input: int,
    fresh_input: int,
) -> list["RequestAttributionBucket"]:
    """Normalize heuristic buckets so they cannot inflate located_rate beyond total_input.

    Rules:
    1. Classify buckets into measured, estimated, heuristic_fixed, heuristic_scaled.
    2. measured_sum = sum(measured buckets)
    3. estimated_sum = sum(estimated buckets)
    4. heuristic_budget = max(0, fresh_input - measured_sum - estimated_sum)
    5. If heuristic_fixed_sum > heuristic_budget, scale heuristic_fixed proportionally.
    6. If estimated_sum > (total_input - measured_sum), scale estimated proportionally.
       NOTE: estimated uses total_input (not fresh_input) because estimated buckets
       represent content that cannot be cached — they should not be crushed when
       fresh_input is small due to high cache hit rate.
    7. Recompute unlocated_residual = max(total_input - known_sum, 0).
    8. Recompute coverage = min(known_sum / total_input, 1.0).
    9. Never scale measured buckets down.
    10. Add note to attribution_notes if normalization was applied.

    The function modifies bucket tokens/percent in place and returns the list.
    """
    if not buckets or fresh_input <= 0:
        return buckets

    measured_sum = 0
    estimated_sum = 0
    heuristic_fixed_sum = 0
    heuristic_scaled_sum = 0
    residual_tokens = 0

    measured_buckets = []
    estimated_buckets = []
    heuristic_fixed_buckets = []
    heuristic_scaled_buckets = []
    residual_bucket = None

    for b in buckets:
        if b.key in _MEASURED_BUCKET_KEYS:
            measured_sum += b.tokens
            measured_buckets.append(b)
        elif b.key in _ESTIMATED_BUCKET_KEYS:
            estimated_sum += b.tokens
            estimated_buckets.append(b)
        elif b.key in _HEURISTIC_FIXED_KEYS:
            heuristic_fixed_sum += b.tokens
            heuristic_fixed_buckets.append(b)
        elif b.key in _HEURISTIC_SCALED_KEYS:
            heuristic_scaled_sum += b.tokens
            heuristic_scaled_buckets.append(b)
        elif b.key in ("unlocated_residual", "unknown_overhead", "unknown"):
            residual_tokens = b.tokens
            residual_bucket = b

    normalization_applied = False

    # Step 5: Scale heuristic_fixed if they exceed budget
    heuristic_budget = max(0, fresh_input - measured_sum - estimated_sum)
    if heuristic_fixed_sum > heuristic_budget and heuristic_budget > 0:
        scale = heuristic_budget / heuristic_fixed_sum
        for b in heuristic_fixed_buckets:
            _scale_bucket_and_details(b, scale)
        heuristic_fixed_sum = sum(b.tokens for b in heuristic_fixed_buckets)
        normalization_applied = True
    # NOTE: When heuristic_budget <= 0 (measured + estimated already exhausts
    # fresh_input), we do NOT zero out heuristic_fixed buckets.  These
    # represent real known token costs (e.g. tool_schemas from SDK definitions).
    # Instead, let the unlocated_residual absorb the overflow by becoming 0.

    # Step 6: Scale estimated if they exceed remaining budget.
    # Use total_input (not fresh_input) as the budget because estimated buckets
    # represent content that cannot be cached (CLAUDE.md, agent prompts, etc.).
    # They are real token costs that should fit within total_input, not fresh_input.
    # When cache hit rate is high, fresh_input can be much smaller than measured_sum,
    # which would incorrectly zero out estimated buckets with actual content.
    remaining_for_estimated = max(0, total_input - measured_sum)
    if estimated_sum > remaining_for_estimated and remaining_for_estimated > 0:
        scale = remaining_for_estimated / estimated_sum
        for b in estimated_buckets:
            _scale_bucket_and_details(b, scale)
        estimated_sum = sum(b.tokens for b in estimated_buckets)
        normalization_applied = True
    elif estimated_sum > remaining_for_estimated and remaining_for_estimated <= 0:
        # When measured already fills/exceeds total_input, preserve estimated
        # buckets at their original values — they represent real content.
        # Let unlocated_residual absorb the overflow by becoming 0.
        normalization_applied = True

    # Step 7: Recompute unlocated_residual
    known_sum = (
        measured_sum + estimated_sum + heuristic_fixed_sum + heuristic_scaled_sum
    )
    new_residual = max(total_input - known_sum, 0) if total_input > 0 else 0
    if residual_bucket:
        residual_bucket.tokens = new_residual

    # Recompute percentages for all buckets
    for b in buckets:
        b.percent = _pct(b.tokens, total_input)

    # Step 10: Add normalization note
    if normalization_applied:
        # The caller should add this to attribution_notes
        pass  # note is added by the builder

    return buckets


class ClaudeCodeAttributionBuilder(BaseAttributionBuilder):
    """Request / response attribution for Claude Code sessions."""

    # ── Helpers ─────────────────────────────────────────────────────────

    def _extract_prior_messages(self) -> list[dict]:
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

    def _get_available_tools(self) -> list[str]:
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

    def build_request(self) -> LLMRequestAttribution:
        lc = self.llm_call
        ro = self.round_obj

        # ── Step 1: provider usage (authoritative) ─────────────────────
        # Claude Code fields:
        #   input_tokens  = non-cache input (fresh)
        #   cache_read_input_tokens / cached_input_tokens = cache read
        #   cache_creation_input_tokens = cache write
        #   total = input + cache_read + cache_write (exclusive components)
        total_input_val = lc.input_tokens or 0
        cache_read_val = lc.cache_read_tokens or 0
        cache_write_val = lc.cache_write_tokens or 0

        # input_tokens in Claude Code JSONL usage is the fresh (non-cache)
        # input — it does NOT include cache_read.  So fresh_input == input_tokens.
        fresh_input_val = total_input_val

        total_call_input = total_input_val + cache_read_val + cache_write_val

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
        prior_messages = self._extract_prior_messages()
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

        # Tool schemas: use real JSON Schema definitions extracted from
        # Claude Code npm package (sdk-tools.d.ts) for accurate token
        # counting, instead of the old per-tool heuristic.
        available_tools = self._get_available_tools()
        # When available_tools is empty (e.g. tool_calls_raw not parseable),
        # fall back to the full Claude Code SDK tool registry so that the
        # token count and bucket details use the same comprehensive list.
        from session_browser.attribution.agents.claude_code_tool_schemas import (
            ALL_CLAUDE_CODE_TOOLS,
        )
        tools_for_schema = available_tools if available_tools else ALL_CLAUDE_CODE_TOOLS
        tool_schema_tokens = 0
        tool_schemas_availability = ValuePrecision.UNAVAILABLE
        tool_schemas_source = ValueSource.HEURISTIC
        tool_schemas_summary = (
            "无法从本地日志获取可用工具定义列表；不能用实际 tool calls 代替 tool schemas。"
        )
        # Always compute tokens against the list that will be displayed.
        from session_browser.attribution.agents.claude_code_tool_schemas import (
            get_all_tool_schema_tokens,
            get_cached_schemas,
        )
        schemas = get_cached_schemas()
        tool_schema_tokens = get_all_tool_schema_tokens(tools_for_schema, schemas)
        if available_tools:
            tool_schemas_availability = ValuePrecision.ESTIMATED
            tool_schemas_source = ValueSource.TOOL_LIST
        tool_schemas_summary = (
            f"基于 Claude Code SDK 真实 tool schema 定义，"
            f"{len(tools_for_schema)} 个工具共 {tool_schema_tokens} tokens。"
        )

        # Local instruction context: look for system-reminder content in
        # session_context or round user_msg.
        local_instruction_tokens = 0
        local_instruction_text = ""
        local_instruction_availability = ValuePrecision.UNAVAILABLE
        local_instruction_summary = "未检测到本地指令上下文。"
        ctx = self.session_context or {}
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

        # Top-level system estimate: if cache_read > 0 and prior messages are
        # small, some tokens are likely system-level.
        top_level_system_tokens = 0
        if cache_read_val > 0 and prior_conversation_tokens < cache_read_val:
            # Some cache tokens are likely system-level content.
            known_before_system = (
                current_user_msg_tokens + tool_results_tokens
                + prior_conversation_tokens + tool_schema_tokens
                + local_instruction_tokens + agent_subagent_tokens
                + mcp_metadata_tokens
            )
            top_level_system_tokens = min(500, max(0, total_call_input - known_before_system))
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
            + prior_conversation_tokens + tool_schema_tokens
            + local_instruction_tokens + agent_subagent_tokens
            + mcp_metadata_tokens + top_level_system_tokens
            + hidden_builtin_tokens
        )

        unlocated_residual = max(total_call_input - known_sum, 0) if total_call_input > 0 else 0

        buckets = []

        # 1. current_user_message — 当前用户输入
        if current_user_msg_tokens > 0:
            masked_user_content = _mask_sensitive_keys(user_msg_content or "")
            current_user_details = {
                "kind": "current_user_message",
                "preview": _truncate_preview(masked_user_content, 1000),
                "tokens": current_user_msg_tokens,
            }
            buckets.append(RequestAttributionBucket(
                key="current_user_message",
                label="当前用户输入",
                tokens=current_user_msg_tokens,
                percent=_pct(current_user_msg_tokens, total_call_input),
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
                        "tool_name": _extract_tool_name(rt),
                        "summary": _truncate_preview(_mask_sensitive_keys(rt), 180),
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
                percent=_pct(tool_results_tokens, total_call_input),
                count_label=f"{len(tool_result_texts)} results" if tool_result_texts else "",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TOOL_LOGS,
                confidence_label="中",
                summary="前序 Tool result 内容可从 tool logs 获取，token 通过文本估算。",
                details=preceding_tool_details,
            ))

        # 3. prior_conversation_messages — 前序对话消息
        if prior_conversation_tokens > 0 and prior_messages:
            prior_details = {
                "kind": "message_history",
                "items": [
                    {
                        "round_id": i + 1,
                        "role": pm.get("role", "unknown"),
                        "summary": _truncate_preview(
                            pm.get("content_preview", pm.get("content", "")), 180,
                        ),
                        "timestamp": "",  # not available from context
                        "tokens": pm.get("content_token_estimate", 0),
                    }
                    for i, pm in enumerate(prior_messages)
                ],
                "total_items": len(prior_messages),
                "truncated": False,
            }
            buckets.append(RequestAttributionBucket(
                key="prior_conversation_messages",
                label="前序对话消息",
                tokens=prior_conversation_tokens,
                percent=_pct(prior_conversation_tokens, total_call_input),
                count_label=f"{prior_msg_count} messages",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="前序对话消息从 prior messages 列表获取，token 通过文本估算。",
                content_preview=lc.request_preview[:120] if lc.request_preview else "",
                details=prior_details,
            ))

        # 4. tool_schemas — 工具定义
        # Import schema extractor for per-tool token counts
        from session_browser.attribution.agents.claude_code_tool_schemas import (
            get_cached_schemas,
            get_tool_schema_tokens as _real_schema_tokens,
        )
        _schemas_for_detail = get_cached_schemas()

        tool_schemas_details = {
            "kind": "tools",
            "items": [
                {
                    "name": tool_name,
                    "source": "available_tools" if available_tools else "default_fallback",
                    "enabled": True,
                    "description_preview": _tool_description(tool_name),
                    "estimated_tokens": _real_schema_tokens(tool_name, _schemas_for_detail),
                    "precision": "extracted_from_sdk",
                    "description": _tool_description(tool_name),
                    "input_schema": json.dumps(
                        _schemas_for_detail.get(tool_name, {}).get("input_schema", {}),
                        ensure_ascii=False, indent=2,
                    ) if tool_name in _schemas_for_detail else "",
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
            percent=_pct(tool_schema_tokens, total_call_input),
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
            masked_text = _mask_sensitive_keys(ctx["local_instructions"])
            local_instruction_details["items"].append({
                "file_path": "CLAUDE.md",
                "source_type": "project_instructions",
                "preview": _truncate_preview(masked_text, 500),
                "tokens": local_instruction_tokens,
                "precision": "heuristic",
            })
        if ctx.get("system_reminder_content"):
            masked_reminder = _mask_sensitive_keys(ctx["system_reminder_content"])
            local_instruction_details["items"].append({
                "file_path": "system-reminder",
                "source_type": "transcript_system_reminder",
                "preview": _truncate_preview(masked_reminder, 500),
                "tokens": estimate_tokens_from_text(ctx["system_reminder_content"]),
                "precision": "heuristic",
            })
        buckets.append(RequestAttributionBucket(
            key="local_instruction_context",
            label="本地指令上下文",
            tokens=local_instruction_tokens,
            percent=_pct(local_instruction_tokens, total_call_input),
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
            masked_agent = _mask_sensitive_keys(ctx["subagent_prompt"])
            agent_subagent_details["items"].append({
                "file_path": f".claude/agents/{agent_name_for_path or 'unknown'}.md",
                "source_type": "agent_prompt",
                "preview": _truncate_preview(masked_agent, 500),
                "tokens": agent_subagent_tokens,
                "precision": "heuristic",
            })
        buckets.append(RequestAttributionBucket(
            key="agent_subagent_prompt",
            label="Agent/Subagent 提示",
            tokens=agent_subagent_tokens,
            percent=_pct(agent_subagent_tokens, total_call_input),
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
            percent=_pct(mcp_metadata_tokens, total_call_input),
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
                percent=_pct(top_level_system_tokens, total_call_input),
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.HEURISTIC,
                confidence_label="低",
                summary="根据 cache_read 和前序消息量估算的顶层系统提示。",
                details=top_level_details,
            ))

        # 9. hidden_builtin_system_estimate — 内置系统提示
        if system_reminder_text:
            hidden_builtin_details = {
                "kind": "hidden_estimate",
                "explanation": [
                    f"从会话 transcript 中提取 <system-reminder> 内容，共 {len(system_reminder_text)} 字符",
                    f"token 数 {hidden_builtin_tokens} 通过文本估算",
                ],
            }
        else:
            hidden_builtin_details = {
                "kind": "hidden_estimate",
                "explanation": [
                    "Claude Code 内置隐藏 system prompt 不可见",
                    "按 300-800 tokens 典型值估算",
                ],
            }
        buckets.append(RequestAttributionBucket(
            key="hidden_builtin_system_estimate",
            label="内置系统提示",
            tokens=hidden_builtin_tokens,
            percent=_pct(hidden_builtin_tokens, total_call_input),
            precision=ValuePrecision.HEURISTIC,
            source=ValueSource.HEURISTIC,
            confidence_label="低",
            summary=(
                "Claude Code 内置 prompt 不公开，此处为 300-800 tokens 典型值估算，"
                "非真实内容。"
            ),
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
            percent=_pct(unlocated_residual, total_call_input),
            precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
            confidence_label="中",
            summary="Total input 减去已知所有 bucket 后的剩余部分。",
            details=unlocated_details,
        ))

        # ── Step 3b: normalize heuristic buckets ─────────────────────
        buckets = normalize_request_reconstruction_buckets(
            buckets,
            total_input=total_call_input,
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
        if total_call_input > 0:
            coverage_val = min(known_bucket_sum / total_call_input, 1.0)
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
                        fill_strategy="residual = total - all_known"),
        ]

        notes = []
        if cache_read_val > 0:
            notes.append(f"Cache read {cache_read_val:,} tokens — 主要来自历史消息和系统提示，但无法逐块确认。")
        notes.append(f"Tool schemas 基于 Claude Code SDK 真实定义，{len(tools_for_schema)} 个工具共 {tool_schema_tokens} tokens。")
        if not available_tools:
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
        notes.append(_NORMALIZATION_NOTE)

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
                fill_strategy="known_buckets / total_input",
            ),
            unknown=AttributedValue(
                value=normalized_residual,
                unit="tokens",
                precision=ValuePrecision.RESIDUAL,
                source=ValueSource.RESIDUAL,
                fill_strategy="total - sum(all_known_buckets)",
            ),
            buckets=buckets,
            captured_context_preview="",
            attribution_notes=notes,
            availability_rows=avail_rows,
            timing=timing,
        )

    def build_response(self) -> LLMResponseAttribution:
        lc = self.llm_call

        total_output_val = lc.output_tokens or 0

        # ── Step 1: visible content estimation ─────────────────────────
        response_text = lc.response_full or ""
        visible_text_tokens = estimate_tokens_from_text(response_text)

        # Tool use blocks — include both tool definition (description + input_schema)
        # and actual call (tool_use content block) for accurate token accounting.
        from session_browser.attribution.agents.claude_code_tool_schemas import (
            get_cached_schemas,
        )

        schemas = get_cached_schemas()
        tool_use_schema_tokens = 0      # definition (description + input_schema)
        tool_use_call_tokens = 0        # actual tool_use block (name + input)
        tool_use_json_parts = []
        tool_use_detail_items = []

        for cb in (lc.content_blocks or []):
            if cb.get("type") == "tool_use":
                tname = cb.get("name", "unknown")
                # 1. Tool definition tokens (schema: description + input_schema)
                schema_text = json.dumps(schemas.get(tname, {}), ensure_ascii=False) if tname in schemas else ""
                schema_tok = estimate_tokens_from_text(schema_text) if schema_text else 0
                tool_use_schema_tokens += schema_tok

                # 2. Tool call tokens (actual tool_use content block)
                call_text = json.dumps(cb, ensure_ascii=False)
                call_tok = estimate_tokens_from_text(call_text)
                tool_use_call_tokens += call_tok
                tool_use_json_parts.append(call_text)

                # 3. Per-tool detail for bucket display
                tool_def = schemas.get(tname, {})
                desc_preview = tool_def.get("description", _tool_description(tname))[:200]
                input_props = tool_def.get("input_schema", {}).get("properties", {})
                input_schema_preview = ""
                if input_props:
                    input_schema_preview = ", ".join(list(input_props.keys())[:5])
                    if len(input_props) > 5:
                        input_schema_preview += f", ...(+{len(input_props) - 5})"

                tool_use_detail_items.append({
                    "name": tname,
                    "tool_use_id": cb.get("id", ""),
                    "schema_tokens": schema_tok,
                    "call_tokens": call_tok,
                    "total_tokens": schema_tok + call_tok,
                    "description_preview": desc_preview,
                    "input_schema_properties": input_schema_preview,
                    "call_input_preview": _truncate_preview(
                        json.dumps(cb.get("input", {}), ensure_ascii=False)[:200], 120,
                    ),
                })

        # Fallback: use tool_calls_raw if content_blocks unavailable
        if not tool_use_json_parts and lc.tool_calls_raw:
            tool_use_call_tokens = estimate_tokens_from_text(lc.tool_calls_raw)

        tool_use_tokens = tool_use_schema_tokens + tool_use_call_tokens

        # Metadata tokens: small heuristic value for non-content fields
        metadata_tokens = 0
        if lc.finish_reason:
            metadata_tokens += 10  # finish_reason
        if lc.tool_calls_raw:
            metadata_tokens += 20  # raw structure overhead

        # ── Step 2: normalize against total ────────────────────────────
        known_sum = visible_text_tokens + tool_use_tokens + metadata_tokens

        if total_output_val > 0:
            if known_sum > total_output_val:
                # Normalize: scale down estimated parts proportionally
                scale = total_output_val / known_sum
                visible_text_tokens = max(0, int(visible_text_tokens * scale))
                tool_use_tokens = max(0, int(tool_use_tokens * scale))
                metadata_tokens = max(0, int(metadata_tokens * scale))
                known_sum = visible_text_tokens + tool_use_tokens + metadata_tokens
            unknown_val = total_output_val - known_sum
        else:
            unknown_val = 0
            total_output_val = known_sum  # fallback: estimated total

        total_output = AttributedValue(
            value=total_output_val,
            unit="tokens",
            precision=ValuePrecision.PROVIDER_REPORTED if lc.output_tokens > 0 else ValuePrecision.ESTIMATED,
            source=ValueSource.PROVIDER_USAGE if lc.output_tokens > 0 else ValueSource.HEURISTIC,
            fill_strategy="provider output_tokens" if lc.output_tokens > 0 else "sum of visible content",
        )

        # ── Step 3: buckets ────────────────────────────────────────────
        buckets = []

        if visible_text_tokens > 0:
            buckets.append(ResponseAttributionBucket(
                key="assistant_text",
                label="Assistant text",
                tokens=visible_text_tokens,
                percent=_pct(visible_text_tokens, total_output_val),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中高",
                summary="助手文本内容可从 transcript 获取，token 通过文本估算。",
            ))

        if tool_use_tokens > 0:
            # Per-tool breakdown (children, contributes_to_total=False)
            block_refs = []
            for item in tool_use_detail_items:
                buckets.append(ResponseAttributionBucket(
                    key=f"tool_use:{item['name']}",
                    label=f"tool_use: {item['name']}",
                    tokens=item['total_tokens'],
                    percent=0.0,
                    precision=ValuePrecision.ESTIMATED,
                    source=ValueSource.TRANSCRIPT,
                    confidence_label="中",
                    summary=(
                        f"工具定义 {item['schema_tokens']} tokens + "
                        f"调用参数 {item['call_tokens']} tokens"
                    ),
                    contributes_to_total=False,
                    parent_key="tool_use",
                    display_group="tool_use",
                ))
                block_refs.append(item['tool_use_id'])

            tool_use_details = {
                "kind": "tool_use",
                "total_schema_tokens": tool_use_schema_tokens,
                "total_call_tokens": tool_use_call_tokens,
                "total_items": len(tool_use_detail_items),
                "items": tool_use_detail_items,
            }
            buckets.append(ResponseAttributionBucket(
                key="tool_use",
                label="Tool use (total)",
                tokens=tool_use_tokens,
                percent=_pct(tool_use_tokens, total_output_val),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary=(
                    f"工具使用：{tool_use_schema_tokens} tokens 定义 + "
                    f"{tool_use_call_tokens} tokens 调用参数，"
                    f"共 {len(tool_use_detail_items)} 个工具调用。"
                ),
                block_refs=block_refs,
                contributes_to_total=True,
                details=tool_use_details,
            ))

        if metadata_tokens > 0:
            buckets.append(ResponseAttributionBucket(
                key="metadata",
                label="Metadata",
                tokens=metadata_tokens,
                percent=_pct(metadata_tokens, total_output_val),
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.SESSION_METADATA,
                confidence_label="低",
                summary="可见字段（如 finish_reason）估算。",
            ))

        buckets.append(ResponseAttributionBucket(
            key="unknown",
            label="Unknown",
            tokens=unknown_val,
            percent=_pct(unknown_val, total_output_val),
            precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
            confidence_label="中",
            summary="Total output 减去已知 bucket 后的剩余部分。",
        ))

        # ── Step 4: coverage (only counts contributes_to_total=True) ─────
        known_bucket_sum = sum(
            b.tokens for b in buckets
            if b.key != "unknown" and b.contributes_to_total
        )
        coverage_val = min(known_bucket_sum / total_output_val, 1.0) if total_output_val > 0 else 0.0

        # ── Step 5: availability rows ──────────────────────────────────
        avail_rows = [
            self._avail("total_output", "Total output tokens", True,
                        precision=ValuePrecision.PROVIDER_REPORTED if lc.output_tokens > 0 else ValuePrecision.ESTIMATED,
                        source=ValueSource.PROVIDER_USAGE if lc.output_tokens > 0 else ValueSource.HEURISTIC,
                        fill_strategy="provider output_tokens" if lc.output_tokens > 0 else "sum of visible content"),
            self._avail("assistant_text_content", "Assistant text content", bool(response_text),
                        exact=True,
                        precision=ValuePrecision.TRANSCRIPT_EXACT if response_text else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="direct from response_full"),
            self._avail("assistant_text_tokens", "Assistant text tokens", True,
                        exact=False,
                        precision=ValuePrecision.ESTIMATED,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="estimated from text"),
            self._avail("tool_use_structure", "Tool use structure",
                        bool(lc.content_blocks or lc.tool_calls_raw), exact=True,
                        precision=ValuePrecision.TRANSCRIPT_EXACT,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="from content_blocks or tool_calls_raw"),
            self._avail("tool_use_tokens", "Tool use tokens", True,
                        exact=False,
                        precision=ValuePrecision.ESTIMATED,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="estimated from JSON"),
            self._avail("metadata", "Metadata", True,
                        exact=False,
                        precision=ValuePrecision.HEURISTIC,
                        source=ValueSource.SESSION_METADATA,
                        fill_strategy="visible field count heuristic"),
            self._avail("finish_reason", "Finish reason", bool(lc.finish_reason),
                        exact=True,
                        precision=ValuePrecision.EXACT if lc.finish_reason else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="from llm_call.finish_reason"),
            self._avail("blocks_count", "Blocks count", True,
                        exact=True,
                        precision=ValuePrecision.EXACT,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy=f"{len(lc.content_blocks)} blocks" if lc.content_blocks else "0"),
            self._avail("unknown", "Unknown / residual", True, exact=False,
                        precision=ValuePrecision.RESIDUAL,
                        source=ValueSource.RESIDUAL,
                        fill_strategy="residual"),
        ]

        notes = []
        finish_r = lc.finish_reason or ""
        if finish_r and finish_r not in ("end_turn", "tool_use", "stop"):
            notes.append(f"finish_reason: {finish_r} — 可能影响归因完整性。")

        return LLMResponseAttribution(
            agent="claude_code",
            model=lc.model or "unknown",
            request_id=lc.id or "unavailable",
            call_id=lc.id,
            source_label="local logs",
            confidence_label="中高",
            raw_body_available=False,
            total_output=total_output,
            visible_text=AttributedValue(
                value=visible_text_tokens,
                unit="tokens",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                fill_strategy="estimate_tokens_from_text(response_full)",
            ),
            tool_use=AttributedValue(
                value=tool_use_tokens,
                unit="tokens",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                fill_strategy="estimate_tokens_from_text(serialized tool_use blocks)",
            ),
            metadata=AttributedValue(
                value=metadata_tokens,
                unit="tokens",
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.SESSION_METADATA,
                fill_strategy="visible field count heuristic",
            ),
            coverage=AttributedValue(
                value=coverage_val,
                unit="ratio",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.HEURISTIC,
                fill_strategy="known_buckets / total_output",
            ),
            unknown=AttributedValue(
                value=unknown_val,
                unit="tokens",
                precision=ValuePrecision.RESIDUAL,
                source=ValueSource.RESIDUAL,
                fill_strategy="total - sum(known_buckets)",
            ),
            finish_reason=AttributedValue(
                value=finish_r,
                unit="str",
                precision=ValuePrecision.EXACT if finish_r else ValuePrecision.UNAVAILABLE,
                source=ValueSource.TRANSCRIPT,
                fill_strategy="from llm_call.finish_reason",
            ),
            buckets=buckets,
            blocks=lc.content_blocks or [],
            captured_output_preview=lc.response_preview or "",
            attribution_notes=notes,
            availability_rows=avail_rows,
        )


def _pct(part: int, total: int) -> float:
    """Compute percentage, safe for zero total."""
    if total <= 0:
        return 0.0
    return round(part / total * 100, 1)
