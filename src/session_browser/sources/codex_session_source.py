"""Codex 本地 session 数据解析器。

Data sources:
- ~/.codex/session_index.jsonl: thread index (id, thread_name, updated_at)
- ~/.codex/sessions/{year}/{month}/{day}/rollout-*.jsonl: full session event stream
- ~/.codex/state_5.sqlite.threads: thread metadata (title, cwd, branch, model, tokens)
- ~/.codex/history.jsonl: user input history (optional)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterator

from session_browser.config import CODEX_DATA_DIR
from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall, TokenPrecision
from session_browser.domain.token_normalizer import normalize_tokens
from session_browser.domain.token_normalizers.codex_token_normalizer import (
    CODEX_USAGE_FIELDS,
    codex_is_duplicate_cumulative,
    codex_usage_delta,
    extract_codex_usage,
)
from session_browser.sources.jsonl_reader import parse_jsonl_events


def _as_dict(value):
    """返回 value，如果 it is 一个 dict, else empty dict."""
    return value if isinstance(value, dict) else {}


def _int_or_zero(value):
    """说明：Safely convert value to int, returning 0 on failure."""
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _nested_int(d, outer, inner):
    """Safely extract nested int，来源于 d[outer][inner]."""
    child = d.get(outer)
    if isinstance(child, dict):
        return _int_or_zero(child.get(inner))
    return 0


def _extract_codex_usage(raw: dict) -> dict:
    """从多种 Codex/OpenAI Responses 结构中提取扁平 usage 字段。"""
    return extract_codex_usage(raw)


def _codex_usage_delta(current: dict, previous: dict | None) -> dict:
    """计算 Codex cumulative token_count 快照的有效增量。"""
    return codex_usage_delta(current, previous)


def _codex_is_duplicate_cumulative(current: dict, previous: dict | None) -> bool:
    return codex_is_duplicate_cumulative(current, previous)


def _display_phase(phase: str) -> bool:
    return phase in {"commentary", "final", "final_answer"}


def _format_tool_output_request(call_id: str, output: object) -> str:
    output_text = str(output) if output is not None else ""
    if not output_text:
        return ""
    if call_id:
        return f"Tool output for {call_id}:\n{output_text}"
    return output_text
from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall, TokenPrecision
from session_browser.domain.token_normalizer import normalize_tokens
from session_browser.sources.jsonl_reader import parse_jsonl_events


def parse_session_index() -> list[dict]:
    """解析 ~/.codex/session_index.jsonl.

    Returns list of dicts with: id, thread_name, updated_at.
    """
    path = CODEX_DATA_DIR / "session_index.jsonl"
    if not path.exists():
        return []

    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    continue
                entries.append({
                    "id": obj.get("id", ""),
                    "thread_name": obj.get("thread_name", ""),
                    "updated_at": obj.get("updated_at", ""),
                })
            except json.JSONDecodeError:
                continue
    return entries


def read_threads_db() -> dict[str, dict]:
    """读取 ~/.codex/state_5.sqlite threads table.

    Returns dict keyed by thread id.
    Includes rollout_path for direct session file lookup.
    Uses a timeout to avoid blocking when Codex is actively writing.
    """
    db_path = CODEX_DATA_DIR / "state_5.sqlite"
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT id, title, cwd, model, tokens_used, created_at, updated_at, "
            "git_branch, source, model_provider, cli_version, rollout_path, "
            "first_user_message "
            "FROM threads"
        )
        result = {}
        for row in cursor:
            tid = row["id"]
            result[tid] = {
                "id": tid,
                "title": row["title"],
                "cwd": row["cwd"],
                "model": row["model"] or "",
                "tokens_used": row["tokens_used"] or 0,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "git_branch": row["git_branch"] or "",
                "source": row["source"] or "",
                "model_provider": row["model_provider"] or "",
                "cli_version": row["cli_version"] or "",
                "rollout_path": row["rollout_path"] or "",
                "first_user_message": row["first_user_message"] or "",
            }
        return result
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def _find_session_file(session_id: str, rollout_path: str = "") -> Path | None:
    """查找 一个 Codex session file under ~/.codex/sessions/.

    If rollout_path is provided (from state_5.sqlite threads table), use it directly.
    Otherwise walk the year/month/day hierarchy to find the file.

    Sessions are stored as: {year}/{month}/{day}/rollout-{timestamp}-{uuid}.jsonl
    The uuid in the filename is the session id.
    """
    if rollout_path:
        p = Path(rollout_path)
        if p.exists():
            return p
        # 说明：rollout_path may be stale — fall through to hierarchy search

    sessions_dir = CODEX_DATA_DIR / "sessions"
    if not sessions_dir.exists():
        return None

    # Walk 该 year/month/day hierarchy
    for year_dir in sorted(sessions_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for day_dir in sorted(month_dir.iterdir()):
                if not day_dir.is_dir():
                    continue
                found = list(day_dir.glob(f"rollout-*-{session_id}.jsonl"))
                if found:
                    return found[0]
    return None


def parse_session_detail(
    session_id: str,
    threads_db: dict | None = None,
    verbose: bool = False,
) -> tuple[SessionSummary, list[ChatMessage], list[ToolCall], list[dict]]:
    """解析 一个 single Codex session.

    Args:
        session_id: The Codex thread/session ID.
        threads_db: Pre-loaded threads DB data (from read_threads_db).
        verbose: If True, print diagnostic info about skipped JSON lines.

    Returns: (SessionSummary, chat_messages, tool_calls, []).
    """
    from session_browser.index.diagnostics import (
        ParseDiagnostics,
        ParseIssue,
        ParseIssueItem,
        ParseSeverity,
        build_parse_diagnostics,
    )

    # Get metadata，来源于 threads DB
    thread_info = (threads_db or {}).get(session_id, {})

    # 查找 和 parse session event stream (use rollout_path，来源于 DB，如果 available)
    rollout_path = thread_info.get("rollout_path", "")
    session_file = _find_session_file(session_id, rollout_path)
    if session_file is None:
        s = _empty_session(session_id, thread_info)
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

    # 提取 session_meta，用于 cwd, source
    session_meta = {}
    for ev in events:
        if ev.get("type") == "session_meta":
            session_meta = ev.get("payload", {})
            break

    summary = _build_summary_from_events(
        events, session_id, thread_info, session_meta
    )
    model_from_db = thread_info.get("model", "")
    if not model_from_db:
        model_from_db = session_meta.get("model_provider", "")
    messages = _extract_messages(events, model=model_from_db)
    tool_calls = _extract_tool_calls(events)
    subagent_runs = _parse_subagent_runs(session_file, session_id)
    _attach_subagents_to_spawn_tools(tool_calls, subagent_runs)
    tool_calls.extend(_flatten_subagent_tool_calls(subagent_runs))
    summary.subagent_instance_count = len(subagent_runs)

    # 附加 parse diagnostics，来源于 JSONL reader
    parse_diag = build_parse_diagnostics(
        session_key=summary.session_key,
        file_path=str(session_file),
        jsonl_diag=jsonl_diag,
    )
    summary.file_path = str(session_file)
    summary.parse_diagnostics = parse_diag.to_dict()

    return summary, messages, tool_calls, subagent_runs


def parse_session_detail_with_normalized(
    session_id: str,
    threads_db: dict | None = None,
    verbose: bool = False,
) -> tuple[SessionSummary, list[ChatMessage], list[ToolCall], list[dict], dict, Path | None]:
    """解析 一个 Codex session 和 normalized JSON，来源于 一个 single event pass."""
    from session_browser.index.diagnostics import (
        ParseDiagnostics,
        ParseIssue,
        ParseIssueItem,
        ParseSeverity,
        build_parse_diagnostics,
    )
    from session_browser.normalized.agents.codex_normalization import parse_codex_rollout_file

    thread_info = (threads_db or {}).get(session_id, {})
    rollout_path = thread_info.get("rollout_path", "")
    session_file = _find_session_file(session_id, rollout_path)
    if session_file is None:
        summary = _empty_session(session_id, thread_info)
        summary.parse_diagnostics = ParseDiagnostics(
            session_key=summary.session_key,
            issues=[ParseIssueItem(
                issue=ParseIssue.FILE_NOT_FOUND,
                severity=ParseSeverity.WARNING,
                message="Session file not found",
            )],
        ).to_dict()
        return summary, [], [], [], {}, None

    events, jsonl_diag = parse_jsonl_events(session_file, verbose=verbose)

    session_meta = {}
    for ev in events:
        if ev.get("type") == "session_meta":
            session_meta = ev.get("payload", {})
            break

    summary = _build_summary_from_events(
        events, session_id, thread_info, session_meta
    )
    model_from_db = thread_info.get("model", "") or session_meta.get("model_provider", "")
    messages = _extract_messages(events, model=model_from_db)
    tool_calls = _extract_tool_calls(events)
    subagent_runs = _parse_subagent_runs(session_file, session_id)
    _attach_subagents_to_spawn_tools(tool_calls, subagent_runs)
    tool_calls.extend(_flatten_subagent_tool_calls(subagent_runs))
    summary.subagent_instance_count = len(subagent_runs)

    parse_diag = build_parse_diagnostics(
        session_key=summary.session_key,
        file_path=str(session_file),
        jsonl_diag=jsonl_diag,
    )
    summary.file_path = str(session_file)
    summary.parse_diagnostics = parse_diag.to_dict()

    normalized_thread_info = dict(thread_info)
    normalized_thread_info.setdefault("id", summary.session_id)
    normalized_thread_info.setdefault("title", summary.title)
    normalized_thread_info.setdefault("cwd", summary.cwd)
    normalized_thread_info.setdefault("git_branch", summary.git_branch)
    normalized_thread_info.setdefault("model", summary.model)
    normalized = parse_codex_rollout_file(
        session_file,
        thread_info=normalized_thread_info,
    )
    return summary, messages, tool_calls, subagent_runs, normalized, session_file


def parse_session_detail_normalized(
    session_id: str,
    threads_db: dict | None = None,
) -> dict:
    """解析 一个 Codex session，转换为 该 normalized intermediate JSON contract.

    This is the first-stage adapter entry point used by snapshot tests and the
    future importer path. It intentionally does not replace parse_session_detail
    yet, so existing Session Detail behavior remains unchanged while the
    normalized contract is hardened.
    """
    from session_browser.normalized.agents.codex_normalization import parse_codex_rollout_file

    thread_info = (threads_db or {}).get(session_id, {})
    session_file = _find_session_file(session_id, thread_info.get("rollout_path", ""))
    if session_file is None:
        raise FileNotFoundError(f"Codex rollout file not found for session {session_id}")
    return parse_codex_rollout_file(session_file, thread_info=thread_info)


def parse_normalized_session_file(
    session_file: str | Path,
    thread_info: dict | None = None,
) -> dict:
    """解析 一个 Codex rollout file directly，转换为 normalized JSON.

    Tests use this file-level entry point to avoid touching the user's live
    Codex data directory.
    """
    from session_browser.normalized.agents.codex_normalization import parse_codex_rollout_file

    return parse_codex_rollout_file(session_file, thread_info=thread_info or {})


def _empty_session(session_id: str, thread_info: dict) -> SessionSummary:
    from pathlib import PurePosixPath
    cwd = thread_info.get("cwd", "")
    project_key = cwd
    project_name = PurePosixPath(cwd).name if cwd else "unknown"
    return SessionSummary(
        agent="codex",
        session_id=session_id,
        title=thread_info.get("title", ""),
        project_key=project_key,
        project_name=project_name,
        cwd=cwd,
        started_at="",
        ended_at="",
        model=thread_info.get("model", ""),
        git_branch=thread_info.get("git_branch", ""),
    )


def _ts_iso(ts_str: str) -> str:
    """转换 ISO8601 string to canonical form."""
    if not ts_str:
        return ""
    # Normalize: ensure it ends，使用 +00:00 或 Z
    return ts_str.replace("Z", "+00:00")


def _ts_to_epoch(ts_str: str) -> float:
    """转换 ISO8601 to epoch seconds."""
    if not ts_str:
        return 0
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0


def _build_summary_from_events(
    events: list[dict],
    session_id: str,
    thread_info: dict,
    session_meta: dict,
) -> SessionSummary:
    """构建 SessionSummary，来源于 Codex events + threads DB."""
    from pathlib import PurePosixPath

    user_count = 0
    assistant_count = 0
    tool_count = 0
    tokens_used = thread_info.get("tokens_used", 0)

    # Track cumulative token usage，用于 delta recovery
    prev_cumulative = None
    # 说明：Session-level accumulated component totals
    sum_fresh = 0
    sum_cache_read = 0
    sum_output = 0

    # 说明：Track first/last timestamps
    first_ts = ""
    last_ts = ""

    # Process event_msg，用于 message counts
    for ev in events:
        etype = ev.get("type", "")
        payload = ev.get("payload", {})
        ts = ev.get("timestamp", "")

        if not first_ts:
            first_ts = ts

        if etype == "event_msg":
            msg_type = payload.get("type", "")
            if msg_type == "user_message":
                user_count += 1
            elif msg_type == "agent_message":
                assistant_count += 1
            elif msg_type == "token_count":
                # 说明：Codex provides cumulative totals via total_token_usage.
                # last_token_usage is 该 last LLM call's usage (not 一个 delta),
                # so we 仅 use total_token_usage cumulative deltas.
                info = payload.get("info") or {}
                cumulative_usage = info.get("total_token_usage") or payload.get("total_token_usage")

                if cumulative_usage and isinstance(cumulative_usage, dict):
                    # 使用 _extract_codex_usage，用于 proper alias handling
                    extracted = _extract_codex_usage(cumulative_usage)
                    usage_for_delta = extracted if extracted else cumulative_usage
                    if prev_cumulative:
                        prev_extracted = _extract_codex_usage(prev_cumulative)
                        prev_for_delta = prev_extracted if prev_extracted else prev_cumulative
                        # 计算 per-turn delta，来源于 cumulative
                        delta = {}
                        for key in ("input_tokens", "prompt_tokens", "cached_input_tokens",
                                     "cache_read_input_tokens", "cached_tokens",
                                     "output_tokens", "completion_tokens",
                                     "reasoning_output_tokens", "reasoning_tokens", "thinking_tokens"):
                            cur_val = _get_int_safe(usage_for_delta, key)
                            prev_val = _get_int_safe(prev_for_delta, key)
                            delta[key] = max(cur_val - prev_val, 0)
                        bd = normalize_tokens(delta, provider="codex")
                        bd.precision = TokenPrecision.PROVIDER_REPORTED_DELTA
                        sum_fresh += bd.fresh_input_tokens
                        sum_cache_read += bd.cache_read_tokens
                        sum_output += bd.output_tokens
                    else:
                        # 说明：First cumulative snapshot — treat as-is
                        bd = normalize_tokens(usage_for_delta, provider="codex")
                        sum_fresh += bd.fresh_input_tokens
                        sum_cache_read += bd.cache_read_tokens
                        sum_output += bd.output_tokens

                    # Track 该 final cumulative total directly (not summed deltas)
                    cumulative_total = (
                        _get_int_safe(cumulative_usage, "total_tokens")
                        or _get_int_safe(cumulative_usage, "total_token_usage")
                        or _get_int_safe(cumulative_usage, "tokens_used")
                    )
                    if cumulative_total > 0:
                        tokens_used = max(tokens_used, cumulative_total)

                    prev_cumulative = cumulative_usage

        elif etype == "response_item":
            rtype = payload.get("type", "")
            if rtype == "function_call":
                tool_count += 1

        last_ts = ts

    # Codex: input_tokens is 该 logical request input size; cached is reported separately.
    raw_input_total = sum_fresh
    cache_read = sum_cache_read
    fresh = sum_fresh
    output = sum_output

    # UI token composition uses component sum. SQLite tokens_used is 一个 raw
    # fallback only，当 component fields are unavailable.
    component_total = fresh + cache_read + output
    total = component_total if component_total > 0 else tokens_used

    # Get metadata，来源于 thread_info (priority，来源于 DB)
    cwd = thread_info.get("cwd", "")
    if not cwd:
        cwd = session_meta.get("cwd", "")
    title = thread_info.get("title", "")
    model = thread_info.get("model", "")
    if not model:
        model = session_meta.get("model_provider", "")
    git_branch = thread_info.get("git_branch", "")
    source = thread_info.get("source", "")

    # 计算 duration
    start_epoch = _ts_to_epoch(first_ts)
    end_epoch = _ts_to_epoch(last_ts)
    duration = end_epoch - start_epoch if (start_epoch and end_epoch) else 0

    # 计算 project info
    project_key = cwd
    project_name = PurePosixPath(cwd).name if cwd else "unknown"

    return SessionSummary(
        agent="codex",
        session_id=session_id,
        title=title,
        project_key=project_key,
        project_name=project_name,
        cwd=cwd,
        started_at=_ts_iso(first_ts),
        ended_at=_ts_iso(last_ts),
        duration_seconds=round(duration, 1),
        model=model,
        git_branch=git_branch,
        source=source,
        user_message_count=user_count,
        assistant_message_count=assistant_count,
        tool_call_count=tool_count,
        output_tokens=output,
        fresh_input_tokens=fresh,
        cache_read_tokens=cache_read,
        cache_write_tokens=0,
        total_tokens=total,
    )


def _get_int_safe(d: dict, key: str) -> int:
    """Safely get int，来源于 dict."""
    val = d.get(key, 0)
    if val is None:
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _extract_wall_time_ms(text: str) -> float:
    """提取 tool wall time，来源于 Codex tool output text."""
    if not text:
        return 0
    import re
    match = re.search(r"Wall time:\s*([0-9]+(?:\.[0-9]+)?)\s*(seconds?|secs?|s|ms)\b", text, re.IGNORECASE)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "ms":
        return value
    return value * 1000


def _extract_messages(events: list[dict], model: str = "") -> list[ChatMessage]:
    """提取 visible user messages 和 Codex LLM-call assistant messages.

    Codex ``event_msg.token_count`` records are the only authoritative boundary
    for model-call token ownership.  Assistant text mirrors and response items
    are associated with the current token_count segment for display, but they do
    not define token windows.
    """
    messages = []
    pending_request_parts: list[str] = []

    response_blocks: list[dict] = []
    tool_ids: list[dict] = []
    deferred_tool_outputs: list[str] = []
    previous_cumulative: dict | None = None
    last_assistant: ChatMessage | None = None
    call_index = 0

    for i, ev in enumerate(events):
        etype = ev.get("type", "")
        payload = ev.get("payload", {})
        ts = ev.get("timestamp", "")

        if etype == "event_msg":
            msg_type = payload.get("type", "")
            if msg_type == "user_message":
                content = payload.get("message", "")
                if isinstance(content, list):
                    content = "\n".join(str(c) for c in content)
                content_str = str(content)
                if content_str:
                    pending_request_parts.append(content_str)
                messages.append(ChatMessage(
                    role="user",
                    content=content_str,
                    timestamp=ts,
                ))
            elif msg_type == "agent_message":
                phase = payload.get("phase", "")
                content = payload.get("message", "")
                if isinstance(content, list):
                    content = "\n".join(str(c) for c in content)
                content_str = str(content)
                if _display_phase(phase) and content_str.strip():
                    response_blocks.append({
                        "type": "text",
                        "content": content_str,
                        "source": "event_msg.agent_message",
                        "phase": phase,
                    })
            elif msg_type == "token_count":
                info = payload.get("info") or {}
                last_usage = info.get("last_token_usage") or payload.get("last_token_usage")
                cumulative_usage = info.get("total_token_usage") or payload.get("total_token_usage")

                duplicate = (
                    isinstance(cumulative_usage, dict)
                    and _codex_is_duplicate_cumulative(cumulative_usage, previous_cumulative)
                )
                if duplicate:
                    if last_assistant and last_assistant.usage is not None:
                        duplicates = last_assistant.usage.setdefault("_duplicate_token_count_records", [])
                        duplicates.append({
                            "record_index": i + 1,
                            "timestamp": ts,
                            "status": "duplicate_token_count",
                            "contribution": 0,
                            "last_total_tokens": _get_int_safe(_as_dict(last_usage), "total_tokens"),
                            "cumulative_total_tokens": _get_int_safe(cumulative_usage, "total_tokens"),
                        })
                        last_assistant.usage["_usage_duplicate_count"] = len(duplicates)
                    previous_cumulative = cumulative_usage
                    continue

                usage_source = "last_token_usage"
                usage = _extract_codex_usage(last_usage) if isinstance(last_usage, dict) else {}
                delta = {}
                if isinstance(cumulative_usage, dict):
                    delta = _codex_usage_delta(cumulative_usage, previous_cumulative)
                    if any(value < 0 for value in delta.values()):
                        usage_source = "last_token_usage_after_cumulative_reset"
                    elif not usage:
                        usage_source = "total_token_usage_delta"
                        usage = {
                            "input_tokens": max(delta["input_tokens"], 0),
                            "cached_input_tokens": max(delta["cached_input_tokens"], 0),
                            "output_tokens": max(delta["output_tokens"], 0),
                            "reasoning_output_tokens": max(delta["reasoning_output_tokens"], 0),
                            "total_tokens": max(delta["total_tokens"], 0),
                            "_usage_source": usage_source,
                        }
                    previous_cumulative = cumulative_usage

                if not usage:
                    continue

                call_index += 1
                usage["_usage_fragment_count"] = 1
                usage["_token_count_record_index"] = i + 1
                usage["_token_count_timestamp"] = ts
                usage["_token_count_status"] = "counted"
                usage["_usage_source"] = usage.get("_usage_source") or usage_source
                if delta:
                    usage["_cumulative_delta"] = {
                        field: max(delta[field], 0) for field in CODEX_USAGE_FIELDS
                    }
                if isinstance(cumulative_usage, dict):
                    usage["_cumulative_total_tokens"] = _get_int_safe(cumulative_usage, "total_tokens")

                request_full = "\n\n".join(p for p in pending_request_parts if p)
                pending_request_parts = [p for p in deferred_tool_outputs if p]
                deferred_tool_outputs = []

                content_blocks = _canonical_response_blocks(response_blocks)
                content_str = "\n\n".join(
                    str(block.get("content") or block.get("text") or "").strip()
                    for block in content_blocks
                    if block.get("type") == "text"
                    and str(block.get("content") or block.get("text") or "").strip()
                )
                assistant = ChatMessage(
                    role="assistant",
                    content=content_str,
                    timestamp=ts,
                    model=model,
                    request_full=request_full,
                    usage=usage,
                    tool_calls=list(tool_ids),
                    content_blocks=content_blocks,
                    llm_call_id=f"codex-call-{call_index:04d}",
                )
                messages.append(assistant)
                last_assistant = assistant

                response_blocks = []
                tool_ids = []
        elif etype == "response_item":
            rtype = payload.get("type", "")
            if rtype == "message" and payload.get("role") == "assistant":
                phase = str(payload.get("phase") or "")
                if not phase or _display_phase(phase):
                    for block in _response_item_text_blocks(payload):
                        response_blocks.append(block)
            elif rtype == "reasoning":
                response_blocks.append(_response_item_reasoning_block(payload))
            elif rtype in ("function_call", "custom_tool_call"):
                call_id = payload.get("call_id", "")
                tool_name = payload.get("name", "")
                if call_id:
                    tool_ids.append({"id": call_id, "name": tool_name})
                tool_block = _response_item_tool_block(payload)
                if tool_block:
                    response_blocks.append(tool_block)
            elif rtype in ("function_call_output", "custom_tool_call_output"):
                call_id = payload.get("call_id", "")
                output = payload.get("output", "")
                formatted = _format_tool_output_request(call_id, output)
                if formatted:
                    deferred_tool_outputs.append(formatted)

    return messages


def _canonical_response_blocks(blocks: list[dict]) -> list[dict]:
    """优先使用 response_item assistant text over matching event_msg mirrors."""
    response_item_texts = {
        str(block.get("content") or block.get("text") or "").strip()
        for block in blocks
        if block.get("type") == "text"
        and block.get("source") == "response_item.message"
        and str(block.get("content") or block.get("text") or "").strip()
    }
    result: list[dict] = []
    seen_texts: set[str] = set()
    for block in blocks:
        if block.get("type") != "text":
            result.append(block)
            continue
        text = str(block.get("content") or block.get("text") or "").strip()
        if not text:
            continue
        if block.get("source") == "event_msg.agent_message" and text in response_item_texts:
            continue
        if text in seen_texts:
            continue
        seen_texts.add(text)
        result.append(block)
    return result


def _response_item_text_blocks(payload: dict) -> list[dict]:
    """提取 visible assistant text blocks，来源于 一个 Codex response_item."""
    blocks: list[dict] = []
    for part in payload.get("content") or []:
        if not isinstance(part, dict):
            continue
        text = part.get("text") or part.get("content") or ""
        if not str(text).strip():
            continue
        blocks.append({
            "type": "text",
            "content": str(text),
            "source": "response_item.message",
            "phase": payload.get("phase") or "",
        })
    return blocks


def _response_item_reasoning_block(payload: dict) -> dict:
    """把 Codex reasoning item 保留为 response-side reasoning block。"""
    summary = payload.get("summary") if isinstance(payload.get("summary"), list) else []
    return {
        "type": "reasoning",
        "content": json.dumps(summary, ensure_ascii=False),
        "has_encrypted_content": bool(payload.get("encrypted_content")),
        "source": "response_item.reasoning",
    }


def _response_item_tool_block(payload: dict) -> dict:
    """返回 一个 renderable tool_use block，用于 一个 Codex function_call item."""
    call_id = payload.get("call_id", "") or ""
    name = payload.get("name", "") or payload.get("type", "tool").replace("_call", "")
    return {
        "type": "tool_use",
        "id": call_id,
        "name": name,
        "parameters": _response_item_tool_arguments(payload),
        "source": f"response_item.{payload.get('type', 'function_call')}",
    }


def _response_item_tool_arguments(payload: dict) -> dict:
    args = payload.get("arguments", {})
    if payload.get("type") == "custom_tool_call" and not args:
        args = payload.get("input", "")
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"raw": args[:2000]}
    return args if isinstance(args, dict) else {}


def _extract_tool_calls(events: list[dict]) -> list[ToolCall]:
    """提取 tool calls，来源于 Codex response_items.

    Each function_call has a call_id (used as tool_use_id) and a matching
    function_call_output with the result and exit status.
    custom_tool_call (e.g. apply_patch) is also handled the same way.
    """
    # Pre-index outputs by call_id (both function_call_output 和 custom_tool_call_output)
    outputs_by_id: dict[str, dict] = {}
    for ev in events:
        if ev.get("type") == "response_item":
            payload = ev.get("payload", {})
            if payload.get("type") in ("function_call_output", "custom_tool_call_output"):
                call_id = payload.get("call_id", "")
                if call_id:
                    outputs_by_id[call_id] = {
                        "payload": payload,
                        "timestamp": ev.get("timestamp", ""),
                    }

    tool_calls = []
    for ev in events:
        etype = ev.get("type", "")
        payload = ev.get("payload", {})
        ts = ev.get("timestamp", "")

        if etype == "response_item":
            rtype = payload.get("type", "")
            if rtype in ("function_call", "custom_tool_call"):
                name = payload.get("name", "")
                # custom_tool_call uses "input"，用于 args; function_call uses "arguments"
                args = payload.get("arguments", {})
                if rtype == "custom_tool_call" and not args:
                    args_raw = payload.get("input", "")
                    if isinstance(args_raw, str):
                        args = {"patch": args_raw}
                if isinstance(args, str):
                    try:
                        import json
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args[:200]}
                call_id = payload.get("call_id", "")

                # Match，使用 output，用于 status/result
                status = "completed"
                result = ""
                duration_ms = 0
                exit_code: int | None = None
                output_info = outputs_by_id.get(call_id, {})
                output_ev = output_info.get("payload", {}) if isinstance(output_info, dict) else {}
                if output_ev:
                    output_text = str(output_ev.get("output", ""))
                    result = output_text
                    duration_ms = _extract_wall_time_ms(output_text)
                    if duration_ms <= 0:
                        started_at = _ts_to_epoch(ts)
                        ended_at = _ts_to_epoch(output_info.get("timestamp", ""))
                        if started_at > 0 and ended_at > started_at:
                            duration_ms = (ended_at - started_at) * 1000
                    # 提取 exit code，来源于 output (e.g. "Process exited，使用 code 1" 或 "Exit code: 1")
                    import re
                    exit_match = re.search(r"exited with code (\d+)", output_text)
                    if not exit_match:
                        exit_match = re.search(r"Exit code[:\s]*(\d+)", output_text)
                    if exit_match:
                        exit_code = int(exit_match.group(1))
                        if exit_code != 0:
                            status = "error"

                tool_calls.append(ToolCall(
                    name=name,
                    parameters=args if isinstance(args, dict) else {},
                    result=result,
                    status=status,
                    duration_ms=duration_ms,
                    timestamp=ts,
                    tool_use_id=call_id,
                    exit_code=exit_code,
                ))

    return tool_calls


def _parse_subagent_runs(session_file: Path, parent_session_id: str) -> list[dict]:
    """解析 Codex child rollout files that declare this thread as parent."""
    if not parent_session_id or not session_file.exists():
        return []
    runs: list[dict] = []
    for candidate in sorted(session_file.parent.glob("rollout-*.jsonl")):
        if candidate == session_file:
            continue
        events, _ = parse_jsonl_events(candidate)
        meta = _first_session_meta(events)
        spawn = _codex_thread_spawn(meta)
        if spawn.get("parent_thread_id") != parent_session_id:
            continue
        agent_id = str(meta.get("id") or _session_id_from_path(str(candidate)))
        model = str(meta.get("model_provider") or "")
        messages = _extract_messages(events, model=model)
        tool_calls = _extract_tool_calls(events)
        for tc in tool_calls:
            tc.scope = "subagent"
            tc.subagent_id = agent_id
            tc.parent_tool_name = "spawn_agent"
        summary = _subagent_summary_from_events(events, candidate, agent_id, spawn)
        runs.append({
            "path": str(candidate),
            "messages": messages,
            "tool_calls": tool_calls,
            "summary": summary,
        })
    return runs


def _first_session_meta(events: list[dict]) -> dict:
    for event in events:
        if event.get("type") == "session_meta" and isinstance(event.get("payload"), dict):
            return event["payload"]
    return {}


def _codex_thread_spawn(meta: dict) -> dict:
    source = meta.get("source") if isinstance(meta.get("source"), dict) else {}
    subagent = source.get("subagent") if isinstance(source.get("subagent"), dict) else {}
    spawn = subagent.get("thread_spawn") if isinstance(subagent.get("thread_spawn"), dict) else {}
    return spawn


def _subagent_summary_from_events(
    events: list[dict],
    path: Path,
    agent_id: str,
    spawn: dict,
) -> dict:
    llm_calls = 0
    input_tokens = 0
    cache_read = 0
    output_tokens = 0
    first_ts = ""
    last_ts = ""
    previous_cumulative: dict | None = None
    for event in events:
        ts = str(event.get("timestamp") or "")
        if ts and not first_ts:
            first_ts = ts
        if ts:
            last_ts = ts
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event.get("type") == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
            cumulative_usage = info.get("total_token_usage") or payload.get("total_token_usage")
            if isinstance(cumulative_usage, dict):
                if _codex_is_duplicate_cumulative(cumulative_usage, previous_cumulative):
                    previous_cumulative = cumulative_usage
                    continue
                previous_cumulative = cumulative_usage
            usage = _extract_codex_usage({"payload": payload})
            if usage:
                llm_calls += 1
                input_tokens += max(_int_or_zero(usage.get("input_tokens")) - _int_or_zero(usage.get("cached_input_tokens")), 0)
                cache_read += _int_or_zero(usage.get("cached_input_tokens"))
                output_tokens += _int_or_zero(usage.get("output_tokens"))
    return {
        "agent_id": agent_id,
        "agent_type": str(spawn.get("agent_role") or ""),
        "agent_nickname": str(spawn.get("agent_nickname") or ""),
        "parent_thread_id": str(spawn.get("parent_thread_id") or ""),
        "depth": _int_or_zero(spawn.get("depth")),
        "path": str(path),
        "started_at": first_ts,
        "ended_at": last_ts,
        "llm_call_count": llm_calls,
        "tool_call_count": sum(
            1
            for event in events
            if event.get("type") == "response_item"
            and (event.get("payload") or {}).get("type") in {"function_call", "custom_tool_call"}
        ),
        "failed_tool_count": 0,
        "input_tokens": input_tokens,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": 0,
        "output_tokens": output_tokens,
    }


def _attach_subagents_to_spawn_tools(tool_calls: list[ToolCall], subagent_runs: list[dict]) -> None:
    by_id = {(run.get("summary") or {}).get("agent_id", ""): run for run in subagent_runs}
    for tc in tool_calls:
        if tc.name != "spawn_agent":
            continue
        data = _json_dict(tc.result)
        agent_id = str(data.get("agent_id") or "")
        run = by_id.get(agent_id)
        if not run:
            continue
        summary = run.get("summary") or {}
        tc.subagent_id = agent_id
        tc.subagent_summary = {
            **summary,
            "nickname": data.get("nickname") or summary.get("agent_nickname", ""),
        }
        tc.llm_call_count = summary.get("llm_call_count", 0)
        tc.llm_error_count = 0
        tc.subagent_tool_call_count = summary.get("tool_call_count", 0)
        tc.subagent_failed_tool_count = summary.get("failed_tool_count", 0)
        for child in run.get("tool_calls") or []:
            child.parent_tool_use_id = tc.tool_use_id
            child.parent_tool_name = tc.name


def _flatten_subagent_tool_calls(subagent_runs: list[dict]) -> list[ToolCall]:
    result: list[ToolCall] = []
    for run in subagent_runs:
        result.extend(run.get("tool_calls") or [])
    return result


def _json_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def scan_all_sessions(
    threads_db: dict | None = None,
    verbose: bool = False,
) -> Iterator[SessionSummary]:
    """扫描 所有 Codex sessions 和 yield SessionSummary，用于 each.

    Primary source is state_5.sqlite threads table (complete and authoritative).
    session_index.jsonl is used as a fallback to catch sessions that exist
    but haven't been flushed to the threads DB yet (e.g. active sessions).
    """
    if threads_db is None:
        threads_db = read_threads_db()

    # 加载 session_index.jsonl，用于 title enrichment AND fallback discovery
    index_entries = {e["id"]: e for e in parse_session_index()}

    seen_ids: set[str] = set()

    for sid, thread_info in threads_db.items():
        seen_ids.add(sid)
        summary, _msgs, _tcs, _sa = parse_session_detail(sid, threads_db, verbose=verbose)
        # Enrich title，来源于 index，如果 empty in threads DB
        if not summary.title:
            idx_entry = index_entries.get(sid)
            if idx_entry and idx_entry.get("thread_name"):
                summary.title = idx_entry["thread_name"][:120]
            # 兜底 to first_user_message，来源于 threads DB
            elif thread_info.get("first_user_message"):
                summary.title = thread_info["first_user_message"][:120]
        yield summary

    # Fallback: scan session_index.jsonl，用于 sessions not in threads DB
    # 说明：This catches active sessions that haven't been flushed to state_5.sqlite yet
    for sid, idx_entry in index_entries.items():
        if sid in seen_ids:
            continue
        # 说明：Session exists in index but not in threads DB yet
        thread_info = {
            "id": sid,
            "title": idx_entry.get("thread_name", ""),
            "cwd": "",
            "model": "",
            "tokens_used": 0,
            "created_at": 0,
            "updated_at": 0,
            "git_branch": "",
            "source": "",
            "model_provider": "",
            "cli_version": "",
            "rollout_path": "",
            "first_user_message": "",
        }
        summary, _msgs, _tcs, _sa = parse_session_detail(sid, {sid: thread_info})
        if not summary.title and idx_entry.get("thread_name"):
            summary.title = idx_entry["thread_name"][:120]
        yield summary
