"""Qoder attribution builder.

Qoder 是 broker/runtime。通过标准化后的 LLMCall 字段获取真实 usage 数据：
- ``lc.input_tokens`` 经 normalizer 改写后为 fresh input
- ``lc.cache_read_tokens`` 对应 cache_read_input_tokens
- ``lc.cache_write_tokens`` 对应 cache_creation_input_tokens（provider-reported）
- total = fresh + cache_read + cache_write
- 0 是有效值，不能显示为 unavailable。
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


_DEFAULT_SCHEMA_TOKENS_PER_TOOL = 240


class QoderAttributionBuilder(BaseAttributionBuilder):
    """Request / response attribution for Qoder sessions.

    Qoder typically does not provide cache_read / cache_write split.
    We rely on transcript reconstruction and usage metadata when available.
    """

    # ── Helpers ─────────────────────────────────────────────────────────

    def _extract_prior_messages(self) -> list[dict]:
        """Extract prior messages from session_context if available."""
        ctx = self.session_context or {}
        prior = ctx.get("prior_messages", ctx.get("conversation_history", []))
        if isinstance(prior, list):
            return prior
        return []

    def _get_available_tools(self) -> list[str]:
        """Get available tool schemas. Qoder typically does not expose this."""
        ctx = self.session_context or {}
        available = ctx.get("available_tools", ctx.get("available_tool_schemas", []))
        if isinstance(available, list):
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

        # ── Step 1: 从标准化后的 LLMCall 获取真实 usage ─────────────
        # normalizer 已将 input_tokens 改写为 fresh，保留 cache 字段
        fresh_input = lc.input_tokens or 0
        cache_read = lc.cache_read_tokens or 0
        cache_write = lc.cache_write_tokens or 0
        total_input = fresh_input + cache_read + cache_write

        # 也尝试从 session_context 或 round usage 获取 total marker
        ctx = self.session_context or {}
        qoder_total = ctx.get("qoder_input_tokens_total")
        if qoder_total is not None:
            total_input = int(qoder_total)
        # 也检查 assistant_msg.usage 中是否有 total marker
        elif ro and getattr(ro, "assistant_msg", None) and ro.assistant_msg.usage:
            raw_usage = ro.assistant_msg.usage
            marker = raw_usage.get("qoder_input_tokens_total")
            if marker is not None:
                total_input = int(marker)

        precision_total = (ValuePrecision.PROVIDER_REPORTED if total_input > 0
                           else ValuePrecision.UNAVAILABLE)
        source_total = (ValueSource.PROVIDER_USAGE if total_input > 0
                        else ValueSource.HEURISTIC)

        total_input_val = AttributedValue(
            value=total_input if total_input > 0 else None,
            unit="tokens",
            precision=precision_total,
            source=source_total,
            fill_strategy="from normalized usage (fresh + cache_read + cache_write)",
        )

        # Qoder: 使用真实 cache 数据，0 是有效值
        fresh_input_val = AttributedValue(
            value=fresh_input, unit="tokens",
            precision=ValuePrecision.PROVIDER_REPORTED if total_input > 0 else ValuePrecision.UNAVAILABLE,
            source=ValueSource.PROVIDER_USAGE if total_input > 0 else ValueSource.HEURISTIC,
            fill_strategy="from normalized usage (input_tokens after normalization)",
        )
        cache_read_val = AttributedValue(
            value=cache_read, unit="tokens",
            precision=ValuePrecision.PROVIDER_REPORTED if total_input > 0 else ValuePrecision.UNAVAILABLE,
            source=ValueSource.PROVIDER_USAGE if total_input > 0 else ValueSource.HEURISTIC,
            fill_strategy="from normalized usage (cache_read_input_tokens)",
        )
        cache_write_val = AttributedValue(
            value=cache_write, unit="tokens",
            precision=ValuePrecision.PROVIDER_REPORTED if total_input > 0 else ValuePrecision.UNAVAILABLE,
            source=ValueSource.PROVIDER_USAGE if total_input > 0 else ValueSource.HEURISTIC,
            fill_strategy="from normalized usage (cache_creation_input_tokens)",
        )

        # ── Step 2: visible content estimation ─────────────────────────
        user_msg_content = ro.user_msg.content if ro.user_msg else ""
        current_user_msg_tokens = estimate_tokens_from_text(user_msg_content)

        # Tool results: ONLY preceding ones from session_context
        tool_result_texts = self._get_preceding_tool_result_texts()
        tool_results_tokens = estimate_tokens_from_text("\n".join(tool_result_texts))

        # History messages: ONLY from explicit prior_messages
        prior_messages = self._extract_prior_messages()
        prior_message_texts = []
        for pm in prior_messages:
            if isinstance(pm, dict):
                prior_message_texts.append(pm.get("content", ""))
            else:
                prior_message_texts.append(str(pm))
        history_msg_count = len(prior_messages)
        history_tokens = 0
        if prior_messages:
            history_tokens = estimate_tokens_from_text("\n".join(prior_message_texts))

        # Captured context fragment: deduped against known content
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

        # Tool schemas: ONLY from available_tools, NOT from observed tool_calls
        available_tools = self._get_available_tools()
        tool_schema_tokens = 0
        if available_tools:
            tool_schema_tokens = len(available_tools) * _DEFAULT_SCHEMA_TOKENS_PER_TOOL

        # Injected context / rules (Qoder may inject CLAUDE.md etc.)
        injected_context_tokens = 0  # heuristic placeholder

        # ── Step 3: normalize and assemble buckets ─────────────────────
        total_input_raw = total_input if isinstance(total_input, int) else (total_input_val.value or 0)
        known_sum = (current_user_msg_tokens + tool_results_tokens
                     + history_tokens + captured_context_tokens
                     + tool_schema_tokens + injected_context_tokens)

        if total_input_raw > 0 and known_sum > total_input_raw:
            # Normalize: scale estimated buckets proportionally
            scale = total_input_raw / known_sum
            history_tokens = max(0, int(history_tokens * scale))
            tool_results_tokens = max(0, int(tool_results_tokens * scale))
            tool_schema_tokens = max(0, int(tool_schema_tokens * scale))
            current_user_msg_tokens = max(0, int(current_user_msg_tokens * scale))
            captured_context_tokens = max(0, int(captured_context_tokens * scale))
            known_sum = (current_user_msg_tokens + tool_results_tokens
                         + history_tokens + captured_context_tokens
                         + tool_schema_tokens + injected_context_tokens)

        unknown_val = max(total_input_raw - known_sum, 0) if total_input_raw > 0 else 0

        buckets = []

        # History messages — ONLY with explicit prior_messages
        if history_tokens > 0 and prior_messages:
            buckets.append(RequestAttributionBucket(
                key="history_messages",
                label="History messages",
                tokens=history_tokens,
                percent=_pct(history_tokens, total_input_raw),
                count_label=f"{history_msg_count} messages",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="历史消息从 prior messages 列表获取，token 通过文本估算。",
                content_preview=lc.request_preview[:120] if lc.request_preview else "",
            ))

        # Captured context fragment
        if captured_context_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="captured_context_fragment",
                label="Captured context / unknown",
                tokens=captured_context_tokens,
                percent=_pct(captured_context_tokens, total_input_raw),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="低",
                summary="request_full 中存在但无法分类为历史消息的上下文片段。",
                content_preview=captured_context_text[:120] if captured_context_text else "",
            ))

        if tool_results_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_results",
                label="Tool results",
                tokens=tool_results_tokens,
                percent=_pct(tool_results_tokens, total_input_raw),
                count_label=f"{len(tool_result_texts)} results" if tool_result_texts else "",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TOOL_LOGS,
                confidence_label="中",
                summary="Tool result 内容从工具日志获取，token 通过文本估算。",
            ))

        if current_user_msg_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="current_user_message",
                label="Current user prompt",
                tokens=current_user_msg_tokens,
                percent=_pct(current_user_msg_tokens, total_input_raw),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中高",
                summary="用户 prompt 从 transcript 获取，token 通过文本估算。",
                content_preview=(user_msg_content or "")[:120],
            ))

        if injected_context_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="injected_context",
                label="Injected context / rules",
                tokens=injected_context_tokens,
                percent=_pct(injected_context_tokens, total_input_raw),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.LOCAL_RULES,
                confidence_label="低",
                summary="Qoder 可能注入的上下文/规则，无法直接读取时作为估算 bucket。",
            ))

        # Tool schemas — ONLY with available_tools
        if tool_schema_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_schemas",
                label="Tool schemas",
                tokens=tool_schema_tokens,
                percent=_pct(tool_schema_tokens, total_input_raw),
                count_label=f"{len(available_tools)} tools",
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.TOOL_LIST,
                confidence_label="中低",
                summary=f"按 {len(available_tools)} 个可用工具 × {_DEFAULT_SCHEMA_TOKENS_PER_TOOL} tokens/tool 估算。",
            ))
        else:
            # Zero-token unavailable bucket so UI can show "not available"
            buckets.append(RequestAttributionBucket(
                key="tool_schemas",
                label="Tool schemas",
                tokens=0,
                percent=0.0,
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                confidence_label="低",
                summary="无法从本地日志获取可用工具定义列表；Qoder 不提供 available tools 信息。",
            ))

        buckets.append(RequestAttributionBucket(
            key="unknown_overhead",
            label="未定位",
            tokens=unknown_val,
            percent=_pct(unknown_val, total_input_raw),
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
        coverage_val = (min(known_bucket_sum / total_input_raw, 1.0)
                        if total_input_raw > 0 else 0.0)

        # ── Step 5: availability rows ──────────────────────────────────
        has_usage = total_input_raw > 0
        avail_rows = [
            self._avail("total_input", "Total input tokens", has_usage,
                        precision=ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC,
                        fill_strategy="from normalized usage (fresh + cache_read + cache_write)"),
            self._avail("fresh_input", "Fresh input tokens", has_usage,
                        precision=ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC,
                        fill_strategy="from normalized usage (input_tokens after normalization)"),
            self._avail("cache_read", "Cache read tokens", has_usage,
                        precision=ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC,
                        fill_strategy="from normalized usage (cache_read_input_tokens)"),
            self._avail("cache_write", "Cache write tokens", has_usage,
                        precision=ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC,
                        fill_strategy="from normalized usage (cache_creation_input_tokens)"),
            self._avail("history_messages_count", "History message count",
                        history_msg_count > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if history_msg_count > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT if history_msg_count > 0 else ValueSource.HEURISTIC,
                        fill_strategy="count of prior messages" if history_msg_count > 0 else "no prior messages"),
            self._avail("history_messages_tokens", "History message tokens",
                        history_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if history_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT if history_tokens > 0 else ValueSource.HEURISTIC,
                        fill_strategy="estimated from prior message text" if history_tokens > 0 else "no prior messages"),
            self._avail("current_user_prompt_content", "Current user prompt content",
                        bool(user_msg_content), exact=True,
                        precision=ValuePrecision.EXACT if user_msg_content else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="direct from round user_msg"),
            self._avail("current_user_prompt_tokens", "Current user prompt tokens",
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
                        precision=ValuePrecision.UNAVAILABLE,
                        source=ValueSource.HEURISTIC,
                        fill_strategy="no available_tools list for Qoder"),
            self._avail("injected_context_tokens", "Injected context tokens",
                        False,
                        precision=ValuePrecision.UNAVAILABLE,
                        source=ValueSource.HEURISTIC,
                        fill_strategy="not directly readable"),
            self._avail("unknown", "Unknown / residual", True, exact=False,
                        precision=ValuePrecision.RESIDUAL,
                        source=ValueSource.RESIDUAL,
                        fill_strategy="residual = total - known"),
        ]

        notes = []
        if has_usage:
            notes.append(
                f"Qoder broker-reported usage: total={total_input_raw}, "
                f"fresh={fresh_input}, cache_read={cache_read}, cache_write={cache_write}"
            )
        else:
            notes.append("Qoder 无 provider usage 数据，使用本地估算。")
        if available_tools:
            notes.append(f"Tool schemas 按 {len(available_tools)} available tools × {_DEFAULT_SCHEMA_TOKENS_PER_TOOL} tokens 估算。")
        else:
            notes.append("Tool schemas: Qoder 不提供 available tools 信息，tool_schemas 标记为 unavailable。")
        if not prior_messages and lc.request_full:
            notes.append("History messages: 无明确 prior messages，request_full 内容归入 captured_context_fragment。")

        return LLMRequestAttribution(
            agent="qoder",
            model=lc.model or "unknown",
            request_id=lc.id or "unavailable",
            call_id=lc.id,
            source_label="transcript",
            confidence_label="中",
            raw_body_available=False,
            total_input=total_input_val,
            fresh_input=fresh_input_val,
            cache_read=cache_read_val,
            cache_write=cache_write_val,
            coverage=AttributedValue(
                value=coverage_val, unit="ratio",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.HEURISTIC,
                fill_strategy="known_buckets / total_input",
            ),
            unknown=AttributedValue(
                value=unknown_val, unit="tokens",
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

        # ── Step 1: visible content ────────────────────────────────────
        response_text = lc.response_full or ""
        visible_text_tokens = estimate_tokens_from_text(response_text)

        # Tool use blocks
        tool_use_tokens = 0
        block_refs = []
        for cb in (lc.content_blocks or []):
            if cb.get("type") == "tool_use":
                tool_use_tokens += estimate_tokens_from_text(json.dumps(cb, ensure_ascii=False))
                block_refs.append(cb.get("id", ""))
        if tool_use_tokens == 0 and lc.tool_calls_raw:
            tool_use_tokens = estimate_tokens_from_text(lc.tool_calls_raw)

        # Metadata
        metadata_tokens = 0
        if lc.finish_reason:
            metadata_tokens += 10

        # ── Step 2: normalize ──────────────────────────────────────────
        known_sum = visible_text_tokens + tool_use_tokens + metadata_tokens

        if total_output_val > 0:
            if known_sum > total_output_val:
                scale = total_output_val / known_sum
                visible_text_tokens = max(0, int(visible_text_tokens * scale))
                tool_use_tokens = max(0, int(tool_use_tokens * scale))
                metadata_tokens = max(0, int(metadata_tokens * scale))
                known_sum = visible_text_tokens + tool_use_tokens + metadata_tokens
            unknown_val = total_output_val - known_sum
        else:
            unknown_val = 0
            total_output_val = known_sum

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
                confidence_label="中",
                summary="助手文本从 transcript 获取，token 通过文本估算。",
            ))

        if tool_use_tokens > 0:
            buckets.append(ResponseAttributionBucket(
                key="tool_use",
                label="Tool use",
                tokens=tool_use_tokens,
                percent=_pct(tool_use_tokens, total_output_val),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="Tool use 结构从 content_blocks 获取，token 通过 JSON 估算。",
                block_refs=block_refs,
                contributes_to_total=True,
            ))

        if metadata_tokens > 0:
            buckets.append(ResponseAttributionBucket(
                key="metadata",
                label="Progress / metadata",
                tokens=metadata_tokens,
                percent=_pct(metadata_tokens, total_output_val),
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.SESSION_METADATA,
                confidence_label="低",
                summary="可见 progress/metadata 字段估算。",
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

        # ── Step 4: coverage (only counts contributes_to_total=True) ────
        known_bucket_sum = sum(
            b.tokens for b in buckets
            if b.key != "unknown" and b.contributes_to_total
        )
        coverage_val = (min(known_bucket_sum / total_output_val, 1.0)
                        if total_output_val > 0 else 0.0)

        finish_str = lc.finish_reason or ""
        avail_rows = [
            self._avail("total_output", "Total output tokens", total_output_val > 0,
                        precision=ValuePrecision.PROVIDER_REPORTED if lc.output_tokens > 0 else ValuePrecision.ESTIMATED,
                        source=ValueSource.PROVIDER_USAGE if lc.output_tokens > 0 else ValueSource.HEURISTIC,
                        fill_strategy="provider output_tokens" if lc.output_tokens > 0 else "estimated"),
            self._avail("assistant_text_content", "Assistant text content", bool(response_text),
                        exact=True,
                        precision=ValuePrecision.TRANSCRIPT_EXACT if response_text else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="direct from response_full"),
            self._avail("assistant_text_tokens", "Assistant text tokens", True,
                        exact=False,
                        precision=ValuePrecision.ESTIMATED,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="estimated"),
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
            self._avail("progress_metadata", "Progress / metadata",
                        metadata_tokens > 0, exact=False,
                        precision=ValuePrecision.HEURISTIC,
                        source=ValueSource.SESSION_METADATA,
                        fill_strategy="visible fields"),
            self._avail("finish_reason", "Finish reason", bool(finish_str),
                        exact=True,
                        precision=ValuePrecision.EXACT if finish_str else ValuePrecision.UNAVAILABLE,
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

        return LLMResponseAttribution(
            agent="qoder",
            model=lc.model or "unknown",
            request_id=lc.id or "unavailable",
            call_id=lc.id,
            source_label="transcript",
            confidence_label="中",
            raw_body_available=False,
            total_output=total_output,
            visible_text=AttributedValue(
                value=visible_text_tokens, unit="tokens",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                fill_strategy="estimate_tokens_from_text(response_full)",
            ),
            tool_use=AttributedValue(
                value=tool_use_tokens, unit="tokens",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                fill_strategy="estimate_tokens_from_text(serialized tool_use blocks)",
            ),
            metadata=AttributedValue(
                value=metadata_tokens, unit="tokens",
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.SESSION_METADATA,
                fill_strategy="visible field heuristic",
            ),
            coverage=AttributedValue(
                value=coverage_val, unit="ratio",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.HEURISTIC,
                fill_strategy="known_buckets / total_output",
            ),
            unknown=AttributedValue(
                value=unknown_val, unit="tokens",
                precision=ValuePrecision.RESIDUAL,
                source=ValueSource.RESIDUAL,
                fill_strategy="total - sum(known_buckets)",
            ),
            finish_reason=AttributedValue(
                value=finish_str, unit="str",
                precision=ValuePrecision.EXACT if finish_str else ValuePrecision.UNAVAILABLE,
                source=ValueSource.TRANSCRIPT,
                fill_strategy="from llm_call.finish_reason",
            ),
            buckets=buckets,
            blocks=lc.content_blocks or [],
            captured_output_preview=lc.response_preview or "",
            attribution_notes=[],
            availability_rows=avail_rows,
        )


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total * 100, 1)
