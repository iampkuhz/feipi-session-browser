"""Qoder session 解析逻辑。

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
from session_browser.domain.models import ChatMessage, SessionSummary, SubagentRun, ToolCall
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
) -> tuple[SessionSummary, list[ChatMessage], list[ToolCall], list[SubagentRun]]:
    """解析 一个 single Qoder session's full event stream.

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

    # 归一化 cache-format events: cache uses "role" instead of "type".
    # 转换 so 该 rest of 该 pipeline can process them uniformly.
    if events and "type" not in events[0] and "role" in events[0]:
        for ev in events:
            if "role" in ev and "type" not in ev:
                ev["type"] = ev["role"]

    # 说明：Detect cache format: no timestamps, no structured events. Use simpler pipeline.
    is_cache_format = all(
        not ev.get("timestamp") and not ev.get("cwd") and not ev.get("sessionId")
        for ev in events
    ) if events else False

    if is_cache_format:
        # 说明：Cache format: build summary via _parse_cache_session, then extract messages
        file_mtime = os.path.getmtime(session_file) if session_file.exists() else 0
        summary = _parse_cache_session(
            project_key,
            session_id,
            session_file,
            file_mtime=file_mtime,
            events=events,
        )
        messages = _extract_messages(events)
        tool_calls = []
        subagent_runs = []
    else:
        summary = _build_summary_from_events(events, session_id, project_key)
        messages = _extract_messages(events)
        tool_calls = _extract_tool_calls(events, messages)
        subagent_runs = []

    # 附加 parse diagnostics，来源于 JSONL reader
    parse_diag = build_parse_diagnostics(
        session_key=summary.session_key,
        file_path=str(session_file),
        jsonl_diag=jsonl_diag,
    )
    summary.file_path = str(session_file)
    summary.parse_diagnostics = parse_diag.to_dict()

    return summary, messages, tool_calls, subagent_runs


def parse_session_detail_normalized(
    project_key: str,
    session_id: str,
    session_file: Path | None = None,
) -> dict:
    """解析 一个 Qoder session，转换为 该 normalized intermediate contract."""
    from session_browser.normalized.agents.qoder_normalization import parse_qoder_session_file

    target_file = session_file or _find_session_file(project_key, session_id)
    if target_file is None:
        raise FileNotFoundError(f"Qoder session file not found for session {session_id}")
    return parse_qoder_session_file(
        target_file,
        project_key=project_key,
        session_id=session_id,
    )


def parse_normalized_session_file(
    session_file: str | Path,
    project_key: str = "",
    session_id: str | None = None,
) -> dict:
    """解析 一个 Qoder JSONL file directly，转换为 normalized JSON."""
    from session_browser.normalized.agents.qoder_normalization import parse_qoder_session_file

    return parse_qoder_session_file(
        session_file,
        project_key=project_key,
        session_id=session_id,
    )


def build_normalized_session(
    *,
    summary: SessionSummary,
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    subagent_runs: list[SubagentRun],
    source_path: str,
) -> dict:
    """构建 normalized JSON，来源于 该 models already parsed，用于 indexing."""
    from session_browser.normalized.agents.qoder_normalization import build_qoder_normalized_session

    return build_qoder_normalized_session(
        summary=summary,
        messages=messages,
        tool_calls=tool_calls,
        source_path=source_path,
        subagent_runs=subagent_runs,
    )


def _find_session_file(project_key: str, session_id: str) -> Path | None:
    """搜索，用于 一个 Qoder session file under projects/ 和 cache/projects/.

    Search order:
    1. Resolve short ID alias -> full UUID via canonical map, then search projects/.
    2. Search projects/ (CLI sessions) by session_id.
    3. Fall back to cache/projects/ (GUI sessions) -- recursive walk.

    Mirrors _locate_qoder_session_file in indexer.py.
    """
    uuid_pattern = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )

    # 说明：Step 1: resolve short ID alias -> full UUID, then try projects/ direct
    if not uuid_pattern.match(session_id):
        canonical_map = _build_canonical_id_map()
        resolved_id = canonical_map.get(session_id.lower(), session_id)
        if resolved_id != session_id.lower():
            # 说明：Short ID resolved to full UUID -- try projects/ direct match
            projects_dir = QODER_DATA_DIR / "projects"
            if projects_dir.exists():
                candidate = projects_dir / project_key / f"{resolved_id}.jsonl"
                if candidate.exists():
                    return candidate

    # 说明：Step 2: search projects/ by original session_id
    projects_dir = QODER_DATA_DIR / "projects"
    if projects_dir.exists():
        candidate = projects_dir / project_key / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate

    # 说明：Step 3: fall back to cache/projects/
    cache_dir = QODER_DATA_DIR / "cache" / "projects"
    if cache_dir.exists():
        for root, _dirs, files in os.walk(cache_dir):
            if f"{session_id}.jsonl" in files:
                return Path(root) / f"{session_id}.jsonl"

    return None


