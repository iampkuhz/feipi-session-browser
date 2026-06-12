"""Qoder attribution builder.

Qoder 是 broker/runtime。通过标准化后的 LLMCall 字段获取真实 usage 数据：
- ``lc.input_tokens`` 为本次请求输入规模，作为 Fresh
- ``lc.cache_read_tokens`` 对应 cache_read_input_tokens
- ``lc.cache_write_tokens`` 对应 cache_creation_input_tokens（provider-reported）
- usage summary total = fresh + cache_read + cache_write
- request attribution denominator = fresh + cache_read; cache_write is shown
  in the summary but not treated as an extra request-source bucket
- 0 是有效值，不能显示为 unavailable。
"""

from __future__ import annotations

import json
import re
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
    ALL_CLAUDE_CODE_TOOLS,
    get_cached_schemas,
    get_all_tool_schema_tokens,
    get_tool_schema_tokens,
)


_DEFAULT_SCHEMA_TOKENS_PER_TOOL = 240


class QoderAttributionBuilder(BaseAttributionBuilder):
    """Request / response attribution for Qoder sessions.

    Qoder provides normalized usage metadata when indexed.  We rely on
    call-scoped transcript reconstruction for visible request content and keep
    provider cache counters as explicit request/accounting fields.
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

    def _extract_request_full_parts(
        self,
        request_full: str,
        *,
        current_user_text: str = "",
    ) -> dict:
        """Split rendered Qoder request context into local source buckets."""
        result = {
            "tool_results_texts": [],
            "context_texts": [],
        }
        text = (request_full or "").strip()
        if not text:
            return result

        current_user_norm = _normalize_ws(current_user_text or "")
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        for part in parts:
            match = re.match(
                r"^(?:Tool result|Tool output) for (\S+):\n(?P<body>.*)$",
                part,
                re.DOTALL,
            )
            if match:
                body = (match.group("body") or "").strip()
                if body:
                    result["tool_results_texts"].append(body)
                continue
            if current_user_norm and _normalize_ws(part) == current_user_norm:
                continue
            result["context_texts"].append(part)
        return result

    def _prior_message_stats(self, prior_messages: list[dict]) -> tuple[list[str], int]:
        """Return prior message previews and full-content token estimates."""
        texts: list[str] = []
        token_total = 0
        for pm in prior_messages:
            if isinstance(pm, dict):
                content = (
                    pm.get("content")
                    or pm.get("content_preview")
                    or pm.get("summary")
                    or ""
                )
                token_est = _int_or_zero(pm.get("content_token_estimate"))
                if not token_est and content:
                    token_est = estimate_tokens_from_text(str(content))
            else:
                content = str(pm)
                token_est = estimate_tokens_from_text(content)
            if content:
                texts.append(str(content))
            token_total += max(0, token_est)
        return texts, token_total

    def _full_messages_stats(self) -> tuple[list[dict], int]:
        ctx = self.session_context or {}
        full_messages = ctx.get("full_messages_array") or []
        if not isinstance(full_messages, list):
            return [], 0
        total = 0
        items = []
        for item in full_messages:
            if not isinstance(item, dict):
                continue
            token_est = _int_or_zero(item.get("content_token_estimate"))
            total += max(0, token_est)
            items.append(item)
        return items, total

    def _remove_known_fragments_from_texts(
        self,
        texts: list[str],
        known: list[str],
    ) -> list[str]:
        if not known:
            return texts
        known_normalized = {_normalize_ws(t): t for t in known if t and len(t.strip()) >= 20}
        result: list[str] = []
        for text in texts:
            if not text:
                continue
            stripped = text.strip()
            norm = _normalize_ws(stripped)
            if stripped in known or norm in known_normalized:
                continue
            result.append(text)
        return result

    def _tool_schema_tokens_and_details(self, available_tools: list[str]) -> tuple[int, dict, str, str]:
        """Estimate Qoder available-tool schema footprint.

        Qoder logs show invoked tools, not the full available tool schema list.
        Use the shared Claude-Code-like SDK schema registry as the baseline and
        add observed Qoder-only tools with a conservative fallback estimate.
        """
        tools_for_schema = sorted(set(ALL_CLAUDE_CODE_TOOLS) | set(available_tools or []))
        schemas = get_cached_schemas()
        known_tools = [tool for tool in tools_for_schema if tool in schemas]
        unknown_tools = [tool for tool in tools_for_schema if tool not in schemas]
        known_tokens = get_all_tool_schema_tokens(known_tools, schemas)
        unknown_tokens = len(unknown_tools) * _DEFAULT_SCHEMA_TOKENS_PER_TOOL
        total = known_tokens + unknown_tokens
        details = {
            "kind": "tools",
            "items": [
                {
                    "name": tool,
                    "source": "qoder_observed_tool" if tool in (available_tools or []) else "default_fallback",
                    "enabled": True,
                    "description_preview": (schemas.get(tool, {}).get("description") or "")[:180],
                    "estimated_tokens": (
                        get_tool_schema_tokens(tool, schemas)
                        if tool in schemas
                        else _DEFAULT_SCHEMA_TOKENS_PER_TOOL
                    ),
                    "precision": "extracted_from_sdk" if tool in schemas else "heuristic",
                    "description": schemas.get(tool, {}).get("description", ""),
                    "input_schema": json.dumps(
                        schemas.get(tool, {}).get("input_schema", {}),
                        ensure_ascii=False,
                        indent=2,
                    ) if tool in schemas else "",
                }
                for tool in tools_for_schema
            ],
            "total_items": len(tools_for_schema),
            "truncated": False,
        }
        source_summary = (
            "Qoder 未持久化完整 available tools schema；"
            "使用 Claude-Code-like SDK 默认工具定义，并补充本 session 观测到的 Qoder 工具。"
        )
        count_label = f"{len(tools_for_schema)} tools"
        return total, details, source_summary, count_label

    def build_request(self) -> LLMRequestAttribution:
        lc = self.llm_call
        ro = self.round_obj

        # ── Step 1: 从标准化后的 LLMCall 获取真实 usage ─────────────
        # input_tokens 表示 Fresh request input size，cache 字段单独展示。
        # Request-content distribution uses Fresh only. Cache Read / Cache Write
        # are provider accounting components and are not standalone content
        # buckets beside messages or tool results.
        fresh_input = lc.input_tokens or 0
        cache_read = lc.cache_read_tokens or 0
        cache_write = lc.cache_write_tokens or 0

        # marker 只用于兼容旧记录中缺失 lc.input_tokens 的情况，不覆盖组件合计。
        ctx = self.session_context or {}
        qoder_total = ctx.get("qoder_input_tokens_total")
        if fresh_input <= 0 and qoder_total is not None:
            fresh_input = int(qoder_total)
        elif fresh_input <= 0 and ro and getattr(ro, "assistant_msg", None) and ro.assistant_msg.usage:
            raw_usage = ro.assistant_msg.usage
            marker = raw_usage.get("qoder_input_tokens_total")
            if marker is not None:
                fresh_input = int(marker)

        request_content_input = max(0, fresh_input)
        total_input = fresh_input + cache_read + cache_write

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
            fill_strategy="from normalized usage (input_tokens request input size)",
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

        request_full_parts = {}
        if lc.request_full:
            request_full_parts = self._extract_request_full_parts(
                lc.request_full,
                current_user_text=user_msg_content,
            )

        # Tool results: preceding context plus rendered Qoder request_full
        # tool_result fragments.  Qoder persists tool outputs as user events,
        # so for a follow-up LLM call these are request-side input.
        tool_result_texts = self._get_preceding_tool_result_texts()
        request_tool_results = request_full_parts.get("tool_results_texts") or []
        if request_tool_results:
            tool_result_texts = self._remove_known_fragments_from_texts(
                tool_result_texts,
                request_tool_results,
            )
            tool_result_texts = request_tool_results + tool_result_texts
        tool_results_tokens = estimate_tokens_from_text("\n".join(tool_result_texts))

        # History messages: ONLY from explicit prior_messages
        prior_messages = self._extract_prior_messages()
        prior_message_texts, history_tokens = self._prior_message_stats(prior_messages)
        history_msg_count = len(prior_messages)

        # Qoder is Claude-like and the context layer can reconstruct the
        # request messages array for the current call. Prefer that structured
        # bucket because it has call boundaries and per-item token estimates.
        full_messages_array, full_messages_tokens = self._full_messages_stats()
        full_msg_count = len(full_messages_array)
        use_full_messages_bucket = full_messages_tokens > 0

        # Captured context fragment: deduped against known content
        captured_context_texts = request_full_parts.get("context_texts") or []
        captured_context_texts = self._remove_known_fragments_from_texts(
            captured_context_texts,
            [
                user_msg_content,
                *prior_message_texts,
                *tool_result_texts,
            ],
        )
        captured_context_text = "\n\n".join(captured_context_texts)
        captured_context_tokens = estimate_tokens_from_text(captured_context_text)

        # Tool schemas: Qoder logs observed tools but does not expose the full
        # available schema list. Use the shared Claude-like SDK schema registry
        # as a stable default and add observed Qoder-only tools heuristically.
        available_tools = self._get_available_tools()
        (
            tool_schema_tokens,
            tool_schema_details,
            tool_schema_summary,
            tool_schema_count_label,
        ) = self._tool_schema_tokens_and_details(available_tools)

        # Local instruction context when available from the project.
        ctx = self.session_context or {}
        local_text = (
            ctx.get("local_instructions")
            or ctx.get("system_reminder_content")
            or ""
        )
        local_instruction_text = local_text[:3000] if local_text else ""
        local_instruction_tokens = estimate_tokens_from_text(local_instruction_text)

        # Qoder hidden runtime prompt / wrapper.  This is deliberately bounded:
        # it explains a stable small part of the hidden request, without trying
        # to fabricate full system prompt content.
        hidden_runtime_tokens = 0
        if total_input > 0:
            hidden_runtime_tokens = min(500, request_content_input)

        # ── Step 3: normalize and assemble buckets ─────────────────────
        denominator = request_content_input
        if use_full_messages_bucket:
            transcript_tokens = full_messages_tokens
            current_user_msg_tokens = 0
            history_tokens = 0
            tool_results_tokens = 0
            captured_context_tokens = 0
        else:
            transcript_tokens = 0

        measured_tokens = (
            transcript_tokens
            + current_user_msg_tokens
            + history_tokens
            + tool_results_tokens
            + captured_context_tokens
        )
        heuristic_tokens = (
            tool_schema_tokens
            + local_instruction_tokens
            + hidden_runtime_tokens
        )
        estimated_budget = denominator

        if denominator > 0:
            if measured_tokens > estimated_budget:
                scale = estimated_budget / measured_tokens if measured_tokens > 0 else 0
                transcript_tokens = max(0, int(transcript_tokens * scale))
                current_user_msg_tokens = max(0, int(current_user_msg_tokens * scale))
                history_tokens = max(0, int(history_tokens * scale))
                tool_results_tokens = max(0, int(tool_results_tokens * scale))
                captured_context_tokens = max(0, int(captured_context_tokens * scale))
                tool_schema_tokens = 0
                local_instruction_tokens = 0
                hidden_runtime_tokens = 0
            else:
                heuristic_budget = max(estimated_budget - measured_tokens, 0)
                if heuristic_tokens > heuristic_budget:
                    scale = heuristic_budget / heuristic_tokens if heuristic_tokens > 0 else 0
                    tool_schema_tokens = max(0, int(tool_schema_tokens * scale))
                    local_instruction_tokens = max(0, int(local_instruction_tokens * scale))
                    hidden_runtime_tokens = max(0, int(hidden_runtime_tokens * scale))

        known_sum = (
            transcript_tokens + current_user_msg_tokens + history_tokens + tool_results_tokens
            + captured_context_tokens + tool_schema_tokens
            + local_instruction_tokens + hidden_runtime_tokens
        )
        unknown_val = max(denominator - known_sum, 0) if denominator > 0 else 0

        buckets = []

        if use_full_messages_bucket:
            full_messages_details = {
                "kind": "full_messages_array",
                "explanation": [
                    "这里对应 Qoder 发送给模型的 Claude-like API messages 输入结构。",
                    "每一行是一段 request-side 消息内容；当前 assistant response 属于输出，不计入这个数组。",
                    "token 使用 context 层为每条消息保存的完整 content_token_estimate 求和。",
                ],
                "items": [
                    {
                        "message_index": item.get("message_index", i),
                        "role": item.get("role", "unknown"),
                        "content_type": item.get("content_type", "unknown"),
                        "tool_name": item.get("tool_name", ""),
                        "tool_use_id": item.get("tool_use_id", ""),
                        "summary": item.get("content_preview", ""),
                        "full_content": (
                            item.get("full_content")
                            or item.get("content")
                            or item.get("content_preview", "")
                        ),
                        "tokens": item.get("content_token_estimate", 0),
                        "has_full_content": item.get("has_full_content", False),
                    }
                    for i, item in enumerate(full_messages_array)
                ],
                "total_items": full_msg_count,
                "truncated": False,
            }
            buckets.append(RequestAttributionBucket(
                key="full_messages_array",
                label="API messages 数组",
                tokens=transcript_tokens,
                percent=_pct(transcript_tokens, denominator),
                count_label=f"{full_msg_count} messages",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary=(
                    f"Qoder Claude-like API messages 数组，共 {full_msg_count} 条，"
                    "按当前 call 边界重建。"
                ),
                details=full_messages_details,
            ))

        # History messages — ONLY with explicit prior_messages
        if not use_full_messages_bucket and history_tokens > 0 and prior_messages:
            buckets.append(RequestAttributionBucket(
                key="history_messages",
                label="History messages",
                tokens=history_tokens,
                percent=_pct(history_tokens, denominator),
                count_label=f"{history_msg_count} messages",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="历史消息从 prior messages 列表获取，优先使用完整 content_token_estimate。",
                content_preview=lc.request_preview[:120] if lc.request_preview else "",
                details={
                    "kind": "source_items",
                    "items": [
                        {
                            "label": f"history message #{i + 1}",
                            "name": f"history message #{i + 1}",
                            "role": pm.get("role", "") if isinstance(pm, dict) else "",
                            "summary": (str(pm.get("content_preview") or pm.get("content") or "")[:180]
                                        if isinstance(pm, dict) else str(pm)[:180]),
                            "preview": (str(pm.get("content_preview") or pm.get("content") or "")[:260]
                                        if isinstance(pm, dict) else str(pm)[:260]),
                            "full_content": (str(pm.get("full_content") or pm.get("content") or pm.get("content_preview") or "")
                                             if isinstance(pm, dict) else str(pm)),
                            "tokens": (pm.get("content_token_estimate", 0) if isinstance(pm, dict)
                                       else estimate_tokens_from_text(str(pm))),
                        }
                        for i, pm in enumerate(prior_messages)
                    ],
                    "total_items": len(prior_messages),
                },
            ))

        # Captured context fragment
        if not use_full_messages_bucket and captured_context_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="captured_context_fragment",
                label="Captured context / unknown",
                tokens=captured_context_tokens,
                percent=_pct(captured_context_tokens, denominator),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="低",
                summary="request_full 中存在但无法分类为历史消息的上下文片段。",
                content_preview=captured_context_text[:120] if captured_context_text else "",
            ))

        if not use_full_messages_bucket and tool_results_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_results",
                label="Tool results",
                tokens=tool_results_tokens,
                percent=_pct(tool_results_tokens, denominator),
                count_label=f"{len(tool_result_texts)} results" if tool_result_texts else "",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TOOL_LOGS,
                confidence_label="中",
                summary="Tool result 内容从工具日志或 Qoder request_full 获取，token 通过文本估算。",
                details={
                    "kind": "tool_results",
                    "items": [
                        {
                            "label": f"tool result #{i + 1}",
                            "name": f"tool result #{i + 1}",
                            "tool_name": "unknown",
                            "summary": text[:180],
                            "preview": text[:260],
                            "full_content": text,
                            "tokens": estimate_tokens_from_text(text),
                        }
                        for i, text in enumerate(tool_result_texts)
                    ],
                    "total_items": len(tool_result_texts),
                },
            ))

        if not use_full_messages_bucket and current_user_msg_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="current_user_message",
                label="Current user prompt",
                tokens=current_user_msg_tokens,
                percent=_pct(current_user_msg_tokens, denominator),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中高",
                summary="用户 prompt 从 transcript 获取，token 通过文本估算。",
                content_preview=(user_msg_content or "")[:120],
                details={
                    "kind": "current_user_message",
                    "preview": (user_msg_content or "")[:260],
                    "full_content": user_msg_content or "",
                    "tokens": current_user_msg_tokens,
                },
            ))

        if local_instruction_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="local_instruction_context",
                label="Local instruction context",
                tokens=local_instruction_tokens,
                percent=_pct(local_instruction_tokens, denominator),
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.LOCAL_RULES,
                confidence_label="中低",
                summary="从项目本地指令文件或 transcript system reminder 中提取。",
                content_preview=local_instruction_text[:120],
                details={
                    "kind": "source_items",
                    "items": [
                        {
                            "label": "local instruction context",
                            "name": "local instruction context",
                            "source_type": "local_rules",
                            "summary": local_instruction_text[:180],
                            "preview": local_instruction_text[:260],
                            "full_content": local_instruction_text,
                            "tokens": local_instruction_tokens,
                        }
                    ],
                    "total_items": 1,
                },
            ))

        if tool_schema_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_schemas",
                label="Tool schemas",
                tokens=tool_schema_tokens,
                percent=_pct(tool_schema_tokens, denominator),
                count_label=tool_schema_count_label,
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.TOOL_LIST,
                confidence_label="中低",
                summary=tool_schema_summary,
                details=tool_schema_details,
            ))

        if hidden_runtime_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="qoder_runtime_context_estimate",
                label="Qoder runtime context estimate",
                tokens=hidden_runtime_tokens,
                percent=_pct(hidden_runtime_tokens, denominator),
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.HEURISTIC,
                confidence_label="低",
                summary="Qoder 内置 runtime/system wrapper 未在本地日志展开；仅按保守上限解释一小段固定开销。",
                details={
                    "kind": "hidden_estimate",
                    "explanation": [
                        "Qoder 没有持久化完整 raw request body。",
                        "本 bucket 不包含真实 prompt 内容，只解释少量稳定 runtime wrapper 开销。",
                    ],
                },
            ))

        buckets.append(RequestAttributionBucket(
            key="unknown_overhead",
            label="未定位",
            tokens=unknown_val,
            percent=_pct(unknown_val, denominator),
            precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
            confidence_label="中",
            summary="Fresh input 减去已知 request 内容 bucket 后的剩余部分。",
        ))

        # ── Step 4: coverage ───────────────────────────────────────────
        known_bucket_sum = sum(
            b.tokens for b in buckets
            if b.key not in ("unknown_overhead",) and b.contributes_to_total
        )
        coverage_val = (min(known_bucket_sum / denominator, 1.0)
                        if denominator > 0 else 0.0)

        # ── Step 5: availability rows ──────────────────────────────────
        has_usage = total_input > 0
        avail_rows = [
            self._avail("total_input", "Total input tokens", has_usage,
                        precision=ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC,
                        fill_strategy="from normalized usage (fresh + cache_read + cache_write)"),
            self._avail("fresh_input", "Fresh input tokens", has_usage,
                        precision=ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC,
                        fill_strategy="from normalized usage (input_tokens request input size)"),
            self._avail("cache_read", "Cache read tokens", has_usage,
                        precision=ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC,
                        fill_strategy="from normalized usage (cache_read_input_tokens)"),
            self._avail("cache_write", "Cache write tokens", has_usage,
                        precision=ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC,
                        fill_strategy="from normalized usage (cache_creation_input_tokens)"),
            self._avail("full_messages_array", "API messages array",
                        full_msg_count > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if full_msg_count > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT if full_msg_count > 0 else ValueSource.HEURISTIC,
                        fill_strategy="call-scoped context full_messages_array" if full_msg_count > 0 else "not reconstructed"),
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
                        tool_schema_tokens > 0, exact=False,
                        precision=ValuePrecision.HEURISTIC,
                        source=ValueSource.TOOL_LIST,
                        fill_strategy="Claude-like SDK fallback plus observed Qoder tools"),
            self._avail("local_instruction_tokens", "Local instruction tokens",
                        local_instruction_tokens > 0, exact=False,
                        precision=ValuePrecision.HEURISTIC if local_instruction_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.LOCAL_RULES if local_instruction_tokens > 0 else ValueSource.HEURISTIC,
                        fill_strategy="from local_instructions or system_reminder_content" if local_instruction_tokens > 0 else "no local instruction context"),
            self._avail("qoder_runtime_context", "Qoder runtime context estimate",
                        hidden_runtime_tokens > 0, exact=False,
                        precision=ValuePrecision.HEURISTIC,
                        source=ValueSource.HEURISTIC,
                        fill_strategy="bounded hidden runtime wrapper estimate"),
            self._avail("unknown", "Unknown / residual", True, exact=False,
                        precision=ValuePrecision.RESIDUAL,
                        source=ValueSource.RESIDUAL,
                        fill_strategy="residual = fresh_input - known request content buckets"),
        ]

        notes = []
        if has_usage:
            notes.append(
                f"Qoder broker-reported usage: total={total_input}, "
                f"fresh={fresh_input}, cache_read={cache_read}, cache_write={cache_write}"
            )
        else:
            notes.append("Qoder 无 provider usage 数据，使用本地估算。")
        if cache_read > 0:
            notes.append(
                "Cache Read 只作为 provider-reported accounting 展示；"
                "不作为 request 内容 bucket 参与分布或本地重建覆盖率。"
            )
        if cache_write > 0:
            notes.append("Cache Write 仅作为 provider cache creation/write 统计展示，不进入 request bucket 分母。")
        if use_full_messages_bucket:
            notes.append("已使用 call-scoped full_messages_array 重建 Qoder request-side API messages。")
        elif not prior_messages and lc.request_full:
            notes.append("History messages: 无明确 prior messages，request_full 内容归入 captured_context_fragment。")
        notes.append(tool_schema_summary)

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
                fill_strategy="known request content buckets / fresh_input",
            ),
            unknown=AttributedValue(
                value=unknown_val, unit="tokens",
                precision=ValuePrecision.RESIDUAL,
                source=ValueSource.RESIDUAL,
                fill_strategy="fresh_input - sum(known request content buckets)",
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


def _int_or_zero(value) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
