"""Sessions list presenter.

Extracted view-model construction logic for the /sessions list page.
Kept in a separate module so it can be unit-tested in isolation and
does not clutter the HTTP routes handler.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from session_browser.index.indexer import (
    list_sessions,
    count_sessions,
    get_sessions_list_aggregate,
)
from session_browser.index.metrics import compute_derived_metrics
from session_browser.index.anomalies import (
    detect_all_anomalies,
    enrich_sessions_with_anomalies,
)


# ── Query parameter defaults ─────────────────────────────────────────

VALID_PAGE_SIZES = {20, 100, 500}

SORT_KEY_MAP = {
    "ended-at": "ended_at",
    "duration": "duration_seconds",
    "tokens": "total_tokens",
    "total-tokens": "total_tokens",
    "rounds": "assistant_message_count",
    "tools": "tool_call_count",
}


def parse_sessions_query_params(raw_params: dict[str, list[str]]) -> dict[str, Any]:
    """Parse URL query parameters into a typed dict.

    Args:
        raw_params: Result of urllib.parse.parse_qs().

    Returns:
        Dict with keys: page, page_size, filter_agent, filter_model,
        filter_project, filter_q, sort_by, raw_sort, sort_dir.
    """
    # Pagination — page
    try:
        page = int(raw_params.get("page", ["1"])[0])
        if page < 1:
            page = 1
    except (ValueError, IndexError):
        page = 1

    # Pagination — page_size
    raw_size = raw_params.get("page_size", ["20"])[0].strip().lower()
    if raw_size == "all":
        page_size: int | str = "all"
    else:
        try:
            page_size_int = int(raw_size)
            if page_size_int in VALID_PAGE_SIZES:
                page_size = page_size_int
            else:
                page_size = 20
        except ValueError:
            page_size = 20

    # Filters
    filter_agent = raw_params.get("agent", [""])[0].strip() or None
    filter_model = raw_params.get("model", [""])[0].strip() or None
    filter_project = raw_params.get("project", [""])[0].strip() or None
    filter_q = raw_params.get("q", [""])[0].strip() or None

    # Sort
    raw_sort = raw_params.get("sort", [""])[0].strip().lower()
    raw_dir = raw_params.get("dir", ["desc"])[0].strip().lower()
    if raw_dir not in ("asc", "desc"):
        raw_dir = "desc"
    sort_by = SORT_KEY_MAP.get(raw_sort, "ended_at")

    return {
        "page": page,
        "page_size": page_size,
        "filter_agent": filter_agent,
        "filter_model": filter_model,
        "filter_project": filter_project,
        "filter_q": filter_q,
        "sort_by": sort_by,
        "raw_sort": raw_sort,
        "sort_dir": raw_dir,
    }


def compute_pagination(
    total_count: int,
    page: int,
    page_size: int | str,
) -> dict[str, Any]:
    """Compute limit, offset and pagination metadata.

    Returns:
        Dict with keys: limit, offset, effective_page_size, total_pages,
        page_start, page_end, has_prev, has_next.
    """
    if page_size == "all":
        limit = total_count if total_count > 0 else 2000
        offset = 0
        effective_page_size = total_count
        total_pages = 1
    else:
        limit = page_size
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * page_size
        effective_page_size = page_size

    # page_start / page_end
    if total_count == 0:
        page_start = 0
        page_end = 0
    else:
        page_start = offset + 1
        page_end = min(offset + limit, total_count)

    has_prev = page > 1
    has_next = page_start < total_count if page_size != "all" else False

    return {
        "limit": limit,
        "offset": offset,
        "effective_page_size": effective_page_size,
        "total_pages": total_pages,
        "page_start": page_start,
        "page_end": page_end,
        "has_prev": has_prev,
        "has_next": has_next,
        "page": page,  # possibly clamped
    }


def fetch_sessions_view_model(
    conn: sqlite3.Connection,
    filter_agent: str | None,
    filter_model: str | None,
    filter_project: str | None,
    filter_q: str | None,
    sort_by: str,
    sort_dir: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Fetch data needed for the sessions list view model.

    Args:
        conn: SQLite connection.
        filter_agent/model/project/q: Server-side filters.
        sort_by: DB column name.
        sort_dir: 'asc' or 'desc'.
        limit/offset: Pagination bounds.

    Returns:
        Dict with keys: sessions_enriched, total_count, sessions_aggregate,
        model_list, project_list.
    """
    # Total count
    total_count = count_sessions(
        conn,
        agent=filter_agent,
        project_key=filter_project,
        model=filter_model,
        title_like=filter_q,
    )

    # Aggregate stats
    sessions_aggregate = get_sessions_list_aggregate(
        conn,
        agent=filter_agent,
        project_key=filter_project,
        model=filter_model,
        title_like=filter_q,
    )

    # Paginated sessions
    sessions = list_sessions(
        conn,
        agent=filter_agent,
        project_key=filter_project,
        model=filter_model,
        title_like=filter_q,
        limit=limit,
        offset=offset,
        order_by=sort_by,
        order_dir=sort_dir,
    )

    # Filter dropdowns
    models = conn.execute(
        "SELECT DISTINCT model FROM sessions WHERE model != '' ORDER BY model"
    ).fetchall()
    projects = conn.execute(
        "SELECT DISTINCT project_key, project_name FROM sessions ORDER BY project_name"
    ).fetchall()

    # Anomaly detection (scoped to filtered set for performance)
    all_sessions_raw = list_sessions(conn, limit=2000, order_by="ended_at")
    sessions_data = []
    sessions_lookup = {}
    for s in all_sessions_raw:
        d = compute_derived_metrics(s.to_dict())
        sessions_data.append(d)
        sessions_lookup[d["session_key"]] = d

    anomalies_map = detect_all_anomalies(sessions_data)
    sessions_enriched = enrich_sessions_with_anomalies(sessions, anomalies_map)

    model_list = [r["model"] for r in models]
    project_list = [p[0] for p in projects]

    return {
        "sessions_enriched": sessions_enriched,
        "total_count": total_count,
        "sessions_aggregate": sessions_aggregate,
        "model_list": model_list,
        "project_list": project_list,
    }


