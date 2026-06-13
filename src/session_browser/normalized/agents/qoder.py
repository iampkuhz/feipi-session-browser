"""Qoder JSONL to normalized session JSON."""

from __future__ import annotations

from pathlib import Path

from session_browser.normalized.agents.chat_jsonl import (
    build_chat_jsonl_normalized_session,
    session_id_from_file,
)
from session_browser.sources.jsonl_reader import parse_jsonl_events
from session_browser.sources.qoder_parts.parse import (
    _build_summary_from_events,
    _extract_messages,
    _extract_tool_calls,
    _parse_cache_session,
)


def build_qoder_normalized_session(
    *,
    summary,
    messages,
    tool_calls,
    source_path: str,
    subagent_runs: list[dict] | None = None,
) -> dict:
    """Build normalized Qoder JSON from already parsed session models."""
    return build_chat_jsonl_normalized_session(
        agent="qoder",
        summary=summary,
        messages=messages,
        tool_calls=tool_calls,
        source_path=source_path,
        source_role="main_session",
        subagent_runs=subagent_runs or [],
    )


def parse_qoder_session_file(
    path: str | Path,
    *,
    project_key: str = "",
    session_id: str | None = None,
) -> dict:
    """Parse one Qoder session JSONL into the normalized contract."""
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
