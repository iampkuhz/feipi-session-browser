"""Claude Code JSONL to normalized session JSON."""

from __future__ import annotations

from pathlib import Path

from session_browser.normalized.agents.chat_jsonl import (
    build_chat_jsonl_normalized_session,
    jsonl_diag_to_dict,
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
    jsonl_diagnostics: dict | None = None,
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
        jsonl_diagnostics=jsonl_diagnostics or {},
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

    events, jsonl_diag = parse_jsonl_events(session_file)
    subagent_runs = _parse_subagent_runs(session_file)
    summary = _build_summary_from_events(events, sid, project, subagent_runs)
    messages = _extract_messages(events)
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
        jsonl_diagnostics=jsonl_diag_to_dict(jsonl_diag),
    )