def build_sessions_context(
    raw_params: dict[str, list[str]],
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """High-level helper: parse params, fetch data, return template context.

    This is the main entry point for the /sessions page presenter.
    It returns everything the template needs (minus the actions URLs,
    which are built separately via _build_view_actions in routes.py).

    Args:
        raw_params: Parsed query string via urllib.parse.parse_qs().
        conn: SQLite connection.

    Returns:
        Context dict suitable for passing to _render_template().
    """
    params = parse_sessions_query_params(raw_params)

    pagination = compute_pagination(
        # We need total_count first, so do a preliminary fetch
        total_count=count_sessions(
            conn,
            agent=params["filter_agent"],
            project_key=params["filter_project"],
            model=params["filter_model"],
            title_like=params["filter_q"],
        ),
        page=params["page"],
        page_size=params["page_size"],
    )

    vm = fetch_sessions_view_model(
        conn=conn,
        filter_agent=params["filter_agent"],
        filter_model=params["filter_model"],
        filter_project=params["filter_project"],
        filter_q=params["filter_q"],
        sort_by=params["sort_by"],
        sort_dir=params["sort_dir"],
        limit=pagination["limit"],
        offset=pagination["offset"],
    )

    # Normalize sort key for template (ui uses 'updated' for 'ended-at')
    ui_sort = "updated" if params["raw_sort"] == "ended-at" else (params["raw_sort"] or "ended-at")

    return {
        "sessions": vm["sessions_enriched"],
        "total_count": vm["total_count"],
        "page": pagination["page"],
        "current_page": pagination["page"],
        "page_size": params["page_size"],
        "total_pages": pagination["total_pages"],
        "page_start": pagination["page_start"],
        "page_end": pagination["page_end"],
        "has_prev": pagination["has_prev"],
        "has_next": pagination["has_next"],
        "filter_agent": params["filter_agent"] or "",
        "filter_model": params["filter_model"] or "",
        "filter_project": params["filter_project"] or "",
        "filter_q": params["filter_q"] or "",
        "sort_by": ui_sort,
        "sort_dir": params["sort_dir"],
        "model_list": vm["model_list"],
        "project_list": vm["project_list"],
        "sessions_aggregate": vm["sessions_aggregate"],
    }
