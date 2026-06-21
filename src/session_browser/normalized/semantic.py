"""构建 normalized session 的语义模型。"""

from __future__ import annotations

from typing import Any

from session_browser.normalized.schema import NORMALIZED_SCHEMA_VERSION


def build_normalized_session_model(
    *,
    agent: str,
    session: dict[str, Any],
    source_files: list[dict[str, Any]],
    call_drafts: list[dict[str, Any]],
    parse_warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """把各 agent 的解析结果转换为当前 LLM call 语义模型。

    适配器仍负责还原 agent 专属 transcript 细节。本层只持久化扫描期事实：
    LLM call、usage 汇总和 tool-call 边；较重的 attribution buckets 与 payload
    indexes 在请求时从源 JSONL 重建。
    """
    calls: list[dict[str, Any]] = []
    tool_executions: list[dict[str, Any]] = []

    for round_obj in call_drafts:
        _append_round_as_calls(
            round_obj=round_obj,
            calls=calls,
            tool_executions=tool_executions,
            parent_call_id="",
            parent_tool_call_id="",
        )

    _resolve_tool_consumers(calls, tool_executions)

    return {
        "schema_version": NORMALIZED_SCHEMA_VERSION,
        "agent": agent,
        "source": {
            "files": source_files,
        },
        "session": session,
        "calls": calls,
        "tool_executions": tool_executions,
        "diagnostics": list(parse_warnings or []),
    }


def _append_round_as_calls(
    *,
    round_obj: dict[str, Any],
    calls: list[dict[str, Any]],
    tool_executions: list[dict[str, Any]],
    parent_call_id: str,
    parent_tool_call_id: str,
) -> None:
    call = _call_from_round(
        round_obj,
        call_index=len(calls) + 1,
        parent_call_id=parent_call_id,
        parent_tool_call_id=parent_tool_call_id,
    )
    calls.append(call)

    for step in round_obj.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if step.get("type") == "tool_batch":
            for tool in step.get("tools") or []:
                if isinstance(tool, dict):
                    tool_execution = _tool_execution_from_tool(
                        tool,
                        declared_by_call=call,
                    )
                    tool_executions.append(tool_execution)
        elif step.get("type") == "subagent_run":
            sub_parent_tool_id = str(step.get("parent_tool_call_id") or "")
            for sub_round in step.get("sub_rounds") or []:
                if isinstance(sub_round, dict):
                    _append_round_as_calls(
                        round_obj=sub_round,
                        calls=calls,
                        tool_executions=tool_executions,
                        parent_call_id=call["call_id"],
                        parent_tool_call_id=sub_parent_tool_id,
                    )


def _call_from_round(
    round_obj: dict[str, Any],
    *,
    call_index: int,
    parent_call_id: str,
    parent_tool_call_id: str,
) -> dict[str, Any]:
    main_call = round_obj.get("main_call") if isinstance(round_obj.get("main_call"), dict) else {}
    call_id = str(main_call.get("call_id") or round_obj.get("call_id") or f"call-{call_index:04d}")
    metrics = round_obj.get("metrics") if isinstance(round_obj.get("metrics"), dict) else {}
    usage = _usage_from_metrics(metrics)
    usage_source = metrics.get("usage_source") if isinstance(metrics.get("usage_source"), dict) else {}
    request = round_obj.get("request") if isinstance(round_obj.get("request"), dict) else {}
    response = round_obj.get("response") if isinstance(round_obj.get("response"), dict) else {}
    attribution_candidates = (
        round_obj.get("attribution_candidates")
        if isinstance(round_obj.get("attribution_candidates"), dict)
        else {}
    )
    source_units = (
        round_obj.get("source_units")
        if isinstance(round_obj.get("source_units"), list)
        else []
    )
    source_unit_ref_ranges = (
        round_obj.get("source_unit_ref_ranges")
        if isinstance(round_obj.get("source_unit_ref_ranges"), list)
        else []
    )
    tool_result_ids = _string_list(request.get("tool_result_ids"))
    tool_call_ids = _string_list(response.get("tool_call_ids"))

    call = {
        "call_id": call_id,
        "call_index": call_index,
        "call_key": f"C{call_index}",
        "scope": str(main_call.get("scope") or "main"),
        "parent_call_id": parent_call_id,
        "parent_tool_call_id": parent_tool_call_id or str(main_call.get("parent_tool_use_id") or ""),
        "turn_id": str(main_call.get("turn_id") or ""),
        "model": str(main_call.get("model") or ""),
        "timestamp": str(main_call.get("timestamp") or ""),
        "usage": usage,
        "request": {
            "tool_result_ids": tool_result_ids,
        },
        "response": {
            "tool_call_ids": tool_call_ids,
        },
    }
    if attribution_candidates:
        call["attribution_candidates"] = attribution_candidates
    if source_units:
        call["source_units"] = source_units
    if source_unit_ref_ranges:
        call["source_unit_ref_ranges"] = source_unit_ref_ranges
    if usage_source:
        call["usage_source"] = {
            "kind": str(usage_source.get("kind") or ""),
            "method": str(usage_source.get("method") or ""),
            "reason": str(usage_source.get("reason") or ""),
        }
    return call


def _usage_from_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    tokens = metrics.get("tokens") if isinstance(metrics.get("tokens"), dict) else {}
    fresh = _int(tokens.get("fresh"))
    cache_read = _int(tokens.get("cache_read"))
    cache_write = _int(tokens.get("cache_write"))
    output = _int(tokens.get("output"))
    total = _int(tokens.get("total")) or fresh + cache_read + cache_write + output
    return {
        "fresh": fresh,
        "cache_read": cache_read,
        "cache_write": cache_write,
        "output": output,
        "total": total,
    }


def _tool_execution_from_tool(
    tool: dict[str, Any],
    *,
    declared_by_call: dict[str, Any],
) -> dict[str, Any]:
    tool_call_id = str(tool.get("tool_call_id") or "")
    result: dict[str, Any] = {
        "tool_call_id": tool_call_id,
        "name": str(tool.get("name") or ""),
        "scope": str(tool.get("scope") or declared_by_call.get("scope") or "main"),
        "declared_by_call_id": declared_by_call["call_id"],
        "result_consumed_by_call_id": "",
    }
    status = str(tool.get("status") or "")
    if status and status != "completed":
        result["status"] = status
    exit_code = tool.get("exit_code")
    if exit_code not in (None, 0):
        result["exit_code"] = exit_code
    duration_ms = _int(tool.get("duration_ms"))
    if duration_ms:
        result["duration_ms"] = duration_ms
    files_touched = list(tool.get("files_touched") or [])
    if files_touched:
        result["files_touched"] = files_touched
    subagent_id = str(tool.get("subagent_id") or "")
    if subagent_id:
        result["subagent_id"] = subagent_id
    return result


def _resolve_tool_consumers(
    calls: list[dict[str, Any]],
    tool_executions: list[dict[str, Any]],
) -> None:
    by_tool = {tool["tool_call_id"]: tool for tool in tool_executions if tool.get("tool_call_id")}
    for call in calls:
        for tool_id in (call.get("request") or {}).get("tool_result_ids") or []:
            tool = by_tool.get(tool_id)
            if not tool:
                continue
            tool["result_consumed_by_call_id"] = call["call_id"]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0
