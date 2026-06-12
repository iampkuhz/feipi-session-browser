"""Parser for Codex local session data.

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
from session_browser.sources.jsonl_reader import parse_jsonl_events


def _as_dict(value):
    """Return value if it is a dict, else empty dict."""
    return value if isinstance(value, dict) else {}


def _int_or_zero(value):
    """Safely convert value to int, returning 0 on failure."""
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _nested_int(d, outer, inner):
    """Safely extract nested int from d[outer][inner]."""
    child = d.get(outer)
    if isinstance(child, dict):
        return _int_or_zero(child.get(inner))
    return 0


def _extract_codex_usage(raw: dict) -> dict:
    """Extract OpenAI/Codex usage from various structures into a flat dict.

    Supports:
    - Direct usage dict (input_tokens, output_tokens, etc.)
    - raw["usage"]
    - raw["response"]["usage"]
    - raw["data"]["usage"]
    - raw["payload"]["usage"]
    - raw["payload"]["info"]["last_token_usage"]
    - raw["payload"]["info"]["total_token_usage"] (marked as cumulative)
    - OpenAI nested: input_tokens_details.cached_tokens, output_tokens_details.reasoning_tokens
    - Chat-compatible fallback: prompt_tokens, completion_tokens, etc.

    Returns:
        Flat dict with keys: input_tokens, cached_input_tokens, output_tokens,
        reasoning_output_tokens, total_tokens, _usage_source.
    """
    if not isinstance(raw, dict):
        return {}

    candidates = []
    candidates.append((raw, "direct"))
    if isinstance(raw.get("usage"), dict):
        candidates.append((raw["usage"], "usage"))
    if isinstance(raw.get("response"), dict) and isinstance(raw["response"].get("usage"), dict):
        candidates.append((raw["response"]["usage"], "response.usage"))
    if isinstance(raw.get("data"), dict) and isinstance(raw["data"].get("usage"), dict):
        candidates.append((raw["data"]["usage"], "data.usage"))

    payload = raw.get("payload")
    if isinstance(payload, dict):
        if isinstance(payload.get("usage"), dict):
            candidates.append((payload["usage"], "payload.usage"))
        info = payload.get("info")
        if isinstance(info, dict):
            if isinstance(info.get("last_token_usage"), dict):
                candidates.append((info["last_token_usage"], "payload.info.last_token_usage"))
            if isinstance(info.get("total_token_usage"), dict):
                candidates.append((info["total_token_usage"], "payload.info.total_token_usage"))

    # Prefer per-call usage over cumulative; last_token_usage before total_token_usage
    # (candidates are already in priority order due to insertion order)
    for usage, source in candidates:
        if not isinstance(usage, dict):
            continue
        has_any = any(k in usage for k in (
            "input_tokens", "prompt_tokens", "output_tokens", "completion_tokens",
            "cached_input_tokens", "cached_tokens", "total_tokens",
            "input_tokens_details", "output_tokens_details",
        ))
        if not has_any:
            continue
        input_tokens = _int_or_zero(usage.get("input_tokens") or usage.get("prompt_tokens"))
        cached = (
            _int_or_zero(usage.get("cached_input_tokens"))
            or _int_or_zero(usage.get("cache_read_input_tokens"))
            or _int_or_zero(usage.get("cached_tokens"))
            or _nested_int(usage, "input_tokens_details", "cached_tokens")
            or _nested_int(usage, "prompt_tokens_details", "cached_tokens")
        )
        output_tokens = _int_or_zero(usage.get("output_tokens") or usage.get("completion_tokens"))
        reasoning = (
            _int_or_zero(usage.get("reasoning_output_tokens"))
            or _int_or_zero(usage.get("reasoning_tokens"))
            or _int_or_zero(usage.get("thinking_tokens"))
            or _nested_int(usage, "output_tokens_details", "reasoning_tokens")
            or _nested_int(usage, "completion_tokens_details", "reasoning_tokens")
        )
        total = (
            _int_or_zero(usage.get("total_tokens"))
            or _int_or_zero(usage.get("total_token_usage"))
            or _int_or_zero(usage.get("tokens_used"))
        )
        result = {
            "input_tokens": input_tokens,
            "cached_input_tokens": min(cached, input_tokens) if input_tokens else cached,
            "output_tokens": output_tokens if output_tokens else reasoning,
            "reasoning_output_tokens": reasoning,
            "total_tokens": total,
            "_usage_source": source,
        }
        if "total_token_usage" in source:
            result["_is_cumulative"] = True
        return result
    return {}
from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall, TokenPrecision
from session_browser.domain.token_normalizer import normalize_tokens
from session_browser.sources.jsonl_reader import parse_jsonl_events


def parse_session_index() -> list[dict]:
    """Parse ~/.codex/session_index.jsonl.

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
    """Read ~/.codex/state_5.sqlite threads table.

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
    """Find a Codex session file under ~/.codex/sessions/.

    If rollout_path is provided (from state_5.sqlite threads table), use it directly.
    Otherwise walk the year/month/day hierarchy to find the file.

    Sessions are stored as: {year}/{month}/{day}/rollout-{timestamp}-{uuid}.jsonl
    The uuid in the filename is the session id.
    """
    if rollout_path:
        p = Path(rollout_path)
        if p.exists():
            return p
        # rollout_path may be stale — fall through to hierarchy search

    sessions_dir = CODEX_DATA_DIR / "sessions"
    if not sessions_dir.exists():
        return None

    # Walk the year/month/day hierarchy
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
    """Parse a single Codex session.

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

    # Get metadata from threads DB
    thread_info = (threads_db or {}).get(session_id, {})

    # Find and parse session event stream (use rollout_path from DB if available)
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

    # Extract session_meta for cwd, source
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

    # Attach parse diagnostics from JSONL reader
    parse_diag = build_parse_diagnostics(
        session_key=summary.session_key,
        file_path=str(session_file),
        jsonl_diag=jsonl_diag,
    )
    summary.file_path = str(session_file)
    summary.parse_diagnostics = parse_diag.to_dict()

    return summary, messages, tool_calls, []


