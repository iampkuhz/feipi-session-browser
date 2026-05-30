"""Parser for Qoder local session data.

Qoder is a Claude Code-based IDE agent. Its data format closely mirrors
Claude Code's:
- ~/.qoder/projects/{url_encoded_path}/{sessionId}.jsonl: full conversation event stream
- No central history.jsonl — sessions are discovered by scanning projects/

Events share the same type/message/timestamp structure as Claude Code,
with additional fields: agentId, isMeta, userType, version.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.parse
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Optional

from session_browser.config import QODER_DATA_DIR
from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall
from session_browser.domain.token_normalizer import normalize_qoder_sqlite_unified, TokenPrecision as TP, TokenProvider
from session_browser.sources.jsonl_reader import parse_jsonl_events


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


def _scan_project_dirs(project_dir: Path) -> list[str]:
    """Scan project directories for Qoder session data (stub)."""
    return []


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


def _normalize_qoder_provider_usage(records: list[dict]) -> None:
    """Normalize Qoder provider usage into canonical token buckets.

    Qoder logs observed from GUI sessions report ``input_tokens`` as an
    inclusive request input total. The rest of the app expects ``input_tokens``
    to mean fresh input only, with cache read/write stored separately.
    """
    usages: list[dict] = []
    for rec in records:
        usage = rec.get("usage")
        usages.append(usage if isinstance(usage, dict) else {})

    for idx, usage in enumerate(usages):
        if not usage or "input_tokens" not in usage:
            continue

        raw_input_total = int(usage.get("input_tokens", 0) or 0)
        cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
        raw_cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)
        cache_write = raw_cache_write

        if cache_write <= 0 and idx + 1 < len(usages):
            next_cache_read = int(usages[idx + 1].get("cache_read_input_tokens", 0) or 0)
            if next_cache_read > cache_read:
                cache_write = next_cache_read - cache_read

        fresh = max(raw_input_total - cache_read - cache_write, 0)

        usage["qoder_input_tokens_total"] = raw_input_total
        usage["qoder_cache_write_inferred"] = raw_cache_write <= 0 and cache_write > 0
        usage["input_tokens"] = fresh
        usage["cache_read_input_tokens"] = cache_read
        usage["cache_creation_input_tokens"] = cache_write


def _extract_qoder_model(record: dict) -> str | None:
    """Extract model from a Qoder assistant record with fallback strategy.

    Priority order:
    1. record["model"] — from message.model (primary, already working)
    2. record["top_level_model"] — from event top-level "model" field
    3. record["metadata_model"] — from event metadata.model
    4. record["raw_model"] — from request/response explicit model field

    Returns None if no model found in any source.
    """
    for key in ("model", "top_level_model", "metadata_model", "raw_model"):
        value = record.get(key, "")
        if value:
            return value
    return None


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
                "top_level_model": ev.get("model", ""),
                "metadata_model": (ev.get("metadata") or {}).get("model", ""),
                "raw_model": "",
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
        if ev.get("model"):
            rec["top_level_model"] = ev.get("model", "")
        metadata_model = (ev.get("metadata") or {}).get("model", "")
        if metadata_model:
            rec["metadata_model"] = metadata_model
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
                # Priority 4: look for explicit model field in request/response content
                if isinstance(item, dict) and item.get("model"):
                    rec["raw_model"] = item.get("model", "")

    merged_records = []
    for key in order:
        rec = records[key]
        rec["usage"] = _merge_usage_dicts(rec.pop("usage_rows"))
        merged_records.append(rec)
    _normalize_qoder_provider_usage(merged_records)
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


def _qoder_app_support_dir() -> Path:
    """Return Qoder's Electron/VSCode-style application support directory."""
    return Path(os.environ.get(
        "QODER_APP_SUPPORT_DIR",
        str(Path.home() / "Library" / "Application Support" / "Qoder"),
    ))


