"""Qoder attribution builder.

Qoder defaults to transcript-level reconstruction.  Do NOT show raw body.
Do NOT assume cache_read / cache_write availability.
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
            fill_strategy="from transcript/usage if available",
        )

        # Qoder: cache split is unknown
        fresh_input = AttributedValue(
            value=None, unit="tokens",
            precision=ValuePrecision.UNAVAILABLE,
            source=ValueSource.HEURISTIC,
            fill_strategy="Qoder does not provide fresh/cache split",
        )
        cache_read = AttributedValue(
            value=None, unit="tokens",
            precision=ValuePrecision.UNAVAILABLE,
            source=ValueSource.HEURISTIC,
            fill_strategy="Qoder does not provide cache_read",
        )
        cache_write = AttributedValue(
            value=None, unit="tokens",
            precision=ValuePrecision.UNAVAILABLE,
            source=ValueSource.HEURISTIC,
            fill_strategy="Qoder does not provide cache_write",
        )

        # ── Step 2: visible content estimation ─────────────────────────
        user_msg_content = ro.user_msg.content if ro.user_msg else ""
        current_user_msg_tokens = estimate_tokens_from_text(user_msg_content)

        # Tool results
        tool_result_texts = []
        for tc in ro.tool_calls:
            if tc.result and not tc.subagent_id:
                tool_result_texts.append(tc.result)
        tool_results_tokens = estimate_tokens_from_text("\n".join(tool_result_texts))

        # History messages from transcript
        history_tokens = 0
        history_msg_count = 0
        # Estimate from interactions — count all message text in round
        for ix in ro.interactions:
            if ix.scope == "main" and ix.request_full:
                history_tokens = estimate_tokens_from_text(ix.request_full[:3000])
                history_msg_count = ix.request_full.count("\n\n") + 1
                break
        if history_tokens == 0 and lc.request_full:
            history_tokens = estimate_tokens_from_text(lc.request_full[:3000])
            history_msg_count = lc.request_full.count("\n\n") + 1

        # Tool schemas
        tool_count = len(ro.tool_calls)
        if tool_count == 0:
            tool_count = sum(1 for ix in ro.interactions for _tc in (getattr(ix, "tool_calls", []) or []) if not getattr(_tc, "subagent_id", ""))
        tool_schema_tokens = tool_count * _DEFAULT_SCHEMA_TOKENS_PER_TOOL if tool_count > 0 else 0

        # Injected context / rules (Qoder may inject CLAUDE.md etc.)
        injected_context_tokens = 0  # heuristic placeholder

        # ── Step 3: normalize and assemble buckets ─────────────────────
        known_sum = (current_user_msg_tokens + tool_results_tokens
                     + history_tokens + tool_schema_tokens + injected_context_tokens)

        if total_input_val > 0 and known_sum > total_input_val:
            # Normalize: scale estimated buckets proportionally
            scale = total_input_val / known_sum
            history_tokens = max(0, int(history_tokens * scale))
            tool_results_tokens = max(0, int(tool_results_tokens * scale))
            tool_schema_tokens = max(0, int(tool_schema_tokens * scale))
            current_user_msg_tokens = max(0, int(current_user_msg_tokens * scale))
            known_sum = (current_user_msg_tokens + tool_results_tokens
                         + history_tokens + tool_schema_tokens + injected_context_tokens)

        unknown_val = max(total_input_val - known_sum, 0) if total_input_val > 0 else 0

        buckets = []

        if history_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="history_messages",
                label="History messages",
                tokens=history_tokens,
                percent=_pct(history_tokens, total_input_val),
                count_label=f"~{history_msg_count} messages" if history_msg_count else "",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="历史消息从 transcript 文本估算，无法精确拆分 token。",
                content_preview=lc.request_preview[:120] if lc.request_preview else "",
            ))

        if tool_results_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_results",
                label="Tool results",
                tokens=tool_results_tokens,
                percent=_pct(tool_results_tokens, total_input_val),
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
                percent=_pct(current_user_msg_tokens, total_input_val),
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
                percent=_pct(injected_context_tokens, total_input_val),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.LOCAL_RULES,
                confidence_label="低",
                summary="Qoder 可能注入的上下文/规则，无法直接读取时作为估算 bucket。",
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
            label="Unknown / unattributed",
            tokens=unknown_val,
            percent=_pct(unknown_val, total_input_val),
            precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
            confidence_label="中",
            summary="Total input 减去已知 bucket 后的剩余部分。",
        ))

        # ── Step 4: coverage ───────────────────────────────────────────
        known_bucket_sum = sum(b.tokens for b in buckets if b.key != "unknown_overhead")
        coverage_val = (min(known_bucket_sum / total_input_val, 1.0)
                        if total_input_val > 0 else 0.0)

        # ── Step 5: availability rows ──────────────────────────────────
        avail_rows = [
            self._avail("total_input", total_input_val > 0, "transcript/usage" if total_input_val > 0 else "unavailable"),
            self._avail("fresh_input", False, "Qoder does not provide fresh/cache split"),
            self._avail("cache_read", False, "Qoder does not provide cache_read"),
            self._avail("cache_write", False, "Qoder does not provide cache_write"),
            self._avail("history_messages_count", history_msg_count > 0, "transcript" if history_msg_count > 0 else "not parsed"),
            self._avail("history_messages_tokens", history_tokens > 0, "estimated from transcript text"),
            self._avail("current_user_prompt_content", bool(user_msg_content)),
            self._avail("current_user_prompt_tokens", True, "estimated from text"),
            self._avail("tool_results_content", bool(tool_result_texts)),
            self._avail("tool_results_tokens", True, "estimated from text"),
            self._avail("tool_schemas_tokens", tool_count > 0, f"estimated: {tool_count} tools" if tool_count > 0 else "no tool list"),
            self._avail("injected_context_tokens", False, "not directly readable"),
            self._avail("unknown", True, "residual = total - known"),
        ]

        notes = []
        notes.append("Qoder 不提供 cache_read / cache_write 拆分，所有 fresh/cache 标记为 unknown。")
        if tool_count > 0:
            notes.append(f"Tool schemas 按 {tool_count} tools × {_DEFAULT_SCHEMA_TOKENS_PER_TOOL} tokens 估算。")

        return LLMRequestAttribution(
            agent="qoder",
            model=lc.model or "unknown",
            request_id="",
            call_id=lc.id,
            source_label="transcript",
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
            self._avail("tool_use_tokens", True, "estimated from JSON"),
            self._avail("progress_metadata", metadata_tokens > 0, "visible fields"),
            self._avail("finish_reason", bool(finish_str)),
            self._avail("blocks_count", True, f"{len(lc.content_blocks)} blocks" if lc.content_blocks else "0"),
            self._avail("unknown", True, "residual"),
        ]

        return LLMResponseAttribution(
            agent="qoder",
            model=lc.model or "unknown",
            request_id="",
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
