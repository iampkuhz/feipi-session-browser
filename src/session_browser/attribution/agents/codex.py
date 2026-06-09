"""Codex attribution builder.

Codex defaults to session jsonl / response items processing.
Do NOT assume raw body availability.  Cache semantics are OpenAI/Codex style:
input_tokens is the request input size, cached_input_tokens is cache read,
no cache_write.
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


_DEFAULT_SCHEMA_TOKENS_PER_TOOL = 240


def _parse_json_object(text: str) -> dict:
    """Safely parse a JSON string into a dict."""
    if not text:
        return {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _int_or_zero(value) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _nested_int(d: dict, outer: str, inner: str) -> int:
    child = d.get(outer)
    if isinstance(child, dict):
        return _int_or_zero(child.get(inner))
    return 0


def _extract_codex_usage_from_raw(raw: dict) -> dict:
    """Extract usage from a raw parsed JSON dict (request/response body).

    Handles:
    - Direct usage dict
    - response.usage
    - data.usage
    - turn.completed with usage key
    """
    if not isinstance(raw, dict):
        return {}

    candidates = []
    if any(k in raw for k in ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens")):
        candidates.append((raw, "direct"))
    if isinstance(raw.get("usage"), dict):
        candidates.append((raw["usage"], "usage"))
    if isinstance(raw.get("response"), dict) and isinstance(raw["response"].get("usage"), dict):
        candidates.append((raw["response"]["usage"], "response.usage"))
    if isinstance(raw.get("data"), dict) and isinstance(raw["data"].get("usage"), dict):
        candidates.append((raw["data"]["usage"], "data.usage"))

    for usage, source in candidates:
        if not isinstance(usage, dict):
            continue
        input_tokens = _int_or_zero(usage.get("input_tokens") or usage.get("prompt_tokens"))
        cached = (
            _int_or_zero(usage.get("cached_input_tokens"))
            or _int_or_zero(usage.get("cache_read_input_tokens"))
            or _int_or_zero(usage.get("cached_tokens"))
            or _nested_int(usage, "input_tokens_details", "cached_tokens")
            or _nested_int(usage, "prompt_tokens_details", "cached_tokens")
        )
        output_tokens = _int_or_zero(usage.get("output_tokens") or usage.get("completion_tokens"))
        reasoning = (
            _int_or_zero(usage.get("reasoning_output_tokens"))
            or _int_or_zero(usage.get("reasoning_tokens"))
            or _int_or_zero(usage.get("thinking_tokens"))
            or _nested_int(usage, "output_tokens_details", "reasoning_tokens")
            or _nested_int(usage, "completion_tokens_details", "reasoning_tokens")
        )
        total = _int_or_zero(usage.get("total_tokens") or usage.get("total_token_usage"))
        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": min(cached, input_tokens) if input_tokens else cached,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": reasoning,
            "total_tokens": total,
            "_usage_source": source,
        }
    return {}


class CodexAttributionBuilder(BaseAttributionBuilder):
    """Request / response attribution for Codex sessions.

    Codex provides session usage totals with OpenAI/Codex semantics:
    - input_tokens is the logical request input size shown as Fresh
    - cached_input_tokens is cache read hit
    - No Anthropic-style cache_write
    - reasoning_output_tokens is part of output but hidden
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
        """Get available tool schemas. Codex typically does not expose this."""
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

    def _get_raw_request_payload(self) -> dict:
        """Parse raw HTTP request payload if available."""
        return _parse_json_object(self.llm_call.request_payload_raw)

    def _get_raw_response_payload(self) -> dict:
        """Parse raw HTTP response payload if available."""
        return _parse_json_object(self.llm_call.response_payload_raw)

    def _estimate_json_tokens(self, obj: dict) -> int:
        """Estimate tokens for a JSON object."""
        if not obj:
            return 0
        return estimate_tokens_from_text(json.dumps(obj, ensure_ascii=False, sort_keys=True))

    def _extract_request_buckets_from_raw(self, req_body: dict) -> dict:
        """Extract request-side bucket info from raw OpenAI Responses request body.

        Returns dict with keys: instructions_text, input_texts, tool_schemas_obj,
        has_previous_response_id, reasoning_config_obj, metadata_obj.
        """
        result = {
            "instructions_text": "",
            "current_user_input_text": "",
            "conversation_history_texts": [],
            "tool_outputs_texts": [],
            "tool_schemas_obj": None,
            "has_previous_response_id": False,
            "reasoning_config_obj": None,
            "metadata_tokens": 0,
        }

        if not req_body:
            return result

        # instructions field
        instructions = req_body.get("instructions", "")
        if isinstance(instructions, str) and instructions:
            result["instructions_text"] = instructions

        # input array
        input_items = req_body.get("input", [])
        if isinstance(input_items, list):
            for item in input_items:
                if not isinstance(item, dict):
                    continue
                role = item.get("role", "")
                item_type = item.get("type", "")

                if item_type == "function_call_output" or item_type == "tool_output":
                    # Tool output
                    output_text = item.get("output", "")
                    if isinstance(output_text, str) and output_text:
                        result["tool_outputs_texts"].append(output_text)
                elif role == "user":
                    # User message — last one is current, rest are history
                    content = item.get("content", "")
                    if isinstance(content, str) and content:
                        result["conversation_history_texts"].append(content)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict):
                                text = part.get("text", "")
                                if isinstance(text, str) and text:
                                    result["conversation_history_texts"].append(text)
                elif role == "assistant":
                    content = item.get("content", "")
                    if isinstance(content, str) and content:
                        result["conversation_history_texts"].append(content)

            # Last user input is current
            if result["conversation_history_texts"]:
                result["current_user_input_text"] = result["conversation_history_texts"].pop()

        # tools array (schemas)
        tools = req_body.get("tools")
        if isinstance(tools, list) and tools:
            result["tool_schemas_obj"] = tools

        # previous_response_id
        if req_body.get("previous_response_id"):
            result["has_previous_response_id"] = True

        # reasoning config
        reasoning = req_body.get("reasoning")
        if isinstance(reasoning, dict) and reasoning:
            result["reasoning_config_obj"] = reasoning

        # metadata
        metadata = req_body.get("metadata")
        if isinstance(metadata, dict):
            result["metadata_tokens"] = self._estimate_json_tokens(metadata)

        return result

    def _remove_known_fragments_from_texts(
        self, texts: list[str], known: list[str]
    ) -> list[str]:
        """Remove known text fragments from a list of texts."""
        if not known:
            return texts
        known_normalized = {_normalize_ws(t): t for t in known if t and len(t.strip()) >= 20}
        result = []
        for t in texts:
            if not t:
                continue
            stripped = t.strip()
            if stripped in known:
                continue
            norm = _normalize_ws(stripped)
            if norm in known_normalized:
                continue
            result.append(t)
        return result

    def build_request(self) -> LLMRequestAttribution:
        lc = self.llm_call

        # ── Step 1: total input from best available source ───────────────
        raw_input_total = 0
        request_input_tokens = 0
        cache_read_tokens = 0
        cache_write_tokens = 0
        precision_total = ValuePrecision.UNAVAILABLE
        source_total = ValueSource.HEURISTIC

        # Priority 1: token_breakdown_normalized
        if lc.token_breakdown_normalized:
            bd = lc.token_breakdown_normalized
            request_input_tokens = bd.fresh_input_tokens
            cache_read_tokens = bd.cache_read_tokens
            cache_write_tokens = bd.cache_write_tokens
            raw_input_total = request_input_tokens + cache_read_tokens + cache_write_tokens
            precision_total = ValuePrecision.PROVIDER_REPORTED
            source_total = ValueSource.PROVIDER_USAGE
        # Priority 2: llm_call fields
        elif lc.input_tokens > 0:
            request_input_tokens = lc.input_tokens
            cache_read_tokens = lc.cache_read_tokens
            cache_write_tokens = lc.cache_write_tokens
            raw_input_total = request_input_tokens + cache_read_tokens + cache_write_tokens
            precision_total = ValuePrecision.PROVIDER_REPORTED
            source_total = ValueSource.PROVIDER_USAGE
        # Priority 3: assistant_msg.usage
        elif lc.round_index >= 0 and self.round_obj and self.round_obj.assistant_msg:
            msg_usage = self.round_obj.assistant_msg.usage
            if msg_usage and isinstance(msg_usage, dict):
                from session_browser.sources.codex import _extract_codex_usage
                extracted = _extract_codex_usage(msg_usage)
                if extracted:
                    request_input_tokens = extracted.get("input_tokens", 0)
                    cache_read_tokens = extracted.get("cached_input_tokens", 0)
                    raw_input_total = request_input_tokens + cache_read_tokens + cache_write_tokens
                    precision_total = ValuePrecision.PROVIDER_REPORTED
                    source_total = ValueSource.PROVIDER_USAGE
        # Priority 4: raw response payload usage
        if raw_input_total == 0:
            resp_body = self._get_raw_response_payload()
            if resp_body:
                usage = _extract_codex_usage_from_raw(resp_body)
                if usage:
                    request_input_tokens = usage.get("input_tokens", 0)
                    cache_read_tokens = usage.get("cached_input_tokens", 0)
                    raw_input_total = request_input_tokens + cache_read_tokens + cache_write_tokens
                    precision_total = ValuePrecision.PROVIDER_REPORTED
                    source_total = ValueSource.PROVIDER_USAGE

        fresh_input_tokens = request_input_tokens

        total_input = AttributedValue(
            value=raw_input_total,
            unit="tokens",
            precision=precision_total,
            source=source_total,
            fill_strategy="from token_breakdown_normalized or session usage",
        )

        fresh_input = AttributedValue(
            value=fresh_input_tokens if precision_total != ValuePrecision.UNAVAILABLE else None,
            unit="tokens",
            precision=precision_total,
            source=source_total,
            fill_strategy="input_tokens request input size",
        )

        cache_read = AttributedValue(
            value=cache_read_tokens if cache_read_tokens > 0 else (
                0 if precision_total != ValuePrecision.UNAVAILABLE else None
            ),
            unit="tokens",
            precision=precision_total if cache_read_tokens > 0 else ValuePrecision.UNAVAILABLE,
            source=source_total if cache_read_tokens > 0 else ValueSource.HEURISTIC,
            fill_strategy="from cached_input_tokens or input_tokens_details.cached_tokens"
            if cache_read_tokens > 0 else "OpenAI/Codex may report cached_input_tokens; unavailable here",
        )

        cache_write = AttributedValue(
            value=0,
            unit="tokens",
            precision=ValuePrecision.UNAVAILABLE,
            source=ValueSource.HEURISTIC,
            fill_strategy="OpenAI/Codex Responses usage does not expose Anthropic-style cache_write/cache_creation tokens",
        )

        # ── Step 2: parse raw request payload for content buckets ───────
        req_body = self._get_raw_request_payload()
        raw_payload_available = bool(req_body)

        rb = {}
        if raw_payload_available:
            rb = self._extract_request_buckets_from_raw(req_body)

        # ── Step 3: estimate content buckets ────────────────────────────
        # Current user instruction
        user_msg_content = self.round_obj.user_msg.content if self.round_obj.user_msg else ""
        if raw_payload_available and rb.get("current_user_input_text"):
            current_user_tokens = estimate_tokens_from_text(rb["current_user_input_text"])
        else:
            current_user_tokens = estimate_tokens_from_text(user_msg_content)

        # Prior messages / conversation history
        prior_messages = self._extract_prior_messages()
        history_texts = []
        if raw_payload_available and rb.get("conversation_history_texts"):
            history_texts = rb["conversation_history_texts"]
        elif prior_messages:
            for pm in prior_messages:
                if isinstance(pm, dict):
                    content = pm.get("content", "")
                    if content:
                        history_texts.append(str(content))
                else:
                    history_texts.append(str(pm))

        history_msg_count = len(history_texts)
        history_tokens = estimate_tokens_from_text("\n".join(history_texts))

        # Tool outputs
        tool_result_texts = self._get_preceding_tool_result_texts()
        if raw_payload_available and rb.get("tool_outputs_texts"):
            # Dedup: remove known tool outputs from local tool_result_texts
            rb_tool = rb["tool_outputs_texts"]
            tool_result_texts = self._remove_known_fragments_from_texts(
                tool_result_texts, rb_tool
            )
            tool_outputs_tokens = estimate_tokens_from_text("\n".join(rb_tool))
        else:
            tool_outputs_tokens = estimate_tokens_from_text("\n".join(tool_result_texts))

        # Instructions
        instructions_tokens = 0
        if raw_payload_available and rb.get("instructions_text"):
            instructions_tokens = estimate_tokens_from_text(rb["instructions_text"])

        # Tool schemas from raw request
        tool_schema_tokens = 0
        if raw_payload_available and rb.get("tool_schemas_obj"):
            tool_schema_tokens = self._estimate_json_tokens(rb["tool_schemas_obj"])
        else:
            # Fallback: observed tools heuristic
            available_tools = self._get_available_tools()
            if available_tools:
                tool_schema_tokens = len(available_tools) * _DEFAULT_SCHEMA_TOKENS_PER_TOOL

        # Repository / file context from request_full or raw input
        repo_context_tokens = 0
        repo_context_text = ""
        if raw_payload_available:
            # Extract file refs from raw input
            input_items = req_body.get("input", [])
            file_texts = []
            for item in input_items:
                if isinstance(item, dict):
                    content = item.get("content", "")
                    if isinstance(content, str) and ("File:" in content or "file:" in content):
                        file_texts.append(content)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict):
                                text = part.get("text", "")
                                if isinstance(text, str) and ("File:" in text or "file:" in text):
                                    file_texts.append(text)
            if file_texts:
                repo_context_text = "\n".join(file_texts)[:3000]
                repo_context_tokens = estimate_tokens_from_text(repo_context_text)
        elif lc.request_full:
            file_refs = re.findall(r'(?:File|file|path)[:\s]+[^\n]+', lc.request_full)
            if file_refs:
                repo_context_text = "\n".join(file_refs)[:3000]
                repo_context_tokens = estimate_tokens_from_text(repo_context_text)

        # Reasoning config bucket
        reasoning_config_tokens = 0
        if raw_payload_available and rb.get("reasoning_config_obj"):
            reasoning_config_tokens = self._estimate_json_tokens(rb["reasoning_config_obj"])

        # Provider wrapper overhead (heuristic)
        provider_wrapper_tokens = 0
        if raw_payload_available:
            # Estimate from model name, store, include, etc.
            overhead_fields = {}
            for key in ("model", "store", "include", "max_output_tokens", "previous_response_id"):
                if key in req_body:
                    val = req_body[key]
                    if isinstance(val, str):
                        overhead_fields[key] = val
                    elif isinstance(val, (list, dict)):
                        overhead_fields[key] = val
            if overhead_fields:
                provider_wrapper_tokens = self._estimate_json_tokens(overhead_fields)

        # ── Step 4: previous_response_id residual handling ──────────────
        has_previous_response_id = raw_payload_available and rb.get("has_previous_response_id", False)

        # ── Step 5: normalize and assemble buckets ─────────────────────
        contributing_buckets = [
            instructions_tokens,
            current_user_tokens,
            history_tokens,
            tool_outputs_tokens,
            repo_context_tokens,
            tool_schema_tokens,
            reasoning_config_tokens,
        ]
        known_sum = sum(contributing_buckets)

        if raw_input_total > 0 and known_sum > raw_input_total:
            scale = raw_input_total / known_sum
            instructions_tokens = max(0, int(instructions_tokens * scale))
            history_tokens = max(0, int(history_tokens * scale))
            tool_outputs_tokens = max(0, int(tool_outputs_tokens * scale))
            current_user_tokens = max(0, int(current_user_tokens * scale))
            repo_context_tokens = max(0, int(repo_context_tokens * scale))
            tool_schema_tokens = max(0, int(tool_schema_tokens * scale))
            reasoning_config_tokens = max(0, int(reasoning_config_tokens * scale))
            known_sum = sum([
                instructions_tokens, current_user_tokens, history_tokens,
                tool_outputs_tokens, repo_context_tokens, tool_schema_tokens,
                reasoning_config_tokens,
            ])

        unknown_val = max(raw_input_total - known_sum, 0) if raw_input_total > 0 else 0

        buckets = []

        # Instructions bucket
        if instructions_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="instructions",
                label="Instructions / system prompt",
                tokens=instructions_tokens,
                percent=_pct(instructions_tokens, raw_input_total),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT if not raw_payload_available else ValueSource.PROVIDER_USAGE,
                confidence_label="中高",
                summary="OpenAI Responses instructions field token estimate.",
            ))

        # Current user instruction
        if current_user_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="current_user_instruction",
                label="Current user instruction",
                tokens=current_user_tokens,
                percent=_pct(current_user_tokens, raw_input_total),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中高",
                summary="用户指令从 session 或 raw request input 获取，token 通过文本估算。",
                content_preview=(rb.get("current_user_input_text") or user_msg_content or "")[:120],
            ))

        # Conversation history
        if history_tokens > 0 and history_texts:
            buckets.append(RequestAttributionBucket(
                key="conversation_history",
                label="Conversation history",
                tokens=history_tokens,
                percent=_pct(history_tokens, raw_input_total),
                count_label=f"{history_msg_count} messages",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary="对话历史从 prior messages 或 raw request input 获取，token 通过文本估算。",
            ))

        # Previous response state / server-side conversation state
        if has_previous_response_id:
            prev_resp_id = req_body.get("previous_response_id", "")
            summary_text = (
                f"Responses API carries prior context by previous_response_id={prev_resp_id!r}; "
                f"local raw request does not include the full replay. "
                f"Large unknown/residual may come from server-side conversation state."
            )
            buckets.append(RequestAttributionBucket(
                key="previous_response_state",
                label="Server-side conversation state (previous_response_id)",
                tokens=0,
                percent=0.0,
                precision=ValuePrecision.EXACT,
                source=ValueSource.PROVIDER_USAGE,
                confidence_label="中",
                summary=summary_text,
                contributes_to_total=False,
                display_group="metadata",
            ))

        # Tool outputs
        if tool_outputs_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_outputs",
                label="Tool outputs",
                tokens=tool_outputs_tokens,
                percent=_pct(tool_outputs_tokens, raw_input_total),
                count_label=f"{len(rb.get('tool_outputs_texts') or tool_result_texts)} outputs",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TOOL_LOGS,
                confidence_label="中",
                summary="Tool outputs 从工具日志或 raw request input 获取，token 通过文本估算。",
            ))

        # Repository / file context
        if repo_context_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="repository_file_context",
                label="Repository / file context",
                tokens=repo_context_tokens,
                percent=_pct(repo_context_tokens, raw_input_total),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中低",
                summary="从 session 可见文件或 raw request input 中的文件片段估算。",
                content_preview=repo_context_text[:120] if repo_context_text else "",
            ))

        # Tool schemas
        if tool_schema_tokens > 0:
            source_label = "raw_request_tools" if (raw_payload_available and rb.get("tool_schemas_obj")) else "observed_tools_heuristic"
            buckets.append(RequestAttributionBucket(
                key="tool_schemas",
                label="Tool schemas",
                tokens=tool_schema_tokens,
                percent=_pct(tool_schema_tokens, raw_input_total),
                precision=ValuePrecision.ESTIMATED if source_label == "observed_tools_heuristic" else ValuePrecision.ESTIMATED,
                source=ValueSource.TOOL_LIST,
                confidence_label="中" if source_label == "raw_request_tools" else "中低",
                summary=(
                    f"从 raw request tools 数组估算。"
                    if source_label == "raw_request_tools"
                    else f"按 observed tools 估算，非完整 schema。"
                ),
            ))
        else:
            buckets.append(RequestAttributionBucket(
                key="tool_schemas",
                label="Tool schemas",
                tokens=0,
                percent=0.0,
                precision=ValuePrecision.UNAVAILABLE,
                source=ValueSource.HEURISTIC,
                confidence_label="低",
                summary="无法从本地日志或 raw request 获取可用工具定义。",
            ))

        # Reasoning config
        if reasoning_config_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="reasoning_config",
                label="Reasoning config",
                tokens=reasoning_config_tokens,
                percent=_pct(reasoning_config_tokens, raw_input_total),
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.PROVIDER_USAGE,
                confidence_label="中",
                summary="OpenAI Responses reasoning configuration overhead.",
                contributes_to_total=True,
                display_group="metadata",
            ))

        # Provider wrapper overhead
        if provider_wrapper_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="provider_wrapper_overhead",
                label="Provider wrapper overhead",
                tokens=provider_wrapper_tokens,
                percent=_pct(provider_wrapper_tokens, raw_input_total),
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.HEURISTIC,
                confidence_label="低",
                summary="JSON framing, metadata, previous_response_id 等 provider wrapper 开销估算。",
                contributes_to_total=True,
                display_group="metadata",
            ))

        # Unknown / residual
        buckets.append(RequestAttributionBucket(
            key="unknown_overhead",
            label="未定位",
            tokens=unknown_val,
            percent=_pct(unknown_val, raw_input_total),
            precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
            confidence_label="中",
            summary=(
                "Total input 减去已知 bucket 后的剩余部分。"
                + (f" 存在 previous_response_id，残差可能来自服务端 conversation state。" if has_previous_response_id else "")
                + (f" 无 raw request payload，只能做 transcript 估算。" if not raw_payload_available else "")
            ),
        ))

        # ── Step 6: coverage ───────────────────────────────────────────
        known_bucket_sum = sum(
            b.tokens for b in buckets
            if b.key not in ("unknown_overhead",) and b.contributes_to_total
        )
        coverage_val = (min(known_bucket_sum / raw_input_total, 1.0)
                        if raw_input_total > 0 else 0.0)

        # ── Step 7: availability rows ──────────────────────────────────
        avail_rows = [
            self._avail("total_input", "Total input tokens", raw_input_total > 0,
                        precision=precision_total,
                        source=source_total,
                        fill_strategy="token_breakdown_normalized or session usage"),
            self._avail("fresh_input", "Fresh input tokens",
                        fresh_input_tokens > 0,
                        precision=precision_total,
                        source=source_total,
                        fill_strategy="input_tokens request input size"),
            self._avail("cache_read", "Cache read tokens",
                        cache_read_tokens > 0,
                        precision=precision_total if cache_read_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=source_total if cache_read_tokens > 0 else ValueSource.HEURISTIC,
                        fill_strategy="from cached_input_tokens or input_tokens_details.cached_tokens"
                        if cache_read_tokens > 0 else "OpenAI/Codex may report cached_input_tokens; unavailable here"),
            self._avail("cache_write", "Cache write tokens", False,
                        precision=ValuePrecision.UNAVAILABLE,
                        source=ValueSource.HEURISTIC,
                        fill_strategy="OpenAI/Codex Responses usage does not expose Anthropic-style cache_write/cache_creation tokens"),
            self._avail("raw_request_payload", "Raw request payload available",
                        raw_payload_available, exact=True,
                        precision=ValuePrecision.EXACT if raw_payload_available else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if raw_payload_available else ValueSource.HEURISTIC,
                        fill_strategy="from llm_call.request_payload_raw"),
            self._avail("responses_previous_response_id", "Responses API previous_response_id",
                        has_previous_response_id, exact=True,
                        precision=ValuePrecision.EXACT,
                        source=ValueSource.PROVIDER_USAGE if has_previous_response_id else ValueSource.HEURISTIC,
                        fill_strategy="from raw request previous_response_id"),
            self._avail("conversation_history_tokens", "Conversation history tokens",
                        history_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if history_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT if history_tokens > 0 else ValueSource.HEURISTIC,
                        fill_strategy="estimated from prior messages or raw request input" if history_tokens > 0 else "no prior messages"),
            self._avail("tool_outputs_tokens", "Tool outputs tokens",
                        tool_outputs_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED,
                        source=ValueSource.TOOL_LOGS,
                        fill_strategy="estimated from text"),
            self._avail("tool_schemas_tokens", "Tool schemas tokens",
                        tool_schema_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if tool_schema_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TOOL_LIST,
                        fill_strategy="from raw request tools or observed tools heuristic"),
            self._avail("repository_file_context_tokens", "Repository / file context tokens",
                        repo_context_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="estimated from file snippets"),
            self._avail("unknown", "Unknown / residual", True, exact=False,
                        precision=ValuePrecision.RESIDUAL,
                        source=ValueSource.RESIDUAL,
                        fill_strategy="residual"),
        ]

        # ── Step 8: notes ──────────────────────────────────────────────
        notes = []
        if cache_read_tokens > 0:
            notes.append(
                f"input_tokens={fresh_input_tokens} 作为 Fresh request input；"
                f"cached_input_tokens={cache_read_tokens} 作为 Cache Read；"
                f"input-side total={raw_input_total}。"
            )
        else:
            notes.append(
                "Codex/OpenAI input_tokens 作为 Fresh request input；"
                "本次调用未报告 cached_input_tokens，Cache Read 不可用。"
            )
        notes.append(
            "OpenAI/Codex 不提供 Anthropic-style cache_write/cache_creation tokens。"
        )
        if not raw_payload_available:
            notes.append("无 raw request/response payload，buckets 通过 transcript/session 文本估算。")
        if has_previous_response_id:
            notes.append(
                "存在 previous_response_id：一部分上下文可能在 provider server-side，不在本地 raw request 展开，残差可能来自服务端 conversation state。"
            )

        return LLMRequestAttribution(
            agent="codex",
            model=lc.model or "unknown",
            request_id=lc.id or "unavailable",
            call_id=lc.id,
            source_label="session jsonl" + (" + raw payload" if raw_payload_available else ""),
            confidence_label="高" if raw_payload_available else "中",
            raw_body_available=raw_payload_available,
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
            captured_context_preview=repo_context_text[:500] if repo_context_text else "",
            attribution_notes=notes,
            availability_rows=avail_rows,
        )

    def build_response(self) -> LLMResponseAttribution:
        lc = self.llm_call

        # ── Step 1: total output from best available source ──────────────
        total_output_val = 0
        reasoning_output_tokens = 0
        precision_total = ValuePrecision.UNAVAILABLE
        source_total = ValueSource.HEURISTIC

        # Priority 1: token_breakdown_normalized
        if lc.token_breakdown_normalized:
            bd = lc.token_breakdown_normalized
            total_output_val = lc.output_tokens or bd.output_tokens
            raw_fields = bd.raw_fields or {}
            reasoning_from_bd = (
                _int_or_zero(raw_fields.get("reasoning_output_tokens"))
                or _int_or_zero(raw_fields.get("reasoning_tokens"))
                or _int_or_zero(raw_fields.get("thinking_tokens"))
            )
            if reasoning_from_bd > 0:
                reasoning_output_tokens = reasoning_from_bd
            precision_total = ValuePrecision.PROVIDER_REPORTED
            source_total = ValueSource.PROVIDER_USAGE
        # Priority 2: llm_call.output_tokens + assistant_msg.usage
        if total_output_val == 0:
            total_output_val = lc.output_tokens or 0
        if total_output_val == 0 and self.round_obj and self.round_obj.assistant_msg:
            msg_usage = self.round_obj.assistant_msg.usage
            if msg_usage and isinstance(msg_usage, dict):
                from session_browser.sources.codex import _extract_codex_usage
                extracted = _extract_codex_usage(msg_usage)
                if extracted:
                    total_output_val = extracted.get("output_tokens", 0)
                    reasoning_output_tokens = extracted.get("reasoning_output_tokens", 0)
                    precision_total = ValuePrecision.PROVIDER_REPORTED
                    source_total = ValueSource.PROVIDER_USAGE
        # Priority 3: raw response payload usage
        if total_output_val == 0:
            resp_body = self._get_raw_response_payload()
            if resp_body:
                usage = _extract_codex_usage_from_raw(resp_body)
                if usage:
                    total_output_val = usage.get("output_tokens", 0)
                    reasoning_output_tokens = usage.get("reasoning_output_tokens", 0)
                    precision_total = ValuePrecision.PROVIDER_REPORTED
                    source_total = ValueSource.PROVIDER_USAGE
        # Check raw response for reasoning even if total is known
        if reasoning_output_tokens == 0:
            resp_body = self._get_raw_response_payload()
            if resp_body:
                usage = _extract_codex_usage_from_raw(resp_body)
                if usage:
                    reasoning_output_tokens = usage.get("reasoning_output_tokens", 0)

        # ── Step 2: visible content ────────────────────────────────────
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

        # Metadata
        metadata_tokens = 0
        if lc.finish_reason:
            metadata_tokens += 10

        # ── Step 3: normalize with provider total ──────────────────────
        known_sum = visible_text_tokens + tool_use_tokens + metadata_tokens + reasoning_output_tokens

        if total_output_val > 0:
            if known_sum > total_output_val:
                # Scale estimated buckets, but DO NOT scale provider-reported reasoning tokens
                estimated_sum = visible_text_tokens + tool_use_tokens + metadata_tokens
                if estimated_sum > 0:
                    # Check if reasoning > total (anomalous)
                    if reasoning_output_tokens > total_output_val:
                        reasoning_output_tokens = total_output_val
                    scale = (total_output_val - reasoning_output_tokens) / estimated_sum
                    if scale < 0:
                        scale = 0
                    visible_text_tokens = max(0, int(visible_text_tokens * scale))
                    tool_use_tokens = max(0, int(tool_use_tokens * scale))
                    metadata_tokens = max(0, int(metadata_tokens * scale))
                known_sum = visible_text_tokens + tool_use_tokens + metadata_tokens + reasoning_output_tokens
            unknown_val = max(total_output_val - known_sum, 0)
        else:
            unknown_val = 0
            total_output_val = known_sum
            precision_total = ValuePrecision.ESTIMATED
            source_total = ValueSource.HEURISTIC

        total_output = AttributedValue(
            value=total_output_val,
            unit="tokens",
            precision=precision_total,
            source=source_total,
            fill_strategy="provider output_tokens" if precision_total == ValuePrecision.PROVIDER_REPORTED else "sum of visible content",
        )

        # ── Step 4: buckets ────────────────────────────────────────────
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
                summary="助手可见文本从 session response_full 获取，token 通过文本估算。",
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
                contributes_to_total=True,
            ))

        # Reasoning output tokens bucket (hidden, provider-reported)
        if reasoning_output_tokens > 0:
            buckets.append(ResponseAttributionBucket(
                key="reasoning_output_tokens",
                label="Hidden reasoning output tokens",
                tokens=reasoning_output_tokens,
                percent=_pct(reasoning_output_tokens, total_output_val),
                precision=ValuePrecision.PROVIDER_REPORTED,
                source=ValueSource.PROVIDER_USAGE,
                confidence_label="高",
                summary="OpenAI/Codex reports hidden reasoning tokens as output-side usage; "
                        "these are billed/counted as output but are not visible assistant text.",
                contributes_to_total=True,
                display_group="reasoning",
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

        # structured_items: display-only bucket
        if lc.content_blocks:
            structured_tokens_val = estimate_tokens_from_text(
                json.dumps(lc.content_blocks, ensure_ascii=False))
            if structured_tokens_val > 0:
                buckets.append(ResponseAttributionBucket(
                    key="structured_items",
                    label="Structured items (display-only)",
                    tokens=structured_tokens_val,
                    percent=0.0,
                    precision=ValuePrecision.ESTIMATED,
                    source=ValueSource.TRANSCRIPT,
                    confidence_label="低",
                    summary="content_blocks 序列化副本，仅用于展示，不参与总量归因。",
                    contributes_to_total=False,
                    display_group="structured_items",
                ))

        # ── Step 5: coverage ───────────────────────────────────────────
        known_bucket_sum = sum(
            b.tokens for b in buckets
            if b.key not in ("unknown",) and b.contributes_to_total
        )
        coverage_val = (min(known_bucket_sum / total_output_val, 1.0)
                        if total_output_val > 0 else 0.0)

        finish_str = lc.finish_reason or ""
        avail_rows = [
            self._avail("total_output", "Total output tokens", total_output_val > 0,
                        precision=precision_total,
                        source=source_total,
                        fill_strategy="provider output_tokens" if precision_total == ValuePrecision.PROVIDER_REPORTED else "estimated"),
            self._avail("visible_assistant_text", "Visible assistant text tokens",
                        visible_text_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if visible_text_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="estimated from response_full"),
            self._avail("tool_use_structure", "Tool use structure",
                        bool(lc.content_blocks or lc.tool_calls_raw), exact=True,
                        precision=ValuePrecision.TRANSCRIPT_EXACT,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="from content_blocks or tool_calls_raw"),
            self._avail("tool_use_tokens", "Tool use tokens",
                        tool_use_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if tool_use_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="estimated from serialization"),
            self._avail("reasoning_output_tokens", "Hidden reasoning output tokens",
                        reasoning_output_tokens > 0, exact=False,
                        precision=ValuePrecision.PROVIDER_REPORTED if reasoning_output_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if reasoning_output_tokens > 0 else ValueSource.HEURISTIC,
                        fill_strategy="from provider usage reasoning_output_tokens / output_tokens_details.reasoning_tokens"),
            self._avail("raw_response_payload", "Raw response payload available",
                        bool(lc.response_payload_raw), exact=True,
                        precision=ValuePrecision.EXACT if lc.response_payload_raw else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.PROVIDER_USAGE if lc.response_payload_raw else ValueSource.HEURISTIC,
                        fill_strategy="from llm_call.response_payload_raw"),
            self._avail("finish_reason", "Finish reason", bool(finish_str),
                        exact=True,
                        precision=ValuePrecision.EXACT if finish_str else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="from llm_call.finish_reason"),
            self._avail("structured_items", "Structured items (display-only)",
                        bool(lc.content_blocks), exact=False,
                        precision=ValuePrecision.ESTIMATED,
                        source=ValueSource.TRANSCRIPT,
                        fill_strategy="JSON length estimate, contributes_to_total=False"),
            self._avail("unknown", "Unknown / residual", True, exact=False,
                        precision=ValuePrecision.RESIDUAL,
                        source=ValueSource.RESIDUAL,
                        fill_strategy="residual"),
        ]

        # Notes
        notes = []
        if reasoning_output_tokens > 0:
            notes.append(
                f"reasoning_output_tokens={reasoning_output_tokens} 是 output 侧 hidden usage，"
                f"不能归到 visible text；包含在 total_output={total_output_val} 中。"
            )
        if not lc.response_payload_raw and not lc.token_breakdown_normalized:
            notes.append("无 raw response payload 或 normalized breakdown，response buckets 通过 transcript 文本估算。")

        return LLMResponseAttribution(
            agent="codex",
            model=lc.model or "unknown",
            request_id=lc.id or "unavailable",
            call_id=lc.id,
            source_label="session jsonl" + (" + raw payload" if lc.response_payload_raw else ""),
            confidence_label="高" if lc.response_payload_raw else "中",
            raw_body_available=bool(lc.response_payload_raw),
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
            attribution_notes=notes,
            availability_rows=avail_rows,
        )


def _normalize_ws(text: str) -> str:
    """Collapse whitespace for normalized comparison."""
    import re
    return re.sub(r'\s+', ' ', text).strip()


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total * 100, 1)