@lru_cache(maxsize=4)
def _load_qoder_custom_model_names(app_support_dir: Path | None = None) -> dict[str, str]:
    """Load custom model id -> display name from Qoder global state.

    Qoder stores BYOK API keys separately under secret:// keys in the same DB.
    This function only reads the non-secret aicoding.customModels value.
    """
    app_support_dir = app_support_dir or _qoder_app_support_dir()
    db_path = app_support_dir / "User" / "globalStorage" / "state.vscdb"
    if not db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            ("aicoding.customModels",),
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return {}

    if not row or not row[0]:
        return {}

    try:
        models = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return {}

    result: dict[str, str] = {}
    if not isinstance(models, list):
        return result

    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "")
        if not model_id:
            continue
        name = str(item.get("alias") or item.get("model") or model_id)
        result[model_id] = name
        result[f"custom:{model_id}"] = name
    return result


@lru_cache(maxsize=4)
def _load_qoder_model_selector_names(app_support_dir: Path | None = None) -> dict[str, str]:
    """Load built-in Qoder model selector labels such as qmodel -> Qwen3.6-Plus."""
    app_support_dir = app_support_dir or _qoder_app_support_dir()
    cache_path = app_support_dir / "User" / "dynamic-text-cache.json"
    if not cache_path.exists():
        return {}

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    labels: dict[str, str] = {}

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if (
                    isinstance(key, str)
                    and key.startswith("modelSelector.item.")
                    and "." not in key.removeprefix("modelSelector.item.")
                    and isinstance(item, str)
                ):
                    labels[key.removeprefix("modelSelector.item.")] = item
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return labels


@lru_cache(maxsize=1)
def _load_qoder_auth_model_names() -> dict[str, str]:
    """Load model key -> display name from Qoder's model cache file."""
    cache_path = QODER_DATA_DIR / ".auth" / "models"
    if not cache_path.exists():
        return {}

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    labels: dict[str, str] = {}
    if not isinstance(data, dict):
        return labels

    for models in data.values():
        if not isinstance(models, list):
            continue
        for item in models:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            display_name = str(item.get("display_name") or "")
            if key and display_name:
                labels[key] = display_name
    return labels


def _resolve_qoder_model_config_name(
    model_config: str,
    custom_names: dict[str, str] | None = None,
    selector_names: dict[str, str] | None = None,
    auth_names: dict[str, str] | None = None,
) -> str:
    """Resolve a Qoder model config id to a human-readable model label."""
    model_config = (model_config or "").strip()
    if not model_config:
        return ""

    if custom_names is None:
        custom_names = _load_qoder_custom_model_names()
    if selector_names is None:
        selector_names = _load_qoder_model_selector_names()
    if auth_names is None:
        auth_names = _load_qoder_auth_model_names()

    if model_config in custom_names:
        return custom_names[model_config]

    if model_config.startswith("custom:"):
        custom_id = model_config.split(":", 1)[1]
        return custom_names.get(custom_id, model_config)

    if model_config in selector_names:
        return selector_names[model_config]
    if model_config in auth_names:
        return auth_names[model_config]

    # Qoder has scoped ids such as quest-auto and experts-ultimate.
    if "-" in model_config:
        suffix = model_config.rsplit("-", 1)[1]
        if suffix in selector_names:
            return selector_names[suffix]
        if suffix in auth_names:
            return auth_names[suffix]

    return model_config


@lru_cache(maxsize=4)
def _load_qoder_current_assistant_model(app_support_dir: Path | None = None) -> str:
    """Load Qoder's current assistant model selector from global state.

    Some Qoder project sessions are created by the client without writing a
    per-session model into JSONL or agent.log. The selector state records the
    currently chosen assistant model without exposing BYOK secret values.
    """
    app_support_dir = app_support_dir or _qoder_app_support_dir()
    db_path = app_support_dir / "User" / "globalStorage" / "state.vscdb"
    if not db_path.exists():
        return ""

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            ("chat.modelConfig.assistant",),
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return ""

    if not row or not row[0]:
        return ""

    return _resolve_qoder_model_config_name(
        str(row[0]),
        custom_names=_load_qoder_custom_model_names(app_support_dir),
        selector_names=_load_qoder_model_selector_names(app_support_dir),
        auth_names=_load_qoder_auth_model_names(),
    )


