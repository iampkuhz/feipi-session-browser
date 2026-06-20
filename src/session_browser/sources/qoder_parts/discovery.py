"""Qoder session 发现逻辑。

Walks ~/.qoder/projects/ (CLI) and ~/.qoder/cache/projects/ (GUI) to
discover session files and build canonical ID mappings.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

from session_browser.config import QODER_DATA_DIR


def _url_decode_path(path: str) -> str:
    """URL-decode 一个 path string (e.g. 'Users%2Fzhehan%2F...' -> 'Users/zhehan/...')."""
    if not path:
        return ""
    return urllib.parse.unquote(path)


def _extract_cwd_from_events(events: list[dict]) -> str:
    """提取 该 actual project working directory，来源于 Qoder events."""
    for ev in events:
        if ev.get("type") == "user":
            cwd = ev.get("cwd", "")
            if cwd:
                return cwd
    return ""


def _discover_sessions() -> list[tuple[str, str, Path]]:
    """Walk ~/.qoder/projects/ 和 discover 所有 CLI session files.

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
                session_id = fname[:-6]  # 说明：strip .jsonl
                # project_key is 该 URL-decoded relative path，来源于 projects/
                raw_key = str(Path(root).relative_to(projects_dir))
                project_key = _url_decode_path(raw_key)
                # If decoded path is meaningless ("." 或 empty), use the
                # 说明：actual filesystem directory name as fallback.
                if not project_key or project_key == ".":
                    project_key = root.name
                results.append((project_key, session_id, fpath))
    return results


def _discover_cache_sessions() -> list[tuple[str, str, Path]]:
    """Walk ~/.qoder/cache/projects/ 和 discover GUI session files.

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
                session_id = fname[:-6]  # 说明：strip .jsonl
                # project_key is 该 relative path，来源于 cache/projects/,
                # but 仅 该 project name (first segment under cache/projects/)
                rel = Path(root).relative_to(cache_dir)
                # 说明：rel could be like "my-project-abc123/conversation-history/session-id"
                # We 仅 want 该 project name (first segment), cleaned of hash suffix
                project_name = rel.parts[0] if rel.parts else ""
                # 说明：Strip trailing hash: "project-name-462acd20" -> "project-name"
                project_name = re.sub(r'-[0-9a-f]{6,}$', '', project_name)
                results.append((project_name, session_id, fpath))
    return results


def _build_canonical_id_map() -> dict[str, str]:
    """构建 一个 mapping，来源于 discovered session IDs to their canonical full UUIDs.

    Strategy:
    1. Collect all full UUID-format IDs from projects/ (the authoritative source).
    2. For each short ID from cache/projects/, check if it is an exact prefix
       of exactly one full UUID.
    3. If a unique prefix match exists, map short_id -> full_uuid.
    4. If ambiguous (multiple full UUIDs share the same prefix) or no match,
       leave the short ID unmapped (no merge; separate record).

    Returns dict mapping {short_id: full_uuid}. Only safe prefix matches are included.
    """
    # Full UUIDs，来源于 projects/ -- use regex to validate UUID format
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

    # 构建 short_id -> full_uuid mapping (only unique prefix matches)
    canonical_map: dict[str, str] = {}
    for short_id in short_ids:
        matches = [uuid for uuid in full_uuids if uuid.startswith(short_id)]
        if len(matches) == 1:
            canonical_map[short_id] = matches[0]
        # If 0 或 >1 matches, do NOT merge -- fuse condition

    return canonical_map
