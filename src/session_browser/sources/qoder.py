"""Parser for Qoder local session data.

Qoder is a Claude Code-based IDE agent. Its data format closely mirrors
Claude Code's:
- ~/.qoder/projects/{url_encoded_path}/{sessionId}.jsonl: full conversation event stream
- No central history.jsonl — sessions are discovered by scanning projects/

Events share the same type/message/timestamp structure as Claude Code,
with additional fields: agentId, isMeta, userType, version.

All paths configurable via QODER_DATA_DIR env var.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from session_browser.config import QODER_DATA_DIR
from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall
from session_browser.domain.token_normalizer import normalize_tokens, TokenPrecision, TokenProvider


# ─── Interval merging (shared with Claude) ──────────────────────────────


def _merge_intervals(intervals: list[tuple[int, int]], max_gap_ms: int = 300_000) -> int:
    """Merge overlapping intervals and return total merged duration in milliseconds.

    Filters out individual intervals longer than max_gap_ms (likely idle time).
    """
    if not intervals:
        return 0
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


# ─── Token estimation (Qoder does not log usage) ──────────────────────────
#
# Qoder 估算固定走 byte-level 启发式，避免 tiktoken encode 的额外开销。
# tiktoken 不在此模块引入，留给非 qoder provider 或未来精确模式使用。

# Max text length to scan for token estimation (32KB). Beyond this, text is
# truncated before counting to keep estimation fast.
_ESTIMATE_TEXT_CAP = 32 * 1024


def _cap_text(s: str) -> str:
    """Truncate text to _ESTIMATE_TEXT_CAP bytes for fast estimation."""
    if not s:
        return ""
    byte_len = len(s.encode("utf-8"))
    if byte_len <= _ESTIMATE_TEXT_CAP:
        return s
    # Truncate by characters to stay under cap.
    avg_bytes = byte_len / len(s)
    safe_chars = int(_ESTIMATE_TEXT_CAP / avg_bytes)
    truncated = s[:safe_chars]
    while len(truncated.encode("utf-8")) > _ESTIMATE_TEXT_CAP and len(truncated) > 0:
        truncated = truncated[:-100]
    return truncated


def _count_tokens(s: str) -> int:
    """Byte-length heuristic for Chinese/English/code mix."""
    capped = _cap_text(s or "")
    return max(1, int(len(capped.encode("utf-8")) / 3.5))


def normalize_timestamp(ts) -> str:
    """Convert timestamp (ISO8601 str or Unix int/float) to local-time ISO8601 str.

    Handles ISO8601 strings, Unix seconds (int/float), and Unix milliseconds
    (large ints > 1e12).
    """
    if not ts:
        return ""
    dt = None
    if isinstance(ts, (int, float)):
        # Detect millisecond timestamps (> 1e12) and convert to seconds
        actual_ts = ts / 1000 if ts > 1e12 else ts
        dt = datetime.fromtimestamp(actual_ts, tz=timezone.utc).astimezone()
    elif isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
        except (ValueError, TypeError):
            return ""
    if dt is None:
        return ""
    return dt.isoformat()


def _ts_ms_to_iso(ts_ms: int | float) -> str:
    """Convert millisecond timestamp to local-time ISO8601 string."""
    if not ts_ms:
        return ""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone()
    return dt.isoformat()


def _parse_session_events(path: Path) -> list[dict]:
    """Parse a single session .jsonl event stream file."""
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
    """Merge duplicated usage snapshots for one logical response."""
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
    """Merge assistant fragments by message id."""
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
    """Extract human-visible user text, ignoring meta/command events."""
    # Skip meta events (internal commands like /login, /model)
    if ev.get("isMeta") is True:
        return ""
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
                text = item.get("text", "")
                # Filter out system caveats
                if text and "Caveat: The messages below were generated" not in text:
                    parts.append(text)
        return "\n".join(p for p in parts if p)
    return ""


def _summarize_text(text: str, max_len: int = 80) -> str:
    """Create a short, readable summary of text."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    sentence_match = re.match(r"^(.+?[.!?])\s", text)
    if sentence_match:
        first_sentence = sentence_match.group(1).strip()
        if len(first_sentence) <= max_len:
            return first_sentence
        return first_sentence[:max_len - 1] + "…"
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def _extract_readable_title(raw_content: str) -> str:
    """Extract a readable title from raw content."""
    if not raw_content:
        return ""
    content = raw_content.strip()
    cmd_match = re.search(r"<command-message>([^<]+)</command-message>", content)
    if cmd_match:
        cmd_name = cmd_match.group(1).strip()
        args_match = re.search(r"<command-args>(.+?)</command-args>", content, re.DOTALL)
        if args_match:
            args_text = args_match.group(1).strip()
            intent = _summarize_text(args_text)
            if intent:
                return f"{cmd_name} · {intent}"
        after_cmd = content[cmd_match.end():].strip()
        if after_cmd:
            intent = _summarize_text(after_cmd)
            if intent:
                return f"{cmd_name} · {intent}"
        return cmd_name
    return _summarize_text(content)