def _empty_session(session_id: str, project_key: str) -> SessionSummary:
    """创建 一个 empty session summary as fallback."""
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
    """构建 SessionSummary，来源于 parsed Qoder events.

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

    # Fallback: Qoder may not report usage -- estimate，来源于 event text.
    # 使用 per-message estimates to ensure session summary matches LLM Calls detail.
    est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
    if has_estimated and input_tokens == 0 and output_tokens == 0:
        input_tokens = est_input
        output_tokens = est_output
        # 说明：Qoder has no cache metrics; do not fabricate cache values.
        cached_tokens = 0
        cache_write_tokens = 0

    # --- Collect timestamps，用于 interval calculation ---
    user_event_timestamps: list[int] = []
    assistant_event_timestamps: list[int] = []
    tool_use_map: dict[str, int] = {}       # 说明：tool_use_id -> start_ts_ms
    tool_result_map: dict[str, int] = {}    # 说明：tool_use_id -> end_ts_ms

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
            # 提取 title，来源于 first non-meta user message
            if not title and user_text:
                title = _extract_readable_title(user_text)
            if not cwd:
                cwd = ev.get("cwd", "")
            if not git_branch:
                git_branch = ev.get("gitBranch", "")

            # 检查，用于 failed tool results in user events (tool results come as user type)
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

    # 说明：--- Model execution: LLM response intervals (user -> next assistant) ---
    llm_intervals: list[tuple[int, int]] = []
    sorted_user_ts = sorted(user_event_timestamps)
    sorted_assistant_ts = sorted(assistant_event_timestamps)
    for u_ts in sorted_user_ts:
        for a_ts in sorted_assistant_ts:
            if a_ts > u_ts:
                llm_intervals.append((u_ts, a_ts))
                break

    # 说明：--- Tool execution: tool_use -> tool_result intervals ---
    tool_intervals: list[tuple[int, int]] = []
    for tool_id, use_ts in tool_use_map.items():
        if tool_id in tool_result_map:
            tool_intervals.append((use_ts, tool_result_map[tool_id]))

    model_execution_seconds = _merge_intervals(llm_intervals) / 1000.0
    tool_execution_seconds = _merge_intervals(tool_intervals) / 1000.0

    # 使用 cwd，来源于 events as 该 primary project_key -- it holds 该 actual
    # filesystem path. Fall back to 该 directory-based project_key (URL-decoded).
    # Guard against cwd being "." 或 一个 relative path that would produce a
    # 说明：meaningless project_key / project_name.
    actual_project = cwd if (cwd and cwd != "." and not cwd.startswith("./")) else project_key
    project_name = PurePosixPath(actual_project).name if actual_project else "unknown"

    # 说明：Unified 5-field breakdown: Qoder input_tokens is Fresh request input size.
    # Cache read/write stay as separate accounting fields 和 are not subtracted.
    fresh_input_tokens = input_tokens
    cache_read_tokens_session = cached_tokens
    cache_write_tokens_session = cache_write_tokens
    total_tokens = fresh_input_tokens + cache_read_tokens_session + cache_write_tokens_session + output_tokens

    # 使用 cwd，来源于 events as 该 primary project_key -- it holds 该 actual
    # filesystem path. Fall back to 该 directory-based project_key (URL-decoded).
    # Guard against cwd being "." 或 一个 relative path that would produce a
    # 说明：meaningless project_key / project_name.
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
        output_tokens=output_tokens,
        fresh_input_tokens=fresh_input_tokens,
        cache_read_tokens=cache_read_tokens_session,
        cache_write_tokens=cache_write_tokens_session,
        total_tokens=total_tokens,
        failed_tool_count=failed_tool_count,
    )


def _extract_messages(events: list[dict]) -> list[ChatMessage]:
    """提取 user 和 assistant chat messages，来源于 Qoder events.

    When Qoder does not report real usage, per-message token counts are
    estimated by walking events in order and accumulating visible context.

    Tracks pending request parts (human text + tool_result text) between
    user events and writes them to the next assistant message's request_full.
    """
    messages = []
    assistant_by_id = {rec["id"]: rec for rec in _assistant_records(events)}
    emitted_assistant_ids: set[str] = set()

    # Pre-pass: check，如果 real usage exists;，如果 not, compute per-message estimates
    has_real_usage = False
    for rec in assistant_by_id.values():
        if rec.get("usage") and rec["usage"].get("input_tokens"):
            has_real_usage = True
            break

    est_input_map: dict[str, int] = {}
    est_output_map: dict[str, int] = {}
    if not has_real_usage:
        _fill_estimates(events, assistant_by_id, est_input_map, est_output_map)

    # Collect pending request context between user events 和 该 next
    # 说明：assistant message.
    pending_request_parts: list[str] = []

    for ev in events:
        etype = ev.get("type", "")

        if etype == "user":
            content = _extract_user_text(ev)
            ts_str = ev.get("timestamp", "")

            # Collect tool_result text，用于 request context
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
            content_blocks = rec.get("content_blocks", [])
            usage = rec.get("usage", {})
            model = rec.get("model", "")
            if text_parts or tool_calls or content_blocks:
                # 使用 real usage，如果 present, otherwise fall back to estimates
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

                # For tool-only responses, include 一个 summary so response_full is not empty
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
                    content_blocks=content_blocks,
                ))

    return messages


def _fill_estimates(
    events: list[dict],
    assistant_by_id: dict,
    est_input_map: dict,
    est_output_map: dict,
) -> None:
    """Walk events 和 populate est_input_map / est_output_map by message key.

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
            # 说明：Only set input on first encounter; accumulate output across fragments
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
    """提取 tool call records，来源于 assistant messages.

    Also populates ToolCall.duration_ms from tool_use/tool_result timestamps.
    """
    tool_calls = []

    # 构建 一个 map of tool_use_id -> tool_result，用于 status/result display
    # and tool_use_id -> result timestamp，用于 duration_ms calculation
    tool_results: dict[str, dict] = {}
    tool_result_timestamps: dict[str, int] = {}  # 说明：tool_use_id -> end_ts_ms
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

                    # Store raw result content; apply heuristic later，当 we
                    # know 该 tool name，来源于 assistant messages.
                    tool_results[tool_use_id] = {
                        "is_error_raw": is_error,
                        "result_text": result_text,
                        "exit_code_raw": exit_code,
                    }

                    # Capture result timestamp，用于 duration_ms
                    ts_str = ev.get("timestamp", "")
                    if ts_str and tool_use_id:
                        dt_local = normalize_timestamp(ts_str)
                        if dt_local:
                            tool_result_timestamps[tool_use_id] = int(
                                datetime.fromisoformat(dt_local).timestamp() * 1000
                            )

    # 提取 tool calls，来源于 assistant messages
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

            # Apply heuristic now that we know 该 tool name
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

            # 计算 duration_ms，来源于 tool_use timestamp (from msg) and
            # 说明：tool_result timestamp (captured above)
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
    events: list[dict] | None = None,
) -> SessionSummary:
    """解析 一个 cache-format JSONL session，转换为 一个 minimal SessionSummary.

    Cache format uses {"role": "user|assistant", "message": {"content": [...]}}
    with no timestamps, tool calls, or usage data. Returns best-effort summary.
    When events lack timestamps, uses file_mtime for started_at/ended_at.
    """
    if events is None:
        events, _ = parse_jsonl_events(session_file)

    # 提取 user text，用于 title
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

    # 说明：Estimate tokens
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

    # When cache-format events lack timestamps, derive，来源于 file mtime.
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
        output_tokens=output_tokens,
        fresh_input_tokens=input_tokens,
        cache_read_tokens=0,
        cache_write_tokens=0,
        total_tokens=input_tokens + output_tokens,
        failed_tool_count=0,
    )


