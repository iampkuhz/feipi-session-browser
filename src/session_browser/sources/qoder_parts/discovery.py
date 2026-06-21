"""Source adapter helpers for reading local agent session data.

Scanner and route code call this module to discover and normalize records.
It keeps raw parsing behavior unchanged.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

from session_browser.config import QODER_DATA_DIR


def _url_decode_path(path: str) -> str:
    """_url_decode_path function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        path: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not path:
        return ''
    return urllib.parse.unquote(path)


def _extract_cwd_from_events(events: list[dict]) -> str:
    """_extract_cwd_from_events function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        events: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    for ev in events:
        if ev.get('type') == 'user':
            cwd = ev.get('cwd', '')
            if cwd:
                return cwd
    return ''


def _discover_sessions() -> list[tuple[str, str, Path]]:
    """_discover_sessions function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    projects_dir = QODER_DATA_DIR / 'projects'
    if not projects_dir.exists():
        return []

    results = []
    for root, _dirs, files in os.walk(projects_dir):
        for fname in files:
            if fname.endswith('.jsonl'):
                fpath = Path(root) / fname
                session_id = fname[:-6]  # 说明:strip .jsonl
                # project_key is 该 URL-decoded relative path,来源于 projects/
                raw_key = str(Path(root).relative_to(projects_dir))
                project_key = _url_decode_path(raw_key)
                # If decoded path is meaningless ("." 或 empty), use the
                # 说明:actual filesystem directory name as fallback.
                if not project_key or project_key == '.':
                    project_key = root.name
                results.append((project_key, session_id, fpath))
    return results


def _discover_cache_sessions() -> list[tuple[str, str, Path]]:
    """_discover_cache_sessions function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    cache_dir = QODER_DATA_DIR / 'cache' / 'projects'
    if not cache_dir.exists():
        return []

    results = []
    for root, _dirs, files in os.walk(cache_dir):
        for fname in files:
            if fname.endswith('.jsonl'):
                fpath = Path(root) / fname
                session_id = fname[:-6]  # 说明:strip .jsonl
                # project_key is 该 relative path,来源于 cache/projects/,
                # but 仅 该 project name (first segment under cache/projects/)
                rel = Path(root).relative_to(cache_dir)
                # 说明:rel could be like "my-project-abc123/conversation-history/session-id"
                # We 仅 want 该 project name (first segment), cleaned of hash suffix
                project_name = rel.parts[0] if rel.parts else ''
                # 说明:Strip trailing hash: "project-name-462acd20" -> "project-name"
                project_name = re.sub(r'-[0-9a-f]{6,}$', '', project_name)
                results.append((project_name, session_id, fpath))
    return results


def _build_canonical_id_map() -> dict[str, str]:
    """_build_canonical_id_map function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    # Full UUIDs,来源于 projects/ -- use regex to validate UUID format
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
