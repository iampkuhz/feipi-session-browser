"""Agents presenter.

Extracted view-model construction logic for the agents listing and
individual agent pages. Keeps data-fetching out of the HTTP handler
so it can be unit-tested in isolation.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from session_browser.index.indexer import (
    list_agents,
    list_sessions,
)
from session_browser.index.metrics import (
    compute_agent_efficiency,
)


def build_agents_view_model(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """Build the complete view model for the agents listing page.

    Args:
        conn: An open SQLite connection to the session index database.

    Returns:
        A dict with keys: agents, efficiency, current_agent, active_page.
    """
    agents = list_agents(conn)
    efficiency = compute_agent_efficiency(conn)

    return {
        "agents": agents,
        "efficiency": efficiency,
        "current_agent": "__all__",
        "active_page": "agents",
    }


def build_agent_view_model(
    conn: sqlite3.Connection,
    agent: str,
) -> dict[str, Any]:
    """Build the complete view model for a single agent page.

    Args:
        conn: An open SQLite connection to the session index database.
        agent: Agent key (e.g. "claude_code", "qoder", "codex").

    Returns:
        A dict with keys: agents, agent_info, sessions, current_agent,
        active_page.
    """
    agents = list_agents(conn)
    sessions = list_sessions(conn, agent=agent, limit=100, order_by="ended_at")

    agent_info = None
    for a in agents:
        if a["agent"] == agent:
            agent_info = a
            break

    return {
        "agents": agents,
        "agent_info": agent_info,
        "sessions": sessions,
        "current_agent": agent,
        "active_page": "agents",
    }
