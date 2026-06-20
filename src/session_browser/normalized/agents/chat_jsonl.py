"""Shared normalized adapter，用于 Anthropic-style local chat JSONL agents."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from session_browser.domain.models import ChatMessage, SessionSummary, ToolCall
from session_browser.normalized.semantic import build_normalized_session_model


def build_chat_jsonl_normalized_session(
    *,
    agent: str,
    summary: SessionSummary,
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    source_path: str,
    source_role: str,
    subagent_runs: list[dict] | None = None,
    parse_warnings: list[dict] | None = None,
) -> dict:
    """构建 normalized session JSON，来源于 parsed local chat transcript models."""
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
    source_files = [{
        "role": source_role,
        "path": source_path,
    }]
    for run in subagent_runs:
        path = run.get("path", "")
        source_files.append({
            "role": "subagent_session",
            "path": str(path) if path else "",
            "subagent_id": (run.get("summary") or {}).get("agent_id", ""),
            "parent_tool_use_id": _parent_tool_for_subagent(main_tool_calls, run),
        })

    return build_normalized_session_model(
        agent=agent,
        session=_session_payload(agent, summary),
        source_files=source_files,
        call_drafts=main_rounds,
        parse_warnings=parse_warnings,
    )


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
        usage = _usage_from_message(msg)
        metrics = {
            "tokens": {
                "fresh": usage["fresh"],
                "cache_read": usage["cache_read"],
                "cache_write": usage["cache_write"],
                "output": usage["output"],
                "total": usage["total"],
            },
        }
        if usage.get("usage_source"):
            metrics["usage_source"] = usage["usage_source"]
        request = {"tool_result_ids": _tool_result_ids_from_request(msg.request_full or "")}
        response = {"tool_call_ids": _tool_call_ids_from_message(msg, tools)}
        subagent_steps = _subagent_steps_for_tools(
            agent=agent,
            round_id=round_id,
            tools=tools,
            subagent_by_parent=subagent_by_parent,
        )
        steps = _steps_for_round(
            timestamp=msg.timestamp,
            tools=tools,
            subagent_steps=subagent_steps,
        )
        rounds.append({
            "round_id": round_id,
            "round_key": f"R{round_id}",
            "main_call": {
                "call_id": call_id,
                "turn_id": "",
                "model": msg.model,
                "timestamp": msg.timestamp,
                "scope": scope,
                "subagent_id": subagent_id,
                "parent_tool_use_id": parent_tool_use_id,
            },
            "metrics": metrics,
            "request": request,
            "response": response,
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
            "sub_rounds": sub_rounds,
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


def _usage_from_message(msg: ChatMessage) -> dict:
    usage = msg.usage if isinstance(msg.usage, dict) else {}
    if usage:
        fresh = _int(usage.get("input_tokens"))
        cache_read = _int(usage.get("cache_read_input_tokens") or usage.get("cached_input_tokens"))
        cache_write = _int(usage.get("cache_creation_input_tokens") or usage.get("cache_write_input_tokens"))
        output = _int(usage.get("output_tokens"))
        total = fresh + cache_read + cache_write + output
        return {
            "fresh": fresh,
            "cache_read": cache_read,
            "cache_write": cache_write,
            "output": output,
            "total": total,
        }

    fresh = _estimate_tokens(msg.request_full)
    cache_read = 0
    cache_write = 0
    output = _estimate_tokens(msg.content)
    total = fresh + cache_read + cache_write + output
    result = {
        "fresh": fresh,
        "cache_read": cache_read,
        "cache_write": cache_write,
        "output": output,
        "total": total,
    }
    if total:
        result["usage_source"] = {
            "kind": "estimated",
            "method": "chars_div_4",
            "reason": "provider_usage_missing",
        }
    return result


def _tool_result_ids_from_request(request_text: str) -> list[str]:
    if not request_text:
        return []
    tool_result_ids: list[str] = []
    segments = re.split(r"\n{2,}", request_text)
    for segment in segments:
        text = segment.strip()
        if not text:
            continue
        match = re.match(r"Tool result for ([^:\n]+):\n?(.*)", text, re.DOTALL)
        if match:
            tool_result_ids.append(match.group(1))
    return tool_result_ids


def _tool_call_ids_from_message(msg: ChatMessage, tools: list[dict]) -> list[str]:
    ids: list[str] = []
    for block in msg.content_blocks or []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
            ids.append(str(block["id"]))
    known_tool_ids = set(ids)
    for tool in tools:
        tid = tool.get("tool_call_id", "")
        if tid and tid not in known_tool_ids:
            ids.append(str(tid))
    return ids


def _steps_for_round(
    *,
    timestamp: str,
    tools: list[dict],
    subagent_steps: list[dict],
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
                timestamp=msg.timestamp,
                tool_use_id=tool_id,
            )
        tools.append(_tool_payload(tool, round_id))
    return tools


def _tool_payload(tool: ToolCall, round_id: int) -> dict:
    payload: dict[str, Any] = {
        "tool_call_id": tool.tool_use_id or f"tool-{round_id}",
        "name": tool.name,
        "scope": tool.scope,
        "exit_code": tool.exit_code,
        "duration_ms": int(tool.duration_ms or 0),
        "files_touched": list(tool.files_touched or []),
        "parent_tool_use_id": tool.parent_tool_use_id,
        "subagent_id": tool.subagent_id,
    }
    if tool.status and tool.status != "completed":
        payload["status"] = tool.status
    return payload


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

def _int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _estimate_tokens(text: Any) -> int:
    value = _stringify(text).strip()
    if not value:
        return 0
    return max(1, (len(value) + 3) // 4)


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


def session_id_from_file(path: str | Path) -> str:
    return Path(path).stem