@lru_cache(maxsize=4)
def _build_qoder_session_model_map(app_support_dir: Path | None = None) -> dict[str, str]:
    """Build session_id -> model label from Qoder GUI agent logs."""
    app_support_dir = app_support_dir or _qoder_app_support_dir()
    logs_dir = app_support_dir / "logs"
    if not logs_dir.exists():
        return {}

    custom_names = _load_qoder_custom_model_names(app_support_dir)
    selector_names = _load_qoder_model_selector_names(app_support_dir)
    auth_names = _load_qoder_auth_model_names()

    session_models: dict[str, str] = {}
    patterns = [
        re.compile(r"activeModelConfig=(?P<model>[^,\s]+).*sessionId=(?P<sid>[^,\s]+)"),
        re.compile(
            r"getCurrentModelConfig: sessionId=(?P<sid>[^,\s]+), "
            r"returning (?:from \w+: )?(?P<model>[^,\s]+)"
        ),
    ]

    for log_path in logs_dir.glob("**/agent.log"):
        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            if "ModelConfigService" not in line and "ModelSelector" not in line:
                continue
            for pattern in patterns:
                match = pattern.search(line)
                if not match:
                    continue
                session_id = match.group("sid").strip()
                model_config = match.group("model").strip()
                if not session_id or session_id == "none":
                    continue
                model = _resolve_qoder_model_config_name(
                    model_config,
                    custom_names=custom_names,
                    selector_names=selector_names,
                    auth_names=auth_names,
                )
                if model:
                    session_models[session_id] = model
                    if session_id.startswith("blank_session_"):
                        session_models[session_id.removeprefix("blank_session_")] = model
                break

    prefix_models: dict[str, set[str]] = {}
    uuid_pattern = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    for session_id, model in session_models.items():
        if uuid_pattern.match(session_id):
            prefix_models.setdefault(session_id[:8].lower(), set()).add(model)
    for prefix, models in prefix_models.items():
        if prefix not in session_models and len(models) == 1:
            session_models[prefix] = next(iter(models))

    return session_models


