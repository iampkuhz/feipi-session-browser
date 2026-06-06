"""Session parsing for Qoder sessions.

Contains parse_session_detail, _build_summary_from_events, _extract_messages,
_fill_estimates, _extract_tool_calls, _parse_cache_session, and supporting
helpers. Also exports scan_all_sessions for indexer use.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from session_browser.config import QODER_DATA_DIR
from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall
from session_browser.sources.jsonl_reader import parse_jsonl_events

from session_browser.sources.qoder_parts.utils import (
    _merge_intervals,
    _count_tokens,
    normalize_timestamp,
    _ts_ms_to_iso,
    _assistant_message_key,
    _extract_qoder_model,
    _assistant_records,
    _extract_user_text,
    _extract_readable_title,
    _stringify_tool_result,
    _tool_result_looks_failed,
    _extract_event_text,
    _estimate_tokens_from_events,
)
from session_browser.sources.qoder_parts.model_config import (
    _infer_qoder_model_for_session,
)
from session_browser.sources.qoder_parts.discovery import (
    _discover_sessions,
    _discover_cache_sessions,
    _build_canonical_id_map,
)


def parse_session_detail(
    project_key: str,
    session_id: str,
    session_file: Path | None = None,
    verbose: bool = False,
) -> tuple[SessionSummary, list[ChatMessage], list[ToolCall], list[dict]]:
    """Parse a single Qoder session's full event stream.

    Args:
        project_key: The project path segment.
        session_id: The session ID.
        session_file: Optional pre-located file path.
        verbose: If True, print diagnostic info about skipped JSON lines.

    Returns (SessionSummary, chat_messages, tool_calls, subagent_runs).
    """
    from session_browser.index.diagnostics import (
        ParseDiagnostics,
        ParseIssue,
        ParseIssueItem,
        ParseSeverity,
        build_parse_diagnostics,
    )

    if session_file is None:
        session_file = _find_session_file(project_key, session_id)
        if session_file is None:
            s = _empty_session(session_id, project_key)
            s.parse_diagnostics = ParseDiagnostics(
                session_key=s.session_key,
                issues=[ParseIssueItem(
                    issue=ParseIssue.FILE_NOT_FOUND,
                    severity=ParseSeverity.WARNING,
                    message=f"Session file not found",
                )],
            ).to_dict()
            return s, [], [], []

    events, jsonl_diag = parse_jsonl_events(session_file, verbose=verbose)

    # Normalize cache-format events: cache uses "role" instead of "type".
    # Convert so the rest of the pipeline can process them uniformly.
    if events and "type" not in events[0] and "role" in events[0]:
        for ev in events:
            if "role" in ev and "type" not in ev:
                ev["type"] = ev["role"]

    # Detect cache format: no timestamps, no structured events. Use simpler pipeline.
    is_cache_format = all(
        not ev.get("timestamp") and not ev.get("cwd") and not ev.get("sessionId")
        for ev in events
    ) if events else False

    if is_cache_format:
        # Cache format: build summary via _parse_cache_session, then extract messages
        summary = _parse_cache_session(project_key, session_id, session_file)
        messages = _extract_messages(events)
        tool_calls = []
        subagent_runs = []
    else:
        summary = _build_summary_from_events(events, session_id, project_key)
        messages = _extract_messages(events)
        tool_calls = _extract_tool_calls(events, messages)
        subagent_runs = []

    # Attach parse diagnostics from JSONL reader
    parse_diag = build_parse_diagnostics(
        session_key=summary.session_key,
        file_path=str(session_file),
        jsonl_diag=jsonl_diag,
    )
    summary.parse_diagnostics = parse_diag.to_dict()

    return summary, messages, tool_calls, subagent_runs


def _find_session_file(project_key: str, session_id: str) -> Path | None:
    """Search for a Qoder session file under projects/ and cache/projects/.

    Search order:
    1. Resolve short ID alias -> full UUID via canonical map, then search projects/.
    2. Search projects/ (CLI sessions) by session_id.
    3. Fall back to cache/projects/ (GUI sessions) -- recursive walk.

    Mirrors _locate_qoder_session_file in indexer.py.
    """
    uuid_pattern = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )

    # Step 1: resolve short ID alias -> full UUID, then try projects/ direct
    if not uuid_pattern.match(session_id):
        canonical_map = _build_canonical_id_map()
        resolved_id = canonical_map.get(session_id.lower(), session_id)
        if resolved_id != session_id.lower():
            # Short ID resolved to full UUID -- try projects/ direct match
            projects_dir = QODER_DATA_DIR / "projects"
            if projects_dir.exists():
                candidate = projects_dir / project_key / f"{resolved_id}.jsonl"
                if candidate.exists():
                    return candidate

    # Step 2: search projects/ by original session_id
    projects_dir = QODER_DATA_DIR / "projects"
    if projects_dir.exists():
        candidate = projects_dir / project_key / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate

    # Step 3: fall back to cache/projects/
    cache_dir = QODER_DATA_DIR / "cache" / "projects"
    if cache_dir.exists():
        for root, _dirs, files in os.walk(cache_dir):
            if f"{session_id}.jsonl" in files:
                return Path(root) / f"{session_id}.jsonl"

    return None


def _empty_session(session_id: str, project_key: str) -> SessionSummary:
    """Create an empty session summary as fallback."""
    from pathlib import PurePosixPath
    project_name = PurePosixPath(project_key).name if project_key else "unknown"
    now = datetime.now(tz=timezone.utc).astimezone().isoformat()
    return SessionSummary(
        agent="qoder",
        session_id=session_id,
        title="",
        project_key=project_key,
        project_name=project_name,
        cwd="",
        started_at=now,
        ended_at=now,
    )


def _build_summary_from_events(
    events: list[dict],
    session_id: str,
    project_key: str,
) -> SessionSummary:
    """Build SessionSummary from parsed Qoder events.

    Computes timeline-based execution times:
    - model_execution_seconds: merged LLM response intervals (user msg -> assistant msg)
    - tool_execution_seconds: merged tool intervals (tool_use -> tool_result),
      with parallel overlaps merged
    """
    from pathlib import PurePosixPath

    user_count = 0
    failed_tool_count = 0
    model = ""
    cwd = ""
    git_branch = ""
    source = "qoder"
    first_ts = 0
    last_ts = 0
    title = ""
    assistant_records_list = _assistant_records(events)
    assistant_count = len(assistant_records_list)
    tool_ids = set()
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    cache_write_tokens = 0

    for rec in assistant_records_list:
        usage = rec.get("usage", {})
        if isinstance(usage, dict):
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            cached_tokens += usage.get("cache_read_input_tokens", 0)
            cache_write_tokens += usage.get("cache_creation_input_tokens", 0)
        for tc in rec.get("tool_calls", []):
            tool_id = tc.get("id") or f"{rec.get('id')}:{tc.get('name')}:{len(tool_ids)}"
            tool_ids.add(tool_id)
        extracted_model = _extract_qoder_model(rec)
        if not model and extracted_model:
            model = extracted_model

    if not model:
        model = _infer_qoder_model_for_session(session_id)

    # Fallback: Qoder may not report usage -- estimate from event text.
    # Use per-message estimates to ensure session summary matches LLM Calls detail.
    est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
    if has_estimated and input_tokens == 0 and output_tokens == 0:
        input_tokens = est_input
        output_tokens = est_output
        # Qoder has no cache metrics; do not fabricate cache values.
        cached_tokens = 0
        cache_write_tokens = 0

    # --- Collect timestamps for interval calculation ---
    user_event_timestamps: list[int] = []
    assistant_event_timestamps: list[int] = []
    tool_use_map: dict[str, int] = {}       # tool_use_id -> start_ts_ms
    tool_result_map: dict[str, int] = {}    # tool_use_id -> end_ts_ms

    for ev in events:
        etype = ev.get("type", "")
        ts_str = ev.get("timestamp", "")
        ts_ms = 0
        if ts_str:
            dt_local = normalize_timestamp(ts_str)
            if dt_local:
                ts_ms = int(datetime.fromisoformat(dt_local).timestamp() * 1000)

        if etype == "user":
            user_text = _extract_user_text(ev)
            if user_text:
                user_count += 1
            if ts_ms and not first_ts:
                first_ts = ts_ms
            # Extract title from first non-meta user message
            if not title and user_text:
                title = _extract_readable_title(user_text)
            if not cwd:
                cwd = ev.get("cwd", "")
            if not git_branch:
                git_branch = ev.get("gitBranch", "")

            # Check for failed tool results in user events (tool results come as user type)
            content = ev.get("message", {}).get("content", "") if isinstance(ev.get("message"), dict) else ""
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        if item.get("is_error") is True or _tool_result_looks_failed(item.get("content", "")):
                            failed_tool_count += 1
                        tuid = item.get("tool_use_id", "")
                        if tuid and ts_ms:
                            tool_result_map[tuid] = ts_ms
            if ts_ms:
                user_event_timestamps.append(ts_ms)

        elif etype == "assistant" and isinstance(ev.get("message"), dict):
            if ts_ms:
                assistant_event_timestamps.append(ts_ms)
            msg = ev.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        if ts_ms:
                            tool_use_map[item["id"]] = ts_ms

        if ts_ms:
            last_ts = ts_ms

    if not last_ts and first_ts:
        last_ts = first_ts

    duration = 0
    if first_ts and last_ts:
        duration = (last_ts - first_ts) / 1000

    # --- Model execution: LLM response intervals (user -> next assistant) ---
    llm_intervals: list[tuple[int, int]] = []
    sorted_user_ts = sorted(user_event_timestamps)
    sorted_assistant_ts = sorted(assistant_event_timestamps)
    for u_ts in sorted_user_ts:
        for a_ts in sorted_assistant_ts:
            if a_ts > u_ts:
                llm_intervals.append((u_ts, a_ts))
                break

    # --- Tool execution: tool_use -> tool_result intervals ---
    tool_intervals: list[tuple[int, int]] = []
    for tool_id, use_ts in tool_use_map.items():
        if tool_id in tool_result_map:
            tool_intervals.append((use_ts, tool_result_map[tool_id]))

    model_execution_seconds = _merge_intervals(llm_intervals) / 1000.0
    tool_execution_seconds = _merge_intervals(tool_intervals) / 1000.0

    # Use cwd from events as the primary project_key -- it holds the actual
    # filesystem path. Fall back to the directory-based project_key (URL-decoded).
    # Guard against cwd being "." or a relative path that would produce a
    # meaningless project_key / project_name.
    actual_project = cwd if (cwd and cwd != "." and not cwd.startswith("./")) else project_key
    project_name = PurePosixPath(actual_project).name if actual_project else "unknown"

    # Unified 5-field breakdown: Qoder input_tokens is often inclusive total
    # fresh = input_tokens - cache_read - cache_write (when input >= cache_read + cache_write)
    if input_tokens >= cached_tokens + cache_write_tokens:
        fresh_input_tokens = input_tokens - cached_tokens - cache_write_tokens
    else:
        fresh_input_tokens = input_tokens
    cache_read_tokens_session = cached_tokens
    cache_write_tokens_session = cache_write_tokens
    total_tokens = fresh_input_tokens + cache_read_tokens_session + cache_write_tokens_session + output_tokens

    # Use cwd from events as the primary project_key -- it holds the actual
    # filesystem path. Fall back to the directory-based project_key (URL-decoded).
    # Guard against cwd being "." or a relative path that would produce a
    # meaningless project_key / project_name.
    actual_project = cwd if (cwd and cwd != "." and not cwd.startswith("./")) else project_key
    project_name = PurePosixPath(actual_project).name if actual_project else "unknown"

    return SessionSummary(
        agent="qoder",
        session_id=session_id,
        title=title,
        project_key=actual_project,
        project_name=project_name,
        cwd=cwd,
        started_at=_ts_ms_to_iso(first_ts) if first_ts else "",
        ended_at=_ts_ms_to_iso(last_ts) if last_ts else "",
        duration_seconds=round(duration, 1),
        model_execution_seconds=round(model_execution_seconds, 1),
        tool_execution_seconds=round(tool_execution_seconds, 1),
        model=model,
        git_branch=git_branch,
        source=source,
        user_message_count=user_count,
        assistant_message_count=assistant_count,
        tool_call_count=len(tool_ids),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_tokens,
        cached_output_tokens=cache_write_tokens,
        fresh_input_tokens=fresh_input_tokens,
        cache_read_tokens=cache_read_tokens_session,
        cache_write_tokens=cache_write_tokens_session,
        total_tokens=total_tokens,
        failed_tool_count=failed_tool_count,
    )


def _extract_messages(events: list[dict]) -> list[ChatMessage]:
    """Extract user and assistant chat messages from Qoder events.

    When Qoder does not report real usage, per-message token counts are
    estimated by walking events in order and accumulating visible context.

    Tracks pending request parts (human text + tool_result text) between
    user events and writes them to the next assistant message's request_full.
    """
    messages = []
    assistant_by_id = {rec["id"]: rec for rec in _assistant_records(events)}
    emitted_assistant_ids: set[str] = set()

    # Pre-pass: check if real usage exists; if not, compute per-message estimates
    has_real_usage = False
    for rec in assistant_by_id.values():
        if rec.get("usage") and rec["usage"].get("input_tokens"):
            has_real_usage = True
            break

    est_input_map: dict[str, int] = {}
    est_output_map: dict[str, int] = {}
    if not has_real_usage:
        _fill_estimates(events, assistant_by_id, est_input_map, est_output_map)

    # Collect pending request context between user events and the next
    # assistant message.
    pending_request_parts: list[str] = []

    for ev in events:
        etype = ev.get("type", "")

        if etype == "user":
            content = _extract_user_text(ev)
            ts_str = ev.get("timestamp", "")

            # Collect tool_result text for request context
            msg = ev.get("message", {})
            if isinstance(msg, dict) and isinstance(msg.get("content"), list):
                for item in msg["content"]:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        tuid = item.get("tool_use_id", "")
                        result_text = _stringify_tool_result(item.get("content", ""))
                        part = f"Tool result for {tuid}:\n{result_text}" if tuid else result_text
                        if item.get("is_error") is True:
                            part += "\nTool result error: true"
                        if part:
                            pending_request_parts.append(part)

            if content:
                pending_request_parts.append(content)

            if not content:
                continue
            messages.append(ChatMessage(
                role="user",
                content=content,
                timestamp=normalize_timestamp(ts_str),
            ))

        elif etype == "assistant":
            key = _assistant_message_key(ev)
            if key in emitted_assistant_ids:
                continue
            emitted_assistant_ids.add(key)
            rec = assistant_by_id.get(key, {})
            text_parts = rec.get("text_parts", [])
            tool_calls = rec.get("tool_calls", [])
            usage = rec.get("usage", {})
            model = rec.get("model", "")
            if text_parts or tool_calls:
                # Use real usage if present, otherwise fall back to estimates
                if usage and usage.get("input_tokens"):
                    final_usage = usage
                elif not has_real_usage and key in est_input_map:
                    final_usage = {
                        "input_tokens": est_input_map[key],
                        "output_tokens": est_output_map.get(key, 0),
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "estimated": True,
                        "estimation_method": "qoder-fast-bytes-v1",
                    }
                else:
                    final_usage = None

                request_full = "\n\n".join(p for p in pending_request_parts if p)
                pending_request_parts = []

                # For tool-only responses, include a summary so response_full is not empty
                content_text = "\n".join(text_parts)
                if not content_text and tool_calls:
                    content_text = "\n".join(
                        f"[tool_use: {tc.get('name', 'unknown')}] {json.dumps(tc.get('parameters', {}), ensure_ascii=False)[:200]}"
                        for tc in tool_calls
                    )

                messages.append(ChatMessage(
                    role="assistant",
                    content=content_text,
                    timestamp=normalize_timestamp(rec.get("timestamp", "")),
                    model=model,
                    tool_calls=tool_calls,
                    usage=final_usage,
                    llm_call_id=rec.get("id", ""),
                    request_full=request_full,
                    stop_reason=rec.get("stop_reason", ""),
                ))

    return messages


def _fill_estimates(
    events: list[dict],
    assistant_by_id: dict,
    est_input_map: dict,
    est_output_map: dict,
) -> None:
    """Walk events and populate est_input_map / est_output_map by message key.

    Each assistant output's estimated input = current visible-context tokens;
    estimated output = accumulated text/tool tokens across all fragments of
    the same message id.
    """
    visible_context = 0
    for ev in events:
        cat, text = _extract_event_text(ev)
        if not cat:
            continue

        tok = _count_tokens(text)

        if cat.startswith("assistant"):
            key = _assistant_message_key(ev)
            # Only set input on first encounter; accumulate output across fragments
            if key not in est_input_map:
                est_input_map[key] = visible_context
                est_output_map[key] = tok
            else:
                est_output_map[key] = est_output_map.get(key, 0) + tok

        visible_context += tok


def _extract_tool_calls(
    events: list[dict],
    messages: list[ChatMessage],
) -> list[ToolCall]:
    """Extract tool call records from assistant messages.

    Also populates ToolCall.duration_ms from tool_use/tool_result timestamps.
    """
    tool_calls = []

    # Build a map of tool_use_id -> tool_result for status/result display
    # and tool_use_id -> result timestamp for duration_ms calculation
    tool_results: dict[str, dict] = {}
    tool_result_timestamps: dict[str, int] = {}  # tool_use_id -> end_ts_ms
    for ev in events:
        if ev.get("type") != "user":
            continue
        msg = ev.get("message", {})
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    tool_use_id = item.get("tool_use_id", "")
                    result_content = item.get("content", "")

                    is_error = item.get("is_error") is True
                    result_text = _stringify_tool_result(result_content)

                    exit_code = None
                    exit_match = re.search(r"exit code[:\s]*(\d+)", result_text, re.IGNORECASE)
                    if exit_match:
                        exit_code = int(exit_match.group(1))

                    # Store raw result content; apply heuristic later when we
                    # know the tool name from assistant messages.
                    tool_results[tool_use_id] = {
                        "is_error_raw": is_error,
                        "result_text": result_text,
                        "exit_code_raw": exit_code,
                    }

                    # Capture result timestamp for duration_ms
                    ts_str = ev.get("timestamp", "")
                    if ts_str and tool_use_id:
                        dt_local = normalize_timestamp(ts_str)
                        if dt_local:
                            tool_result_timestamps[tool_use_id] = int(
                                datetime.fromisoformat(dt_local).timestamp() * 1000
                            )

    # Extract tool calls from assistant messages
    for msg in messages:
        if msg.role != "assistant":
            continue
        for tc in msg.tool_calls:
            tool_use_id = tc.get("id", "")
            name = tc.get("name", "")
            params = tc.get("parameters", {})

            result_info = tool_results.get(tool_use_id, {})
            is_error = result_info.get("is_error_raw", False)
            result_text = result_info.get("result_text", "")

            # Apply heuristic now that we know the tool name
            if _tool_result_looks_failed(result_text, tool_name=name):
                is_error = True

            exit_code = result_info.get("exit_code_raw")

            status = "error" if is_error else "completed"
            error_msg = result_text[:500] if is_error else ""
            result = result_text
            files_touched = []

            file_path = (
                params.get("file_path", "")
                or params.get("path", "")
            )
            if file_path:
                files_touched.append(file_path)

            # Compute duration_ms from tool_use timestamp (from msg) and
            # tool_result timestamp (captured above)
            duration_ms = 0.0
            if tool_use_id and tool_use_id in tool_result_timestamps:
                ts_str = msg.timestamp
                if ts_str:
                    dt_local = normalize_timestamp(ts_str)
                    if dt_local:
                        use_ts_ms = int(datetime.fromisoformat(dt_local).timestamp() * 1000)
                        result_ts_ms = tool_result_timestamps[tool_use_id]
                        if result_ts_ms >= use_ts_ms:
                            duration_ms = float(result_ts_ms - use_ts_ms)

            tool_calls.append(ToolCall(
                name=name,
                parameters=params,
                result=result,
                status=status,
                exit_code=exit_code,
                error_message=error_msg,
                files_touched=files_touched,
                timestamp=msg.timestamp,
                tool_use_id=tool_use_id,
                duration_ms=duration_ms,
            ))

    return tool_calls


def _parse_cache_session(
    project_key: str,
    session_id: str,
    session_file: Path,
    file_mtime: float = 0,
) -> SessionSummary:
    """Parse a cache-format JSONL session into a minimal SessionSummary.

    Cache format uses {"role": "user|assistant", "message": {"content": [...]}}
    with no timestamps, tool calls, or usage data. Returns best-effort summary.
    When events lack timestamps, uses file_mtime for started_at/ended_at.
    """
    events, _ = parse_jsonl_events(session_file)

    # Extract user text for title
    user_texts = []
    for ev in events:
        if ev.get("role") == "user":
            msg = ev.get("message", {})
            content = msg.get("content", "")
            if isinstance(content, str):
                user_texts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        user_texts.append(item.get("text", ""))

    # Estimate tokens
    input_tokens = 0
    output_tokens = 0
    user_count = 0
    assistant_count = 0
    for ev in events:
        role = ev.get("role", "")
        msg = ev.get("message", {})
        content = msg.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        if not text:
            continue
        tok = _count_tokens(text)
        if role == "user":
            user_count += 1
            input_tokens += tok
        elif role == "assistant":
            assistant_count += 1
            output_tokens += tok

    title = _extract_readable_title(user_texts[0]) if user_texts else ""
    model = _infer_qoder_model_for_session(session_id)

    # When cache-format events lack timestamps, derive from file mtime.
    if file_mtime > 0:
        fallback_ts = datetime.fromtimestamp(file_mtime, tz=timezone.utc).astimezone().isoformat()
    else:
        fallback_ts = datetime.now(tz=timezone.utc).astimezone().isoformat()

    return SessionSummary(
        agent="qoder",
        session_id=session_id,
        title=title,
        project_key=project_key,
        project_name=project_key if project_key else "unknown",
        cwd="",
        started_at=fallback_ts,
        ended_at=fallback_ts,
        duration_seconds=0,
        model_execution_seconds=0,
        tool_execution_seconds=0,
        model=model,
        git_branch="",
        source="qoder",
        user_message_count=user_count,
        assistant_message_count=assistant_count,
        tool_call_count=0,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=0,
        cached_output_tokens=0,
        fresh_input_tokens=input_tokens,
        cache_read_tokens=0,
        cache_write_tokens=0,
        total_tokens=input_tokens + output_tokens,
        failed_tool_count=0,
    )


def scan_all_sessions(verbose: bool = False) -> Iterator[SessionSummary]:
    """Scan all Qoder sessions and yield SessionSummary for each.

    Walks ~/.qoder/projects/ (CLI sessions) and ~/.qoder/cache/projects/
    (GUI sessions) to discover session files, then parses each.
    """
    discovered = _discover_sessions()

    for project_key, session_id, fpath in discovered:
        summary, _msgs, _tcs, _sa = parse_session_detail(
            project_key, session_id, session_file=fpath, verbose=verbose
        )
        yield summary

    # Scan cache (GUI) sessions -- canonicalize short IDs to full UUIDs
    cache_sessions = _discover_cache_sessions()
    canonical_map = _build_canonical_id_map()
    # Collect all projects/ session IDs to detect full overlap
    projects_ids = {sid.lower() for _pk, sid, _fp in _discover_sessions()}
    for project_key, session_id, fpath in cache_sessions:
        canonical_id = canonical_map.get(session_id.lower(), session_id)
        # Skip cache sessions that resolve to a projects/ session already yielded
        if canonical_id != session_id.lower() and canonical_id in projects_ids:
            continue
        file_mtime = os.path.getmtime(fpath) if fpath.exists() else 0
        summary = _parse_cache_session(project_key, canonical_id, fpath, file_mtime=file_mtime)
        yield summary
