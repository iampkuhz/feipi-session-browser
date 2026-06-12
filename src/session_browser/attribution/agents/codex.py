"""Codex attribution builder.

Codex defaults to session jsonl / response items processing.
Do NOT assume raw body availability.  Cache semantics are OpenAI/Codex style:
input_tokens is the request input size, cached_input_tokens is cache read,
no cache_write.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
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


_CODEX_BUILTIN_TOOL_SCHEMAS: dict[str, dict] = {
    "exec_command": {
        "name": "exec_command",
        "description": (
            "Run a shell command in a PTY or pipe-backed process for local repository work. "
            "The tool schema includes command text, working directory, shell/login options, "
            "TTY selection, output budget, yield timing, and optional sandbox/escalation metadata."
        ),
        "input_schema": {
            "type": "object",
            "required": ["cmd"],
            "properties": {
                "cmd": {"type": "string", "description": "Shell command to execute."},
                "workdir": {"type": "string", "description": "Working directory for the command."},
                "yield_time_ms": {"type": "integer", "description": "Milliseconds to wait before yielding output."},
                "max_output_tokens": {"type": "integer", "description": "Output token budget."},
                "tty": {"type": "boolean", "description": "Allocate a PTY."},
                "shell": {"type": "string", "description": "Shell binary to launch."},
                "login": {"type": "boolean", "description": "Use login shell semantics."},
                "sandbox_permissions": {"type": "string", "description": "Sandbox override when supported."},
                "justification": {"type": "string", "description": "User-facing approval reason when escalation is required."},
            },
        },
        "token_estimate": 1450,
    },
    "apply_patch": {
        "name": "apply_patch",
        "description": (
            "Apply a structured patch to add, update, move, or delete files. "
            "The schema is grammar-driven and carries the begin/end patch envelope, "
            "file hunk headers, context lines, additions, removals, move targets, and EOF markers."
        ),
        "input_schema": {
            "type": "string",
            "description": "Patch text using the Codex apply_patch grammar.",
        },
        "token_estimate": 1250,
    },
    "write_stdin": {
        "name": "write_stdin",
        "description": (
            "Send literal stdin bytes to an existing exec session and collect recent output. "
            "Used for long-running commands, interactive cancellation, and polling process completion."
        ),
        "input_schema": {
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {"type": "integer", "description": "Existing exec session id."},
                "chars": {"type": "string", "description": "Characters to write to stdin."},
                "yield_time_ms": {"type": "integer", "description": "Milliseconds to wait before yielding output."},
                "max_output_tokens": {"type": "integer", "description": "Output token budget."},
            },
        },
        "token_estimate": 360,
    },
    "update_plan": {
        "name": "update_plan",
        "description": (
            "Publish a short task plan with at most one in-progress item. "
            "The schema carries an optional explanation and a list of step/status pairs."
        ),
        "input_schema": {
            "type": "object",
            "required": ["plan"],
            "properties": {
                "explanation": {"type": "string", "description": "Optional plan update explanation."},
                "plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["step", "status"],
                        "properties": {
                            "step": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                        },
                    },
                },
            },
        },
        "token_estimate": 260,
    },
    "view_image": {
        "name": "view_image",
        "description": (
            "Open a local image file for visual inspection with configurable detail level. "
            "Used when implementation requires checking screenshots, generated images, or saved UI captures."
        ),
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the image file."},
                "detail": {"type": "string", "enum": ["high", "original"], "description": "Image detail level."},
            },
        },
        "token_estimate": 180,
    },
}

_CODEX_TOOL_ALIASES = {
    "shell": "exec_command",
    "bash": "exec_command",
    "exec": "exec_command",
    "command": "exec_command",
    "patch": "apply_patch",
}
_CODEX_DEFAULT_TOOL_ORDER = ["exec_command", "apply_patch", "write_stdin", "update_plan", "view_image"]


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


def _codex_message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts)
    return ""


def _compact_preview(text: str, limit: int = 180) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _detail_item(
    label: str,
    text: str,
    *,
    source_type: str = "",
    role: str = "",
    tokens: int | None = None,
    index: int | None = None,
    extra: dict | None = None,
) -> dict:
    full_content = str(text or "")
    item = {
        "label": label,
        "name": label,
        "source_type": source_type,
        "role": role,
        "summary": _compact_preview(full_content, 180),
        "preview": _compact_preview(full_content, 260),
        "full_content": full_content,
        "tokens": tokens if tokens is not None else estimate_tokens_from_text(full_content),
    }
    if index is not None:
        item["message_index"] = index
    if extra:
        item.update(extra)
    return item


def _source_items_details(
    items: list[dict],
    *,
    kind: str = "source_items",
    explanation: list[str] | None = None,
) -> dict:
    details = {"kind": kind, "items": items, "total_items": len(items), "truncated": False}
    if explanation:
        details["explanation"] = explanation
    return details


def _text_items(
    texts: list[str],
    label_prefix: str,
    *,
    source_type: str = "",
) -> list[dict]:
    return [
        _detail_item(
            f"{label_prefix} #{idx + 1}",
            text,
            source_type=source_type,
            index=idx,
        )
        for idx, text in enumerate(texts)
        if text
    ]


@lru_cache(maxsize=64)
def _read_codex_visible_instruction_sources(file_path: str) -> tuple[tuple[str, str], ...]:
    """Read locally visible Codex system/developer instruction sources.

    Codex rollout JSONL does not expose a raw HTTP request body, but the
    beginning of the file does persist base instructions and developer/system
    messages before the first user message.  These are stable request-side
    inputs and account for a large portion of cache-heavy request attribution.
    """
    if not file_path:
        return tuple()
    path = Path(file_path)
    if not path.exists():
        return tuple()

    sources: list[tuple[str, str]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = ev.get("payload", {})
                if ev.get("type") == "event_msg" and payload.get("type") == "user_message":
                    break
                if ev.get("type") == "session_meta":
                    base = payload.get("base_instructions")
                    if isinstance(base, dict):
                        text = str(base.get("text") or "")
                    elif isinstance(base, str):
                        text = base
                    else:
                        text = ""
                    if text:
                        sources.append(("base_instructions", text))
                elif (
                    ev.get("type") == "response_item"
                    and payload.get("type") == "message"
                    and payload.get("role") in ("developer", "system")
                ):
                    text = _codex_message_text(payload.get("content"))
                    if text:
                        sources.append((str(payload.get("role")), text))
    except OSError:
        return tuple()
    return tuple(sources)


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

    def _tool_schema_tokens_and_details(self, observed_tools: list[str]) -> tuple[int, dict, str, str, str]:
        """Return a Codex tool-schema fallback footprint.

        Codex rollout logs expose invoked tools, not the full tool schema list
        sent to the model.  Use a stable Codex builtin catalog as the baseline
        and add any observed non-default tools as low-confidence extras.
        """
        ordered_tools: list[str] = []
        seen: set[str] = set()

        def add_tool(name: str) -> None:
            canonical = _CODEX_TOOL_ALIASES.get(str(name or ""), str(name or ""))
            if canonical and canonical not in seen:
                ordered_tools.append(canonical)
                seen.add(canonical)

        for name in _CODEX_DEFAULT_TOOL_ORDER:
            add_tool(name)
        for name in observed_tools or []:
            add_tool(name)

        items = []
        total = 0
        for name in ordered_tools:
            schema = _CODEX_BUILTIN_TOOL_SCHEMAS.get(name)
            if schema:
                estimated_tokens = int(schema.get("token_estimate") or 0)
                source_type = "codex_builtin_tool_schema"
                precision = "codex_builtin_estimate"
                description = str(schema.get("description") or "")
                input_schema_obj = schema.get("input_schema") or {}
            else:
                estimated_tokens = _DEFAULT_SCHEMA_TOKENS_PER_TOOL
                source_type = "codex_observed_tool_fallback"
                precision = "heuristic"
                description = f"Observed Codex tool name: {name}"
                input_schema_obj = {"type": "object", "description": "Observed tool; full schema unavailable."}

            schema_payload = {
                "name": name,
                "description": description,
                "input_schema": input_schema_obj,
                "token_estimate": estimated_tokens,
            }
            schema_text = json.dumps(schema_payload, ensure_ascii=False, sort_keys=True, indent=2)
            total += max(0, estimated_tokens)
            items.append({
                "label": name,
                "name": name,
                "source": source_type,
                "source_type": source_type,
                "enabled": True,
                "description_preview": _compact_preview(description, 180),
                "estimated_tokens": estimated_tokens,
                "tokens": estimated_tokens,
                "precision": precision,
                "description": description,
                "input_schema": json.dumps(input_schema_obj, ensure_ascii=False, sort_keys=True, indent=2),
                "summary": _compact_preview(description, 180),
                "preview": _compact_preview(schema_text, 260),
                "full_content": schema_text,
            })

        details = {
            "kind": "tools",
            "items": items,
            "total_items": len(items),
            "truncated": False,
            "explanation": [
                "Codex rollout 未持久化完整 available tools schema；使用 Codex builtin tool catalog 估算，并补充本 session 观测到的额外工具。",
            ],
        }
        summary = "Codex rollout 未持久化完整 available tools schema；使用 Codex builtin tool catalog 估算。"
        count_label = f"{len(items)} tools"
        return total, details, summary, count_label, "codex_builtin_catalog"

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

    def _extract_request_full_parts(
        self,
        request_full: str,
        *,
        current_user_text: str = "",
    ) -> dict:
        """Split rendered Codex request context into visible local sources.

        Codex rollout logs generally do not persist raw HTTP request bodies.
        The source parser therefore renders user input and tool outputs into
        ``request_full``.  This helper keeps those reconstructed sources
        separate so request attribution can credit tool outputs and avoid
        double-counting the current user message.
        """
        result = {
            "tool_outputs_texts": [],
            "context_texts": [],
        }
        text = (request_full or "").strip()
        if not text:
            return result

        current_user_norm = _normalize_ws(current_user_text or "")
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        for part in parts:
            match = re.match(
                r"^(?:Tool output|Tool result) for (\S+):\n(?P<body>.*)$",
                part,
                re.DOTALL,
            )
            if match:
                body = (match.group("body") or "").strip()
                if body:
                    result["tool_outputs_texts"].append(body)
                continue

            if current_user_norm and _normalize_ws(part) == current_user_norm:
                continue
            result["context_texts"].append(part)

        return result

    def _prior_message_stats(self, prior_messages: list[dict]) -> tuple[list[str], int]:
        """Return displayable prior snippets and full-content token estimates."""
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
        request_full_parts = {}
        if not raw_payload_available and lc.request_full:
            request_full_parts = self._extract_request_full_parts(
                lc.request_full,
                current_user_text=user_msg_content,
            )
        current_user_text = rb.get("current_user_input_text") or user_msg_content or ""
        if raw_payload_available and rb.get("current_user_input_text"):
            current_user_tokens = estimate_tokens_from_text(rb["current_user_input_text"])
        else:
            current_user_tokens = estimate_tokens_from_text(user_msg_content)

        # Prior messages / conversation history
        prior_messages = self._extract_prior_messages()
        history_texts = []
        history_tokens = 0
        if raw_payload_available and rb.get("conversation_history_texts"):
            history_texts = rb["conversation_history_texts"]
            history_tokens = estimate_tokens_from_text("\n".join(history_texts))
        elif prior_messages:
            history_texts, history_tokens = self._prior_message_stats(prior_messages)

        history_msg_count = len(history_texts)

        # Tool outputs
        tool_result_texts = self._get_preceding_tool_result_texts()
        tool_outputs_for_count = tool_result_texts
        if raw_payload_available and rb.get("tool_outputs_texts"):
            # Dedup: remove known tool outputs from local tool_result_texts
            rb_tool = rb["tool_outputs_texts"]
            tool_result_texts = self._remove_known_fragments_from_texts(
                tool_result_texts, rb_tool
            )
            tool_outputs_for_count = rb_tool
            tool_outputs_tokens = estimate_tokens_from_text("\n".join(rb_tool))
        else:
            request_tool_outputs = request_full_parts.get("tool_outputs_texts") or []
            if request_tool_outputs:
                tool_result_texts = self._remove_known_fragments_from_texts(
                    tool_result_texts,
                    request_tool_outputs,
                )
                tool_outputs_for_count = request_tool_outputs + tool_result_texts
            else:
                tool_outputs_for_count = tool_result_texts
            tool_outputs_tokens = estimate_tokens_from_text("\n".join(tool_outputs_for_count))

        # Captured request context from rendered request_full.  This is visible
        # local context that is neither the current user message nor a tool
        # output.  File-like snippets are also credited below as repo context.
        captured_context_texts = request_full_parts.get("context_texts") or []
        captured_context_texts = self._remove_known_fragments_from_texts(
            captured_context_texts,
            tool_outputs_for_count,
        )
        captured_context_text = "\n\n".join(captured_context_texts)
        captured_context_tokens = estimate_tokens_from_text(captured_context_text)

        # Instructions
        instructions_tokens = 0
        instruction_sources: tuple[tuple[str, str], ...] = tuple()
        instructions_source_summary = "OpenAI Responses instructions field token estimate."
        if raw_payload_available and rb.get("instructions_text"):
            instructions_tokens = estimate_tokens_from_text(rb["instructions_text"])
        elif self.session_summary is not None:
            instruction_sources = _read_codex_visible_instruction_sources(
                getattr(self.session_summary, "file_path", "") or ""
            )
            if instruction_sources:
                instructions_tokens = sum(
                    estimate_tokens_from_text(text)
                    for _label, text in instruction_sources
                )
                source_labels = ", ".join(label for label, _text in instruction_sources)
                instructions_source_summary = (
                    "从 Codex rollout 开头可见的 session_meta/developer/system "
                    f"上下文估算（{source_labels}）。"
                )

        # Tool schemas from raw request or Codex builtin fallback
        tool_schema_tokens = 0
        available_tools = []
        tool_schema_source_label = ""
        tool_schema_summary = ""
        tool_schema_count_label = ""
        tool_schema_details: dict | None = None
        if raw_payload_available and rb.get("tool_schemas_obj"):
            tool_schema_tokens = self._estimate_json_tokens(rb["tool_schemas_obj"])
            tool_schema_source_label = "raw_request_tools"
            tool_schema_summary = "从 raw request tools 数组估算。"
        else:
            available_tools = self._get_available_tools()
            (
                tool_schema_tokens,
                tool_schema_details,
                tool_schema_summary,
                tool_schema_count_label,
                tool_schema_source_label,
            ) = self._tool_schema_tokens_and_details(available_tools)

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
        elif captured_context_text:
            file_refs = re.findall(r'(?:File|file|path)[:\s]+[^\n]+', captured_context_text)
            if file_refs:
                repo_context_text = "\n".join(file_refs)[:3000]
                repo_context_tokens = estimate_tokens_from_text(repo_context_text)

        # Reasoning config bucket
        reasoning_config_tokens = 0
        if raw_payload_available and rb.get("reasoning_config_obj"):
            reasoning_config_tokens = self._estimate_json_tokens(rb["reasoning_config_obj"])

        # Provider-reported cache read is an input-side bucket in this product's
        # token accounting.  The exact cached content is opaque without raw
        # provider state, but the token count and source category are known.
        provider_cached_context_tokens = max(0, cache_read_tokens)

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
        estimated_buckets = [
            instructions_tokens,
            current_user_tokens,
            history_tokens,
            tool_outputs_tokens,
            captured_context_tokens,
            repo_context_tokens,
            tool_schema_tokens,
            reasoning_config_tokens,
        ]
        estimated_sum = sum(estimated_buckets)
        estimated_budget = max(raw_input_total - provider_cached_context_tokens, 0)

        if raw_input_total > 0 and estimated_sum > estimated_budget:
            scale = estimated_budget / estimated_sum if estimated_sum > 0 else 0
            instructions_tokens = max(0, int(instructions_tokens * scale))
            history_tokens = max(0, int(history_tokens * scale))
            tool_outputs_tokens = max(0, int(tool_outputs_tokens * scale))
            current_user_tokens = max(0, int(current_user_tokens * scale))
            captured_context_tokens = max(0, int(captured_context_tokens * scale))
            repo_context_tokens = max(0, int(repo_context_tokens * scale))
            tool_schema_tokens = max(0, int(tool_schema_tokens * scale))
            reasoning_config_tokens = max(0, int(reasoning_config_tokens * scale))
        known_sum = (
            provider_cached_context_tokens
            + instructions_tokens + current_user_tokens + history_tokens
            + tool_outputs_tokens + captured_context_tokens + repo_context_tokens
            + tool_schema_tokens + reasoning_config_tokens
        )

        unknown_val = max(raw_input_total - known_sum, 0) if raw_input_total > 0 else 0

        if raw_payload_available and rb.get("instructions_text"):
            instruction_detail_items = [
                _detail_item(
                    "raw request instructions",
                    rb["instructions_text"],
                    source_type="raw_request",
                    tokens=instructions_tokens,
                )
            ]
        else:
            instruction_detail_items = [
                _detail_item(
                    label,
                    text,
                    source_type="rollout_visible_instruction",
                )
                for label, text in instruction_sources
            ]

        current_user_details = _source_items_details(
            [
                _detail_item(
                    "current user input",
                    current_user_text,
                    source_type="raw_request" if raw_payload_available else "transcript",
                    role="user",
                    tokens=current_user_tokens,
                )
            ] if current_user_text else [],
            explanation=["当前用户输入来自 raw request input 或 session transcript。"],
        )
        history_details = _source_items_details(
            _text_items(history_texts, "history message", source_type="conversation_history"),
            explanation=["对话历史逐条展示；token 使用完整内容估算。"],
        )
        tool_outputs_details = _source_items_details(
            _text_items(tool_outputs_for_count, "tool output", source_type="tool_output"),
            kind="tool_results",
            explanation=["这些 tool output 会进入下一次 assistant request。"],
        )
        captured_context_details = _source_items_details(
            _text_items(captured_context_texts, "captured context", source_type="request_full_context"),
            explanation=["request_full 中可见但无法归入用户输入或工具输出的片段。"],
        )
        repo_context_details = _source_items_details(
            [
                _detail_item(
                    "repository/file context",
                    repo_context_text,
                    source_type="repository_file_context",
                    tokens=repo_context_tokens,
                )
            ] if repo_context_text else [],
        )
        if raw_payload_available and rb.get("tool_schemas_obj"):
            tool_schema_items = []
            for idx, tool_obj in enumerate(rb["tool_schemas_obj"]):
                tool_name = f"tool #{idx + 1}"
                if isinstance(tool_obj, dict):
                    tool_name = str(tool_obj.get("name") or tool_obj.get("type") or tool_name)
                tool_text = json.dumps(tool_obj, ensure_ascii=False, sort_keys=True)
                tool_schema_items.append(
                    _detail_item(
                        tool_name,
                        tool_text,
                        source_type="raw_request_tools",
                        index=idx,
                    )
                )
            tool_schema_details = _source_items_details(
                tool_schema_items,
                kind="tools",
                explanation=["raw request tools 数组中的工具定义原文。"],
            )
            tool_schema_count_label = f"{len(tool_schema_items)} tools"
        elif tool_schema_details is None:
            tool_schema_details = _source_items_details(
                [],
                kind="tools",
                explanation=["Codex tool schema fallback 不可用。"],
            )
        reasoning_details = _source_items_details(
            [
                _detail_item(
                    "reasoning config",
                    json.dumps(rb.get("reasoning_config_obj"), ensure_ascii=False, sort_keys=True),
                    source_type="raw_request_reasoning",
                    tokens=reasoning_config_tokens,
                )
            ] if raw_payload_available and rb.get("reasoning_config_obj") else [],
        )
        provider_wrapper_details = _source_items_details(
            [
                _detail_item(
                    "provider wrapper fields",
                    json.dumps(
                        {
                            key: req_body.get(key)
                            for key in ("model", "store", "include", "max_output_tokens", "previous_response_id")
                            if key in req_body
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    source_type="raw_request_wrapper",
                    tokens=provider_wrapper_tokens,
                )
            ] if raw_payload_available and provider_wrapper_tokens > 0 else [],
        )

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
                summary=instructions_source_summary,
                count_label=f"{len(instruction_sources)} sources" if instruction_sources else "",
                content_preview=(
                    instruction_sources[0][1][:120]
                    if instruction_sources
                    else (rb.get("instructions_text") or "")[:120]
                ),
                details=_source_items_details(
                    instruction_detail_items,
                    explanation=["Codex request-side instructions 的可见来源。"],
                ),
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
                content_preview=current_user_text[:120],
                details=current_user_details,
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
                details=history_details,
            ))

        # Provider cache read context
        if provider_cached_context_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="provider_cached_context",
                label="Provider cache read context",
                tokens=provider_cached_context_tokens,
                percent=_pct(provider_cached_context_tokens, raw_input_total),
                precision=ValuePrecision.PROVIDER_REPORTED,
                source=ValueSource.PROVIDER_USAGE,
                confidence_label="中",
                summary=(
                    "provider reported cached_input_tokens/cache read；"
                    "说明这部分 input-side token 来自缓存命中，但本地日志不展开其完整内容。"
                ),
                details={
                    "kind": "hidden_estimate",
                    "explanation": [
                        "cached_input_tokens 是 provider reported cache hit token 数。",
                        "Codex rollout 本地日志不展开这部分缓存命中的完整正文。",
                    ],
                },
                display_group="metadata",
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
                details={
                    "kind": "hidden_estimate",
                    "explanation": [summary_text],
                },
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
                count_label=f"{len(tool_outputs_for_count)} outputs",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TOOL_LOGS,
                confidence_label="中",
                summary="Tool outputs 从 raw request、工具日志或 Codex rollout function_call_output 获取，token 通过文本估算。",
                details=tool_outputs_details,
            ))

        # Captured request context
        if captured_context_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="captured_context_fragment",
                label="Captured request context",
                tokens=captured_context_tokens,
                percent=_pct(captured_context_tokens, raw_input_total),
                count_label=f"{len(captured_context_texts)} fragments",
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中低",
                summary="request_full 中可见但无法归入当前用户输入或 tool output 的上下文片段。",
                content_preview=captured_context_text[:120],
                details=captured_context_details,
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
                details=repo_context_details,
            ))

        # Tool schemas
        if tool_schema_tokens > 0:
            buckets.append(RequestAttributionBucket(
                key="tool_schemas",
                label="Tool schemas",
                tokens=tool_schema_tokens,
                percent=_pct(tool_schema_tokens, raw_input_total),
                count_label=tool_schema_count_label,
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TOOL_LIST,
                confidence_label="中" if tool_schema_source_label == "raw_request_tools" else "中低",
                summary=tool_schema_summary,
                details=tool_schema_details,
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
                details={
                    "kind": "hidden_estimate",
                    "explanation": ["无法从本地日志或 raw request 获取可用工具定义。"],
                },
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
                details=reasoning_details,
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
                details=provider_wrapper_details,
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
            details={
                "kind": "unlocated",
                "explanation": [
                    "Total input 减去已知 bucket 后的剩余部分。",
                    "该 bucket 没有可展示的本地原文；只表示仍无法定位的 provider/request 开销。",
                ],
            },
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
            self._avail("instructions_tokens", "Instructions / system prompt tokens",
                        instructions_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if instructions_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT if instruction_sources else (
                            ValueSource.PROVIDER_USAGE if raw_payload_available and rb.get("instructions_text") else ValueSource.HEURISTIC
                        ),
                        fill_strategy="from raw request instructions or visible Codex rollout base/developer/system messages" if instructions_tokens > 0 else "instructions unavailable"),
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
            self._avail("captured_context_tokens", "Captured request context tokens",
                        captured_context_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if captured_context_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TRANSCRIPT if captured_context_tokens > 0 else ValueSource.HEURISTIC,
                        fill_strategy="request_full fragments excluding current user and tool outputs" if captured_context_tokens > 0 else "no extra request_full fragments"),
            self._avail("tool_schemas_tokens", "Tool schemas tokens",
                        tool_schema_tokens > 0, exact=False,
                        precision=ValuePrecision.ESTIMATED if tool_schema_tokens > 0 else ValuePrecision.UNAVAILABLE,
                        source=ValueSource.TOOL_LIST,
                        fill_strategy="from raw request tools or Codex builtin tool catalog fallback"),
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
            notes.append(
                "Cache Read 以 provider-reported bucket 计入覆盖率；"
                "它确认 token 来源为缓存命中，但本地日志无法展开完整缓存内容。"
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
        if instruction_sources:
            notes.append("已使用 Codex rollout 中可见的 base_instructions 与 developer/system message 估算 request-side instructions。")
        if tool_outputs_tokens > 0 and not raw_payload_available:
            notes.append("Codex rollout 中的 function_call_output 已作为下一次 request 的 Tool outputs 参与重建。")
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
            captured_context_preview=(
                captured_context_text[:500]
                if captured_context_text
                else (repo_context_text[:500] if repo_context_text else "")
            ),
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
