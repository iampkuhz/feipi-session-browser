"""Projects presenter.

Extracted view-model construction logic for the projects listing and
individual project pages. Keeps data-fetching out of the HTTP handler
so it can be unit-tested in isolation.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from session_browser.index.indexer import (
    list_projects,
    count_projects,
    list_sessions,
    count_sessions,
    get_project_stats,
)
from session_browser.web.template_env import _display_path


# ── Query parameter defaults ─────────────────────────────────────────

VALID_PAGE_SIZES = {20, 50, 100, 500}


def parse_projects_query_params(raw_params: dict[str, list[str]]) -> dict[str, Any]:
    """Parse URL query parameters into a typed dict for projects pages.

    Args:
        raw_params: Result of urllib.parse.parse_qs().

    Returns:
        Dict with keys: page, page_size.
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

    return {
        "page": page,
        "page_size": page_size,
    }


def compute_projects_pagination(
    total_count: int,
    page: int,
    page_size: int | str,
) -> dict[str, Any]:
    """Compute limit, offset and pagination metadata for projects listing.

    Returns:
        Dict with keys: limit, offset, effective_page_size, total_pages,
        page_start, page_end, has_prev, has_next, page.
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
    has_next = page < total_pages if page_size != "all" else False

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


def build_projects_view_model(
    raw_params: dict[str, list[str]] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Build the complete view model for the projects listing page.

    Args:
        raw_params: Parsed query string via urllib.parse.parse_qs().
        conn: An open SQLite connection to the session index database.

    Returns:
        A dict with keys: projects, active_page, page, current_page,
        page_size, total_pages, total_count, page_start, page_end,
        has_prev, has_next.
    """
    if raw_params is None:
        raw_params = {}
    if conn is None:
        return {
            "projects": [],
            "active_page": "projects",
            "page": 1,
            "current_page": 1,
            "page_size": 20,
            "total_pages": 1,
            "total_count": 0,
            "page_start": 0,
            "page_end": 0,
            "has_prev": False,
            "has_next": False,
        }

    params = parse_projects_query_params(raw_params)

    # Get total count first
    total_count = int(count_projects(conn))

    # Compute pagination
    pagination = compute_projects_pagination(
        total_count=total_count,
        page=params["page"],
        page_size=params["page_size"],
    )

    # Fetch paginated projects
    projects = list_projects(
        conn,
        limit=pagination["limit"],
        offset=pagination["offset"],
    )

    # Compute display_path for each project: use cwd (actual filesystem path)
    # with ~ substitution, falling back to project_key if cwd is empty.
    for p in projects:
        raw_path = p.cwd if hasattr(p, 'cwd') and p.cwd else p.project_key
        p.display_path = _display_path(raw_path)

    return {
        "projects": projects,
        "active_page": "projects",
        "page": pagination["page"],
        "current_page": pagination["page"],
        "page_size": params["page_size"],
        "total_pages": pagination["total_pages"],
        "total_count": total_count,
        "page_start": pagination["page_start"],
        "page_end": pagination["page_end"],
        "has_prev": pagination["has_prev"],
        "has_next": pagination["has_next"],
    }


def build_project_detail_view_model(
    conn: sqlite3.Connection,
    project_key: str,
    raw_params: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Build the complete view model for a single project page.

    Args:
        conn: An open SQLite connection to the session index database.
        project_key: Project key from the URL.
        raw_params: Parsed query string via urllib.parse.parse_qs().

    Returns:
        A dict with keys: project, sessions, project_key, active_page,
        page, current_page, page_size, total_pages, total_count,
        page_start, page_end, has_prev, has_next.
    """
    if raw_params is None:
        raw_params = {}

    params = parse_projects_query_params(raw_params)

    pstats = get_project_stats(conn, project_key)

    # Get total count for this project
    total_count = int(count_sessions(conn, project_key=project_key))

    # Compute pagination
    pagination = compute_projects_pagination(
        total_count=total_count,
        page=params["page"],
        page_size=params["page_size"],
    )

    # Fetch paginated sessions for this project
    sessions = list_sessions(
        conn,
        project_key=project_key,
        limit=pagination["limit"],
        offset=pagination["offset"],
    )

    return {
        "project": pstats,
        "sessions": sessions,
        "project_key": project_key,
        "active_page": "projects",
        "page": pagination["page"],
        "current_page": pagination["page"],
        "page_size": params["page_size"],
        "total_pages": pagination["total_pages"],
        "total_count": total_count,
        "page_start": pagination["page_start"],
        "page_end": pagination["page_end"],
        "has_prev": pagination["has_prev"],
        "has_next": pagination["has_next"],
    }
