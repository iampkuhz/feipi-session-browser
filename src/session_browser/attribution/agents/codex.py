"""Codex attribution builder.

Codex defaults to session jsonl / response items processing.
Do NOT assume raw body availability.  Cache semantics are typically unknown.
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


class CodexAttributionBuilder(BaseAttributionBuilder):
    """Request / response attribution for Codex sessions.

    Codex typically provides session usage totals but no fresh/cache split.
    We reconstruct from conversation history items, tool outputs, and
    visible file context fragments.
    """

    def build_request(self) -> LLMRequestAttribution:
        lc = self.llm_call
        ro = self.round_obj

        # ── Step 1: total input ────────────────────────────────────────
        total_input_val = lc.input_tokens or 0
        precision_total = (ValuePrecision.PROVIDER_REPORTED if total_input_val > 0
                           else ValuePrecision.UNAVAILABLE)
        source_total = (ValueSource.PROVIDER_USAGE if total_input_val > 0
                        else ValueSource.HEURISTIC)

        total_input = AttributedValue(
            value=total_input_val,
            unit="tokens",
            precision=precision_total,
            source=source_total,
            fill_strategy="from session usage if available",
        )

        # Codex: cache split unknown
        fresh_input = AttributedValue(
            value=None, unit="tokens",
            precision=ValuePrecision.UNAVAILABLE,
            source=ValueSource.HEURISTIC,
            fill_strategy="Codex does not provide fresh/cache split",
        )
        cache_read = AttributedValue(
            value=None, unit="tokens",
            precision=ValuePrecision.UNAVAILABLE,
            source=ValueSource.HEURISTIC,
            fill_strategy="Codex does not provide cache_read",
        )
        cache_write = AttributedValue(
            value=None, unit="tokens",
            precision=ValuePrecision.UNAVAILABLE,
            source=ValueSource.HEURISTIC,
            fill_strategy="Codex does not provide cache_write",
        )

        # ── Step 2: visible content estimation ─────────────────────────
        # Current user instruction
        user_msg_content = ro.user_msg.content if ro.user_msg else ""
        current_user_tokens = estimate_tokens_from_text(user_msg_content)

        # Conversation history (from request_full or interactions)
        history_tokens = 0
        history_msg_count = 0
        if lc.request_full:
            history_tokens = estimate_tokens_from_text(lc.request_full[:3000])
            history_msg_count = lc.request_full.count("\n\n") + 1

        # Tool outputs
        tool_result_texts = []
        for tc in ro.tool_calls:
            if tc.result and not tc.subagent_id:
                tool_result_texts.append(tc.result)
        tool_outputs_tokens = estimate_tokens_from_text("\n".join(tool_result_texts))

        # Repository / file context (visible snippets in request)
        repo_context_tokens = 0
        if lc.request_full:
            # Heuristic: look for file-path-like patterns
            import re
            file_refs = re.findall(r'(?:File|file|path)[:\s]+[^\n]+', lc.request_full)
            if file_refs:
                repo_context_tokens = estimate_tokens_from_text("\n".join(file_refs))

        # Tool schemas
        tool_count = len(ro.tool_calls)
        if tool_count == 0:
            tool_count = sum(1 for ix in ro.interactions for _tc in (getattr(ix, "tool_calls", []) or []) if not getattr(_tc, "subagent_id", ""))
        tool_schema_tokens = tool_count * _DEFAULT_SCHEMA_TOKENS_PER_TOOL if tool_count > 0 else 0

        # ── Step 3: normalize and assemble buckets ─────────────────────
        known_sum = (current_user_tokens + history_tokens + tool_outputs_tokens
                     + repo_context_tokens + tool_schema_tokens)

        if total_input_val > 0 and known_sum > total_input_val:
            scale = total_input_val / known_sum
            history_tokens = max(0, int(history_tokens * scale))
            tool_outputs_tokens = max(0, int(tool_outputs_tokens * scale))
            repo_context_tokens = max(0, int(repo_context_tokens * scale))
            current_user_tokens = max(0, int(current_user_tokens * scale))
            tool_schema_tokens = max(0, int(tool_schema_tokens * scale))
            known_sum = (current_user_tokens + history_tokens + tool_outputs_tokens
                         + repo_context_tokens + tool_schema_tokens)

        unknown_val = max(total_input_val - known_sum, 0) if total_input_val > 0 else 0

        buckets = []

        if history_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="conversation_history",
                label="Conversation history",
                tokens=history_tokens,
                percent=_pct(history_tokens, total_input_val),
                count_label=f"~{history_msg_count} messages" if history_msg_count else "",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="对话历史从 session items 文本估算 + 总量归一化。",
                content_preview=lc.request_preview[:120] if lc.request_preview else "",
            ))

        if tool_outputs_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_outputs",
                label="Tool outputs",
                tokens=tool_outputs_tokens,
                percent=_pct(tool_outputs_tokens, total_input_val),
                count_label=f"{len(tool_result_texts)} outputs" if tool_result_texts else "",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TOOL_LOGS,
                confidence_label="中",
                summary="Tool outputs 从工具日志获取，token 通过文本估算。",
            ))

        if current_user_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="current_user_instruction",
                label="Current user instruction",
                tokens=current_user_tokens,
                percent=_pct(current_user_tokens, total_input_val),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中高",
                summary="用户指令从 session 获取，token 通过文本估算。",
                content_preview=(user_msg_content or "")[:120],
            ))

        if repo_context_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="repository_file_context",
                label="Repository / file context",
                tokens=repo_context_tokens,
                percent=_pct(repo_context_tokens, total_input_val),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中低",
                summary="从 session 可见文件片段估算。",
            ))

        if tool_schema_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_schemas",
                label="Tool schemas",
                tokens=tool_schema_tokens,
                percent=_pct(tool_schema_tokens, total_input_val),
                count_label=f"{tool_count} tools" if tool_count > 0 else "",
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.TOOL_LIST,
                confidence_label="中低",
                summary=f"按 {tool_count} 个工具 × {_DEFAULT_SCHEMA_TOKENS_PER_TOOL} tokens/tool 估算。",
            ))

        buckets.append(RequestAttributionBucket(
            key="unknown_overhead",
            label="Unknown / wrapper",
            tokens=unknown_val,
            percent=_pct(unknown_val, total_input_val),
            precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
            confidence_label="中",
            summary="Total input 减去已知 bucket 后的剩余部分（含 provider wrapper 开销）。",
        ))

        # ── Step 4: coverage ───────────────────────────────────────────
        known_bucket_sum = sum(b.tokens for b in buckets if b.key != "unknown_overhead")
        coverage_val = (min(known_bucket_sum / total_input_val, 1.0)
                        if total_input_val > 0 else 0.0)

        # ── Step 5: availability rows ──────────────────────────────────
        avail_rows = [
            self._avail("total_input", total_input_val > 0, "session usage" if total_input_val > 0 else "unavailable"),
            self._avail("fresh_input", False, "Codex does not provide fresh/cache split"),
            self._avail("cache_read", False, "Codex does not provide cache_read"),
            self._avail("cache_write", False, "Codex does not provide cache_write"),
            self._avail("conversation_history_tokens", history_tokens > 0, "estimated from session items"),
            self._avail("tool_outputs_tokens", tool_outputs_tokens > 0, "estimated from text"),
            self._avail("current_user_instruction_tokens", True, "estimated from text"),
            self._avail("repository_file_context_tokens", repo_context_tokens > 0, "estimated from file snippets"),
            self._avail("tool_schemas_tokens", tool_count > 0, f"estimated: {tool_count} tools" if tool_count > 0 else "no tool list"),
            self._avail("unknown", True, "residual"),
        ]

        notes = []
        notes.append("Codex 不提供 cache_read / cache_write 拆分，所有 fresh/cache 标记为 unknown。")
        if tool_count > 0:
            notes.append(f"Tool schemas 按 {tool_count} tools × {_DEFAULT_SCHEMA_TOKENS_PER_TOOL} tokens 估算。")

        return LLMRequestAttribution(
            agent="codex",
            model=lc.model or "unknown",
            request_id="",
            call_id=lc.id,
            source_label="session jsonl",
            confidence_label="中",
            raw_body_available=False,
            total_input=total_input,
            fresh_input=fresh_input,
            cache_read=cache_read,
            cache_write=cache_write,
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
            captured_context_preview=lc.request_preview or "",
            attribution_notes=notes,
            availability_rows=avail_rows,
        )

    def build_response(self) -> LLMResponseAttribution:
        lc = self.llm_call

        total_output_val = lc.output_tokens or 0

        # ── Step 1: visible content ────────────────────────────────────
        response_text = lc.response_full or ""
        visible_text_tokens = estimate_tokens_from_text(response_text)

        # Tool use / function_call / apply_patch / shell command blocks
        tool_use_tokens = 0
        block_refs = []
        for cb in (lc.content_blocks or []):
            if cb.get("type") == "tool_use":
                tool_use_tokens += estimate_tokens_from_text(json.dumps(cb, ensure_ascii=False))
                block_refs.append(cb.get("id", ""))
        if tool_use_tokens == 0 and lc.tool_calls_raw:
            tool_use_tokens = estimate_tokens_from_text(lc.tool_calls_raw)

        # Structured response items (JSON length estimate)
        structured_tokens = 0
        if lc.content_blocks:
            structured_tokens = estimate_tokens_from_text(
                json.dumps(lc.content_blocks, ensure_ascii=False))

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
                summary="助手文本从 session 获取，token 通过文本估算。",
            ))

        if tool_use_tokens > 0:
            buckets.append(ResponseAttributionBucket(
                key="tool_use",
                label="Tool use / function_call",
                tokens=tool_use_tokens,
                percent=_pct(tool_use_tokens, total_output_val),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="Tool use 结构序列化估算。",
                block_refs=block_refs,
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
                summary="可见字段估算。",
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

        # ── Step 4: coverage ───────────────────────────────────────────
        known_bucket_sum = sum(b.tokens for b in buckets if b.key != "unknown")
        coverage_val = (min(known_bucket_sum / total_output_val, 1.0)
                        if total_output_val > 0 else 0.0)

        finish_str = lc.finish_reason or ""
        avail_rows = [
            self._avail("total_output", total_output_val > 0, "provider" if lc.output_tokens > 0 else "estimated"),
            self._avail("assistant_text_content", bool(response_text)),
            self._avail("assistant_text_tokens", True, "estimated"),
            self._avail("tool_use_structure", bool(lc.content_blocks or lc.tool_calls_raw)),
            self._avail("tool_use_tokens", True, "estimated from serialization"),
            self._avail("structured_items", structured_tokens > 0, "JSON length estimate"),
            self._avail("metadata", metadata_tokens > 0, "visible fields"),
            self._avail("finish_reason", bool(finish_str)),
            self._avail("blocks_count", True, f"{len(lc.content_blocks)} blocks" if lc.content_blocks else "0"),
            self._avail("unknown", True, "residual"),
        ]

        return LLMResponseAttribution(
            agent="codex",
            model=lc.model or "unknown",
            request_id="",
            call_id=lc.id,
            source_label="session jsonl",
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
                fill_strategy="estimate_tokens_from_text(serialized blocks)",
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
