"""Codex rollout JSONL to normalized session JSON."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from session_browser.normalized.semantic import build_normalized_session_model
from session_browser.sources.jsonl_reader import parse_jsonl_events


_CODEX_USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def parse_codex_rollout_file(
    path: str | Path,
    thread_info: dict | None = None,
) -> dict:
    """Parse a Codex rollout JSONL file into normalized session JSON."""
    rollout_path = Path(path)
    events, _ = parse_jsonl_events(rollout_path)
    normalized = parse_codex_events(
        events,
        source_path=str(rollout_path),
        thread_info=thread_info or {},
    )
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

        self.pending_tool_results: list[dict] = []
        self.segment_response_items: list[dict] = []
        self.segment_tool_events: list[dict] = []

        self.rounds: list[dict] = []
        self.parse_warnings: list[dict] = []
        self.previous_cumulative_usage: dict | None = None
        self.token_fragments: list[dict] = []

    def accept_session_meta(self, payload: dict, timestamp: str) -> None:
        self._touch(timestamp)
        self.session_meta = payload or {}

    def accept_turn_context(self, payload: dict, timestamp: str) -> None:
        self._touch(timestamp)
        self.latest_turn_context = payload or {}
        self.current_turn_id = str(payload.get("turn_id") or self.current_turn_id)

    def accept_compacted(self, payload: dict, timestamp: str) -> None:
        self._touch(timestamp)

    def accept_response_item(self, payload: dict, timestamp: str) -> None:
        self._touch(timestamp)
        ptype = payload.get("type", "")
        if ptype == "message" and payload.get("role") in {"developer", "user"}:
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
            return
        if ptype == "agent_message":
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
        }]
        normalized = build_normalized_session_model(
            agent="codex",
            session=session,
            source_files=source_files,
            call_drafts=self.rounds,
            parse_warnings=self.parse_warnings,
        )
        if self.token_fragments:
            normalized["diagnostics"].extend(self.token_fragments)
        return normalized

    def _close_llm_call(self, token_payload: dict, timestamp: str) -> None:
        fragment = self._token_fragment(token_payload, timestamp)
        if fragment.get("status") == "duplicate_token_count":
            self.token_fragments.append(fragment)
            return

        usage = _extract_token_count_usage(token_payload)
        if not usage.get("source_total_tokens") and fragment.get("cumulative_delta"):
            delta = fragment["cumulative_delta"]
            usage = {
                "input_tokens": delta.get("input_tokens", 0),
                "cached_input_tokens": delta.get("cached_input_tokens", 0),
                "output_tokens": delta.get("output_tokens", 0),
                "reasoning_output_tokens": delta.get("reasoning_output_tokens", 0),
                "source_total_tokens": delta.get("total_tokens", 0),
                "model_context_window": 0,
            }
        if fragment.get("status") == "cumulative_reset_or_invalid":
            usage["quality_status"] = "cumulative_reset_or_invalid"
            self.token_fragments.append(fragment)
        if not self.segment_response_items:
            self.parse_warnings.append({
                "kind": "token_count_without_response_items",
                "message": "token_count had no preceding response items.",
                "event_order": self.event_order,
            })

        round_id = len(self.rounds) + 1
        call_id = f"codex-call-{round_id:04d}"
        request_tool_results = list(self.pending_tool_results)

        tools = _collect_tools(self.segment_response_items, self.segment_tool_events)

        round_obj = _build_round(
            round_id=round_id,
            call_id=call_id,
            turn_id=self.current_turn_id,
            timestamp=timestamp,
            model=self.thread_info.get("model") or self.latest_turn_context.get("model") or "",
            usage=usage,
            request_tool_results=request_tool_results,
            tools=tools,
        )
        self.rounds.append(round_obj)

        self.pending_tool_results = [
            _tool_result_for_next_request(t)
            for t in tools
            if t.get("tool_call_id") and t.get("status") != "missing"
        ]
        self.segment_response_items = []
        self.segment_tool_events = []

    def _token_fragment(self, token_payload: dict, timestamp: str) -> dict:
        info = token_payload.get("info") if isinstance(token_payload.get("info"), dict) else {}
        last_usage = info.get("last_token_usage") or token_payload.get("last_token_usage") or {}
        cumulative_usage = info.get("total_token_usage") or token_payload.get("total_token_usage") or {}
        record = {
            "record_index": self.event_order,
            "timestamp": timestamp,
            "last_total_tokens": _int(last_usage.get("total_tokens")) if isinstance(last_usage, dict) else 0,
            "cumulative_total_tokens": _int(cumulative_usage.get("total_tokens")) if isinstance(cumulative_usage, dict) else 0,
        }
        if not isinstance(cumulative_usage, dict):
            return {**record, "status": "fallback_last_usage", "contribution": record["last_total_tokens"]}

        delta = _token_usage_delta(cumulative_usage, self.previous_cumulative_usage)
        record["cumulative_delta"] = {field: max(delta[field], 0) for field in _CODEX_USAGE_FIELDS}
        record["contribution"] = record["cumulative_delta"]["total_tokens"]

        if self.previous_cumulative_usage is not None and all(delta[field] == 0 for field in _CODEX_USAGE_FIELDS):
            self.previous_cumulative_usage = cumulative_usage
            return {**record, "status": "duplicate_token_count", "contribution": 0}

        status = "counted"
        if any(delta[field] < 0 for field in _CODEX_USAGE_FIELDS):
            status = "cumulative_reset_or_invalid"
        self.previous_cumulative_usage = cumulative_usage
        return {**record, "status": status}

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
    request_tool_results: list[dict],
    tools: list[dict],
) -> dict:
    fresh_tokens = max(usage["input_tokens"] - usage["cached_input_tokens"], 0)
    token_total = fresh_tokens + usage["cached_input_tokens"] + usage["output_tokens"]
    steps = _build_steps(
        timestamp=timestamp,
        tools=tools,
    )
    return {
        "round_id": round_id,
        "round_key": f"R{round_id}",
        "main_call": {
            "call_id": call_id,
            "turn_id": turn_id,
            "model": model,
            "timestamp": timestamp,
        },
        "metrics": {
            "tokens": {
                "fresh": fresh_tokens,
                "cache_read": usage["cached_input_tokens"],
                "cache_write": 0,
                "output": usage["output_tokens"],
                "total": token_total,
            },
        },
        "request": {
            "tool_result_ids": [t["tool_call_id"] for t in request_tool_results if t.get("tool_call_id")],
        },
        "response": {
            "tool_call_ids": [t["tool_call_id"] for t in tools if t.get("tool_call_id")],
        },
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


def _token_usage_delta(current: dict, previous: dict | None) -> dict:
    previous = previous if isinstance(previous, dict) else {}
    return {
        "input_tokens": _int(current.get("input_tokens")) - _int(previous.get("input_tokens")),
        "cached_input_tokens": _int(current.get("cached_input_tokens")) - _int(previous.get("cached_input_tokens")),
        "output_tokens": _int(current.get("output_tokens")) - _int(previous.get("output_tokens")),
        "reasoning_output_tokens": _int(current.get("reasoning_output_tokens")) - _int(previous.get("reasoning_output_tokens")),
        "total_tokens": _int(current.get("total_tokens")) - _int(previous.get("total_tokens")),
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
                result = outputs.setdefault(call_id, {"observed": True})
                status = str(payload.get("status") or "")
                if status and status != "completed":
                    result["status"] = status
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
        result_info = outputs.get(call_id, {})
        status = _tool_status(result_info)
        tool: dict[str, Any] = {
            "tool_call_id": call_id,
            "name": name,
            "exit_code": result_info.get("exit_code"),
            "duration_ms": result_info.get("duration_ms", 0),
        }
        if status != "completed":
            tool["status"] = status
        calls.append(tool)
    return calls


def _tool_event_output(payload: dict) -> dict:
    ptype = payload.get("type")
    if ptype == "exec_command_end":
        exit_code = payload.get("exit_code")
        result = {
            "observed": True,
            "duration_ms": _duration_ms(payload.get("duration") or {}),
        }
        if exit_code not in (None, 0):
            result["exit_code"] = exit_code
            result["status"] = "error"
        return result
    if ptype == "mcp_tool_call_end":
        return {
            "observed": True,
            "duration_ms": _duration_ms(payload.get("duration") or {}),
        }
    if ptype == "patch_apply_end":
        result = {"observed": True}
        if not payload.get("success"):
            result["status"] = "error"
        return result
    if ptype == "web_search_end":
        return {
            "observed": True,
        }
    if ptype == "view_image_tool_call":
        return {
            "observed": True,
        }
    return {}


def _build_steps(
    *,
    timestamp: str,
    tools: list[dict],
) -> list[dict]:
    steps: list[dict] = []
    if tools:
        steps.append({
            "type": "tool_batch",
            "started_at": timestamp,
            "ended_at": timestamp,
            "duration_ms": sum(int(t.get("duration_ms") or 0) for t in tools),
            "tools": tools,
        })
    return steps


def _tool_result_for_next_request(tool: dict) -> dict:
    return {
        "tool_call_id": tool.get("tool_call_id") or "",
    }


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


def _session_id_from_path(path: str) -> str:
    name = Path(path).name
    if name.startswith("rollout-") and name.endswith(".jsonl"):
        return name.rsplit("-", 1)[-1].removesuffix(".jsonl")
    return ""