def _stringify_tool_result(result_content) -> str:
    """Convert tool_result content into compact text."""
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
    """Heuristic for **tool runtime failure** in Qoder logs.

    Mirrors the Claude parser's conservative approach: only detect failures
    where the tool itself could not execute. Does NOT treat command output
    containing error keywords or nonzero exit codes as tool failures.

    For Read/Write/Edit/Glob/Grep/LS tools, also detects file-level errors
    (file does not exist, permission denied, etc.).
    """
    text = _stringify_tool_result(result_content).lower()
    if not text:
        return False

    # For Read/Write/Edit/Glob/Grep/LS tools, detect file-level errors
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

    # ── Tool runtime error markers (anchored at line start) ─────
    # These indicate the tool could not execute, not that it ran and
    # produced an error result.
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
            parts = stripped.split(": ")
            if len(parts) > 1:
                last_part = parts[-1].strip()
                if last_part.startswith(marker):
                    return True

    # ── "command not found" at line start or after shell prefix ──
    if re.search(r"(?:^|\n)\s*command not found", text, re.MULTILINE):
        return True
    for line in text.split("\n"):
        stripped = line.strip()
        m = re.match(r"^(?:ba)?sh:\s+.*:\s+command not found", stripped)
        if m:
            return True

    # ── "timeout" at line start ──────────────────────────────────
    if re.search(r"(?:^|\n)\s*timeout\b", text, re.MULTILINE):
        return True

    return False


def _extract_event_text(ev: dict) -> tuple[str, str]:
    """Extract (category, text) from a Qoder event.

    Categories: "user_prompt", "tool_result", "assistant_text", "assistant_tool_call".
    """
    typ = ev.get("type")
    msg = ev.get("message") or {}
    content = msg.get("content")

    if typ == "user":
        if ev.get("isMeta") is True:
            return None, ""
        if isinstance(content, str):
            return "user_prompt", content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if text and "Caveat: The messages below were generated" not in text:
                        parts.append(text)
            if parts:
                return "user_prompt", "\n".join(parts)
            # tool_result content goes back as input on next turn
            tr_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    tr_parts.append(str(item.get("content", "")))
            if tr_parts:
                return "tool_result", "\n".join(tr_parts)

    if typ == "assistant":
        if isinstance(content, list):
            text_parts = []
            tool_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "tool_use":
                        tool_parts.append(json.dumps(item, ensure_ascii=False))
            if tool_parts and not text_parts:
                return "assistant_tool_call", "\n".join(tool_parts)
            if text_parts or tool_parts:
                return "assistant_text", "\n".join(text_parts + tool_parts)

    return None, ""


