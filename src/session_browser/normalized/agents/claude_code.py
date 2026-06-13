"""Claude Code JSONL to normalized session JSON."""

from __future__ import annotations

from pathlib import Path

from session_browser.domain.models import ChatMessage
from session_browser.normalized.agents.chat_jsonl import (
    build_chat_jsonl_normalized_session,
    session_id_from_file,
)
from session_browser.sources.claude import (
    _apply_subagent_totals,
    _attach_subagents_to_agent_tools,
    _build_summary_from_events,
    _extract_messages,
    _extract_tool_calls,
    _flatten_subagent_tool_calls,
    _parse_subagent_runs,
)
from session_browser.sources.jsonl_reader import parse_jsonl_events


def build_claude_code_normalized_session(
    *,
    summary,
    messages,
    tool_calls,
    source_path: str,
    subagent_runs: list[dict] | None = None,
    parse_warnings: list[dict] | None = None,
) -> dict:
    """Build normalized Claude Code JSON from already parsed session models."""
    return build_chat_jsonl_normalized_session(
        agent="claude_code",
        summary=summary,
        messages=messages,
        tool_calls=tool_calls,
        source_path=source_path,
        source_role="main_session",
        subagent_runs=subagent_runs or [],
        parse_warnings=parse_warnings or [],
    )


def parse_claude_code_session_file(
    path: str | Path,
    *,
    project_key: str = "",
    session_id: str | None = None,
) -> dict:
    """Parse one Claude Code session JSONL into the normalized contract."""
    session_file = Path(path)
    sid = session_id or session_id_from_file(session_file)
    project = project_key or session_file.parent.name

    events, _ = parse_jsonl_events(session_file)
    subagent_runs = _parse_subagent_runs(session_file)
    summary = _build_summary_from_events(events, sid, project, subagent_runs)
    messages = _extract_messages(events)
    messages, parse_warnings = _with_away_summary_messages(events, messages)
    tool_calls = _extract_tool_calls(events, messages)
    _attach_subagents_to_agent_tools(tool_calls, subagent_runs)
    tool_calls.extend(_flatten_subagent_tool_calls(subagent_runs))
    _apply_subagent_totals(summary, subagent_runs, tool_calls)

    return build_claude_code_normalized_session(
        summary=summary,
        messages=messages,
        tool_calls=tool_calls,
        source_path=str(session_file),
        subagent_runs=subagent_runs,
        parse_warnings=parse_warnings,
    )


def _with_away_summary_messages(
    events: list[dict],
    messages: list[ChatMessage],
) -> tuple[list[ChatMessage], list[dict]]:
    """Add Claude Code recap calls that are persisted as system events only."""
    existing_ids = {msg.llm_call_id for msg in messages if msg.llm_call_id}
    last_prompts_by_leaf = _last_prompts_by_leaf_uuid(events)
    result = list(messages)
    warnings: list[dict] = []
    fallback_model = _last_assistant_model(messages)

    for record_index, ev in enumerate(events, 1):
        if ev.get("type") != "system" or ev.get("subtype") != "away_summary":
            continue
        content = str(ev.get("content") or "")
        if not content:
            continue
        call_id = str(ev.get("uuid") or f"away-summary-{len(result) + 1}")
        if last_prompts_by_leaf and call_id not in last_prompts_by_leaf:
            continue
        if call_id in existing_ids:
            continue

        last_prompt = last_prompts_by_leaf.get(call_id, "")
        result.append(ChatMessage(
            role="assistant",
            content=content,
            timestamp=str(ev.get("timestamp") or ""),
            model=fallback_model,
            usage=None,
            llm_call_id=call_id,
            request_full=last_prompt,
            stop_reason="away_summary",
        ))
        warnings.append({
            "kind": "away_summary_usage_estimated",
            "message": "Claude Code away_summary indicates a recap LLM call, but local JSONL does not persist provider usage for that call; usage is estimated from lastPrompt and summary text.",
            "record_index": record_index,
            "call_id": call_id,
        })
        existing_ids.add(call_id)

    return result, warnings


def _last_prompts_by_leaf_uuid(events: list[dict]) -> dict[str, str]:
    return {
        str(ev.get("leafUuid") or ""): str(ev.get("lastPrompt") or "")
        for ev in events
        if ev.get("type") == "last-prompt" and ev.get("leafUuid")
    }


def _last_assistant_model(messages: list[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "assistant" and msg.model:
            return msg.model
    return ""