def _infer_qoder_model_for_session(session_id: str) -> str:
    """Infer a Qoder model from persisted GUI logs/config for one session."""
    if not session_id:
        return ""
    app_support_dir = _qoder_app_support_dir()
    session_model = _build_qoder_session_model_map(app_support_dir).get(session_id, "")
    if session_model:
        return session_model
    if not re.match(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        session_id,
    ):
        return ""
    return _load_qoder_current_assistant_model(app_support_dir)


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
    """Walk ~/.qoder/projects/ and discover all CLI session files.

    Returns list of (project_key, session_id, file_path).
    project_key is URL-decoded from the directory name.
    If the decoded path is "." or empty, falls back to the actual
    directory name to avoid meaningless project keys.
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
                # If decoded path is meaningless ("." or empty), use the
                # actual filesystem directory name as fallback.
                if not project_key or project_key == ".":
                    project_key = root.name
                results.append((project_key, session_id, fpath))
    return results


def _discover_cache_sessions() -> list[tuple[str, str, Path]]:
    """Walk ~/.qoder/cache/projects/ and discover GUI session files.

    GUI sessions are stored as:
      cache/projects/{project-name}/conversation-history/{session_id}/{session_id}.jsonl

    Returns list of (project_key, session_id, file_path).
    """
    cache_dir = QODER_DATA_DIR / "cache" / "projects"
    if not cache_dir.exists():
        return []

    results = []
    for root, _dirs, files in os.walk(cache_dir):
        for fname in files:
            if fname.endswith(".jsonl"):
                fpath = Path(root) / fname
                session_id = fname[:-6]  # strip .jsonl
                # project_key is the relative path from cache/projects/,
                # but only the project name (first segment under cache/projects/)
                rel = Path(root).relative_to(cache_dir)
                # rel could be like "my-project-abc123/conversation-history/session-id"
                # We only want the project name (first segment), cleaned of hash suffix
                project_name = rel.parts[0] if rel.parts else ""
                # Strip trailing hash: "project-name-462acd20" → "project-name"
                project_name = re.sub(r'-[0-9a-f]{6,}$', '', project_name)
                results.append((project_name, session_id, fpath))
    return results


def _build_canonical_id_map() -> dict[str, str]:
    """Build a mapping from discovered session IDs to their canonical full UUIDs.

    Strategy:
    1. Collect all full UUID-format IDs from projects/ (the authoritative source).
    2. For each short ID from cache/projects/, check if it is an exact prefix
       of exactly one full UUID.
    3. If a unique prefix match exists, map short_id -> full_uuid.
    4. If ambiguous (multiple full UUIDs share the same prefix) or no match,
       leave the short ID unmapped (no merge; separate record).

    Returns dict mapping {short_id: full_uuid}. Only safe prefix matches are included.
    """
    # Full UUIDs from projects/ — use regex to validate UUID format
    uuid_pattern = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )
    full_uuids: list[str] = []
    for _pk, sid, _fp in _discover_sessions():
        if uuid_pattern.match(sid):
            full_uuids.append(sid.lower())

    short_ids: list[str] = []
    for _pk, sid, _fp in _discover_cache_sessions():
        if not uuid_pattern.match(sid):
            short_ids.append(sid.lower())

    # Build short_id -> full_uuid mapping (only unique prefix matches)
    canonical_map: dict[str, str] = {}
    for short_id in short_ids:
        matches = [uuid for uuid in full_uuids if uuid.startswith(short_id)]
        if len(matches) == 1:
            canonical_map[short_id] = matches[0]
        # If 0 or >1 matches, do NOT merge — fuse condition

    return canonical_map


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

    Search order (optimised for old-index scenarios where file_path is missing):
    1. Resolve short ID alias -> full UUID via canonical map, then search projects/.
    2. Search projects/ (CLI sessions) by session_id — direct match then recursive.
    3. Fall back to cache/projects/ (GUI sessions) — recursive walk.

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
            # Short ID resolved to full UUID — try projects/ direct match
            projects_dir = QODER_DATA_DIR / "projects"
            if projects_dir.exists():
                # Try with original project_key
                candidate = projects_dir / project_key / f"{resolved_id}.jsonl"
                if candidate.exists():
                    return candidate
                # Also search all project dirs (project_key may be stale)
                for root, _dirs, files in os.walk(projects_dir):
                    if f"{resolved_id}.jsonl" in files:
                        return Path(root) / f"{resolved_id}.jsonl"

    # Step 2: search projects/ by original session_id
    projects_dir = QODER_DATA_DIR / "projects"
    if projects_dir.exists():
        # Try direct match
        candidate = projects_dir / project_key / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate

        # Search all project directories
        for root, _dirs, files in os.walk(projects_dir):
            if f"{session_id}.jsonl" in files:
                return Path(root) / f"{session_id}.jsonl"

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
        extracted_model = _extract_qoder_model(rec)
        if not model and extracted_model:
            model = extracted_model

    if not model:
        model = _infer_qoder_model_for_session(session_id)

    # Fallback: Qoder may not report usage — estimate from event text.
    # Use per-message estimates to ensure session summary matches LLM Calls detail.
    est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
    if has_estimated and input_tokens == 0 and output_tokens == 0:
        input_tokens = est_input
        output_tokens = est_output
        # Qoder has no cache metrics; do not fabricate cache values.
        cached_tokens = 0
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

    # Use cwd from events as the primary project_key — it holds the actual
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

    # Scan cache (GUI) sessions — canonicalize short IDs to full UUIDs
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
