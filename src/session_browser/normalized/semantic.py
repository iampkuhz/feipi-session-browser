"""Build the normalized session semantic model."""

from __future__ import annotations

import copy
from typing import Any

from session_browser.normalized.schema import NORMALIZED_SCHEMA_VERSION


REQUEST_SOURCE_ORDER = (
    "system_base_prompt",
    "runtime_policy_context",
    "tool_definitions",
    "skills_and_agents",
    "project_context",
    "current_user_input",
    "tool_results",
    "conversation_history",
    "unknown_retained_context",
)


REQUEST_BUCKET_CATEGORY = {
    "Developer instructions": "runtime_policy_context",
    "Project/environment context": "project_context",
    "Current user prompt": "current_user_input",
    "Tool results": "tool_results",
    "Compacted history": "conversation_history",
    "Unknown / retained context": "unknown_retained_context",
}


RESPONSE_BUCKET_CATEGORY = {
    "Visible text": "visible_text",
    "Thinking": "thinking",
    "Reasoning": "reasoning",
    "Tool use": "tool_use",
    "Unknown output": "unknown_output",
}


def build_normalized_session_model(
    *,
    agent: str,
    session: dict[str, Any],
    source_files: list[dict[str, Any]],
    call_drafts: list[dict[str, Any]],
    parse_warnings: list[dict[str, Any]] | None = None,
    jsonl_diagnostics: dict[str, Any] | None = None,
    extra_parse_diagnostics: dict[str, Any] | None = None,
    context_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert parsed agent output into the current LLM-call semantic model.

    Existing adapters still reconstruct agent-specific transcript details. This
    layer removes the UI-oriented round shape from the persisted artifact and
    makes LLM calls, tool executions, token sources, and source references the
    primary objects.
    """
    payload_index: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    tool_executions: list[dict[str, Any]] = []

    for round_obj in call_drafts:
        _append_round_as_calls(
            round_obj=round_obj,
            calls=calls,
            tool_executions=tool_executions,
            payload_index=payload_index,
            parent_call_id="",
            parent_tool_call_id="",
        )

    _resolve_tool_consumers(calls, tool_executions)

    diagnostics = {
        "token_timeline": [_token_timeline_row(call) for call in calls],
        "warnings": parse_warnings or [],
    }
    parse_diagnostics = {
        "jsonl": jsonl_diagnostics or {},
        "warnings": parse_warnings or [],
    }
    if extra_parse_diagnostics:
        parse_diagnostics.update(extra_parse_diagnostics)

    return {
        "schema_version": NORMALIZED_SCHEMA_VERSION,
        "agent": agent,
        "source": {
            "agent": agent,
            "files": source_files,
            "artifact": {
                "kind": "normalized_session_json",
                "model": "llm_call_semantic",
            },
        },
        "session": session,
        "context_sources": context_sources or _default_context_sources(agent, source_files),
        "calls": calls,
        "tool_executions": tool_executions,
        "payload_index": {"items": payload_index},
        "diagnostics": diagnostics,
        "parse_diagnostics": parse_diagnostics,
    }


def _append_round_as_calls(
    *,
    round_obj: dict[str, Any],
    calls: list[dict[str, Any]],
    tool_executions: list[dict[str, Any]],
    payload_index: list[dict[str, Any]],
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
    _append_payload_index_for_call(payload_index, call)

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
                    _append_tool_payload_index(payload_index, call, tool_execution)
        elif step.get("type") == "subagent_run":
            sub_parent_tool_id = str(step.get("parent_tool_call_id") or "")
            for sub_round in step.get("sub_rounds") or []:
                if isinstance(sub_round, dict):
                    _append_round_as_calls(
                        round_obj=sub_round,
                        calls=calls,
                        tool_executions=tool_executions,
                        payload_index=payload_index,
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
    refs = round_obj.get("payload_refs") if isinstance(round_obj.get("payload_refs"), dict) else {}
    request_payload = round_obj.get("request") if isinstance(round_obj.get("request"), dict) else {}
    response_payload = round_obj.get("response") if isinstance(round_obj.get("response"), dict) else {}
    metrics = copy.deepcopy(round_obj.get("metrics") or {})
    usage = _usage_from_metrics(metrics)

    request_blocks = ((request_payload.get("rendered") or {}).get("blocks") or [])
    response_blocks = ((response_payload.get("rendered") or {}).get("blocks") or [])
    request_content_refs = [
        _content_ref(
            payload_id=str(refs.get("request_payload_id") or ""),
            payload_path=f"rendered.blocks[{idx}]",
            block=block,
            default_event_type="request_content",
        )
        for idx, block in enumerate(request_blocks)
        if isinstance(block, dict)
    ]
    response_content_refs = [
        _content_ref(
            payload_id=str(refs.get("response_payload_id") or ""),
            payload_path=f"rendered.blocks[{idx}]",
            block=block,
            default_event_type="response_content",
        )
        for idx, block in enumerate(response_blocks)
        if isinstance(block, dict)
    ]
    tool_result_ids = [
        str(block.get("tool_call_id") or "")
        for block in request_blocks
        if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_call_id")
    ]
    tool_use_ids = [
        str(block.get("id") or block.get("tool_call_id") or "")
        for block in response_blocks
        if isinstance(block, dict) and block.get("type") == "tool_use" and (block.get("id") or block.get("tool_call_id"))
    ]

    request_token_sources = _token_sources(
        attribution=round_obj.get("request_attribution") or {},
        source_kind="request",
        token_source_ref=str(refs.get("request_attribution_id") or ""),
    )
    response_token_sources = _token_sources(
        attribution=round_obj.get("response_attribution") or {},
        source_kind="response",
        token_source_ref=str(refs.get("response_attribution_id") or ""),
    )

    return {
        "call_id": call_id,
        "call_index": call_index,
        "call_key": f"C{call_index}",
        "scope": str(main_call.get("scope") or "main"),
        "parent_call_id": parent_call_id,
        "parent_tool_call_id": parent_tool_call_id or str(main_call.get("parent_tool_use_id") or ""),
        "turn_id": str(main_call.get("turn_id") or ""),
        "model": str(main_call.get("model") or ""),
        "timestamp": str(main_call.get("timestamp") or ""),
        "source": str(main_call.get("source") or ""),
        "summary": str(round_obj.get("summary") or ""),
        "status": str(round_obj.get("status") or "ok"),
        "timing": copy.deepcopy(round_obj.get("timing") or {}),
        "usage": usage,
        "request": {
            "payload_ref": str(refs.get("request_payload_id") or ""),
            "token_source_ref": str(refs.get("request_attribution_id") or ""),
            "content_refs": request_content_refs,
            "tool_result_ids": tool_result_ids,
            "token_sources": request_token_sources,
            "availability": copy.deepcopy(request_payload.get("availability") or {}),
        },
        "response": {
            "payload_ref": str(refs.get("response_payload_id") or ""),
            "token_source_ref": str(refs.get("response_attribution_id") or ""),
            "content_refs": response_content_refs,
            "message_refs": [
                ref for ref in response_content_refs
                if ref.get("payload_type") in {"text", "output_text"}
            ],
            "reasoning_refs": [
                ref for ref in response_content_refs
                if ref.get("payload_type") in {"reasoning", "thinking"}
            ],
            "tool_use_refs": [
                ref for ref in response_content_refs
                if ref.get("payload_type") == "tool_use"
            ],
            "tool_use_ids": tool_use_ids,
            "token_sources": response_token_sources,
            "availability": copy.deepcopy(response_payload.get("availability") or {}),
        },
        "signals": copy.deepcopy(round_obj.get("signals") or {}),
    }


def _usage_from_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    tokens = copy.deepcopy(metrics.get("tokens") or {})
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
        "source_total": _int(tokens.get("source_total")) or total,
        "total_semantics": tokens.get("total_semantics") or "component_sum",
        "quality": copy.deepcopy(tokens.get("quality") or {}),
        "raw_fields": copy.deepcopy(tokens.get("raw_fields") or {}),
    }


def _content_ref(
    *,
    payload_id: str,
    payload_path: str,
    block: dict[str, Any],
    default_event_type: str,
) -> dict[str, Any]:
    payload_type = str(block.get("type") or "")
    ref_id = f"{payload_id}:{payload_path}" if payload_id else payload_path
    return {
        "ref_id": ref_id,
        "payload_id": payload_id,
        "payload_path": payload_path,
        "event_type": str(block.get("event_type") or default_event_type),
        "payload_type": payload_type,
        "role": str(block.get("role") or ""),
        "tool_call_id": str(block.get("tool_call_id") or block.get("id") or ""),
        "text_preview": _truncate_text(str(block.get("text") or block.get("summary") or ""), 120),
    }


def _token_sources(
    *,
    attribution: dict[str, Any],
    source_kind: str,
    token_source_ref: str,
) -> list[dict[str, Any]]:
    buckets = attribution.get("buckets") if isinstance(attribution, dict) else []
    if not isinstance(buckets, list):
        buckets = []
    if source_kind == "request":
        expanded = _request_token_sources(buckets, token_source_ref)
    else:
        expanded = [
            _token_source_from_bucket(bucket, source_kind, token_source_ref)
            for bucket in buckets
            if isinstance(bucket, dict)
        ]
    return expanded


def _request_token_sources(
    buckets: list[Any],
    token_source_ref: str,
) -> list[dict[str, Any]]:
    by_category: dict[str, list[dict[str, Any]]] = {cat: [] for cat in REQUEST_SOURCE_ORDER}
    other: list[dict[str, Any]] = []
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        source = _token_source_from_bucket(bucket, "request", token_source_ref)
        category = source["canonical_category"]
        if category in by_category:
            by_category[category].append(source)
        else:
            other.append(source)

    result: list[dict[str, Any]] = []
    for category in REQUEST_SOURCE_ORDER:
        items = by_category[category]
        if items:
            result.extend(items)
        else:
            result.append(_empty_request_token_source(category, token_source_ref))
    result.extend(other)
    return result


def _token_source_from_bucket(
    bucket: dict[str, Any],
    source_kind: str,
    token_source_ref: str,
) -> dict[str, Any]:
    agent_bucket = str(bucket.get("bucket") or "")
    if source_kind == "request":
        canonical = REQUEST_BUCKET_CATEGORY.get(agent_bucket, _canonicalize(agent_bucket) or "unknown_request_context")
    else:
        canonical = RESPONSE_BUCKET_CATEGORY.get(agent_bucket, _canonicalize(agent_bucket) or "unknown_output")
    return {
        "canonical_category": canonical,
        "agent_bucket": agent_bucket,
        "tokens": _int(bucket.get("tokens")),
        "share": bucket.get("share"),
        "precision": str(bucket.get("precision") or ""),
        "source": str(bucket.get("source") or ""),
        "preview": str(bucket.get("preview") or ""),
        "source_refs": [_source_ref(
            payload_id=token_source_ref,
            payload_path="buckets[]",
            event_type=f"{source_kind}_token_source",
            payload_type=agent_bucket,
        )],
    }


def _empty_request_token_source(category: str, token_source_ref: str) -> dict[str, Any]:
    return {
        "canonical_category": category,
        "agent_bucket": "",
        "tokens": 0,
        "share": 0,
        "precision": "unavailable",
        "source": "not_observable_in_local_log",
        "preview": "",
        "source_refs": [_source_ref(
            payload_id=token_source_ref,
            payload_path="buckets[]",
            event_type="request_token_source",
            payload_type=category,
        )],
    }


def _tool_execution_from_tool(
    tool: dict[str, Any],
    *,
    declared_by_call: dict[str, Any],
) -> dict[str, Any]:
    tool_call_id = str(tool.get("tool_call_id") or "")
    return {
        "tool_call_id": tool_call_id,
        "name": str(tool.get("name") or ""),
        "type": str(tool.get("type") or "tool_use"),
        "scope": str(tool.get("scope") or declared_by_call.get("scope") or "main"),
        "declared_by_call_id": declared_by_call["call_id"],
        "declared_by_call_index": declared_by_call["call_index"],
        "result_consumed_by_call_id": "",
        "result_consumed_by_call_index": None,
        "parameters": copy.deepcopy(tool.get("parameters") or {}),
        "status": str(tool.get("status") or ""),
        "exit_code": tool.get("exit_code"),
        "duration_ms": _int(tool.get("duration_ms")),
        "timestamp": str(tool.get("timestamp") or ""),
        "files_touched": list(tool.get("files_touched") or []),
        "call_ref": _source_ref(
            payload_id=str((declared_by_call.get("response") or {}).get("payload_ref") or ""),
            payload_path="rendered.blocks[]",
            event_type="response_content",
            payload_type="tool_use",
        ),
        "result_ref": _source_ref(
            payload_id=str(tool.get("payload_id") or ""),
            payload_path="result",
            event_type="tool_result",
            payload_type="tool_result",
        ),
        "result": copy.deepcopy(tool.get("result") or {}),
        "subagent_id": str(tool.get("subagent_id") or ""),
        "subagent_summary": copy.deepcopy(tool.get("subagent_summary") or {}),
        "llm_call_count": _int(tool.get("llm_call_count")),
        "llm_error_count": _int(tool.get("llm_error_count")),
        "subagent_tool_call_count": _int(tool.get("subagent_tool_call_count")),
        "subagent_failed_tool_count": _int(tool.get("subagent_failed_tool_count")),
    }


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
            tool["result_consumed_by_call_index"] = call["call_index"]


def _append_payload_index_for_call(
    items: list[dict[str, Any]],
    call: dict[str, Any],
) -> None:
    target = {
        "call_id": call["call_id"],
        "call_index": call["call_index"],
        "scope": call["scope"],
    }
    for kind, field, title in (
        ("request", "payload_ref", "Raw Request"),
        ("response", "payload_ref", "Raw Response"),
        ("llm.request_token_sources", "token_source_ref", "Request Token Sources"),
    ):
        owner = call["request"] if kind != "response" else call["response"]
        payload_id = owner.get(field)
        if payload_id:
            items.append({
                "payload_id": payload_id,
                "kind": kind,
                "title": f"{call['call_key']} · {title}",
                "target": target,
            })
    response_token_source_ref = call["response"].get("token_source_ref")
    if response_token_source_ref:
        items.append({
            "payload_id": response_token_source_ref,
            "kind": "llm.response_token_sources",
            "title": f"{call['call_key']} · Response Token Sources",
            "target": target,
        })


def _append_tool_payload_index(
    items: list[dict[str, Any]],
    call: dict[str, Any],
    tool_execution: dict[str, Any],
) -> None:
    payload_id = (tool_execution.get("result_ref") or {}).get("payload_id")
    if not payload_id:
        return
    items.append({
        "payload_id": payload_id,
        "kind": "tool_result",
        "title": f"{call['call_key']} · Tool Result · {tool_execution.get('name') or 'tool'}",
        "target": {
            "call_id": call["call_id"],
            "call_index": call["call_index"],
            "tool_call_id": tool_execution.get("tool_call_id", ""),
        },
    })


def _source_ref(
    *,
    payload_id: str,
    payload_path: str,
    event_type: str,
    payload_type: str,
) -> dict[str, Any]:
    return {
        "payload_id": payload_id,
        "payload_path": payload_path,
        "event_type": event_type,
        "payload_type": payload_type,
    }


def _token_timeline_row(call: dict[str, Any]) -> dict[str, Any]:
    usage = call.get("usage") or {}
    input_side = _int(usage.get("fresh")) + _int(usage.get("cache_read")) + _int(usage.get("cache_write"))
    return {
        "call_id": call.get("call_id", ""),
        "call_index": call.get("call_index", 0),
        "scope": call.get("scope", ""),
        "usage": usage,
        "cache_read_ratio": _ratio(_int(usage.get("cache_read")), input_side),
    }


def _default_context_sources(agent: str, source_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_path = ""
    if source_files:
        source_path = str(source_files[0].get("path") or "")
    return [
        {
            "canonical_category": category,
            "label": category.replace("_", " "),
            "source": f"{agent}_local_session",
            "status": "derived" if category in {"current_user_input", "tool_results"} else "not_directly_observable",
            "source_ref": {
                "path": source_path,
                "payload_path": "",
            },
        }
        for category in REQUEST_SOURCE_ORDER
    ]


def _canonicalize(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


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