def parse_session_detail_with_normalized(
    session_id: str,
    threads_db: dict | None = None,
    verbose: bool = False,
) -> tuple[SessionSummary, list[ChatMessage], list[ToolCall], list[dict], dict, Path | None]:
    """Parse one Codex session and normalized JSON from a single event pass."""
    from session_browser.index.diagnostics import (
        ParseDiagnostics,
        ParseIssue,
        ParseIssueItem,
        ParseSeverity,
        build_parse_diagnostics,
    )
    from session_browser.normalized.agents.codex import parse_codex_events

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
    normalized = parse_codex_events(
        events,
        source_path=str(session_file),
        thread_info=normalized_thread_info,
    )
    normalized["parse_diagnostics"]["jsonl"] = {
        "total_lines": jsonl_diag.total_lines,
        "non_empty_lines": jsonl_diag.non_empty_lines,
        "events_parsed": jsonl_diag.events_parsed,
        "events_skipped": jsonl_diag.events_skipped,
        "warning_count": jsonl_diag.warning_count,
        "error_count": jsonl_diag.error_count,
    }
    return summary, messages, tool_calls, [], normalized, session_file


def parse_session_detail_normalized(
    session_id: str,
    threads_db: dict | None = None,
) -> dict:
    """Parse a Codex session into the normalized intermediate JSON contract.

    This is the first-stage adapter entry point used by snapshot tests and the
    future importer path. It intentionally does not replace parse_session_detail
    yet, so existing Session Detail behavior remains unchanged while the
    normalized contract is hardened.
    """
    from session_browser.normalized.agents.codex import parse_codex_rollout_file

    thread_info = (threads_db or {}).get(session_id, {})
    session_file = _find_session_file(session_id, thread_info.get("rollout_path", ""))
    if session_file is None:
        raise FileNotFoundError(f"Codex rollout file not found for session {session_id}")
    return parse_codex_rollout_file(session_file, thread_info=thread_info)


def parse_normalized_session_file(
    session_file: str | Path,
    thread_info: dict | None = None,
) -> dict:
    """Parse a Codex rollout file directly into normalized JSON.

    Tests use this file-level entry point to avoid touching the user's live
    Codex data directory.
    """
    from session_browser.normalized.agents.codex import parse_codex_rollout_file

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
    """Convert ISO8601 string to canonical form."""
    if not ts_str:
        return ""
    # Normalize: ensure it ends with +00:00 or Z
    return ts_str.replace("Z", "+00:00")


