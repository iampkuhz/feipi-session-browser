"""Shared normalized adapter for Anthropic-style local chat JSONL agents."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from session_browser.domain.models import ChatMessage, SessionSummary, ToolCall
from session_browser.normalized.schema import NORMALIZED_SCHEMA_VERSION


def build_chat_jsonl_normalized_session(
    *,
    agent: str,
    summary: SessionSummary,
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    source_path: str,
    source_role: str,
    subagent_runs: list[dict] | None = None,
    jsonl_diagnostics: dict | None = None,
    parse_warnings: list[dict] | None = None,
) -> dict:
    """Build normalized session JSON from parsed local chat transcript models."""
    subagent_runs = subagent_runs or []
    parse_warnings = parse_warnings or []
    main_tool_calls = [tc for tc in tool_calls if getattr(tc, "scope", "main") == "main"]
    main_rounds = _build_rounds(
        agent=agent,
        messages=messages,
        tool_calls=main_tool_calls,
        scope="main",
        subagent_id="",
        parent_tool_use_id="",
        subagent_runs=subagent_runs,
    )
    payload_items: list[dict] = []
    for round_obj in main_rounds:
        _append_payload_index_for_round(payload_items, round_obj)

    known_main_tool_ids = _known_tool_ids(main_rounds)
    tool_result_links = _tool_result_links(main_rounds, known_main_tool_ids)

    source_files = [{
        "role": source_role,
        "path": source_path,
        "status": "available" if source_path else "unknown",
    }]
    for run in subagent_runs:
        path = run.get("path", "")
        source_files.append({
            "role": "subagent_session",
            "path": str(path) if path else "",
            "status": "available" if path else "unknown",
            "subagent_id": (run.get("summary") or {}).get("agent_id", ""),
            "parent_tool_use_id": _parent_tool_for_subagent(main_tool_calls, run),
        })

    normalized = {
        "schema_version": NORMALIZED_SCHEMA_VERSION,
        "agent": agent,
        "session": _session_payload(agent, summary),
        "source_files": source_files,
        "rounds": main_rounds,
        "tool_result_links": tool_result_links,
        "payload_index": {"items": payload_items},
        "diagnostics": {
            "token_timeline": [_token_timeline_row(r) for r in main_rounds],
            "warnings": parse_warnings,
        },
        "parse_diagnostics": {
            "jsonl": jsonl_diagnostics or {},
            "warnings": parse_warnings,
        },
    }
    return normalized


def _build_rounds(
    *,
    agent: str,
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    scope: str,
    subagent_id: str,
    parent_tool_use_id: str,
    subagent_runs: list[dict] | None = None,
) -> list[dict]:
    rounds: list[dict] = []
    tool_by_id = {tc.tool_use_id: tc for tc in tool_calls if tc.tool_use_id}
    subagent_by_parent = _subagent_runs_by_parent(tool_calls, subagent_runs or [])

    for msg in messages:
        if msg.role != "assistant" or not msg.llm_call_id:
            continue
        round_id = len(rounds) + 1
        call_id = msg.llm_call_id
        tools = _tools_for_message(msg, tool_by_id, round_id)
        usage = _usage_from_message(msg, agent)
        payload_refs = _payload_refs(round_id, call_id, scope, parent_tool_use_id)
        payload_refs["related_result_payload_ids"] = [t["payload_id"] for t in tools if t.get("payload_id")]
        request = _request_payload_body(agent, msg)
        response = _response_payload_body(agent, msg, tools)
        request_attribution = _request_attribution(agent, usage, request)
        response_attribution = _response_attribution(agent, usage, msg, tools)
        subagent_steps = _subagent_steps_for_tools(
            agent=agent,
            round_id=round_id,
            tools=tools,
            subagent_by_parent=subagent_by_parent,
        )
        steps = _steps_for_round(
            agent=agent,
            round_id=round_id,
            call_id=call_id,
            scope=scope,
            model=msg.model,
            timestamp=msg.timestamp,
            usage=usage,
            payload_refs=payload_refs,
            request=request,
            tools=tools,
            subagent_steps=subagent_steps,
        )
        failed_tool_count = sum(1 for t in tools if t.get("status") == "error")
        rounds.append({
            "round_id": round_id,
            "round_key": f"R{round_id}",
            "call_id": call_id,
            "main_call": {
                "call_id": call_id,
                "turn_id": "",
                "model": msg.model,
                "timestamp": msg.timestamp,
                "source": usage["quality"]["source"],
                "scope": scope,
                "subagent_id": subagent_id,
                "parent_tool_use_id": parent_tool_use_id,
            },
            "summary": _summary_from_message(msg, tools, agent),
            "status": "failed" if failed_tool_count else "ok",
            "timing": {
                "started_at": msg.timestamp,
                "ended_at": msg.timestamp,
                "duration_seconds": 0,
                "process_seconds": 0,
                "waiting_seconds": 0,
            },
            "metrics": {
                "tokens": {
                    "fresh": usage["fresh"],
                    "cache_read": usage["cache_read"],
                    "cache_write": usage["cache_write"],
                    "output": usage["output"],
                    "total": usage["total"],
                    "source_total": usage["source_total"],
                    "total_semantics": "component_sum",
                    "quality": usage["quality"],
                    "raw_fields": usage["raw_fields"],
                },
                "cache_read_ratio": _ratio(usage["cache_read"], usage["fresh"] + usage["cache_read"] + usage["cache_write"]),
                "llm_call_count": 1,
                "tool_call_count": len(tools),
                "failed_tool_count": failed_tool_count,
                "subagent_count": len(subagent_steps),
            },
            "signals": {
                "failed": failed_tool_count > 0,
                "low_cache": False,
                "fresh_spike": False,
                "payload_gap": False,
                "attribution_gap": request_attribution["status"] != "available",
                "items": _issues_from_tools(round_id, tools),
            },
            "request": request,
            "response": response,
            "request_attribution": request_attribution,
            "response_attribution": response_attribution,
            "payload_refs": payload_refs,
            "steps": steps,
        })
    return rounds


def _subagent_steps_for_tools(
    *,
    agent: str,
    round_id: int,
    tools: list[dict],
    subagent_by_parent: dict[str, dict],
) -> list[dict]:
    steps: list[dict] = []
    for tool in tools:
        parent_tool_id = tool.get("tool_call_id", "")
        run = subagent_by_parent.get(parent_tool_id)
        if not run:
            continue
        summary = run.get("summary") or {}
        sub_rounds = _build_rounds(
            agent=agent,
            messages=run.get("messages") or [],
            tool_calls=run.get("tool_calls") or [],
            scope="subagent",
            subagent_id=summary.get("agent_id", ""),
            parent_tool_use_id=parent_tool_id,
            subagent_runs=[],
        )
        for sub_round in sub_rounds:
            sub_round["round_key"] = f"R{round_id}.{sub_round['round_id']}"
        tool["subagent_id"] = summary.get("agent_id", "")
        tool["subagent_summary"] = summary
        tool["sub_round_count"] = len(sub_rounds)
        steps.append({
            "type": "subagent_run",
            "step_id": f"R{round_id}-subagent-{summary.get('agent_id') or parent_tool_id}",
            "parent_tool_call_id": parent_tool_id,
            "subagent_id": summary.get("agent_id", ""),
            "subagent_type": summary.get("agent_type", ""),
            "description": summary.get("description", ""),
            "summary": summary,
            "sub_rounds": sub_rounds,
            "quality": {
                "source": f"{agent}_subagent_sidechain",
                "precision": "reconstructed",
                "status": "available",
            },
        })
    return steps


def _session_payload(agent: str, summary: SessionSummary) -> dict:
    return {
        "session_key": f"{agent}:{summary.session_id}",
        "session_id": summary.session_id,
        "title": _truncate_text(summary.title, 160),
        "agent": agent,
        "model": summary.model,
        "cwd": summary.cwd,
        "started_at": summary.started_at,
        "ended_at": summary.ended_at,
        "git_branch": summary.git_branch,
        "source": summary.source,
        "project_key": summary.project_key,
        "project_name": summary.project_name,
    }


def _usage_from_message(msg: ChatMessage, agent: str) -> dict:
    usage = msg.usage if isinstance(msg.usage, dict) else {}
    fresh = _int(usage.get("input_tokens"))
    cache_read = _int(usage.get("cache_read_input_tokens") or usage.get("cached_input_tokens"))
    cache_write = _int(usage.get("cache_creation_input_tokens") or usage.get("cache_write_input_tokens"))
    output = _int(usage.get("output_tokens"))
    total = fresh + cache_read + cache_write + output
    source_total = _int(usage.get("total_tokens")) or total
    source, precision = _usage_quality(agent, usage)
    return {
        "fresh": fresh,
        "cache_read": cache_read,
        "cache_write": cache_write,
        "output": output,
        "total": total,
        "source_total": source_total,
        "raw_fields": dict(usage),
        "quality": {
            "source": source,
            "precision": precision,
            "status": "available" if usage else "missing",
        },
    }


def _usage_quality(agent: str, usage: dict) -> tuple[str, str]:
    if agent == "qoder" and usage.get("estimated"):
        return "qoder_transcript_estimated", "estimated"
    if agent == "qoder":
        return "qoder_jsonl_usage", "provider_reported"
    if agent == "claude_code":
        return "claude_code_jsonl_usage", "provider_reported"
    return f"{agent}_jsonl_usage", "provider_reported"


def _request_payload_body(agent: str, msg: ChatMessage) -> dict:
    request_text = msg.request_full or ""
    blocks = _request_blocks(request_text)
    status = "partial" if request_text else "missing"
    return _payload_body(
        text=request_text,
        raw=None,
        source=f"{agent}_jsonl_reconstructed_request",
        precision="estimated_partial",
        status=status,
        blocks=blocks,
        fallback_reason="Raw provider request body is not persisted in the local session JSONL.",
    )


def _request_blocks(request_text: str) -> list[dict]:
    if not request_text:
        return []
    blocks: list[dict] = []
    segments = re.split(r"\n{2,}", request_text)
    for segment in segments:
        text = segment.strip()
        if not text:
            continue
        match = re.match(r"Tool result for ([^:\n]+):\n?(.*)", text, re.DOTALL)
        if match:
            blocks.append({
                "type": "tool_result",
                "tool_call_id": match.group(1),
                "text": match.group(2).strip(),
            })
        else:
            blocks.append({
                "type": "message",
                "role": "user",
                "bucket": "Current user prompt",
                "text": text,
            })
    return blocks


def _response_payload_body(agent: str, msg: ChatMessage, tools: list[dict]) -> dict:
    blocks = _response_blocks(msg, tools)
    raw = {"blocks": blocks} if blocks else None
    return _payload_body(
        text=msg.content or "",
        raw=raw,
        source=f"{agent}_jsonl_assistant_message",
        precision="exact" if blocks else "unavailable",
        status="available" if blocks else "missing",
        blocks=blocks,
    )


def _response_blocks(msg: ChatMessage, tools: list[dict]) -> list[dict]:
    blocks: list[dict] = []
    for block in msg.content_blocks or []:
        btype = block.get("type", "")
        if btype == "text":
            blocks.append({"type": "text", "text": block.get("content") or block.get("text") or ""})
        elif btype == "thinking":
            blocks.append({"type": "thinking", "text": block.get("content") or block.get("thinking") or ""})
        elif btype == "tool_use":
            blocks.append({
                "type": "tool_use",
                "id": block.get("id", ""),
                "name": block.get("name", ""),
                "input": block.get("parameters") or block.get("input") or {},
            })
    if not blocks and msg.content:
        blocks.append({"type": "text", "text": msg.content})
    known_tool_ids = {b.get("id") for b in blocks if b.get("type") == "tool_use"}
    for tool in tools:
        tid = tool.get("tool_call_id", "")
        if tid and tid not in known_tool_ids:
            blocks.append({
                "type": "tool_use",
                "id": tid,
                "name": tool.get("name", ""),
                "input": tool.get("parameters") or {},
            })
    return blocks


def _request_attribution(agent: str, usage: dict, request: dict) -> dict:
    request_total = usage["fresh"] + usage["cache_read"] + usage["cache_write"]
    buckets: list[dict] = []
    for block in (request.get("rendered") or {}).get("blocks") or []:
        text = block.get("text") or ""
        if not text:
            continue
        if block.get("type") == "tool_result":
            buckets.append(_bucket("Tool results", _estimate_tokens(text), f"{agent} user.tool_result", "estimated", text))
        else:
            buckets.append(_bucket("Current user prompt", _estimate_tokens(text), f"{agent} user.message", "estimated", text))
    visible = sum(b["tokens"] for b in buckets)
    residual = max(request_total - visible, 0)
    if residual:
        buckets.append(_bucket(
            "Unknown / retained context",
            residual,
            "provider usage residual",
            "estimated_partial",
            "system prompt, tool schemas, history, or hidden runtime context",
        ))
    status = "available" if request_total and visible >= request_total else "partial"
    return _attribution_payload(
        status=status,
        summary={
            "total_input": request_total,
            "fresh_input": usage["fresh"],
            "cache_read": usage["cache_read"],
            "cache_write": usage["cache_write"],
            "visible_estimated_tokens": visible,
            "coverage": _ratio(min(visible, request_total), request_total),
        },
        buckets=buckets,
        total=request_total,
        source=f"{agent} normalized adapter",
        precision="estimated_partial",
    )


def _response_attribution(agent: str, usage: dict, msg: ChatMessage, tools: list[dict]) -> dict:
    total = usage["output"]
    raw_buckets: list[dict] = []
    visible_text = "\n".join(
        block.get("content") or block.get("text") or ""
        for block in msg.content_blocks or []
        if block.get("type") == "text"
    ) or (msg.content if not msg.content_blocks else "")
    thinking_text = "\n".join(
        block.get("content") or block.get("thinking") or ""
        for block in msg.content_blocks or []
        if block.get("type") == "thinking"
    )
    tool_text = json.dumps([
        {"name": t.get("name"), "parameters": t.get("parameters")}
        for t in tools
    ], ensure_ascii=False, sort_keys=True)

    visible_tokens_raw = _estimate_tokens(visible_text)
    thinking_tokens_raw = _estimate_tokens(thinking_text)
    tool_tokens_raw = _estimate_tokens(tool_text) if tools else 0
    budget = total
    visible_tokens = min(visible_tokens_raw, budget)
    budget -= visible_tokens
    thinking_tokens = min(thinking_tokens_raw, budget)
    budget -= thinking_tokens
    tool_tokens = min(tool_tokens_raw, budget)
    if visible_tokens:
        raw_buckets.append(_bucket("Visible text", visible_tokens, f"{agent} assistant.text", "estimated", visible_text))
    if thinking_tokens:
        raw_buckets.append(_bucket("Thinking", thinking_tokens, f"{agent} assistant.thinking", "estimated", thinking_text))
    if tool_tokens:
        raw_buckets.append(_bucket("Tool use", tool_tokens, f"{agent} assistant.tool_use", "estimated", tool_text))
    explained = sum(b["tokens"] for b in raw_buckets)
    residual = max(total - explained, 0)
    if residual:
        raw_buckets.append(_bucket("Unknown output", residual, "provider usage residual", "estimated_partial", "output tokens not explained by visible JSONL blocks"))
    return _attribution_payload(
        status="available" if raw_buckets else "partial",
        summary={
            "total_output": total,
            "visible_estimated_tokens": visible_tokens,
            "thinking_estimated_tokens": thinking_tokens,
            "tool_use_estimated_tokens": tool_tokens,
            "coverage": _ratio(min(explained, total), total),
        },
        buckets=raw_buckets,
        total=total,
        source=f"{agent} normalized adapter",
        precision="estimated",
    )


def _steps_for_round(
    *,
    agent: str,
    round_id: int,
    call_id: str,
    scope: str,
    model: str,
    timestamp: str,
    usage: dict,
    payload_refs: dict,
    request: dict,
    tools: list[dict],
    subagent_steps: list[dict],
) -> list[dict]:
    steps: list[dict] = []
    for idx, block in enumerate((request.get("rendered") or {}).get("blocks") or [], 1):
        if block.get("type") != "message":
            continue
        steps.append({
            "type": "user_context",
            "step_id": f"R{round_id}-user-{idx}",
            "timestamp": timestamp,
            "content": {
                "text": block.get("text", ""),
                "blocks": [block],
                "quality": {"source": f"{agent} user.message", "precision": "exact", "status": "available"},
            },
        })
    steps.append({
        "type": "llm_call",
        "step_id": f"R{round_id}-{scope}-call",
        "call_id": call_id,
        "scope": scope,
        "model": model,
        "status": "ok",
        "timestamp": timestamp,
        "usage": {
            "fresh": usage["fresh"],
            "cache_read": usage["cache_read"],
            "cache_write": usage["cache_write"],
            "output": usage["output"],
            "total": usage["total"],
            "source_total": usage["source_total"],
            "total_semantics": "component_sum",
            "quality": usage["quality"],
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
    steps.extend(subagent_steps)
    return steps


def _tools_for_message(msg: ChatMessage, tool_by_id: dict[str, ToolCall], round_id: int) -> list[dict]:
    tools: list[dict] = []
    for idx, raw in enumerate(msg.tool_calls or [], 1):
        tool_id = str(raw.get("id") or raw.get("tool_use_id") or f"{msg.llm_call_id}-tool-{idx}")
        tool = tool_by_id.get(tool_id)
        if tool is None:
            tool = ToolCall(
                name=str(raw.get("name") or "tool"),
                parameters=raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {},
                timestamp=msg.timestamp,
                tool_use_id=tool_id,
            )
        tools.append(_tool_payload(tool, round_id))
    return tools


def _tool_payload(tool: ToolCall, round_id: int) -> dict:
    result_text = tool.result or ""
    payload_id = f"tool-{_safe_id(tool.tool_use_id or tool.name)}-result"
    return {
        "tool_call_id": tool.tool_use_id or f"tool-{round_id}",
        "name": tool.name,
        "type": "tool_use",
        "scope": tool.scope,
        "parameters": tool.parameters or {},
        "status": tool.status,
        "exit_code": tool.exit_code,
        "duration_ms": int(tool.duration_ms or 0),
        "timestamp": tool.timestamp,
        "files_touched": list(tool.files_touched or []),
        "result": _payload_body(
            text=result_text,
            raw=result_text,
            source="user.tool_result",
            precision="exact" if result_text else "unavailable",
            status="available" if result_text else "missing",
        ),
        "payload_id": payload_id,
        "parent_tool_use_id": tool.parent_tool_use_id,
        "parent_tool_name": tool.parent_tool_name,
        "subagent_id": tool.subagent_id,
        "subagent_summary": tool.subagent_summary or {},
        "llm_call_count": tool.llm_call_count,
        "llm_error_count": tool.llm_error_count,
        "subagent_tool_call_count": tool.subagent_tool_call_count,
        "subagent_failed_tool_count": tool.subagent_failed_tool_count,
    }


def _subagent_runs_by_parent(tool_calls: list[ToolCall], subagent_runs: list[dict]) -> dict[str, dict]:
    by_id = {(run.get("summary") or {}).get("agent_id", ""): run for run in subagent_runs}
    result: dict[str, dict] = {}
    for tc in tool_calls:
        if tc.name != "Agent" or not tc.tool_use_id or not tc.subagent_id:
            continue
        run = by_id.get(tc.subagent_id)
        if run:
            result[tc.tool_use_id] = run
    return result


def _parent_tool_for_subagent(tool_calls: list[ToolCall], run: dict) -> str:
    agent_id = (run.get("summary") or {}).get("agent_id", "")
    for tc in tool_calls:
        if tc.subagent_id == agent_id:
            return tc.tool_use_id
    return ""


def _payload_refs(round_id: int, call_id: str, scope: str, parent_tool_use_id: str) -> dict:
    if scope == "subagent":
        prefix = f"llm-sub-{_safe_id(parent_tool_use_id)}-R{round_id}-C1"
    else:
        prefix = f"llm-R{round_id}-C1"
    return {
        "request_payload_id": f"{prefix}-request",
        "response_payload_id": f"{prefix}-response",
        "request_attribution_id": f"{prefix}-request-attribution",
        "response_attribution_id": f"{prefix}-response-attribution",
        "related_result_payload_ids": [],
    }


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
        "size_bytes": len((text or "").encode("utf-8")),
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


def _append_payload_index_for_round(items: list[dict], round_obj: dict) -> None:
    _append_payload_refs(items, round_obj, {"round_id": round_obj["round_id"], "call_id": round_obj["main_call"]["call_id"]})
    for step in round_obj.get("steps") or []:
        if step.get("type") == "tool_batch":
            for tool in step.get("tools") or []:
                payload_id = tool.get("payload_id")
                if payload_id:
                    items.append({
                        "payload_id": payload_id,
                        "kind": "tool_result",
                        "title": f"{round_obj['round_key']} · Tool Result · {tool.get('name') or 'tool'}",
                        "target": {
                            "round_id": round_obj["round_id"],
                            "tool_call_id": tool.get("tool_call_id", ""),
                        },
                    })
        elif step.get("type") == "subagent_run":
            for sub_round in step.get("sub_rounds") or []:
                _append_payload_refs(items, sub_round, {
                    "round_id": round_obj["round_id"],
                    "sub_round_id": sub_round.get("round_id"),
                    "call_id": sub_round.get("main_call", {}).get("call_id", ""),
                    "parent_tool_call_id": step.get("parent_tool_call_id", ""),
                })
                for sub_step in sub_round.get("steps") or []:
                    if sub_step.get("type") != "tool_batch":
                        continue
                    for tool in sub_step.get("tools") or []:
                        payload_id = tool.get("payload_id")
                        if payload_id:
                            items.append({
                                "payload_id": payload_id,
                                "kind": "tool_result",
                                "title": f"{round_obj['round_key']}.{sub_round.get('round_id')} · Tool Result · {tool.get('name') or 'tool'}",
                                "target": {
                                    "round_id": round_obj["round_id"],
                                    "sub_round_id": sub_round.get("round_id"),
                                    "tool_call_id": tool.get("tool_call_id", ""),
                                },
                            })


def _append_payload_refs(items: list[dict], round_obj: dict, target: dict) -> None:
    refs = round_obj.get("payload_refs") or {}
    label = round_obj.get("round_key") or f"R{round_obj.get('round_id')}"
    for kind, ref_field, title in (
        ("request", "request_payload_id", "Raw Request"),
        ("response", "response_payload_id", "Raw Response"),
        ("llm.request_attribution", "request_attribution_id", "Request Attribution"),
        ("llm.response_attribution", "response_attribution_id", "Response Attribution"),
    ):
        ref = refs.get(ref_field)
        if ref:
            items.append({
                "payload_id": ref,
                "kind": kind,
                "title": f"{label} · {title}",
                "target": target,
            })


def _known_tool_ids(rounds: list[dict]) -> set[str]:
    ids: set[str] = set()
    for round_obj in rounds:
        for step in round_obj.get("steps") or []:
            if step.get("type") == "tool_batch":
                ids.update(t.get("tool_call_id", "") for t in step.get("tools") or [])
    return {i for i in ids if i}


def _tool_result_links(rounds: list[dict], known_tool_ids: set[str]) -> list[dict]:
    links: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for round_obj in rounds:
        request_text = ((round_obj.get("request") or {}).get("rendered") or {}).get("text") or ""
        for source_tool_id in re.findall(r"Tool result for ([^:\n]+):", request_text):
            if source_tool_id not in known_tool_ids:
                continue
            key = (source_tool_id, round_obj["main_call"]["call_id"])
            if key in seen:
                continue
            seen.add(key)
            links.append({
                "source_tool_call_id": source_tool_id,
                "consumed_by_call_id": round_obj["main_call"]["call_id"],
                "consumed_by_round_id": round_obj["round_id"],
            })
    return links


def _token_timeline_row(round_obj: dict) -> dict:
    tokens = round_obj["metrics"]["tokens"]
    return {
        "round_id": round_obj["round_id"],
        "tokens": tokens,
        "cache_read_ratio": round_obj["metrics"]["cache_read_ratio"],
    }


def _summary_from_message(msg: ChatMessage, tools: list[dict], agent: str) -> str:
    text = _truncate_text(msg.content or "", 80)
    if text:
        return text
    if tools:
        names = ", ".join(t.get("name") or "tool" for t in tools[:3])
        return f"Tool call: {names}"
    return f"{agent} LLM call"


def _issues_from_tools(round_id: int, tools: list[dict]) -> list[dict]:
    issues = []
    for tool in tools:
        if tool.get("status") == "error":
            issues.append({
                "kind": "tool_failure",
                "severity": "critical",
                "label": "Tool failure",
                "evidence": f"{tool.get('name')} exit {tool.get('exit_code')}",
                "target": {
                    "round_id": round_id,
                    "tool_call_id": tool.get("tool_call_id"),
                    "payload_id": tool.get("payload_id"),
                },
            })
    return issues


def jsonl_diag_to_dict(jsonl_diag: Any) -> dict:
    if jsonl_diag is None:
        return {}
    if isinstance(jsonl_diag, dict):
        return dict(jsonl_diag)
    issues = []
    for item in getattr(jsonl_diag, "issues", []) or []:
        issue = getattr(item, "issue", "")
        severity = getattr(item, "severity", "")
        issues.append({
            "issue": getattr(issue, "value", str(issue)),
            "severity": getattr(severity, "name", str(severity)).lower(),
            "line_no": getattr(item, "line_no", 0),
            "detail": getattr(item, "detail", ""),
            "preview": getattr(item, "preview", ""),
        })
    return {
        "issues": issues,
        "total_lines": getattr(jsonl_diag, "total_lines", 0),
        "non_empty_lines": getattr(jsonl_diag, "non_empty_lines", 0),
        "events_parsed": getattr(jsonl_diag, "events_parsed", 0),
        "events_skipped": getattr(jsonl_diag, "events_skipped", 0),
        "warning_count": getattr(jsonl_diag, "warning_count", 0),
        "error_count": getattr(jsonl_diag, "error_count", 0),
    }


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


def _safe_id(value: Any) -> str:
    text = _stringify(value) or "unknown"
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "-", text).strip("-")
    return text or "unknown"


def session_id_from_file(path: str | Path) -> str:
    return Path(path).stem