def scan_all_sessions(verbose: bool = False) -> Iterator[SessionSummary]:
    """扫描 所有 Qoder sessions 和 yield SessionSummary，用于 each.

    Walks ~/.qoder/projects/ (CLI sessions) and ~/.qoder/cache/projects/
    (GUI sessions) to discover session files, then parses each.
    """
    discovered = _discover_sessions()

    for project_key, session_id, fpath in discovered:
        summary, _msgs, _tcs, _sa = parse_session_detail(
            project_key, session_id, session_file=fpath, verbose=verbose
        )
        yield summary

    # 扫描 cache (GUI) sessions -- canonicalize short IDs to full UUIDs
    cache_sessions = _discover_cache_sessions()
    canonical_map = _build_canonical_id_map()
    # Collect 所有 projects/ session IDs to detect full overlap
    projects_ids = {sid.lower() for _pk, sid, _fp in _discover_sessions()}
    for project_key, session_id, fpath in cache_sessions:
        canonical_id = canonical_map.get(session_id.lower(), session_id)
        # 跳过 cache sessions that resolve to 一个 projects/ session already yielded
        if canonical_id != session_id.lower() and canonical_id in projects_ids:
            continue
        file_mtime = os.path.getmtime(fpath) if fpath.exists() else 0
        summary = _parse_cache_session(project_key, canonical_id, fpath, file_mtime=file_mtime)
        yield summary