def _estimate_tokens_from_events(events: list[dict]):
    """Roughly estimate input/output tokens for a Qoder session.

    Qoder does not expose per-call usage in its event logs.  This function
    walks events in order, accumulates visible context tokens, and for each
    assistant logical message (grouped by message id) treats the current
    visible-context size as the estimated input and the message's own token
    count as the estimated output.

    Caveats:
    - Ignores system prompt tokens (always present in real API calls).
    - Assumes no context-window truncation / compression.
    - Tool results are added to visible context as-is.

    Returns (input_tokens, output_tokens, has_estimated) where has_estimated
    is False when real usage data was found in events (so estimation is skipped).
    """
    # First pass: check whether any event already carries usage dict
    has_real_usage = False
    for ev in events:
        if ev.get("type") == "assistant":
            usage = (ev.get("message") or {}).get("usage")
            if isinstance(usage, dict) and usage.get("input_tokens"):
                has_real_usage = True
                break

    if has_real_usage:
        return 0, 0, False

    visible_context_tokens = 0
    estimated_input = 0
    estimated_output = 0
    seen_keys: set[str] = set()

    for ev in events:
        cat, text = _extract_event_text(ev)
        if not cat:
            continue

        tok = _count_tokens(text)

        if cat.startswith("assistant"):
            key = _assistant_message_key(ev)
            if key not in seen_keys:
                # First fragment: capture visible context as input
                seen_keys.add(key)
                estimated_input += visible_context_tokens
                estimated_output += tok
            else:
                # Subsequent fragments: accumulate output only
                estimated_output += tok

        visible_context_tokens += tok

    return estimated_input, estimated_output, True


# ─── Session scanning ─────────────────────────────────────────────────────


def _url_decode_path(path: str) -> str:
    """URL-decode a path string (e.g. 'Users%2Fzhehan%2F...' → 'Users/zhehan/...')."""
    if not path:
        return ""
    return urllib.parse.unquote(path)


def _extract_cwd_from_events(events: list[dict]) -> str:
    """Extract the actual project working directory from Qoder events."""
    for ev in events:
        if ev.get("type") == "user":
            cwd = ev.get("cwd", "")
            if cwd:
                return cwd
    return ""


def _discover_sessions() -> list[tuple[str, str, Path]]:
    """Walk ~/.qoder/projects/ and discover all session files.

    Returns list of (project_key, session_id, file_path).
    project_key is URL-decoded from the directory name.
    """
    projects_dir = QODER_DATA_DIR / "projects"
    if not projects_dir.exists():
        return []

    results = []
    for root, _dirs, files in os.walk(projects_dir):
        for fname in files:
            if fname.endswith(".jsonl"):
                fpath = Path(root) / fname
                session_id = fname[:-6]  # strip .jsonl
                # project_key is the URL-decoded relative path from projects/
                raw_key = str(Path(root).relative_to(projects_dir))
                project_key = _url_decode_path(raw_key)
                results.append((project_key, session_id, fpath))
    return results


def parse_session_detail(
    project_key: str,
    session_id: str,
    session_file: Path | None = None,
) -> tuple[SessionSummary, list[ChatMessage], list[ToolCall], list[dict]]:
    """Parse a single Qoder session's full event stream.

    Args:
        project_key: The project path segment.
        session_id: The session ID.
        session_file: Optional pre-located file path.

    Returns (SessionSummary, chat_messages, tool_calls, subagent_runs).
    """
    if session_file is None:
        session_file = _find_session_file(project_key, session_id)
        if session_file is None:
            s = _empty_session(session_id, project_key)
            return s, [], [], []

    events = _parse_session_events(session_file)
    summary = _build_summary_from_events(events, session_id, project_key)
    messages = _extract_messages(events)
    tool_calls = _extract_tool_calls(events, messages)

    return summary, messages, tool_calls, []