def _ts_to_epoch(ts_str: str) -> float:
    """Convert ISO8601 to epoch seconds."""
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
    """Build SessionSummary from Codex events + threads DB."""
    from pathlib import PurePosixPath

    user_count = 0
    assistant_count = 0
    tool_count = 0
    tokens_used = thread_info.get("tokens_used", 0)

    # Track cumulative token usage for delta recovery
    prev_cumulative = None
    # Session-level accumulated component totals
    sum_fresh = 0
    sum_cache_read = 0
    sum_output = 0

    # Track first/last timestamps
    first_ts = ""
    last_ts = ""

    # Process event_msg for message counts
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
                # Codex provides cumulative totals via total_token_usage.
                # last_token_usage is the last LLM call's usage (not a delta),
                # so we only use total_token_usage cumulative deltas.
                info = payload.get("info") or {}
                cumulative_usage = info.get("total_token_usage") or payload.get("total_token_usage")

                if cumulative_usage and isinstance(cumulative_usage, dict):
                    # Use _extract_codex_usage for proper alias handling
                    extracted = _extract_codex_usage(cumulative_usage)
                    usage_for_delta = extracted if extracted else cumulative_usage
                    if prev_cumulative:
                        prev_extracted = _extract_codex_usage(prev_cumulative)
                        prev_for_delta = prev_extracted if prev_extracted else prev_cumulative
                        # Compute per-turn delta from cumulative
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
                        # First cumulative snapshot — treat as-is
                        bd = normalize_tokens(usage_for_delta, provider="codex")
                        sum_fresh += bd.fresh_input_tokens
                        sum_cache_read += bd.cache_read_tokens
                        sum_output += bd.output_tokens

                    # Track the final cumulative total directly (not summed deltas)
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

    # Codex: input_tokens is the logical request input size; cached is reported separately.
    raw_input_total = sum_fresh
    cache_read = sum_cache_read
    fresh = sum_fresh
    output = sum_output

    # UI token composition uses component sum. SQLite tokens_used is a raw
    # fallback only when component fields are unavailable.
    component_total = fresh + cache_read + output
    total = component_total if component_total > 0 else tokens_used

    # Get metadata from thread_info (priority from DB)
    cwd = thread_info.get("cwd", "")
    if not cwd:
        cwd = session_meta.get("cwd", "")
    title = thread_info.get("title", "")
    model = thread_info.get("model", "")
    if not model:
        model = session_meta.get("model_provider", "")
    git_branch = thread_info.get("git_branch", "")
    source = thread_info.get("source", "")

    # Compute duration
    start_epoch = _ts_to_epoch(first_ts)
    end_epoch = _ts_to_epoch(last_ts)
    duration = end_epoch - start_epoch if (start_epoch and end_epoch) else 0

    # Compute project info
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
        input_tokens=raw_input_total,
        output_tokens=output,
        cached_input_tokens=cache_read,
        cached_output_tokens=0,
        fresh_input_tokens=fresh,
        cache_read_tokens=cache_read,
        cache_write_tokens=0,
        total_tokens=total,
    )


