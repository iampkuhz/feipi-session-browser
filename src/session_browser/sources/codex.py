"""Parser for Codex local session data.

Data sources:
- ~/.codex/session_index.jsonl: thread index (id, thread_name, updated_at)
- ~/.codex/sessions/{year}/{month}/{day}/rollout-*.jsonl: full session event stream
- ~/.codex/state_5.sqlite.threads: thread metadata (title, cwd, branch, model, tokens)
- ~/.codex/history.jsonl: user input history (optional)

All paths configurable via CODEX_DATA_DIR env var.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterator

from session_browser.config import CODEX_DATA_DIR
from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall


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


def _parse_session_events(path: Path) -> list[dict]:
    """Parse a single Codex session .jsonl event stream."""
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                events.append(obj)
            except json.JSONDecodeError:
                continue
    return events


def parse_session_detail(
    session_id: str,
    threads_db: dict | None = None,
) -> tuple[SessionSummary, list[ChatMessage], list[ToolCall], list[dict]]:
    """Parse a single Codex session.

    Args:
        session_id: The Codex thread/session ID.
        threads_db: Pre-loaded threads DB data (from read_threads_db).

    Returns: (SessionSummary, chat_messages, tool_calls, []).
    """
    # Get metadata from threads DB
    thread_info = (threads_db or {}).get(session_id, {})

    # Find and parse session event stream (use rollout_path from DB if available)
    rollout_path = thread_info.get("rollout_path", "")
    session_file = _find_session_file(session_id, rollout_path)
    if session_file is None:
        return _empty_session(session_id, thread_info), [], [], []

    events = _parse_session_events(session_file)

    # Extract session_meta for cwd, source
    session_meta = {}
    for ev in events:
        if ev.get("type") == "session_meta":
            session_meta = ev.get("payload", {})
            break

    summary = _build_summary_from_events(
        events, session_id, thread_info, session_meta
    )
    messages = _extract_messages(events)
    tool_calls = _extract_tool_calls(events)

    return summary, messages, tool_calls, []


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
                # Take the last/largest total
                total = payload.get("total_token_usage", 0)
                if total:
                    tokens_used = total

        elif etype == "response_item":
            rtype = payload.get("type", "")
            if rtype == "function_call":
                tool_count += 1

        last_ts = ts

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
        input_tokens=tokens_used,  # Codex uses total tokens
        output_tokens=0,  # Not separately available
        cached_input_tokens=0,
    )


def _extract_messages(events: list[dict]) -> list[ChatMessage]:
    """Extract user and agent messages from Codex events.

    Uses event_msg with type=user_message and type=agent_message.
    Tracks pending request parts for subsequent assistant messages.
    """
    messages = []
    pending_request_parts: list[str] = []

    for ev in events:
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
                # Include commentary and final as assistant messages
                content = payload.get("message", "")
                if isinstance(content, list):
                    content = "\n".join(str(c) for c in content)
                if phase in ("commentary", "final"):
                    request_full = "\n\n".join(p for p in pending_request_parts if p)
                    pending_request_parts = []
                    messages.append(ChatMessage(
                        role="assistant",
                        content=str(content),
                        timestamp=ts,
                        request_full=request_full,
                    ))

    return messages


def _extract_tool_calls(events: list[dict]) -> list[ToolCall]:
    """Extract tool calls from Codex response_items.

    Only counts function_call, not function_call_output (to avoid double counting).
    """
    tool_calls = []
    for ev in events:
        etype = ev.get("type", "")
        payload = ev.get("payload", {})
        ts = ev.get("timestamp", "")

        if etype == "response_item":
            rtype = payload.get("type", "")
            if rtype == "function_call":
                name = payload.get("name", "")
                args = payload.get("arguments", {})
                if isinstance(args, str):
                    try:
                        import json
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args[:200]}
                call_id = payload.get("call_id", "")
                # Try to find matching output for status
                status = "completed"
                result = ""
                for ev2 in events:
                    if ev2.get("type") == "response_item":
                        p2 = ev2.get("payload", {})
                        if (p2.get("type") == "function_call_output"
                                and p2.get("call_id") == call_id):
                            result = str(p2.get("output", ""))[:500]
                            break
                tool_calls.append(ToolCall(
                    name=name,
                    parameters=args if isinstance(args, dict) else {},
                    result=result,
                    status=status,
                    timestamp=ts,
                ))

    return tool_calls


def scan_all_sessions(
    threads_db: dict | None = None,
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
        summary, _msgs, _tcs, _sa = parse_session_detail(sid, threads_db)
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
