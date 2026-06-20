"""ID resolution，用于 session identifiers.

Extracted from routes.py. Handles Qoder short ID → canonical full UUID
resolution.
"""

from __future__ import annotations

import re

_UUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)


def _resolve_qoder_short_id(short_id: str) -> tuple[str | None, str | None]:
    """Resolve 一个 Qoder short ID to its canonical full UUID.

    Returns (resolved_id, error_message):
    - (full_uuid, None) when exactly one full UUID has short_id as prefix.
    - (None, error_message) when multiple matches exist (ambiguous).
    - (None, None) when no match found or short_id looks like a full UUID.
    """
    if not short_id or _UUID_PATTERN.match(short_id):
        return None, None

    from session_browser.sources.qoder import _build_canonical_id_map
    canonical_map = _build_canonical_id_map()
    resolved = canonical_map.get(short_id.lower())
    if resolved:
        return resolved, None

    # 说明：Not in pre-built map — fall back to direct prefix scan
    from session_browser.sources.qoder import _discover_sessions
    uuid_pattern = _UUID_PATTERN
    full_uuids: list[str] = []
    for _pk, sid, _fp in _discover_sessions():
        if uuid_pattern.match(sid) and sid.lower().startswith(short_id.lower()):
            full_uuids.append(sid.lower())

    if len(full_uuids) == 1:
        return full_uuids[0], None
    elif len(full_uuids) > 1:
        return None, (
            f"Short ID '{short_id}' matches {len(full_uuids)} sessions "
            f"(ambiguous). Use the full UUID to disambiguate."
        )
    return None, None
