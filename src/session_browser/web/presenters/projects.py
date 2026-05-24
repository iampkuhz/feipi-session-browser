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
    list_sessions,
    get_project_stats,
)


def build_projects_view_model(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """Build the complete view model for the projects listing page.

    Args:
        conn: An open SQLite connection to the session index database.

    Returns:
        A dict with keys: projects, active_page.
    """
    projects = list_projects(conn, limit=100)

    return {
        "projects": projects,
        "active_page": "projects",
    }


def build_project_view_model(
    conn: sqlite3.Connection,
    project_key: str,
) -> dict[str, Any]:
    """Build the complete view model for a single project page.

    Args:
        conn: An open SQLite connection to the session index database.
        project_key: Project key from the URL.

    Returns:
        A dict with keys: project, sessions, project_key, active_page.
    """
    pstats = get_project_stats(conn, project_key)
    sessions = list_sessions(conn, project_key=project_key, limit=100)

    return {
        "project": pstats,
        "sessions": sessions,
        "project_key": project_key,
        "active_page": "projects",
    }
