"""SQLite indexer，用于 session-browser.

Manages a local SQLite index of all sessions from both Claude Code and Codex.
Supports:
- Full initial scan (drops old schema, rebuilds)
- Incremental refresh (mtime-based: only re-parse changed .jsonl files)
- Tiered background scanning (hot/warm/cold by session age)
- Query interface for dashboard, project, and session pages

This module exposes the public index API. Implementation lives in:
- schema.py: connection, schema, tier config constants
- writers.py: upsert_session, _row_to_summary
- scanners.py: full_scan, incremental_scan, file locators, normalization
- queries.py: get_session, list_sessions, count_sessions, project/agent/dashboard queries
"""

from __future__ import annotations

# 说明：--- Queries ------------------------------------------------------------------
from session_browser.index.queries import (
    count_projects,
    count_sessions,
    get_dashboard_stats,
    get_project_stats,
    get_prompt_activity_trend,
    get_session,
    get_sessions_list_aggregate,
    get_trend_data,
    list_agents,
    list_projects,
    list_sessions,
)

# 说明：--- Scanners -----------------------------------------------------------------
from session_browser.index.scanners import (
    _locate_claude_session_file,
    _locate_codex_session_file,
    _locate_qoder_session_file,
    _normalize_qoder_cache_projects,
    full_scan,
    incremental_scan,
)

# 说明：--- Schema & connection ------------------------------------------------------
from session_browser.index.schema import (
    SCAN_LOGIC_VERSION,
    SCAN_LOGIC_VERSION_KEY,
    TIER_HOT_INTERVAL,
    TIER_HOT_SECONDS,
    TIER_WARM_INTERVAL,
    TIER_WARM_SECONDS,
    _get_connection,
    ensure_index_metadata_schema,
    get_stored_scan_logic_version,
    init_schema,
    set_stored_scan_logic_version,
)

# 说明：--- Writers ------------------------------------------------------------------
from session_browser.index.writers import (
    _row_to_summary,
    upsert_session,
)