def _get_int_safe(d: dict, key: str) -> int:
    """Safely get int from dict."""
    val = d.get(key, 0)
    if val is None:
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _extract_messages(events: list[dict], model: str = "") -> list[ChatMessage]:
    """Extract user and agent messages from Codex events.

    Uses event_msg with type=user_message and type=agent_message.
    Tracks pending request parts for subsequent assistant messages.
    Attaches per-turn token usage from token_count events and tool call IDs
    from function_call and custom_tool_call response_items to each assistant message.

    Note: Each agent_message is followed by multiple token_count events (one per
    LLM call including tool follow-ups). All token_counts between two
    agent_messages are aggregated to form the per-turn usage for the preceding
    agent_message. Similarly, function_call and custom_tool_call IDs between
    agent_messages are collected to populate assistant_msg.tool_calls for round
    matching.
    """
    messages = []
    pending_request_parts: list[str] = []

    # Locate agent_message events
    agent_msg_indices: list[int] = []
    for i, ev in enumerate(events):
        etype = ev.get("type", "")
        payload = ev.get("payload", {})
        if (etype == "event_msg"
                and payload.get("type") == "agent_message"
                and payload.get("phase", "") in ("commentary", "final")):
            agent_msg_indices.append(i)

    # For each agent_message, collect token_counts, tool call IDs, and the
    # canonical response_item payloads between it and the next agent_message.
    # Codex writes the same assistant text twice: event_msg.agent_message is a
    # UI/status mirror, while response_item.message is the model response item.
    # Use response_item as canonical when present and fall back to event_msg.
    agent_usage: dict[int, dict] = {}  # agent_msg_index -> aggregated usage
    agent_tool_ids: dict[int, list[dict]] = {}  # agent_msg_index -> [{id, name}, ...]
    agent_response_content: dict[int, dict] = {}
    for ai, start_idx in enumerate(agent_msg_indices):
        if ai + 1 < len(agent_msg_indices):
            end_idx = agent_msg_indices[ai + 1]
        else:
            end_idx = len(events)

        # Aggregate token counts
        usage: dict = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": 0,
        }
        tool_ids: list[dict] = []
        response_texts: list[str] = []
        response_blocks: list[dict] = []
        for i in range(start_idx, end_idx):
            ev = events[i]
            if ev.get("type") == "event_msg":
                payload = ev.get("payload", {})
                if payload.get("type") == "token_count":
                    info = payload.get("info") or {}
                    last_usage = info.get("last_token_usage") or payload.get("last_token_usage")
                    if last_usage and isinstance(last_usage, dict):
                        # Use _extract_codex_usage to handle flat + nested aliases
                        extracted = _extract_codex_usage(last_usage)
                        if extracted:
                            usage["input_tokens"] += extracted.get("input_tokens", 0)
                            usage["cached_input_tokens"] += extracted.get("cached_input_tokens", 0)
                            usage["output_tokens"] += extracted.get("output_tokens", 0)
                            usage["reasoning_output_tokens"] += extracted.get("reasoning_output_tokens", 0)
                            usage["total_tokens"] += extracted.get("total_tokens", 0)
                        else:
                            # Fallback: direct field access
                            usage["input_tokens"] += last_usage.get("input_tokens", 0) or 0
                            usage["cached_input_tokens"] += last_usage.get("cached_input_tokens", 0) or 0
                            usage["output_tokens"] += last_usage.get("output_tokens", 0) or 0
                            usage["reasoning_output_tokens"] += last_usage.get("reasoning_output_tokens", 0) or 0
                            usage["total_tokens"] += last_usage.get("total_tokens", 0) or 0
            elif ev.get("type") == "response_item":
                payload = ev.get("payload", {})
                rtype = payload.get("type", "")
                if rtype == "message" and payload.get("role") == "assistant":
                    for block in _response_item_text_blocks(payload):
                        response_blocks.append(block)
                        text = block.get("content") or block.get("text") or ""
                        if str(text).strip():
                            response_texts.append(str(text).strip())
                elif rtype in ("function_call", "custom_tool_call"):
                    call_id = payload.get("call_id", "")
                    tool_name = payload.get("name", "")
                    if call_id:
                        tool_ids.append({"id": call_id, "name": tool_name})
                    tool_block = _response_item_tool_block(payload)
                    if tool_block:
                        response_blocks.append(tool_block)

        agent_usage[start_idx] = usage
        agent_tool_ids[start_idx] = tool_ids
        agent_response_content[start_idx] = {
            "text": "\n\n".join(response_texts),
            "blocks": response_blocks,
        }

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
                if phase in ("commentary", "final"):
                    request_full = "\n\n".join(p for p in pending_request_parts if p)
                    pending_request_parts = []

                    # Attach aggregated per-turn usage and tool call IDs
                    usage = agent_usage.get(i)
                    tool_calls_list = agent_tool_ids.get(i, [])
                    response_content = agent_response_content.get(i, {})
                    response_text = str(response_content.get("text") or "").strip()
                    content_str = response_text or str(content)
                    content_blocks = list(response_content.get("blocks") or [])
                    if not content_blocks and content_str:
                        content_blocks = [{
                            "type": "text",
                            "content": content_str,
                            "source": "event_msg.agent_message",
                        }]

                    messages.append(ChatMessage(
                        role="assistant",
                        content=content_str,
                        timestamp=ts,
                        model=model,
                        request_full=request_full,
                        usage=usage,
                        tool_calls=tool_calls_list,
                        content_blocks=content_blocks,
                    ))
        elif etype == "response_item":
            rtype = payload.get("type", "")
            if rtype in ("function_call_output", "custom_tool_call_output"):
                call_id = payload.get("call_id", "")
                output = payload.get("output", "")
                output_text = str(output) if output is not None else ""
                if output_text:
                    if call_id:
                        pending_request_parts.append(
                            f"Tool output for {call_id}:\n{output_text}"
                        )
                    else:
                        pending_request_parts.append(output_text)

    return messages


