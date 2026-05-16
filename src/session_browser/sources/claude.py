"""Parser for Claude Code local session data.

Data sources:
- ~/.claude/history.jsonl: session index (sessionId, project, display, timestamp)
- ~/.claude/projects/{project}/{sessionId}.jsonl: full conversation event stream
- ~/.claude/sessions/{pid}.json: active session metadata (optional)

All paths configurable via CLAUDE_DATA_DIR env var.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterator

from session_browser.config import CLAUDE_DATA_DIR
from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall, TokenBreakdown
from session_browser.domain.token_normalizer import normalize_tokens, TokenPrecision


def parse_history() -> list[dict]:
    """Parse ~/.claude/history.jsonl and return raw session index entries.

    Returns list of dicts with: session_id, project, display, timestamp
    """
    path = CLAUDE_DATA_DIR / "history.jsonl"
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
                    "session_id": obj.get("sessionId", ""),
                    "project": obj.get("project", ""),
                    "display": obj.get("display", ""),
                    "timestamp": obj.get("timestamp", 0),
                })
            except json.JSONDecodeError:
                continue
    return entries


def _ts_ms_to_iso(ts_ms: int | float) -> str:
    """Convert millisecond timestamp to ISO8601 string."""
    if not ts_ms:
        return ""
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.isoformat()


def _ts_to_iso(ts: int | float) -> str:
    """Convert second timestamp to ISO8601 string."""
    if not ts:
        return ""
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.isoformat()


def _parse_session_events(path: Path) -> list[dict]:
    """Parse a single session .jsonl event stream file.

    Returns list of raw event dicts, filtered to relevant types.
    """
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


def _assistant_message_key(ev: dict) -> str:
    """Return a stable key for one logical assistant/LLM response."""
    msg = ev.get("message", {})
    if isinstance(msg, dict) and msg.get("id"):
        return str(msg["id"])
    return str(ev.get("uuid") or ev.get("parentUuid") or id(ev))


def _merge_usage_dicts(usages: list[dict]) -> dict:
    """Merge duplicated Claude usage snapshots for one logical response.

    Claude Code may persist one assistant response as several JSONL rows
    (thinking/text/tool_use fragments). The same usage snapshot can repeat
    once per fragment or once per parallel tool_use. Taking the max per token
    field preserves the logical response footprint without multiplying it by
    the number of fragments.
    """
    if not usages:
        return {}

    merged: dict = {}
    numeric_keys = {
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    }
    for usage in usages:
        for key, value in usage.items():
            if key in numeric_keys and isinstance(value, (int, float)):
                merged[key] = max(int(value), int(merged.get(key, 0)))
            elif key not in merged:
                merged[key] = value
    return merged


def _assistant_records(events: list[dict]) -> list[dict]:
    """Merge assistant fragments by message id.

    Returns records with: id, timestamp, model, text_parts, tool_calls, usage,
    and raw row count. This record is the parser's LLM-call-level view.
    """
    records: dict[str, dict] = {}
    order: list[str] = []

    for ev in events:
        if ev.get("type") != "assistant":
            continue
        msg = ev.get("message", {})
        if not isinstance(msg, dict):
            continue

        key = _assistant_message_key(ev)
        if key not in records:
            records[key] = {
                "id": key,
                "timestamp": ev.get("timestamp", ""),
                "model": msg.get("model", ""),
                "text_parts": [],
                "tool_calls": [],
                "usage_rows": [],
                "stop_reason": "",
                "row_count": 0,
            }
            order.append(key)

        rec = records[key]
        rec["row_count"] += 1
        if ev.get("timestamp"):
            rec["timestamp"] = ev.get("timestamp", "")
        if msg.get("model"):
            rec["model"] = msg.get("model", "")
        if msg.get("stop_reason"):
            rec["stop_reason"] = msg.get("stop_reason", "")

        usage = msg.get("usage")
        if isinstance(usage, dict):
            rec["usage_rows"].append(usage)

        content = msg.get("content", [])
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text = item.get("text", "")
                    if text:
                        rec["text_parts"].append(text)
                elif item.get("type") == "tool_use":
                    rec["tool_calls"].append({
                        "id": item.get("id", ""),
                        "name": item.get("name", ""),
                        "parameters": item.get("input", {}),
                    })

    merged_records = []
    for key in order:
        rec = records[key]
        rec["usage"] = _merge_usage_dicts(rec.pop("usage_rows"))
        merged_records.append(rec)
    return merged_records


def _extract_user_text(ev: dict) -> str:
    """Extract human-visible user text, ignoring tool_result-only events."""
    msg = ev.get("message", {})
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def parse_session_detail(
    project_key: str,
    session_id: str,
    history_entry: dict | None = None,
) -> tuple[SessionSummary, list[ChatMessage], list[ToolCall], list[dict]]:
    """Parse a single Claude session's full event stream.

    Args:
        project_key: The project path from history.jsonl.
        session_id: The session ID.
        history_entry: Optional history.jsonl entry for metadata fallback.

    Returns (SessionSummary, chat_messages, tool_calls, subagent_runs).
    """
    # Locate the session file
    project_dir = CLAUDE_DATA_DIR / "projects" / _normalize_project_segment(project_key)
    session_file = project_dir / f"{session_id}.jsonl"
    if not session_file.exists():
        # Try to find it by scanning
        session_file = _find_session_file(project_key, session_id)
        if session_file is None:
            s = _session_from_history(session_id, history_entry)
            return s, [], [], []

    events = _parse_session_events(session_file)
    subagent_runs = _parse_subagent_runs(session_file)

    summary = _build_summary_from_events(events, session_id, project_key, subagent_runs)
    messages = _extract_messages(events)
    tool_calls = _extract_tool_calls(events, messages)
    _attach_subagents_to_agent_tools(tool_calls, subagent_runs)
    nested_tool_calls = _flatten_subagent_tool_calls(subagent_runs)
    tool_calls.extend(nested_tool_calls)
    _apply_subagent_totals(summary, subagent_runs, tool_calls)

    return summary, messages, tool_calls, subagent_runs


def _normalize_project_segment(project_key: str) -> str:
    """Convert a full project path to the directory name used in ~/.claude/projects/."""
    if not project_key:
        return ""
    # The projects directory uses a URL-encoded style of the full path
    # For now, return as-is; the actual mapping is 1:1 with path segments
    return project_key


def _find_session_file(project_key: str, session_id: str) -> Path | None:
    """Search for a session file under projects/."""
    projects_dir = CLAUDE_DATA_DIR / "projects"
    if not projects_dir.exists():
        return None

    # Try direct match
    candidate = projects_dir / project_key / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate

    # Search all project directories
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        candidate = proj_dir / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    return None


def _empty_session(session_id: str, project_key: str) -> SessionSummary:
    """Create an empty session summary as fallback."""
    from pathlib import PurePosixPath
    project_name = PurePosixPath(project_key).name if project_key else "unknown"
    return SessionSummary(
        agent="claude_code",
        session_id=session_id,
        title="",
        project_key=project_key,
        project_name=project_name,
        cwd="",
        started_at="",
        ended_at="",
    )


def _session_from_history(session_id: str, history_entry: dict | None = None) -> SessionSummary:
    """Create a session summary from history.jsonl metadata when the event file is missing.

    This ensures sessions with deleted .jsonl files still appear in the index
    with valid timestamps and titles from history.jsonl.
    """
    from pathlib import PurePosixPath

    project = (history_entry or {}).get("project", "")
    display = (history_entry or {}).get("display", "")
    ts_ms = (history_entry or {}).get("timestamp", 0)

    # Use history timestamp as both started_at and ended_at since we don't
    # have the actual event stream to determine session duration
    ts_iso = _ts_ms_to_iso(ts_ms) if ts_ms else ""
    project_name = PurePosixPath(project).name if project else "unknown"

    # Clean up title from display field
    title = _extract_readable_title(display)

    return SessionSummary(
        agent="claude_code",
        session_id=session_id,
        title=title,
        project_key=project,
        project_name=project_name,
        cwd="",
        started_at=ts_iso,
        ended_at=ts_iso,
    )


# ─── Title extraction ─────────────────────────────────────────────────────


def _extract_readable_title(raw_content: str) -> str:
    """Extract a readable title from raw content that may contain command envelopes.

    Handles:
    1. <command-message>spec-research</command-message><command-args>... → "spec-research · user-intent"
    2. Normal text → first sentence/intent summary
    3. Empty → ""
    """
    if not raw_content:
        return ""

    content = raw_content.strip()

    # Detect command envelope pattern
    cmd_match = re.search(r"<command-message>([^<]+)</command-message>", content)
    if cmd_match:
        cmd_name = cmd_match.group(1).strip()

        # Try to extract user intent from <command-args>
        args_match = re.search(r"<command-args>(.+?)</command-args>", content, re.DOTALL)
        if args_match:
            args_text = args_match.group(1).strip()
            # Clean up: remove XML-like tags, take first meaningful sentence
            intent = _summarize_text(args_text)
            if intent:
                return f"{cmd_name} · {intent}"

        # Fallback: take text after the command envelope
        after_cmd = content[cmd_match.end():].strip()
        if after_cmd:
            intent = _summarize_text(after_cmd)
            if intent:
                return f"{cmd_name} · {intent}"

        return cmd_name

    # No command envelope — summarize normally
    return _summarize_text(content)


def _summarize_text(text: str, max_len: int = 80) -> str:
    """Create a short, readable summary of text.

    Strips tags, takes first sentence or up to max_len chars.
    """
    if not text:
        return ""

    # Strip XML-like tags
    text = re.sub(r"<[^>]+>", "", text).strip()

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    # Take first sentence (up to first period/question/exclamation followed by space)
    sentence_match = re.match(r"^(.+?[.!?])\s", text)
    if sentence_match:
        first_sentence = sentence_match.group(1).strip()
        if len(first_sentence) <= max_len:
            return first_sentence
        return first_sentence[:max_len - 1] + "…"

    # No sentence boundary — truncate
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


# ─── Summary building ─────────────────────────────────────────────────────


def _parse_ts_ms(ts_str: str) -> int:
    """Parse ISO8601 timestamp string to millisecond epoch."""
    if not ts_str:
        return 0
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return 0


def _build_summary_from_events(
    events: list[dict],
    session_id: str,
    project_key: str,
    subagent_runs: list | None = None,
) -> SessionSummary:
    """Build SessionSummary from parsed Claude events.

    Computes timeline-based execution times:
    - model_execution_seconds: merged LLM response intervals (user msg → assistant msg)
    - tool_execution_seconds: merged tool + subagent intervals (tool_use → tool_result),
      with parallel overlaps merged
    """
    from pathlib import PurePosixPath

    user_count = 0
    failed_tool_count = 0
    model = ""
    cwd = ""
    git_branch = ""
    source = ""
    first_ts = 0
    last_ts = 0
    title = ""
    assistant_records = _assistant_records(events)
    assistant_count = len(assistant_records)
    tool_ids = set()
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    cache_write_tokens = 0

    for rec in assistant_records:
        usage = rec.get("usage", {})
        if isinstance(usage, dict):
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            cached_tokens += usage.get("cache_read_input_tokens", 0)
            cache_write_tokens += usage.get("cache_creation_input_tokens", 0)
        for tc in rec.get("tool_calls", []):
            tool_id = tc.get("id") or f"{rec.get('id')}:{tc.get('name')}:{len(tool_ids)}"
            tool_ids.add(tool_id)
        if not model and rec.get("model"):
            model = rec.get("model", "")

    # Collect timestamps for interval calculation
    user_event_timestamps: list[int] = []
    assistant_event_timestamps: list[int] = []
    tool_use_map: dict[str, int] = {}       # tool_use_id -> start_ts_ms
    tool_result_map: dict[str, int] = {}    # tool_use_id -> end_ts_ms

    for ev in events:
        etype = ev.get("type", "")
        ts_str = ev.get("timestamp", "")
        ts_ms = _parse_ts_ms(ts_str) if ts_str else 0

        if etype == "user":
            user_text = _extract_user_text(ev)
            if user_text:
                user_count += 1
            if ts_str and not first_ts:
                first_ts = _parse_ts_ms(ts_str)
            if not title and user_text:
                title = _extract_readable_title(user_text)
            if not cwd:
                cwd = ev.get("cwd", "")
            if not source:
                source = ev.get("entrypoint", "")
            if not git_branch:
                git_branch = ev.get("gitBranch", "")

            content = ev.get("message", {}).get("content", "") if isinstance(ev.get("message"), dict) else ""
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        if item.get("is_error") is True:
                            failed_tool_count += 1
                        tuid = item.get("tool_use_id", "")
                        if tuid and ts_ms:
                            tool_result_map[tuid] = ts_ms
            if ts_ms:
                user_event_timestamps.append(ts_ms)

        elif etype == "assistant" and ev.get("message", {}).get("type") == "message":
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

    # ─── Model execution: LLM response intervals (user → next assistant) ───
    llm_intervals: list[tuple[int, int]] = []
    sorted_user_ts = sorted(user_event_timestamps)
    sorted_assistant_ts = sorted(assistant_event_timestamps)
    for u_ts in sorted_user_ts:
        # Find the next assistant message after this user message
        for a_ts in sorted_assistant_ts:
            if a_ts > u_ts:
                llm_intervals.append((u_ts, a_ts))
                break

    # ─── Tool execution: tool_use → tool_result intervals ───
    tool_intervals: list[tuple[int, int]] = []
    for tool_id, use_ts in tool_use_map.items():
        if tool_id in tool_result_map:
            tool_intervals.append((use_ts, tool_result_map[tool_id]))

    # ─── Subagent intervals from sidechain event streams ───
    subagent_intervals: list[tuple[int, int]] = []
    for run in (subagent_runs or []):
        summary = run.get("summary", {})
        s_ms = _parse_ts_ms(summary.get("started_at", ""))
        e_ms = _parse_ts_ms(summary.get("ended_at", ""))
        if s_ms and e_ms:
            subagent_intervals.append((s_ms, e_ms))

    if not last_ts and first_ts:
        last_ts = first_ts

    duration = 0
    if first_ts and last_ts:
        duration = (last_ts - first_ts) / 1000

    model_execution_seconds = _merge_intervals(llm_intervals) / 1000.0
    tool_execution_seconds = _merge_intervals(tool_intervals + subagent_intervals) / 1000.0

    project_name = PurePosixPath(project_key).name if project_key else "unknown"

    return SessionSummary(
        agent="claude_code",
        session_id=session_id,
        title=title,
        project_key=project_key,
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
        failed_tool_count=failed_tool_count,
    )


def _merge_intervals(intervals: list[tuple[int, int]], max_gap_ms: int = 300_000) -> int:
    """Merge overlapping intervals and return total merged duration in milliseconds.

    Filters out individual intervals longer than max_gap_ms (likely idle time).
    """
    if not intervals:
        return 0
    # Filter out intervals > max_gap_ms (idle time)
    intervals = [(s, e) for s, e in intervals if (e - s) <= max_gap_ms]
    if not intervals:
        return 0
    intervals.sort()
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return sum(e - s for s, e in merged)


def _extract_messages(events: list[dict]) -> list[ChatMessage]:
    """Extract user and assistant chat messages from Claude events.

    Tracks pending request parts (human text + tool_result text) between
    user events and writes them to the next assistant message's request_full.
    """
    messages = []
    assistant_by_id = {rec["id"]: rec for rec in _assistant_records(events)}
    emitted_assistant_ids: set[str] = set()

    # Collect pending request context between user events and the next
    # assistant message.  This captures both human text and tool_result
    # text that become part of the API request preceding an assistant reply.
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

            # Human user text
            if content:
                pending_request_parts.append(content)

            if content:
                messages.append(ChatMessage(
                    role="user",
                    content=content,
                    timestamp=ts_str,
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
                token_bd = normalize_tokens(usage, model=model) if usage else None

                request_full = "\n\n".join(p for p in pending_request_parts if p)
                pending_request_parts = []

                messages.append(ChatMessage(
                    role="assistant",
                    content="\n".join(text_parts),
                    timestamp=rec.get("timestamp", ""),
                    model=model,
                    tool_calls=tool_calls,
                    usage=usage if usage else None,
                    token_breakdown=token_bd,
                    llm_call_id=rec.get("id", ""),
                    request_full=request_full,
                ))

    return messages


def _stringify_tool_result(result_content) -> str:
    """Convert Claude tool_result content into compact text."""
    if result_content is None:
        return ""
    if isinstance(result_content, str):
        return result_content
    if isinstance(result_content, list):
        parts = []
        for item in result_content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif "content" in item:
                    parts.append(str(item.get("content", "")))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    if isinstance(result_content, dict):
        return json.dumps(result_content, ensure_ascii=False)
    return str(result_content)


def _tool_result_looks_failed(result_content, tool_name: str = "") -> bool:
    """Heuristic for **tool runtime failure** in Claude logs.

    Only detects failures where the tool itself could not execute:
    - API / model access errors
    - User rejection of tool use
    - Request / timeout failures
    - Shell can't run the command (command not found)
    - File-level errors for Read/Write/etc. (file doesn't exist, permission denied)

    Does NOT treat these as tool failures:
    - Nonzero exit codes (command ran but returned an error status)
    - Lint / test / build errors (tool ran successfully, result has error text)
    - Source code, logs, or HTML containing error keywords
    """
    text = _stringify_tool_result(result_content).lower()
    if not text:
        return False

    # For Read/Write/Edit/Glob/Grep/LS tools, only trust the JSONL
    # is_error flag and obvious file-level error messages.  Their
    # results are file/glob contents which can legitimately contain
    # words like "error", "failed", "key_model_access_denied" in
    # source code, logs, or comments.
    if tool_name in ("Read", "Write", "Edit", "Glob", "Grep", "LS"):
        first_line = text.split("\n", 1)[0].strip()
        if first_line.startswith((
            "file does not exist",
            "permission denied",
            "no such file",
            "directory not found",
            "path not found",
            "cannot read",
            "not a directory",
            "too many levels of symbolic links",
            "input/output error",
            "is a directory",
        )):
            return True
        return False

    # For Bash/Agent and others: detect **tool runtime errors**, not
    # command output that happens to contain error keywords.

    # ── Tool runtime error markers (anchored at line start) ─────
    # These indicate the tool could not execute, not that it executed
    # and produced an error result (like lint failures, test failures).
    line_markers = [
        "api error",
        "tool_use_error",
        "key_model_access_denied",
        "rate limit exceeded",
        "user rejected",
        "request cancelled",
        "permission denied",       # bash: ./deploy.sh: Permission denied
        "fatal:",                  # git errors: fatal: not a git repository
    ]
    for marker in line_markers:
        if text.startswith(marker):
            return True
        for line in text.split("\n"):
            stripped = line.strip().lstrip("$# ").strip()
            if stripped.startswith(marker):
                return True
            # Also match after shell error prefix: "bash: cmd: ..."
            # e.g. "bash: kubectl: command not found"
            parts = stripped.split(": ")
            if len(parts) > 1:
                last_part = parts[-1].strip()
                if last_part.startswith(marker):
                    return True

    # ── "command not found" at line start or after shell prefix ──
    # Real shell error: the tool couldn't run the command.
    # Match: "command not found" at line start, or "bash: xyz: command not found"
    if re.search(r"(?:^|\n)\s*command not found", text, re.MULTILINE):
        return True
    for line in text.split("\n"):
        stripped = line.strip()
        # "bash: xyz: command not found" or "sh: xyz: command not found"
        m = re.match(r"^(?:ba)?sh:\s+.*:\s+command not found", stripped)
        if m:
            return True

    # ── "timeout" as standalone word at line start ────────────────
    # Tool execution timed out at the runtime level.
    if re.search(r"(?:^|\n)\s*timeout\b", text, re.MULTILINE):
        return True

    return False


def _usage_totals_from_messages(messages: list[ChatMessage]) -> dict:
    """Aggregate merged per-message usage into token totals."""
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    for msg in messages:
        if msg.role != "assistant" or not msg.usage:
            continue
        totals["input_tokens"] += msg.usage.get("input_tokens", 0)
        totals["output_tokens"] += msg.usage.get("output_tokens", 0)
        totals["cache_read_input_tokens"] += msg.usage.get("cache_read_input_tokens", 0)
        totals["cache_creation_input_tokens"] += msg.usage.get("cache_creation_input_tokens", 0)
    return totals


def _parse_subagent_runs(session_file: Path) -> list[dict]:
    """Parse Claude Code subagent sidechain files for a parent session."""
    subagents_dir = session_file.with_suffix("") / "subagents"
    if not subagents_dir.exists():
        return []

    runs = []
    for path in sorted(subagents_dir.glob("*.jsonl")):
        events = _parse_session_events(path)
        messages = _extract_messages(events)
        tool_calls = _extract_tool_calls(events, messages)
        usage_totals = _usage_totals_from_messages(messages)
        llm_call_count = len([
            m for m in messages
            if m.role == "assistant" and m.llm_call_id
        ])
        failed_tool_count = sum(1 for tc in tool_calls if tc.is_failed)
        tool_counts = Counter(tc.name for tc in tool_calls)

        meta = {}
        meta_path = path.with_suffix(".meta.json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {}

        started_at = ""
        ended_at = ""
        for ev in events:
            if ev.get("timestamp"):
                if not started_at:
                    started_at = ev.get("timestamp", "")
                ended_at = ev.get("timestamp", "")

        agent_id = path.stem.replace("agent-", "")
        summary = {
            "agent_id": agent_id,
            "agent_type": meta.get("agentType", ""),
            "description": meta.get("description", ""),
            "llm_call_count": llm_call_count,
            "llm_error_count": 0,
            "assistant_event_count": sum(1 for ev in events if ev.get("type") == "assistant"),
            "tool_call_count": len(tool_calls),
            "failed_tool_count": failed_tool_count,
            "tool_counts": dict(tool_counts.most_common()),
            "input_tokens": usage_totals["input_tokens"],
            "output_tokens": usage_totals["output_tokens"],
            "cache_read_input_tokens": usage_totals["cache_read_input_tokens"],
            "cache_creation_input_tokens": usage_totals["cache_creation_input_tokens"],
            "started_at": started_at,
            "ended_at": ended_at,
            "status": "error" if failed_tool_count else "ok",
        }

        for tc in tool_calls:
            tc.scope = "subagent"
            tc.subagent_id = agent_id

        runs.append({
            "path": path,
            "summary": summary,
            "tool_calls": tool_calls,
            "messages": messages,
        })

    return runs


def _attach_subagents_to_agent_tools(
    tool_calls: list[ToolCall],
    subagent_runs: list[dict],
) -> None:
    """Attach parsed sidechain summaries to the matching parent Agent tool."""
    remaining = list(subagent_runs)
    for tc in tool_calls:
        if tc.name != "Agent" or not remaining:
            continue
        params = tc.parameters if isinstance(tc.parameters, dict) else {}
        description = params.get("description", "")
        subagent_type = params.get("subagent_type", "")

        match_index = None
        for idx, run in enumerate(remaining):
            summary = run["summary"]
            if description and summary.get("description") == description:
                match_index = idx
                break
            if subagent_type and summary.get("agent_type") == subagent_type:
                match_index = idx
                break
        if match_index is None:
            match_index = 0

        run = remaining.pop(match_index)
        summary = run["summary"]
        tc.subagent_summary = summary
        tc.llm_call_count = summary.get("llm_call_count", 0)
        tc.llm_error_count = summary.get("llm_error_count", 0)
        tc.subagent_tool_call_count = summary.get("tool_call_count", 0)
        tc.subagent_failed_tool_count = summary.get("failed_tool_count", 0)
        for child in run["tool_calls"]:
            child.parent_tool_use_id = tc.tool_use_id
            child.parent_tool_name = tc.name


def _flatten_subagent_tool_calls(subagent_runs: list[dict]) -> list[ToolCall]:
    """Return all parsed child tool calls."""
    flattened: list[ToolCall] = []
    for run in subagent_runs:
        flattened.extend(run["tool_calls"])
    return flattened


def _apply_subagent_totals(
    summary: SessionSummary,
    subagent_runs: list[dict],
    tool_calls: list[ToolCall],
) -> None:
    """Add subagent traffic into session-level diagnostic totals."""
    summary.tool_call_count = len(tool_calls)
    summary.failed_tool_count = sum(1 for tc in tool_calls if tc.is_failed)
    for run in subagent_runs:
        s = run["summary"]
        summary.input_tokens += s.get("input_tokens", 0)
        summary.output_tokens += s.get("output_tokens", 0)
        summary.cached_input_tokens += s.get("cache_read_input_tokens", 0)
        summary.cached_output_tokens += s.get("cache_creation_input_tokens", 0)


def _extract_tool_calls(
    events: list[dict],
    messages: list[ChatMessage],
) -> list[ToolCall]:
    """Extract tool call records from assistant messages.

    Enhanced to detect:
    - Failed tool calls (error in tool_result)
    - Exit codes (for Bash tools)
    - Files touched (for Read/Write/Edit tools)
    """
    tool_calls = []

    # Build a map of tool_use_id → tool_result for status/result display.
    # We only extract the JSONL is_error flag and raw content here;
    # the heuristic is applied later once we know the tool name.
    tool_results: dict[str, dict] = {}
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
                    result_text = _stringify_tool_result(result_content)
                    tool_results[tool_use_id] = {
                        "is_error_raw": item.get("is_error") is True,
                        "result_text": result_text,
                    }

    # Extract tool calls from assistant messages
    for msg in messages:
        if msg.role != "assistant":
            continue
        for tc in msg.tool_calls:
            tool_use_id = tc.get("id", "")
            name = tc.get("name", "")
            params = tc.get("parameters", {})

            # Try to find matching tool result
            raw = tool_results.get(tool_use_id, {})
            is_error = raw.get("is_error_raw", False)
            result_text = raw.get("result_text", "")

            # Apply heuristic now that we know the tool name
            if _tool_result_looks_failed(result_text, tool_name=name):
                is_error = True

            exit_code = None
            exit_match = re.search(r"exit code[:\s]*(\d+)", result_text, re.IGNORECASE)
            if exit_match:
                exit_code = int(exit_match.group(1))
                # Do NOT set is_error from nonzero exit_code.
                # exit_code records the command's return status, which may be
                # business logic (e.g. rg found no matches), not a tool failure.

            error_msg = result_text[:500] if is_error else ""

            status = "error" if is_error else "completed"
            result = result_text[:2000]
            files_touched = []

            # For Read/Write/Edit tools, extract file path from params
            file_path = (
                params.get("file_path", "")
                or params.get("path", "")
                or params.get("file_path", "")
            )
            if file_path:
                files_touched.append(file_path)

            # For Grep/Glob, extract pattern
            # For Bash, extract command

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
            ))

    return tool_calls


def scan_all_sessions() -> Iterator[SessionSummary]:
    """Scan all Claude sessions and yield SessionSummary for each.

    This is the main entry point for the indexer.
    It reads history.jsonl for the session list, then parses each session file.
    """
    history = parse_history()

    # Group by project
    # session_id -> project mapping
    session_projects = {}
    for entry in history:
        session_projects[entry["session_id"]] = entry["project"]

    for entry in history:
        sid = entry["session_id"]
        project = entry["project"]
        summary, _msgs, _tcs, _sa = parse_session_detail(project, sid, history_entry=entry)
        # Ensure title from history if empty (fallback)
        if not summary.title and entry.get("display"):
            summary.title = _extract_readable_title(entry["display"])
        yield summary
