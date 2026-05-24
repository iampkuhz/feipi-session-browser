"""Dashboard presenter.

Extracted view-model construction logic for the dashboard page.
Kept in a separate module so it can be unit-tested in isolation and
does not clutter the HTTP routes handler.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from session_browser.index.indexer import (
    get_dashboard_stats,
    list_sessions,
    list_projects,
    get_trend_data,
    get_prompt_activity_trend,
)
from session_browser.index.metrics import (
    get_model_distribution,
    get_agent_distribution,
    get_token_breakdown,
    compute_derived_metrics,
    compute_aggregate_metrics,
)
from session_browser.index.anomalies import (
    detect_all_anomalies,
    get_needs_attention,
)


def build_dashboard_view_model(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """Build the complete view model for the dashboard page.

    Responsibilities:
    - Fetch dashboard stats, projects, trend data, distributions.
    - Compute aggregate metrics.
    - Fetch sessions list, compute derived metrics, detect anomalies.
    - Assemble a dict ready to be passed to the Jinja template.

    Args:
        conn: An open SQLite connection to the session index database.

    Returns:
        A dict with keys: stats, projects, trend, prompt_activity,
        model_dist, agent_dist, tokens, aggregate, needs_attention,
        active_page.
    """
    # Core stats and lists
    stats = get_dashboard_stats(conn)
    projects = list_projects(conn, limit=10)
    trend = get_trend_data(conn, days=365)
    prompt_activity = get_prompt_activity_trend(conn, days=365)
    model_dist = get_model_distribution(conn)
    agent_dist = get_agent_distribution(conn)
    token_breakdown = get_token_breakdown(conn)
    aggregate_metrics = compute_aggregate_metrics(conn)

    # Anomaly detection for all sessions
    all_sessions_raw = list_sessions(conn, limit=2000, order_by="ended_at")
    sessions_data = []
    sessions_lookup = {}
    for s in all_sessions_raw:
        d = compute_derived_metrics(s.to_dict())
        sessions_data.append(d)
        sessions_lookup[d["session_key"]] = d

    anomalies_map = detect_all_anomalies(sessions_data)
    needs_attention = get_needs_attention(anomalies_map, sessions_lookup, limit=8)

    return {
        "stats": stats,
        "projects": projects,
        "trend": trend,
        "prompt_activity": prompt_activity,
        "model_dist": model_dist.distribution,
        "agent_dist": agent_dist,
        "tokens": token_breakdown,
        "aggregate": aggregate_metrics,
        "needs_attention": needs_attention,
        "active_page": "dashboard",
    }
