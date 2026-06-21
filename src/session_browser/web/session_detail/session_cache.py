"""说明:In-memory session data cache.

Extracted from routes.py. Provides a short-lived cache for parsed session
data so that round lazy-load, payload fetch, and attribution API calls
don't re-parse large JSONL files on every request.
"""

from __future__ import annotations

import time

_session_data_cache: dict[str, dict] = {}
_SESSION_CACHE_TTL = 300  # 说明:5 minutes
_session_cache_timestamps: dict[str, float] = {}


def _get_cached_session_data(agent: str, session_id: str) -> dict | None:
    """Get parsed session data,来源于 in-memory cache,如果 still valid."""
    key = f'{agent}:{session_id}'
    ts = _session_cache_timestamps.get(key, 0)
    if ts and (time.time() - ts) < _SESSION_CACHE_TTL:
        return _session_data_cache.get(key)
    # 说明:Evict expired entry
    if key in _session_data_cache:
        del _session_data_cache[key]
        del _session_cache_timestamps[key]
    return None


def _set_cached_session_data(agent: str, session_id: str, data: dict) -> None:
    """说明:Store parsed session data in in-memory cache."""
    key = f'{agent}:{session_id}'
    _session_data_cache[key] = data
    _session_cache_timestamps[key] = time.time()

    # Cap cache size — evict oldest entries,如果 too many
    if len(_session_data_cache) > 50:
        oldest_keys = sorted(_session_cache_timestamps, key=_session_cache_timestamps.get)[:10]
        for k in oldest_keys:
            _session_data_cache.pop(k, None)
            _session_cache_timestamps.pop(k, None)
