"""Qoder 会话 normalized 归因适配器。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from session_browser.domain.models import ChatMessage, SessionSummary, SubagentRun, ToolCall
from session_browser.normalized.agents.qoder_parts import (
    QoderSourceUnitDraft,
    finalize_source_units,
    payload_unit,
    source_units_to_candidates,
    text_unit,
)
from session_browser.normalized.semantic import build_normalized_session_model
from session_browser.sources.jsonl_reader import parse_jsonl_events


class QoderNormalizationAdapter:
    """Qoder 专属 normalized source unit 构造器。"""

    def build(
        self,
        *,
        summary: SessionSummary,
        messages: list[ChatMessage],
        tool_calls: list[ToolCall],
        source_path: str,
        subagent_runs: list[SubagentRun] | None = None,
        parse_warnings: list[dict] | None = None,
    ) -> dict:
        subagent_runs = subagent_runs or []
        main_tool_calls = [tc for tc in tool_calls if getattr(tc, "scope", "main") == "main"]
        rounds = self._build_rounds(
            summary=summary,
            messages=messages,
            tool_calls=main_tool_calls,
            source_path=source_path,
            scope="main",
            subagent_id="",
            parent_tool_use_id="",
            subagent_runs=subagent_runs,
        )
        source_files = [{"role": "main_session", "path": source_path}]
        for run in subagent_runs:
            path = run.get("path", "")
            source_files.append({
                "role": "subagent_session",
                "path": str(path) if path else "",
                "subagent_id": (run.get("summary") or {}).get("agent_id", ""),
                "parent_tool_use_id": _parent_tool_for_subagent(main_tool_calls, run),
            })
        return build_normalized_session_model(
            agent="qoder",
            session=_session_payload(summary),
            source_files=source_files,
            call_drafts=rounds,
            parse_warnings=parse_warnings or [],
        )

    def _build_rounds(
        self,
        *,
        summary: SessionSummary,
        messages: list[ChatMessage],
        tool_calls: list[ToolCall],
        source_path: str,
        scope: str,
        subagent_id: str,
        parent_tool_use_id: str,
        subagent_runs: list[SubagentRun],
    ) -> list[dict]:
        rounds: list[dict] = []
        tool_by_id = {tc.tool_use_id: tc for tc in tool_calls if tc.tool_use_id}
        subagent_by_parent = _subagent_runs_by_parent(tool_calls, subagent_runs)
        assistant_seen = 0
        instruction_units = _project_instruction_units(summary, source_path)

        for msg_index, msg in enumerate(messages):
            if msg.role != "assistant" or not msg.llm_call_id:
                continue
            assistant_seen += 1
            round_id = len(rounds) + 1
            call_id = msg.llm_call_id
            tools = _tools_for_message(msg, tool_by_id, round_id)
            usage = _usage_from_message(msg)
            request_units = self._request_units_for_call(
                call_id=call_id,
                msg=msg,
                messages_before=messages[:msg_index],
                summary=summary,
                source_path=source_path,
                instruction_units=instruction_units,
                event_order=assistant_seen,
            )
            response_units = self._response_units_for_call(
                msg=msg,
                event_order=assistant_seen,
            )
            source_units = finalize_source_units(call_id, request_units + response_units)
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
            subagent_steps = _subagent_steps_for_tools(
                adapter=self,
                summary=summary,
                source_path=source_path,
                round_id=round_id,
                tools=tools,
                subagent_by_parent=subagent_by_parent,
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
                "request": {"tool_result_ids": _tool_result_ids_from_request(msg.request_full or "")},
                "response": {"tool_call_ids": _tool_call_ids_from_message(msg, tools)},
                "source_units": source_units,
                "attribution_candidates": source_units_to_candidates(source_units),
                "steps": _steps_for_round(timestamp=msg.timestamp, tools=tools, subagent_steps=subagent_steps),
            })
        return rounds

    def _request_units_for_call(
        self,
        *,
        call_id: str,
        msg: ChatMessage,
        messages_before: list[ChatMessage],
        summary: SessionSummary,
        source_path: str,
        instruction_units: list[QoderSourceUnitDraft],
        event_order: int,
    ) -> list[QoderSourceUnitDraft]:
        units: list[QoderSourceUnitDraft] = []
        timestamp = msg.timestamp
        units.extend(_clone_units_for_call(instruction_units, event_order=event_order, timestamp=timestamp))
        runtime_payload = {
            "cwd": summary.cwd,
            "project_key": summary.project_key,
            "git_branch": summary.git_branch,
            "source": summary.source,
            "model": msg.model or summary.model,
        }
        units.append(payload_unit(
            origin_path="session.runtime",
            unit_type="qoder_runtime_context",
            candidate="runtime_context",
            direction="request",
            payload={k: v for k, v in runtime_payload.items() if v},
            timestamp=timestamp,
            event_order=event_order,
            label="Qoder 运行上下文",
            priority=40,
        ))

        current_user_index = _current_user_index_for_call(messages_before)
        if current_user_index >= 0:
            current_user = messages_before[current_user_index]
            if current_user.content:
                units.append(text_unit(
                    origin_path=f"messages[{current_user_index}].content",
                    unit_type="current_user_message",
                    candidate="user_input",
                    direction="request",
                    text=current_user.content,
                    timestamp=current_user.timestamp or timestamp,
                    event_order=event_order,
                    label="当前用户输入",
                    priority=90,
                ))
        for idx, prior in enumerate(messages_before):
            if idx == current_user_index or not prior.content:
                continue
            units.append(text_unit(
                origin_path=f"messages[{idx}].content",
                unit_type=f"prior_{prior.role}_message",
                candidate="conversation_history",
                direction="request",
                text=prior.content,
                timestamp=prior.timestamp,
                event_order=event_order,
                part_index=idx,
                label=f"历史 {prior.role} 消息",
                priority=50,
            ))

        for idx, segment in enumerate(_request_segments(msg.request_full), 1):
            parsed = _parse_tool_result_segment(segment)
            if parsed:
                tool_id, body = parsed
                units.append(text_unit(
                    origin_path=f"request_full.tool_result[{idx}]",
                    canonical_source_locator=f"tool_result:{tool_id or idx}",
                    unit_type="tool_result_text",
                    candidate="tool_results",
                    direction="request",
                    text=body,
                    timestamp=timestamp,
                    event_order=event_order,
                    part_index=idx,
                    label=f"工具结果 {tool_id or idx}",
                    priority=85,
                ))
            elif segment and not _matches_current_user(segment, messages_before, current_user_index):
                units.append(text_unit(
                    origin_path=f"request_full.fragment[{idx}]",
                    unit_type="request_context_fragment",
                    candidate="conversation_history",
                    direction="request",
                    text=segment,
                    timestamp=timestamp,
                    event_order=event_order,
                    part_index=idx,
                    label="request 上下文片段",
                    priority=35,
                ))
        return units

    def _response_units_for_call(
        self,
        *,
        msg: ChatMessage,
        event_order: int,
    ) -> list[QoderSourceUnitDraft]:
        units: list[QoderSourceUnitDraft] = []
        blocks = msg.content_blocks or []
        for idx, block in enumerate(blocks, 1):
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "")
            if block_type == "text":
                content = str(block.get("content") or block.get("text") or "")
                if content:
                    units.append(text_unit(
                        origin_path=f"assistant.content_blocks[{idx}]",
                        unit_type="assistant_text",
                        candidate="assistant_output",
                        direction="response",
                        text=content,
                        timestamp=msg.timestamp,
                        event_order=event_order,
                        part_index=idx,
                        label="助手文本",
                    ))
            elif block_type == "thinking":
                content = str(block.get("content") or block.get("thinking") or "")
                units.append(text_unit(
                    origin_path=f"assistant.content_blocks[{idx}]",
                    unit_type="visible_thinking",
                    candidate="reasoning_output",
                    direction="response",
                    text=content,
                    timestamp=msg.timestamp,
                    event_order=event_order,
                    part_index=idx,
                    label="可见 thinking",
                ))
            elif block_type == "tool_use":
                units.append(payload_unit(
                    origin_path=f"assistant.content_blocks[{idx}]",
                    canonical_source_locator=f"tool_use:{block.get('id') or idx}",
                    unit_type="tool_use_block",
                    candidate="tool_calls",
                    direction="response",
                    payload=block,
                    timestamp=msg.timestamp,
                    event_order=event_order,
                    part_index=idx,
                    label=str(block.get("name") or "tool_use"),
                ))
            else:
                units.append(payload_unit(
                    origin_path=f"assistant.content_blocks[{idx}]",
                    unit_type=f"structured_{block_type or 'block'}",
                    candidate="structured_output",
                    direction="response",
                    payload=block,
                    timestamp=msg.timestamp,
                    event_order=event_order,
                    part_index=idx,
                    label="结构化输出",
                ))
        if not units and msg.content:
            units.append(text_unit(
                origin_path="assistant.content",
                unit_type="assistant_text",
                candidate="assistant_output",
                direction="response",
                text=msg.content,
                timestamp=msg.timestamp,
                event_order=event_order,
                label="助手文本",
            ))
        return units


def build_qoder_normalized_session(
    *,
    summary,
    messages,
    tool_calls,
    source_path: str,
    subagent_runs: list[SubagentRun] | None = None,
    parse_warnings: list[dict] | None = None,
) -> dict:
    """从已解析模型构造 Qoder normalized JSON。"""
    return QoderNormalizationAdapter().build(
        summary=summary,
        messages=messages,
        tool_calls=tool_calls,
        source_path=source_path,
        subagent_runs=subagent_runs or [],
        parse_warnings=parse_warnings or [],
    )


def parse_qoder_session_file(
    path: str | Path,
    *,
    project_key: str = "",
    session_id: str | None = None,
) -> dict:
    """把单个 Qoder JSONL 解析为 normalized JSON。"""
    from session_browser.normalized.agents.chat_jsonl import session_id_from_file
    from session_browser.sources.qoder_parts.parse import (
        _build_summary_from_events,
        _extract_messages,
        _extract_tool_calls,
        _parse_cache_session,
    )

    session_file = Path(path)
    sid = session_id or session_id_from_file(session_file)
    project = project_key or session_file.parent.name
    events, _ = parse_jsonl_events(session_file)
    if events and "type" not in events[0] and "role" in events[0]:
        for ev in events:
            if "role" in ev and "type" not in ev:
                ev["type"] = ev["role"]
    is_cache_format = all(
        not ev.get("timestamp") and not ev.get("cwd") and not ev.get("sessionId")
        for ev in events
    ) if events else False
    if is_cache_format:
        summary = _parse_cache_session(project, sid, session_file)
        messages = _extract_messages(events)
        tool_calls = []
    else:
        summary = _build_summary_from_events(events, sid, project)
        messages = _extract_messages(events)
        tool_calls = _extract_tool_calls(events, messages)
    return build_qoder_normalized_session(
        summary=summary,
        messages=messages,
        tool_calls=tool_calls,
        source_path=str(session_file),
        subagent_runs=[],
    )


def _project_instruction_units(summary: SessionSummary, source_path: str) -> list[QoderSourceUnitDraft]:
    units: list[QoderSourceUnitDraft] = []
    root = _project_root(summary, source_path)
    for rel, path in _qoder_instruction_paths(root):
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        candidate = "system_instructions" if _looks_like_instruction_file(rel, text) else "repo_context"
        units.append(text_unit(
            origin_path=str(path),
            canonical_source_locator=rel,
            unit_type="project_instruction_file",
            candidate=candidate,
            direction="request",
            text=text,
            timestamp="",
            event_order=0,
            label=rel,
            priority=75,
        ))
    return units


def _qoder_instruction_paths(root: Path | None) -> list[tuple[str, Path]]:
    base = root or Path(".")
    paths: list[tuple[str, Path]] = [
        ("AGENTS.md", base / "AGENTS.md"),
        ("CLAUDE.md", base / "CLAUDE.md"),
        (".qoder/rules.md", base / ".qoder" / "rules.md"),
    ]
    rules_dir = base / ".qoder" / "rules"
    if rules_dir.exists() and rules_dir.is_dir():
        for path in sorted(rules_dir.rglob("*")):
            if path.is_file():
                paths.append((str(path.relative_to(base)), path))
    return paths


def _clone_units_for_call(
    drafts: list[QoderSourceUnitDraft],
    *,
    event_order: int,
    timestamp: str,
) -> list[QoderSourceUnitDraft]:
    return [
        QoderSourceUnitDraft(
            origin_path=d.origin_path,
            canonical_source_locator=d.canonical_source_locator,
            unit_type=d.unit_type,
            candidate=d.candidate,
            direction=d.direction,
            event_order=event_order,
            part_index=d.part_index,
            byte_range=d.byte_range,
            text=d.text,
            payload=d.payload,
            timestamp=timestamp,
            label=d.label,
            priority=d.priority,
            sub_source=d.sub_source,
            source_candidate=d.source_candidate,
            diagnostics=list(d.diagnostics),
        )
        for d in drafts
    ]


def _session_payload(summary: SessionSummary) -> dict:
    return {
        "session_key": f"qoder:{summary.session_id}",
        "session_id": summary.session_id,
        "title": _truncate_text(summary.title, 160),
        "agent": "qoder",
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
        return {"fresh": fresh, "cache_read": cache_read, "cache_write": cache_write, "output": output, "total": fresh + cache_read + cache_write + output}
    fresh = _estimate_tokens(msg.request_full)
    output = _estimate_tokens(msg.content)
    return {
        "fresh": fresh,
        "cache_read": 0,
        "cache_write": 0,
        "output": output,
        "total": fresh + output,
        "usage_source": {"kind": "estimated", "method": "chars_div_4", "reason": "provider_usage_missing"},
    }


def _tools_for_message(msg: ChatMessage, tool_by_id: dict[str, ToolCall], round_id: int) -> list[dict]:
    tools: list[dict] = []
    for idx, raw in enumerate(msg.tool_calls or [], 1):
        tool_id = str(raw.get("id") or raw.get("tool_use_id") or f"{msg.llm_call_id}-tool-{idx}")
        tool = tool_by_id.get(tool_id)
        if tool is None:
            tool = ToolCall(name=str(raw.get("name") or "tool"), timestamp=msg.timestamp, tool_use_id=tool_id)
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


def _subagent_steps_for_tools(
    *,
    adapter: QoderNormalizationAdapter,
    summary: SessionSummary,
    source_path: str,
    round_id: int,
    tools: list[dict],
    subagent_by_parent: dict[str, SubagentRun],
) -> list[dict]:
    steps: list[dict] = []
    for tool in tools:
        parent_tool_id = tool.get("tool_call_id", "")
        run = subagent_by_parent.get(parent_tool_id)
        if not run:
            continue
        run_summary = run.get("summary") or {}
        sub_rounds = adapter._build_rounds(
            summary=summary,
            messages=run.get("messages") or [],
            tool_calls=run.get("tool_calls") or [],
            source_path=source_path,
            scope="subagent",
            subagent_id=run_summary.get("agent_id", ""),
            parent_tool_use_id=parent_tool_id,
            subagent_runs=[],
        )
        for sub_round in sub_rounds:
            sub_round["round_key"] = f"R{round_id}.{sub_round['round_id']}"
        tool["subagent_id"] = run_summary.get("agent_id", "")
        tool["subagent_summary"] = run_summary
        tool["sub_round_count"] = len(sub_rounds)
        steps.append({
            "type": "subagent_run",
            "step_id": f"R{round_id}-subagent-{run_summary.get('agent_id') or parent_tool_id}",
            "parent_tool_call_id": parent_tool_id,
            "subagent_id": run_summary.get("agent_id", ""),
            "subagent_type": run_summary.get("agent_type", ""),
            "description": run_summary.get("description", ""),
            "sub_rounds": sub_rounds,
        })
    return steps


def _steps_for_round(*, timestamp: str, tools: list[dict], subagent_steps: list[dict]) -> list[dict]:
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


def _subagent_runs_by_parent(tool_calls: list[ToolCall], subagent_runs: list[SubagentRun]) -> dict[str, SubagentRun]:
    by_id = {(run.get("summary") or {}).get("agent_id", ""): run for run in subagent_runs}
    result: dict[str, SubagentRun] = {}
    for tc in tool_calls:
        if tc.name != "Agent" or not tc.tool_use_id or not tc.subagent_id:
            continue
        run = by_id.get(tc.subagent_id)
        if run:
            result[tc.tool_use_id] = run
    return result


def _parent_tool_for_subagent(tool_calls: list[ToolCall], run: SubagentRun) -> str:
    agent_id = (run.get("summary") or {}).get("agent_id", "")
    for tc in tool_calls:
        if tc.subagent_id == agent_id:
            return tc.tool_use_id
    return ""


def _tool_result_ids_from_request(request_text: str) -> list[str]:
    ids: list[str] = []
    for segment in _request_segments(request_text):
        parsed = _parse_tool_result_segment(segment)
        if parsed and parsed[0]:
            ids.append(parsed[0])
    return ids


def _tool_call_ids_from_message(msg: ChatMessage, tools: list[dict]) -> list[str]:
    ids: list[str] = []
    for block in msg.content_blocks or []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
            ids.append(str(block["id"]))
    known = set(ids)
    for tool in tools:
        tid = tool.get("tool_call_id", "")
        if tid and tid not in known:
            ids.append(str(tid))
    return ids


def _request_segments(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n{2,}", text or "") if part.strip()]


def _parse_tool_result_segment(segment: str) -> tuple[str, str] | None:
    match = re.match(r"^Tool result for ([^:\n]+):\n?(?P<body>.*)$", segment, re.DOTALL)
    if not match:
        return None
    return str(match.group(1) or ""), str(match.group("body") or "").strip()


def _current_user_index_for_call(messages: list[ChatMessage]) -> int:
    last_assistant = -1
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].role == "assistant":
            last_assistant = idx
            break
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].role == "user" and idx > last_assistant:
            return idx
    return -1


def _matches_current_user(segment: str, messages: list[ChatMessage], index: int) -> bool:
    if index < 0:
        return False
    return _normalize_ws(segment) == _normalize_ws(messages[index].content)


def _project_root(summary: SessionSummary, source_path: str) -> Path | None:
    for candidate in (summary.cwd, summary.project_key, str(Path(source_path).parent if source_path else "")):
        if not candidate:
            continue
        try:
            path = Path(candidate)
            if path.exists() and path.is_dir():
                return path
        except OSError:
            continue
    return None


def _looks_like_instruction_file(rel: str, text: str) -> bool:
    rel_lower = rel.lower()
    sample = text[:2000].lower()
    return any(name in rel_lower for name in ("agents.md", "claude.md", "rules")) or any(word in sample for word in ("instruction", "规则", "system", "agent"))


def _truncate_text(text: str, limit: int) -> str:
    value = str(text or "")
    return value if len(value) <= limit else value[:limit]


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


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