def _response_item_text_blocks(payload: dict) -> list[dict]:
    """Extract visible assistant text blocks from a Codex response_item."""
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


def _response_item_tool_block(payload: dict) -> dict:
    """Return a renderable tool_use block for a Codex function_call item."""
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
    """Extract tool calls from Codex response_items.

    Each function_call has a call_id (used as tool_use_id) and a matching
    function_call_output with the result and exit status.
    custom_tool_call (e.g. apply_patch) is also handled the same way.
    """
    # Pre-index outputs by call_id (both function_call_output and custom_tool_call_output)
    outputs_by_id: dict[str, dict] = {}
    for ev in events:
        if ev.get("type") == "response_item":
            payload = ev.get("payload", {})
            if payload.get("type") in ("function_call_output", "custom_tool_call_output"):
                call_id = payload.get("call_id", "")
                if call_id:
                    outputs_by_id[call_id] = payload

    tool_calls = []
    for ev in events:
        etype = ev.get("type", "")
        payload = ev.get("payload", {})
        ts = ev.get("timestamp", "")

        if etype == "response_item":
            rtype = payload.get("type", "")
            if rtype in ("function_call", "custom_tool_call"):
                name = payload.get("name", "")
                # custom_tool_call uses "input" for args; function_call uses "arguments"
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

                # Match with output for status/result
                status = "completed"
                result = ""
                exit_code: int | None = None
                output_ev = outputs_by_id.get(call_id, {})
                if output_ev:
                    output_text = str(output_ev.get("output", ""))
                    result = output_text
                    # Extract exit code from output (e.g. "Process exited with code 1" or "Exit code: 1")
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
                    timestamp=ts,
                    tool_use_id=call_id,
                    exit_code=exit_code,
                ))

    return tool_calls


def scan_all_sessions(
    threads_db: dict | None = None,
    verbose: bool = False,
) -> Iterator[SessionSummary]:
    """Scan all Codex sessions and yield SessionSummary for each.

    Primary source is state_5.sqlite threads table (complete and authoritative).
    session_index.jsonl is used as a fallback to catch sessions that exist
    but haven't been flushed to the threads DB yet (e.g. active sessions).
    """
    if threads_db is None:
        threads_db = read_threads_db()

    # Load session_index.jsonl for title enrichment AND fallback discovery
    index_entries = {e["id"]: e for e in parse_session_index()}

    seen_ids: set[str] = set()

    for sid, thread_info in threads_db.items():
        seen_ids.add(sid)
        summary, _msgs, _tcs, _sa = parse_session_detail(sid, threads_db, verbose=verbose)
        # Enrich title from index if empty in threads DB
        if not summary.title:
            idx_entry = index_entries.get(sid)
            if idx_entry and idx_entry.get("thread_name"):
                summary.title = idx_entry["thread_name"][:120]
            # Fallback to first_user_message from threads DB
            elif thread_info.get("first_user_message"):
                summary.title = thread_info["first_user_message"][:120]
        yield summary

    # Fallback: scan session_index.jsonl for sessions not in threads DB
    # This catches active sessions that haven't been flushed to state_5.sqlite yet
    for sid, idx_entry in index_entries.items():
        if sid in seen_ids:
            continue
        # Session exists in index but not in threads DB yet
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
