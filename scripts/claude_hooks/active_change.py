"""Resolve the active OpenSpec change for Claude hook events.

The hook runtime reads ``tmp/active_change.json`` when command, write, or stop events
need to tag evidence with a change id. Invalid or missing input falls back to a stable
UTC date based id, so hook failures do not block normal agent operation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from .paths import RepoPaths


# 01. 默认 change-id
def default_change_id() -> str:
    """Return the fallback change id used when active change input is unavailable.

    Returns:
        Date-based fallback change id.
    """
    return 'adhoc-' + datetime.now(timezone.utc).strftime('%Y%m%d')


# 02. JSON 安全读取
def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object without raising hook runtime errors.

    Args:
        path: JSON file to read.

    Returns:
        Parsed object when the file exists and contains a JSON object; otherwise an
        empty dictionary. Parse failures are swallowed because hook evidence should be
        best-effort rather than user-blocking.
    """
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


# 03. active_change 读取
def read_active_change(paths: RepoPaths) -> dict[str, Any]:
    """Read active change metadata for a hook event.

    Args:
        paths: Repository runtime paths that locate ``tmp/active_change.json``.

    Returns:
        Active change metadata, or a default record containing ``changeId`` when no
        active change file is available.
    """
    data = _read_json(paths.active_change)
    if data:
        return data
    return {'changeId': default_change_id(), 'source': 'default'}


# 04. change-id 提取
def current_change_id(paths: RepoPaths) -> str:
    """Return the change id used to label hook evidence.

    Args:
        paths: Repository runtime paths that locate active change metadata.

    Returns:
        ``changeId`` or ``change_id`` from active metadata, falling back to a generated
        id. The fallback keeps post-write evidence recording non-blocking.
    """
    data = read_active_change(paths)
    return str(data.get('changeId') or data.get('change_id') or default_change_id())
