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


# Default schema token estimate per tool when we can only count tools.
_DEFAULT_SCHEMA_TOKENS_PER_TOOL = 240


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

        # History messages: extract prior messages from session_context
        prior_messages = self._extract_prior_messages()
        prior_message_texts = []
        for pm in prior_messages:
            if isinstance(pm, dict):
                prior_message_texts.append(pm.get("content", ""))
            else:
                prior_message_texts.append(str(pm))
        history_msg_count = len(prior_messages)
        history_visible_tokens = 0
        if prior_messages:
            history_visible_tokens = estimate_tokens_from_text("\n".join(prior_message_texts))

        # Captured context fragment: request_full content that is NOT
        # classified as prior messages, current user message, or preceding
        # tool results.  Deduplicate to avoid double-counting.
        captured_context_tokens = 0
        captured_context_text = ""
        if lc.request_full:
            known_fragments = [
                user_msg_content,
                *prior_message_texts,
                *tool_result_texts,
            ]
            deduped = self._remove_known_fragments(lc.request_full, known_fragments)
            if deduped:
                captured_context_text = deduped[:3000]
                captured_context_tokens = estimate_tokens_from_text(captured_context_text)

        # Tool schemas: ONLY from available_tools list, NOT from observed
        # tool_calls.  Tool schemas refers to the list of tools available to
        # the model, not the tools actually called this round.
        available_tools = self._get_available_tools()
        tool_schema_tokens = 0
        tool_schemas_availability = ValuePrecision.UNAVAILABLE
        tool_schemas_source = ValueSource.HEURISTIC
        tool_schemas_summary = (
            "无法从本地日志获取可用工具定义列表；不能用实际 tool calls 代替 tool schemas。"
        )
        if available_tools:
            tool_schema_tokens = len(available_tools) * _DEFAULT_SCHEMA_TOKENS_PER_TOOL
            tool_schemas_availability = ValuePrecision.HEURISTIC
            tool_schemas_source = ValueSource.TOOL_LIST
            tool_schemas_summary = (
                f"按 {len(available_tools)} 个可用工具 × {_DEFAULT_SCHEMA_TOKENS_PER_TOOL} tokens/tool 估算。"
            )
        # Note: when available_tools is empty, tool_schema_tokens stays 0
        # and we do NOT generate a tool_schemas bucket.

        # System/developer rules: unknown for now (heuristic low)
        system_rules_tokens = 0  # would need CLAUDE.md / AGENTS.md analysis

        # ── Step 3: assemble buckets and normalize ─────────────────────
        known_sum = (current_user_msg_tokens + tool_results_tokens
                     + history_visible_tokens + captured_context_tokens
                     + tool_schema_tokens + system_rules_tokens)

        if total_call_input > 0:
            unknown_val = max(total_call_input - known_sum, 0)
        else:
            unknown_val = 0

        buckets = []

        # History messages — ONLY if we have explicit prior messages
        if history_visible_tokens > 0 and prior_messages:
            buckets.append(RequestAttributionBucket(
                key="history_messages",
                label="History messages",
                tokens=history_visible_tokens,
                percent=_pct(history_visible_tokens, total_call_input),
                count_label=f"{history_msg_count} messages",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="历史消息从 prior messages 列表获取，token 通过文本估算。",
                content_preview=lc.request_preview[:120] if lc.request_preview else "",
            ))

        # Captured context fragment — when request_full exists but cannot be classified
        if captured_context_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="captured_context_fragment",
                label="Captured context / unknown",
                tokens=captured_context_tokens,
                percent=_pct(captured_context_tokens, total_call_input),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="低",
                summary="request_full 中存在但无法分类为历史消息的上下文片段。",
                content_preview=captured_context_text[:120] if captured_context_text else "",
            ))

        # Tool results
        if tool_results_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_results",
                label="Tool results",
                tokens=tool_results_tokens,
                percent=_pct(tool_results_tokens, total_call_input),
                count_label=f"{len(tool_result_texts)} results" if tool_result_texts else "",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TOOL_LOGS,
                confidence_label="中",
                summary="Tool result 内容可从 tool logs 获取，token 通过文本估算。",
            ))

        # Current user message
        if current_user_msg_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="current_user_message",
                label="Current user message",
                tokens=current_user_msg_tokens,
                percent=_pct(current_user_msg_tokens, total_call_input),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中高",
                summary="用户消息内容完整可用，token 通过文本估算。",
                content_preview=(user_msg_content or "")[:120],
            ))

        # Tool schemas — ONLY when we have available_tools (not observed calls)
        if tool_schema_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_schemas",
                label="Tool schemas",
                tokens=tool_schema_tokens,
                percent=_pct(tool_schema_tokens, total_call_input),
                count_label=f"{len(available_tools)} tools",
                precision=tool_schemas_availability,
                source=tool_schemas_source,
                confidence_label="中低",
                summary=tool_schemas_summary,
            ))
        elif not available_tools:
            # Generate a zero-token bucket so UI can show "unavailable"
            buckets.append(RequestAttributionBucket(
                key="tool_schemas",
                label="Tool schemas",
                tokens=0,
                percent=0.0,
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                confidence_label="低",
                summary=tool_schemas_summary,
            ))

        # System / developer rules
        if system_rules_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="system_developer_rules",
                label="System / Developer rules",
                tokens=system_rules_tokens,
                percent=_pct(system_rules_tokens, total_call_input),
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.LOCAL_RULES,
                confidence_label="低",
                summary="系统/开发者规则 token 估算，置信度低。",
            ))

        # Unknown / overhead
        buckets.append(RequestAttributionBucket(
            key="unknown_overhead",
            label="Unknown / unattributed",
            tokens=unknown_val,
            percent=_pct(unknown_val, total_call_input),
            precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
            confidence_label="中",
            summary="Total input 减去已知 bucket 后的剩余部分。",
        ))

        # ── Step 4: coverage ───────────────────────────────────────────
        known_bucket_sum = sum(
            b.tokens for b in buckets
            if b.key not in ("unknown_overhead",) and b.contributes_to_total
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
            self._avail("history_messages_count", "History message count",
                        history_msg_count > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if history_msg_count > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT if history_msg_count > 0 else ValueSource.HEURISTIC,
                        fill_strategy="count of prior messages" if history_msg_count > 0 else "no prior messages"),
            self._avail("history_messages_tokens", "History message tokens",
                        history_visible_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if history_visible_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT if history_visible_tokens > 0 else ValueSource.HEURISTIC,
                        fill_strategy="estimated from prior message text" if history_visible_tokens > 0 else "no prior messages"),
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
                        bool(available_tools), exact=False,
                        precision=tool_schemas_availability,
                        source=tool_schemas_source,
                        fill_strategy="available_tools count × constant" if available_tools else "no available_tools list"),
            self._avail("system_developer_rules_tokens", "System/developer rules tokens",
                        False,
                        precision=ValuePrecision.UNAVAILABLE,
                        source=ValueSource.HEURISTIC,
                        fill_strategy="not parsed from local rules"),
            self._avail("unknown", "Unknown / residual", True, exact=False,
                        precision=ValuePrecision.RESIDUAL,
                        source=ValueSource.RESIDUAL,
                        fill_strategy="residual = total - known"),
        ]

        notes = []
        if cache_read_val > 0:
            notes.append(f"Cache read {cache_read_val:,} tokens — 主要来自历史消息，但无法逐块确认。")
        if available_tools:
            notes.append(f"Tool schemas 按 {len(available_tools)} available tools × {_DEFAULT_SCHEMA_TOKENS_PER_TOOL} tokens 估算。")
        else:
            notes.append("Tool schemas: 无法从本地日志获取可用工具定义列表，未生成正数 tool_schemas bucket。")
        if not prior_messages and lc.request_full:
            notes.append("History messages: 无明确 prior messages，request_full 内容归入 captured_context_fragment。")

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
                value=unknown_val,
                unit="tokens",
                precision=ValuePrecision.RESIDUAL,
                source=ValueSource.RESIDUAL,
                fill_strategy="total - sum(known_buckets)",
            ),
            buckets=buckets,
            captured_context_preview=captured_context_text[:500] if captured_context_text else "",
            attribution_notes=notes,
            availability_rows=avail_rows,
        )

    def build_response(self) -> LLMResponseAttribution:
        lc = self.llm_call

        total_output_val = lc.output_tokens or 0

        # ── Step 1: visible content estimation ─────────────────────────
        response_text = lc.response_full or ""
        visible_text_tokens = estimate_tokens_from_text(response_text)

        # Tool use blocks
        tool_use_tokens = 0
        tool_use_json_parts = []
        for cb in (lc.content_blocks or []):
            if cb.get("type") == "tool_use":
                tool_use_json_parts.append(json.dumps(cb, ensure_ascii=False))
        if tool_use_json_parts:
            tool_use_tokens = estimate_tokens_from_text("\n".join(tool_use_json_parts))
        elif lc.tool_calls_raw:
            tool_use_tokens = estimate_tokens_from_text(lc.tool_calls_raw)

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
            for cb in (lc.content_blocks or []):
                if cb.get("type") == "tool_use":
                    tname = cb.get("name", "unknown")
                    buckets.append(ResponseAttributionBucket(
                        key=f"tool_use:{tname}",
                        label=f"tool_use: {tname}",
                        tokens=estimate_tokens_from_text(json.dumps(cb, ensure_ascii=False)),
                        percent=0.0,  # computed per-call
                        precision=ValuePrecision.ESTIMATED,
                        source=ValueSource.TRANSCRIPT,
                        confidence_label="中",
                        summary=f"Tool use block 结构可从 content_blocks 获取。",
                        contributes_to_total=False,
                        parent_key="tool_use",
                        display_group="tool_use",
                    ))
                    block_refs.append(cb.get("id", ""))

            buckets.append(ResponseAttributionBucket(
                key="tool_use",
                label="Tool use (total)",
                tokens=tool_use_tokens,
                percent=_pct(tool_use_tokens, total_output_val),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="Tool use 结构可从 content_blocks 获取，token 通过 JSON 序列化估算。",
                block_refs=block_refs,
                contributes_to_total=True,
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