def _find_session_file(project_key: str, session_id: str) -> Path | None:
    """Search for a session file under projects/."""
    projects_dir = QODER_DATA_DIR / "projects"
    if not projects_dir.exists():
        return None

    # Try direct match
    candidate = projects_dir / project_key / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate

    # Search all project directories
    for root, _dirs, files in os.walk(projects_dir):
        if f"{session_id}.jsonl" in files:
            return Path(root) / f"{session_id}.jsonl"
    return None


def _empty_session(session_id: str, project_key: str) -> SessionSummary:
    """Create an empty session summary as fallback."""
    from pathlib import PurePosixPath
    project_name = PurePosixPath(project_key).name if project_key else "unknown"
    return SessionSummary(
        agent="qoder",
        session_id=session_id,
        title="",
        project_key=project_key,
        project_name=project_name,
        cwd="",
        started_at="",
        ended_at="",
    )


def _build_summary_from_events(
    events: list[dict],
    session_id: str,
    project_key: str,
) -> SessionSummary:
    """Build SessionSummary from parsed Qoder events.

    Computes timeline-based execution times:
    - model_execution_seconds: merged LLM response intervals (user msg → assistant msg)
    - tool_execution_seconds: merged tool intervals (tool_use → tool_result),
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

    # Fallback: Qoder may not report usage — estimate from event text.
    # Use per-message estimates to ensure session summary matches LLM Calls detail.
    est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
    if has_estimated and input_tokens == 0 and output_tokens == 0:
        input_tokens = est_input
        output_tokens = est_output
        # Qoder has no cache metrics; do not fabricate cache values.
        cache_write_tokens = 0

    # ─── Collect timestamps for interval calculation ───
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

    # ─── Model execution: LLM response intervals (user → next assistant) ───
    llm_intervals: list[tuple[int, int]] = []
    sorted_user_ts = sorted(user_event_timestamps)
    sorted_assistant_ts = sorted(assistant_event_timestamps)
    for u_ts in sorted_user_ts:
        for a_ts in sorted_assistant_ts:
            if a_ts > u_ts:
                llm_intervals.append((u_ts, a_ts))
                break

    # ─── Tool execution: tool_use → tool_result intervals ───
    tool_intervals: list[tuple[int, int]] = []
    for tool_id, use_ts in tool_use_map.items():
        if tool_id in tool_result_map:
            tool_intervals.append((use_ts, tool_result_map[tool_id]))

    model_execution_seconds = _merge_intervals(llm_intervals) / 1000.0
    tool_execution_seconds = _merge_intervals(tool_intervals) / 1000.0

    # Use cwd from events as the primary project_key — it holds the actual
    # filesystem path. Fall back to the directory-based project_key (URL-decoded).
    actual_project = cwd if cwd else project_key
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

                token_bd = normalize_tokens(final_usage, model=model) if final_usage else None
                # Override precision and provider for estimated usage
                if final_usage and final_usage.get("estimated") and token_bd:
                    token_bd.precision = TokenPrecision.ESTIMATED
                    token_bd.provider = TokenProvider.QODER

                request_full = "\n\n".join(p for p in pending_request_parts if p)
                pending_request_parts = []

                messages.append(ChatMessage(
                    role="assistant",
                    content="\n".join(text_parts),
                    timestamp=normalize_timestamp(rec.get("timestamp", "")),
                    model=model,
                    tool_calls=tool_calls,
                    usage=final_usage,
                    token_breakdown=token_bd,
                    llm_call_id=rec.get("id", ""),
                    request_full=request_full,
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

    # Build a map of tool_use_id → tool_result for status/result display
    # and tool_use_id → result timestamp for duration_ms calculation
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
            result = result_text[:2000]
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


def scan_all_sessions() -> Iterator[SessionSummary]:
    """Scan all Qoder sessions and yield SessionSummary for each.

    Walks ~/.qoder/projects/ to discover session files, then parses each.
    """
    discovered = _discover_sessions()

    for project_key, session_id, fpath in discovered:
        summary, _msgs, _tcs, _sa = parse_session_detail(
            project_key, session_id, session_file=fpath
        )
        yield summary
