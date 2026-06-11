"""Codex rollout JSONL to normalized session JSON."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from session_browser.normalized.semantic import build_normalized_session_model
from session_browser.sources.jsonl_reader import parse_jsonl_events


def parse_codex_rollout_file(
    path: str | Path,
    thread_info: dict | None = None,
) -> dict:
    """Parse a Codex rollout JSONL file into normalized session JSON."""
    rollout_path = Path(path)
    events, jsonl_diag = parse_jsonl_events(rollout_path)
    normalized = parse_codex_events(
        events,
        source_path=str(rollout_path),
        thread_info=thread_info or {},
    )
    normalized["parse_diagnostics"]["jsonl"] = {
        "total_lines": jsonl_diag.total_lines,
        "non_empty_lines": jsonl_diag.non_empty_lines,
        "events_parsed": jsonl_diag.events_parsed,
        "events_skipped": jsonl_diag.events_skipped,
        "warning_count": jsonl_diag.warning_count,
        "error_count": jsonl_diag.error_count,
    }
    return normalized


def parse_codex_events(
    events: list[dict],
    source_path: str = "",
    thread_info: dict | None = None,
) -> dict:
    """Parse Codex rollout events into the intermediate normalized contract."""
    thread_info = thread_info or {}
    state = _CodexBuildState(source_path=source_path, thread_info=thread_info)

    for order, event in enumerate(events, 1):
        if not isinstance(event, dict):
            continue
        state.event_order = order
        etype = event.get("type", "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        timestamp = str(event.get("timestamp") or "")

        if etype == "session_meta":
            state.accept_session_meta(payload, timestamp)
        elif etype == "turn_context":
            state.accept_turn_context(payload, timestamp)
        elif etype == "compacted":
            state.accept_compacted(payload, timestamp)
        elif etype == "response_item":
            state.accept_response_item(payload, timestamp)
        elif etype == "event_msg":
            state.accept_event_msg(payload, timestamp)

    state.finish()
    return state.to_normalized()


class _CodexBuildState:
    def __init__(self, source_path: str, thread_info: dict) -> None:
        self.source_path = source_path
        self.thread_info = thread_info
        self.event_order = 0
        self.session_meta: dict = {}
        self.latest_turn_context: dict = {}
        self.current_turn_id = ""
        self.first_ts = ""
        self.last_ts = ""

        self.pending_request_messages: list[dict] = []
        self.pending_user_messages: list[dict] = []
        self.pending_tool_results: list[dict] = []
        self.pending_compactions: list[dict] = []
        self.segment_response_items: list[dict] = []
        self.segment_tool_events: list[dict] = []
        self.segment_agent_messages: list[dict] = []
        self.segment_system_signals: list[dict] = []

        self.rounds: list[dict] = []
        self.parse_warnings: list[dict] = []

    def accept_session_meta(self, payload: dict, timestamp: str) -> None:
        self._touch(timestamp)
        self.session_meta = payload or {}

    def accept_turn_context(self, payload: dict, timestamp: str) -> None:
        self._touch(timestamp)
        self.latest_turn_context = payload or {}
        self.current_turn_id = str(payload.get("turn_id") or self.current_turn_id)

    def accept_compacted(self, payload: dict, timestamp: str) -> None:
        self._touch(timestamp)
        self.pending_compactions.append({
            "timestamp": timestamp,
            "summary": _truncate_text(payload.get("message") or "context compacted"),
            "replacement_count": len(payload.get("replacement_history") or []),
        })

    def accept_response_item(self, payload: dict, timestamp: str) -> None:
        self._touch(timestamp)
        ptype = payload.get("type", "")
        if ptype == "message" and payload.get("role") in {"developer", "user"}:
            self.pending_request_messages.append(_request_message_from_response_item(payload, timestamp))
            return
        self.segment_response_items.append({
            "timestamp": timestamp,
            "event_order": self.event_order,
            "payload": payload,
        })

    def accept_event_msg(self, payload: dict, timestamp: str) -> None:
        self._touch(timestamp)
        ptype = payload.get("type", "")
        if ptype == "task_started":
            self.current_turn_id = str(payload.get("turn_id") or self.current_turn_id)
            return
        if ptype == "user_message":
            self.pending_user_messages.append({
                "timestamp": timestamp,
                "client_id": payload.get("client_id") or "",
                "text": _stringify(payload.get("message")),
                "images": payload.get("images") or [],
                "local_images": payload.get("local_images") or [],
            })
            return
        if ptype == "agent_message":
            self.segment_agent_messages.append({
                "timestamp": timestamp,
                "phase": payload.get("phase") or "",
                "text": _stringify(payload.get("message")),
            })
            return
        if ptype == "token_count":
            self._close_llm_call(payload, timestamp)
            return
        if ptype in {
            "function_call_output",
            "custom_tool_call_output",
            "exec_command_end",
            "mcp_tool_call_end",
            "patch_apply_end",
            "web_search_end",
            "view_image_tool_call",
        }:
            self.segment_tool_events.append({
                "timestamp": timestamp,
                "event_order": self.event_order,
                "payload": payload,
            })
            return
        if ptype in {"turn_aborted", "error", "context_compacted"}:
            self.segment_system_signals.append({
                "timestamp": timestamp,
                "kind": ptype,
                "message": _system_signal_message(payload),
                "severity": "warning" if ptype != "error" else "critical",
            })

    def finish(self) -> None:
        if self.segment_response_items:
            self.parse_warnings.append({
                "kind": "unclosed_response_segment",
                "message": "Response items at end of file had no following token_count event.",
                "event_order": self.event_order,
            })

    def to_normalized(self) -> dict:
        session_id = (
            self.thread_info.get("id")
            or self.session_meta.get("id")
            or _session_id_from_path(self.source_path)
        )
        title = self.thread_info.get("title") or self.thread_info.get("first_user_message") or ""
        model = (
            self.thread_info.get("model")
            or self.latest_turn_context.get("model")
            or self.session_meta.get("model")
            or self.session_meta.get("model_provider")
            or ""
        )
        cwd = self.thread_info.get("cwd") or self.session_meta.get("cwd") or self.latest_turn_context.get("cwd") or ""
        session = {
            "session_key": f"codex:{session_id}",
            "session_id": session_id,
            "title": _truncate_text(title, 160),
            "agent": "codex",
            "model": model,
            "cwd": cwd,
            "started_at": self.first_ts,
            "ended_at": self.last_ts,
            "git_branch": self.thread_info.get("git_branch") or (self.session_meta.get("git") or {}).get("branch", ""),
            "source": self.thread_info.get("source") or self.session_meta.get("source") or "",
        }
        source_files = [{
                "role": "codex_rollout",
                "path": self.source_path,
                "status": "available" if self.source_path else "unknown",
        }]
        return build_normalized_session_model(
            agent="codex",
            session=session,
            source_files=source_files,
            call_drafts=self.rounds,
            parse_warnings=self.parse_warnings,
            extra_parse_diagnostics={},
            context_sources=_codex_context_sources(self.session_meta, self.latest_turn_context, source_files),
        )

    def _close_llm_call(self, token_payload: dict, timestamp: str) -> None:
        usage = _extract_token_count_usage(token_payload)
        if not self.segment_response_items and not self.segment_agent_messages:
            self.parse_warnings.append({
                "kind": "token_count_without_response_items",
                "message": "token_count had no preceding response items.",
                "event_order": self.event_order,
            })
            return

        round_id = len(self.rounds) + 1
        call_id = f"codex-call-{round_id:04d}"
        request_messages = list(self.pending_request_messages)
        visible_user_messages = list(self.pending_user_messages)
        request_tool_results = list(self.pending_tool_results)
        compactions = list(self.pending_compactions)

        response = _collect_response(self.segment_response_items, self.segment_agent_messages)
        tools = _collect_tools(self.segment_response_items, self.segment_tool_events)

        round_obj = _build_round(
            round_id=round_id,
            call_id=call_id,
            turn_id=self.current_turn_id,
            timestamp=timestamp,
            model=self.thread_info.get("model") or self.latest_turn_context.get("model") or "",
            usage=usage,
            request_messages=request_messages,
            visible_user_messages=visible_user_messages,
            request_tool_results=request_tool_results,
            compactions=compactions,
            response=response,
            tools=tools,
            system_signals=list(self.segment_system_signals),
        )
        self.rounds.append(round_obj)

        self.pending_request_messages = []
        self.pending_user_messages = []
        self.pending_compactions = []
        self.pending_tool_results = [_tool_result_for_next_request(t) for t in tools if t.get("result")]
        self.segment_response_items = []
        self.segment_tool_events = []
        self.segment_agent_messages = []
        self.segment_system_signals = []

    def _touch(self, timestamp: str) -> None:
        if timestamp and not self.first_ts:
            self.first_ts = timestamp
        if timestamp:
            self.last_ts = timestamp


def _build_round(
    *,
    round_id: int,
    call_id: str,
    turn_id: str,
    timestamp: str,
    model: str,
    usage: dict,
    request_messages: list[dict],
    visible_user_messages: list[dict],
    request_tool_results: list[dict],
    compactions: list[dict],
    response: dict,
    tools: list[dict],
    system_signals: list[dict],
) -> dict:
    token_total = usage["input_tokens"] + usage["cached_input_tokens"] + usage["output_tokens"]
    payload_refs = {
        "request_payload_id": f"llm-R{round_id}-C1-request",
        "response_payload_id": f"llm-R{round_id}-C1-response",
        "request_attribution_id": f"llm-R{round_id}-C1-request-attribution",
        "response_attribution_id": f"llm-R{round_id}-C1-response-attribution",
        "related_result_payload_ids": [t["payload_id"] for t in tools if t.get("payload_id")],
    }
    request_body = _request_payload_body(request_messages, request_tool_results, compactions)
    response_body = _response_payload_body(response, tools)
    request_attribution = _request_attribution(usage, request_messages, request_tool_results, compactions)
    response_attribution = _response_attribution(usage, response, tools)
    steps = _build_steps(
        round_id=round_id,
        call_id=call_id,
        model=model,
        timestamp=timestamp,
        usage=usage,
        payload_refs=payload_refs,
        visible_user_messages=visible_user_messages,
        tools=tools,
        system_signals=system_signals,
    )
    return {
        "round_id": round_id,
        "round_key": f"R{round_id}",
        "main_call": {
            "call_id": call_id,
            "turn_id": turn_id,
            "model": model,
            "timestamp": timestamp,
            "source": "codex_rollout_token_count",
        },
        "summary": _summary_from_response(response, tools),
        "status": "failed" if any(t.get("status") == "error" for t in tools) else "ok",
        "timing": {
            "started_at": timestamp,
            "ended_at": timestamp,
            "duration_seconds": 0,
            "process_seconds": 0,
            "waiting_seconds": 0,
        },
        "metrics": {
            "tokens": {
                "fresh": usage["input_tokens"],
                "cache_read": usage["cached_input_tokens"],
                "cache_write": 0,
                "output": usage["output_tokens"],
                "total": token_total,
                "source_total": usage["source_total_tokens"],
                "total_semantics": "component_sum",
                "quality": {
                    "source": "event_msg.token_count.info.last_token_usage",
                    "precision": "provider_reported",
                    "status": "available",
                },
            },
            "cache_read_ratio": _ratio(usage["cached_input_tokens"], usage["input_tokens"] + usage["cached_input_tokens"]),
            "llm_call_count": 1,
            "tool_call_count": len(tools),
            "failed_tool_count": sum(1 for t in tools if t.get("status") == "error"),
            "subagent_count": 0,
        },
        "signals": {
            "failed": any(t.get("status") == "error" for t in tools),
            "low_cache": False,
            "fresh_spike": False,
            "payload_gap": False,
            "attribution_gap": False,
            "items": _issues_from_tools(round_id, tools),
        },
        "request": request_body,
        "response": response_body,
        "request_attribution": request_attribution,
        "response_attribution": response_attribution,
        "payload_refs": payload_refs,
        "steps": steps,
    }


def _extract_token_count_usage(payload: dict) -> dict:
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    usage = info.get("last_token_usage") or payload.get("last_token_usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = _int(usage.get("input_tokens") or usage.get("prompt_tokens"))
    cached = (
        _int(usage.get("cached_input_tokens"))
        or _int(usage.get("cache_read_input_tokens"))
        or _nested_int(usage, "input_tokens_details", "cached_tokens")
        or _nested_int(usage, "prompt_tokens_details", "cached_tokens")
    )
    output = _int(usage.get("output_tokens") or usage.get("completion_tokens"))
    reasoning = (
        _int(usage.get("reasoning_output_tokens"))
        or _nested_int(usage, "output_tokens_details", "reasoning_tokens")
        or _nested_int(usage, "completion_tokens_details", "reasoning_tokens")
    )
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": output or reasoning,
        "reasoning_output_tokens": reasoning,
        "source_total_tokens": _int(usage.get("total_tokens")) or input_tokens + output,
        "model_context_window": _int(info.get("model_context_window")),
    }


def _request_message_from_response_item(payload: dict, timestamp: str) -> dict:
    parts = []
    for part in payload.get("content") or []:
        if isinstance(part, dict):
            parts.append({
                "type": part.get("type") or "input_text",
                "text": _stringify(part.get("text") or part.get("content")),
            })
    text = "\n\n".join(p["text"] for p in parts if p["text"])
    return {
        "timestamp": timestamp,
        "role": payload.get("role") or "",
        "parts": parts,
        "text": text,
        "bucket": _request_bucket_for_message(payload.get("role") or "", text),
    }


def _collect_response(response_items: list[dict], agent_messages: list[dict]) -> dict:
    texts: list[str] = []
    blocks: list[dict] = []
    reasoning_count = 0
    for item in response_items:
        payload = item["payload"]
        ptype = payload.get("type")
        if ptype == "reasoning":
            reasoning_count += 1
            blocks.append({
                "type": "reasoning",
                "summary": payload.get("summary") or [],
                "encrypted": bool(payload.get("encrypted_content")),
            })
        elif ptype == "message" and payload.get("role") == "assistant":
            for part in payload.get("content") or []:
                if not isinstance(part, dict):
                    continue
                text = _stringify(part.get("text") or part.get("content"))
                if text:
                    texts.append(text)
                    blocks.append({"type": part.get("type") or "output_text", "text": text})
    if not texts:
        for msg in agent_messages:
            if msg.get("text"):
                texts.append(msg["text"])
                blocks.append({"type": "output_text", "text": msg["text"], "source": "event_msg.agent_message"})
    return {
        "text": "\n\n".join(texts),
        "blocks": blocks,
        "reasoning_count": reasoning_count,
    }


def _collect_tools(response_items: list[dict], tool_events: list[dict]) -> list[dict]:
    calls: list[dict] = []
    outputs: dict[str, dict] = {}
    for item in response_items:
        payload = item["payload"]
        ptype = payload.get("type")
        if ptype in {"function_call_output", "custom_tool_call_output"}:
            call_id = payload.get("call_id") or ""
            if call_id:
                outputs.setdefault(call_id, {}).update({
                    "text": _stringify(payload.get("output")),
                    "status": payload.get("status") or "completed",
                    "source": ptype,
                })
    for event in tool_events:
        payload = event["payload"]
        call_id = payload.get("call_id") or ""
        if not call_id:
            continue
        rich = _tool_event_output(payload)
        if rich:
            outputs.setdefault(call_id, {}).update(rich)

    for item in response_items:
        payload = item["payload"]
        ptype = payload.get("type")
        if ptype not in {"function_call", "custom_tool_call", "tool_search_call", "web_search_call"}:
            continue
        call_id = payload.get("call_id") or f"tool-{len(calls) + 1}"
        name = payload.get("name") or ptype.replace("_call", "")
        parameters = _tool_parameters(payload)
        result_info = outputs.get(call_id, {})
        status = _tool_status(result_info)
        calls.append({
            "tool_call_id": call_id,
            "name": name,
            "type": ptype,
            "parameters": parameters,
            "status": status,
            "exit_code": result_info.get("exit_code"),
            "duration_ms": result_info.get("duration_ms", 0),
            "result": _payload_body(
                text=result_info.get("text", ""),
                raw=result_info.get("raw", result_info.get("text", "")),
                source=result_info.get("source", "tool_output"),
                precision="exact" if result_info else "unavailable",
                status="available" if result_info else "missing",
            ),
            "payload_id": f"tool-{call_id}-result",
        })
    return calls


def _tool_event_output(payload: dict) -> dict:
    ptype = payload.get("type")
    if ptype == "exec_command_end":
        exit_code = payload.get("exit_code")
        text = payload.get("aggregated_output") or payload.get("stdout") or payload.get("stderr") or payload.get("formatted_output") or ""
        return {
            "text": _stringify(text),
            "raw": {
                "stdout": payload.get("stdout") or "",
                "stderr": payload.get("stderr") or "",
                "exit_code": exit_code,
                "command": payload.get("command") or [],
            },
            "exit_code": exit_code,
            "status": "error" if exit_code not in (None, 0) else "completed",
            "duration_ms": _duration_ms(payload.get("duration") or {}),
            "source": ptype,
        }
    if ptype == "mcp_tool_call_end":
        result = payload.get("result") or {}
        return {
            "text": _truncate_text(json.dumps(result, ensure_ascii=False, sort_keys=True), 1000),
            "raw": result,
            "status": "completed",
            "duration_ms": _duration_ms(payload.get("duration") or {}),
            "source": ptype,
        }
    if ptype == "patch_apply_end":
        text = payload.get("stdout") or payload.get("stderr") or ""
        return {
            "text": _stringify(text),
            "raw": {
                "stdout": payload.get("stdout") or "",
                "stderr": payload.get("stderr") or "",
                "success": bool(payload.get("success")),
                "status": payload.get("status") or "",
            },
            "status": "completed" if payload.get("success") else "error",
            "source": ptype,
        }
    if ptype == "web_search_end":
        return {
            "text": _stringify(payload.get("query")),
            "raw": payload,
            "status": "completed",
            "source": ptype,
        }
    if ptype == "view_image_tool_call":
        return {
            "text": _stringify(payload.get("path")),
            "raw": payload,
            "status": "completed",
            "source": ptype,
        }
    return {}


def _tool_parameters(payload: dict) -> dict:
    raw = payload.get("arguments")
    if raw is None:
        raw = payload.get("input")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"raw": raw}
        except json.JSONDecodeError:
            return {"raw": raw}
    return {}


def _request_payload_body(
    messages: list[dict],
    tool_results: list[dict],
    compactions: list[dict],
) -> dict:
    blocks: list[dict] = []
    text_parts: list[str] = []
    for msg in messages:
        text_parts.append(f"{msg.get('role')}: {msg.get('text')}")
        blocks.append({
            "type": "message",
            "role": msg.get("role"),
            "bucket": msg.get("bucket"),
            "text": msg.get("text", ""),
        })
    for result in tool_results:
        text = result.get("text") or ""
        text_parts.append(f"tool_result {result.get('tool_call_id')}: {text}")
        blocks.append({
            "type": "tool_result",
            "tool_call_id": result.get("tool_call_id"),
            "text": text,
        })
    for compaction in compactions:
        text_parts.append(f"compacted: {compaction.get('summary')}")
        blocks.append({"type": "compacted", **compaction})
    return _payload_body(
        text="\n\n".join(t for t in text_parts if t),
        raw=None,
        source="codex_rollout_reconstruction",
        precision="estimated_partial",
        status="partial",
        blocks=blocks,
        fallback_reason="OpenAI raw request body is not persisted in Codex rollout.",
    )


def _response_payload_body(response: dict, tools: list[dict]) -> dict:
    blocks = list(response.get("blocks") or [])
    for tool in tools:
        blocks.append({
            "type": "tool_use",
            "id": tool.get("tool_call_id"),
            "name": tool.get("name"),
            "input": tool.get("parameters") or {},
        })
    return _payload_body(
        text=response.get("text") or "",
        raw={"blocks": blocks},
        source="codex_rollout_response_items",
        precision="exact" if blocks else "unavailable",
        status="available" if blocks else "missing",
        blocks=blocks,
    )


def _request_attribution(
    usage: dict,
    messages: list[dict],
    tool_results: list[dict],
    compactions: list[dict],
) -> dict:
    request_total = usage["input_tokens"] + usage["cached_input_tokens"]
    raw_buckets: list[dict] = []
    for bucket_name in (
        "Developer instructions",
        "Project/environment context",
        "Current user prompt",
    ):
        text = "\n\n".join(m.get("text", "") for m in messages if m.get("bucket") == bucket_name)
        if text:
            raw_buckets.append(_bucket(bucket_name, _estimate_tokens(text), "response_item.message", "estimated", text))
    tool_text = "\n\n".join(r.get("text", "") for r in tool_results if r.get("text"))
    if tool_text:
        raw_buckets.append(_bucket("Tool results", _estimate_tokens(tool_text), "previous tool output", "estimated", tool_text))
    if compactions:
        raw_buckets.append(_bucket("Compacted history", 0, "codex compacted event", "unavailable", "context compacted"))

    visible = sum(b["tokens"] for b in raw_buckets)
    residual = max(request_total - visible, 0)
    if residual:
        raw_buckets.append(_bucket("Unknown / retained context", residual, "provider usage residual", "estimated_partial", "server-side retained context or hidden request data"))
    return _attribution_payload(
        status="partial",
        summary={
            "total_input": request_total,
            "fresh_input": usage["input_tokens"],
            "cache_read": usage["cached_input_tokens"],
            "visible_estimated_tokens": visible,
            "coverage": _ratio(visible, request_total),
        },
        buckets=raw_buckets,
        total=request_total,
        source="codex normalized adapter",
        precision="estimated_partial",
    )


def _response_attribution(usage: dict, response: dict, tools: list[dict]) -> dict:
    total = usage["output_tokens"]
    raw_buckets: list[dict] = []
    visible_tokens_raw = _estimate_tokens(response.get("text") or "")
    tool_text = json.dumps([
        {"name": t.get("name"), "parameters": t.get("parameters")}
        for t in tools
    ], ensure_ascii=False, sort_keys=True)
    tool_tokens_raw = _estimate_tokens(tool_text) if tools else 0
    reasoning = usage.get("reasoning_output_tokens") or 0
    estimate_budget = max(total - reasoning, 0)
    visible_tokens = min(visible_tokens_raw, estimate_budget)
    tool_tokens = min(tool_tokens_raw, max(estimate_budget - visible_tokens, 0))

    if visible_tokens:
        raw_buckets.append(_bucket("Visible text", visible_tokens, "response_item.message role=assistant", "estimated", response.get("text") or ""))
    if tool_tokens:
        raw_buckets.append(_bucket("Tool use", tool_tokens, "response_item.function_call", "estimated", tool_text))
    if reasoning:
        raw_buckets.append(_bucket("Reasoning", reasoning, "event_msg.token_count.reasoning_output_tokens", "provider_reported", "encrypted reasoning payload"))
    visible = sum(b["tokens"] for b in raw_buckets)
    residual = max(total - visible, 0)
    if residual:
        raw_buckets.append(_bucket("Unknown output", residual, "provider usage residual", "estimated_partial", "output tokens not explained by visible rollout items"))
    return _attribution_payload(
        status="available" if response.get("blocks") or tools else "partial",
        summary={
            "total_output": total,
            "visible_estimated_tokens": visible_tokens,
            "tool_use_estimated_tokens": tool_tokens,
            "reasoning_output_tokens": reasoning,
            "coverage": _ratio(min(visible, total), total),
        },
        buckets=raw_buckets,
        total=total,
        source="codex normalized adapter",
        precision="estimated",
    )


def _build_steps(
    *,
    round_id: int,
    call_id: str,
    model: str,
    timestamp: str,
    usage: dict,
    payload_refs: dict,
    visible_user_messages: list[dict],
    tools: list[dict],
    system_signals: list[dict],
) -> list[dict]:
    steps: list[dict] = []
    for idx, msg in enumerate(visible_user_messages, 1):
        steps.append({
            "type": "user_context",
            "step_id": f"R{round_id}-user-{idx}",
            "timestamp": msg.get("timestamp") or timestamp,
            "content": {
                "text": msg.get("text") or "",
                "blocks": [{"type": "text", "text": msg.get("text") or ""}],
                "quality": {"source": "event_msg.user_message", "precision": "exact", "status": "available"},
            },
        })
    steps.append({
        "type": "llm_call",
        "step_id": f"R{round_id}-main-call",
        "call_id": call_id,
        "scope": "main",
        "model": model,
        "status": "ok",
        "timestamp": timestamp,
        "usage": {
            "fresh": usage["input_tokens"],
            "cache_read": usage["cached_input_tokens"],
            "cache_write": 0,
            "output": usage["output_tokens"],
            "total": usage["input_tokens"] + usage["cached_input_tokens"] + usage["output_tokens"],
            "source_total": usage["source_total_tokens"],
            "total_semantics": "component_sum",
            "quality": {"source": "event_msg.token_count", "precision": "provider_reported", "status": "available"},
        },
        "payload_refs": payload_refs,
    })
    if tools:
        steps.append({
            "type": "tool_batch",
            "step_id": f"R{round_id}-tool-batch-1",
            "started_at": timestamp,
            "ended_at": timestamp,
            "duration_ms": sum(int(t.get("duration_ms") or 0) for t in tools),
            "tools": tools,
        })
    for idx, signal in enumerate(system_signals, 1):
        steps.append({
            "type": "system_signal",
            "step_id": f"R{round_id}-signal-{idx}",
            "kind": signal.get("kind") or "system",
            "severity": signal.get("severity") or "warning",
            "message": signal.get("message") or "",
            "quality": {"source": "event_msg", "precision": "exact", "status": "available"},
        })
    return steps


def _payload_body(
    *,
    text: str,
    raw: Any,
    source: str,
    precision: str,
    status: str,
    blocks: list | None = None,
    fallback_reason: str = "",
) -> dict:
    quality = {"source": source, "precision": precision, "status": status}
    if fallback_reason:
        quality["fallback_reason"] = fallback_reason
    return {
        "rendered": {
            "text": text,
            "blocks": blocks if blocks is not None else ([{"type": "text", "text": text}] if text else []),
            "quality": quality,
        },
        "raw": raw,
        "availability": quality,
        "size_bytes": len(text.encode("utf-8")) if text else 0,
    }


def _attribution_payload(
    *,
    status: str,
    summary: dict,
    buckets: list[dict],
    total: int,
    source: str,
    precision: str,
) -> dict:
    for item in buckets:
        item["share"] = _ratio(item["tokens"], total)
    return {
        "status": status,
        "summary": summary,
        "buckets": buckets,
        "quality": {"source": source, "precision": precision, "status": status},
    }


def _bucket(bucket: str, tokens: int, source: str, precision: str, preview: str) -> dict:
    return {
        "bucket": bucket,
        "tokens": max(int(tokens or 0), 0),
        "share": 0,
        "source": source,
        "precision": precision,
        "preview": _truncate_text(preview, 120),
    }


def _request_bucket_for_message(role: str, text: str) -> str:
    if role == "developer":
        return "Developer instructions"
    lower = text.lower()
    if "agents.md instructions" in lower or "<environment_context>" in lower or "workspace_roots" in lower:
        return "Project/environment context"
    return "Current user prompt"


def _codex_context_sources(
    session_meta: dict,
    turn_context: dict,
    source_files: list[dict],
) -> list[dict]:
    source_path = ""
    if source_files:
        source_path = str(source_files[0].get("path") or "")
    base_instructions = session_meta.get("base_instructions") if isinstance(session_meta.get("base_instructions"), dict) else {}
    dynamic_tools = session_meta.get("dynamic_tools") if isinstance(session_meta.get("dynamic_tools"), list) else []
    workspace_roots = turn_context.get("workspace_roots") if isinstance(turn_context.get("workspace_roots"), list) else []
    runtime_keys = [
        key for key in (
            "current_date",
            "timezone",
            "approval_policy",
            "sandbox_policy",
            "model",
            "effort",
        )
        if key in turn_context
    ]
    return [
        _context_source(
            "system_base_prompt",
            "System/base prompt",
            "session_meta.base_instructions",
            "available" if base_instructions.get("text") else "not_observable",
            source_path,
            {"text_preview": _truncate_text(_stringify(base_instructions.get("text")), 120)},
        ),
        _context_source(
            "runtime_policy_context",
            "Runtime policy context",
            "turn_context",
            "available" if runtime_keys else "not_observable",
            source_path,
            {"fields": runtime_keys},
        ),
        _context_source(
            "tool_definitions",
            "Tool definitions",
            "session_meta.dynamic_tools",
            "available" if dynamic_tools else "not_observable",
            source_path,
            {"tool_count": len(dynamic_tools)},
        ),
        _context_source(
            "skills_and_agents",
            "Skills and agents",
            "turn_context or developer context",
            "not_observable",
            source_path,
            {},
        ),
        _context_source(
            "project_context",
            "Project/environment context",
            "turn_context.workspace_roots",
            "available" if workspace_roots else "not_observable",
            source_path,
            {"workspace_roots": workspace_roots},
        ),
        _context_source("current_user_input", "Current user input", "event_msg.user_message", "derived", source_path, {}),
        _context_source("tool_results", "Tool results", "local tool outputs", "derived", source_path, {}),
        _context_source("conversation_history", "Conversation history", "retained or compacted context", "partial", source_path, {}),
        _context_source(
            "unknown_retained_context",
            "Unknown retained context",
            "provider usage residual",
            "estimated_partial",
            source_path,
            {},
        ),
    ]


def _context_source(
    canonical_category: str,
    label: str,
    source: str,
    status: str,
    source_path: str,
    details: dict,
) -> dict:
    return {
        "canonical_category": canonical_category,
        "label": label,
        "source": source,
        "status": status,
        "source_ref": {
            "path": source_path,
            "payload_path": source,
        },
        "details": details,
    }


def _tool_result_for_next_request(tool: dict) -> dict:
    result = tool.get("result") or {}
    rendered = result.get("rendered") or {}
    return {
        "tool_call_id": tool.get("tool_call_id") or "",
        "name": tool.get("name") or "",
        "text": rendered.get("text") or "",
        "payload_id": tool.get("payload_id") or "",
    }


def _summary_from_response(response: dict, tools: list[dict]) -> str:
    text = _truncate_text(response.get("text") or "", 80)
    if text:
        return text
    if tools:
        names = ", ".join(t.get("name") or "tool" for t in tools[:3])
        return f"Tool call: {names}"
    return "Codex LLM call"


def _issues_from_tools(round_id: int, tools: list[dict]) -> list[dict]:
    issues = []
    for tool in tools:
        if tool.get("status") == "error":
            issues.append({
                "kind": "tool_failure",
                "severity": "critical",
                "label": "Tool failure",
                "evidence": f"{tool.get('name')} exit {tool.get('exit_code')}",
                "target": {"round_id": round_id, "tool_call_id": tool.get("tool_call_id"), "payload_id": tool.get("payload_id")},
            })
    return issues


def _tool_status(result_info: dict) -> str:
    if not result_info:
        return "missing"
    if result_info.get("status") == "error":
        return "error"
    exit_code = result_info.get("exit_code")
    if exit_code not in (None, 0):
        return "error"
    return "completed"


def _duration_ms(duration: dict) -> int:
    return int(duration.get("secs") or 0) * 1000 + math.floor(int(duration.get("nanos") or 0) / 1_000_000)


def _estimate_tokens(text: str) -> int:
    text = _stringify(text)
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _ratio(part: int | float, total: int | float) -> float | None:
    if not total:
        return None
    return round(float(part) / float(total), 4)


def _int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _nested_int(data: dict, outer: str, inner: str) -> int:
    child = data.get(outer)
    if isinstance(child, dict):
        return _int(child.get(inner))
    return 0


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_stringify(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _truncate_text(text: Any, limit: int = 240) -> str:
    value = re.sub(r"\s+", " ", _stringify(text)).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _system_signal_message(payload: dict) -> str:
    if payload.get("message"):
        return _stringify(payload.get("message"))
    if payload.get("reason"):
        return _stringify(payload.get("reason"))
    return _stringify(payload.get("type") or "system signal")


def _session_id_from_path(path: str) -> str:
    name = Path(path).name
    if name.startswith("rollout-") and name.endswith(".jsonl"):
        return name.rsplit("-", 1)[-1].removesuffix(".jsonl")
    return ""
