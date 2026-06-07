"""Query functions for reading from the session index SQLite database."""

from __future__ import annotations

import sqlite3

from session_browser.domain.models import SessionSummary, ProjectStats
from session_browser.index.writers import _row_to_summary


# --- Single session queries ---------------------------------------------------


def get_session(conn: sqlite3.Connection, session_key: str) -> SessionSummary | None:
    """Get a single session by key."""
    row = conn.execute(
        "SELECT * FROM sessions WHERE session_key = ?", (session_key,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_summary(row)


# --- Session list queries -----------------------------------------------------


def list_sessions(
    conn: sqlite3.Connection,
    agent: str | None = None,
    project_key: str | None = None,
    model: str | None = None,
    title_like: str | None = None,
    failure_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "ended_at",
    order_dir: str = "desc",
) -> list[SessionSummary]:
    """List sessions with filtering and pagination."""
    clauses = []
    params: list = []

    if agent:
        clauses.append("agent = ?")
        params.append(agent)
    if project_key:
        clauses.append("project_key = ?")
        params.append(project_key)
    if model:
        clauses.append("model = ?")
        params.append(model)
    if title_like:
        # NOTE: title_like now searches both title and session_id,
        # case-insensitively.
        clauses.append(
            "(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))"
        )
        pattern = f"%{title_like}%"
        params.append(pattern)
        params.append(pattern)
    if failure_status == "failed":
        clauses.append("failed_tool_count > 0")
    elif failure_status == "no-failures":
        clauses.append("failed_tool_count = 0")

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    valid_orders = {
        "ended_at": "ended_at",
        "started_at": "started_at",
        "input_tokens": "input_tokens",
        "total_tokens": "total_tokens",
        "assistant_message_count": "assistant_message_count",
        "tool_call_count": "tool_call_count",
        "duration_seconds": "duration_seconds",
        "process_seconds": "(model_execution_seconds + tool_execution_seconds)",
        "failed_tool_count": "failed_tool_count",
        "subagent_instance_count": "subagent_instance_count",
    }
    order_expr = valid_orders.get(order_by, "ended_at")
    safe_dir = "ASC" if order_dir == "asc" else "DESC"
    order = f"{order_expr} {safe_dir}"

    query = f"SELECT * FROM sessions {where} ORDER BY {order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [_row_to_summary(r, truncate_title=True) for r in rows]


def count_sessions(
    conn: sqlite3.Connection,
    agent: str | None = None,
    project_key: str | None = None,
    model: str | None = None,
    title_like: str | None = None,
    failure_status: str | None = None,
) -> int:
    """Count sessions with optional filtering."""
    clauses = []
    params: list = []
    if agent:
        clauses.append("agent = ?")
        params.append(agent)
    if project_key:
        clauses.append("project_key = ?")
        params.append(project_key)
    if model:
        clauses.append("model = ?")
        params.append(model)
    if title_like:
        # NOTE: title_like now searches both title and session_id,
        # case-insensitively.
        clauses.append(
            "(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))"
        )
        pattern = f"%{title_like}%"
        params.append(pattern)
        params.append(pattern)
    if failure_status == "failed":
        clauses.append("failed_tool_count > 0")
    elif failure_status == "no-failures":
        clauses.append("failed_tool_count = 0")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute(f"SELECT COUNT(*) FROM sessions {where}", params).fetchone()
    return row[0]


def get_sessions_list_aggregate(
    conn: sqlite3.Connection,
    agent: str | None = None,
    project_key: str | None = None,
    model: str | None = None,
    title_like: str | None = None,
    failure_status: str | None = None,
) -> dict:
    """Get aggregate stats for filtered sessions list."""
    clauses = []
    params: list = []
    if agent:
        clauses.append("agent = ?")
        params.append(agent)
    if project_key:
        clauses.append("project_key = ?")
        params.append(project_key)
    if model:
        clauses.append("model = ?")
        params.append(model)
    if title_like:
        # NOTE: title_like now searches both title and session_id,
        # case-insensitively.
        clauses.append(
            "(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))"
        )
        pattern = f"%{title_like}%"
        params.append(pattern)
        params.append(pattern)
    if failure_status == "failed":
        clauses.append("failed_tool_count > 0")
    elif failure_status == "no-failures":
        clauses.append("failed_tool_count = 0")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute(
        f"SELECT COUNT(*) as session_count, "
        f"COUNT(DISTINCT project_key) as project_count, "
        f"COALESCE(SUM(total_tokens), 0) as total_tokens "
        f"FROM sessions {where}",
        params,
    ).fetchone()
    return {
        "session_count": row["session_count"],
        "project_count": row["project_count"],
        "total_tokens": row["total_tokens"],
    }


# --- Project queries ----------------------------------------------------------


def get_project_stats(conn: sqlite3.Connection, project_key: str) -> ProjectStats:
    """Get aggregated statistics for a project."""
    row = conn.execute(
        """
        SELECT
            project_key,
            project_name,
            COUNT(*) as total_sessions,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_sessions,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_sessions,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_sessions,
            MIN(started_at) as first_seen,
            MAX(ended_at) as last_seen,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(cached_input_tokens), 0) as total_cached_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
            COALESCE(SUM(user_message_count), 0) as total_user_messages,
            COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages
        FROM sessions
        WHERE project_key = ?
        GROUP BY project_key
        """,
        (project_key,),
    ).fetchone()

    if row is None:
        return ProjectStats(project_key=project_key, project_name="")

    return ProjectStats(
        project_key=row["project_key"],
        project_name=row["project_name"],
        total_sessions=row["total_sessions"],
        claude_sessions=row["claude_sessions"],
        codex_sessions=row["codex_sessions"],
        qoder_sessions=row["qoder_sessions"],
        first_seen=row["first_seen"] or "",
        last_seen=row["last_seen"] or "",
        total_input_tokens=row["total_input_tokens"],
        total_output_tokens=row["total_output_tokens"],
        total_cached_tokens=row["total_cached_tokens"],
        total_cache_write_tokens=row["total_cache_write_tokens"],
        total_tool_calls=row["total_tool_calls"],
        total_failed_tools=row["total_failed_tools"],
        total_user_messages=row["total_user_messages"],
        total_assistant_messages=row["total_assistant_messages"],
    )


def count_projects(conn: sqlite3.Connection, title_like: str | None = None) -> int:
    """Count total number of distinct projects."""
    clauses = []
    params: list = []
    if title_like:
        clauses.append("(LOWER(project_name) LIKE LOWER(?) OR LOWER(project_key) LIKE LOWER(?) OR LOWER(cwd) LIKE LOWER(?))")
        pattern = f"%{title_like}%"
        params.extend([pattern, pattern, pattern])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute(
        f"SELECT COUNT(DISTINCT project_key) FROM sessions {where}",
        params,
    ).fetchone()
    return row[0]


def list_projects(
    conn: sqlite3.Connection,
    title_like: str | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "last_active",
    order_dir: str = "desc",
) -> list[ProjectStats]:
    """List projects sorted by most recent activity with pagination."""
    clauses = []
    params: list = []
    if title_like:
        clauses.append("(LOWER(project_name) LIKE LOWER(?) OR LOWER(project_key) LIKE LOWER(?) OR LOWER(cwd) LIKE LOWER(?))")
        pattern = f"%{title_like}%"
        params.extend([pattern, pattern, pattern])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    valid_orders = {
        "sessions": "total_sessions",
        "tokens": "total_tokens",
        "tools": "total_tool_calls",
        "failed": "total_failed_tools",
        "first_seen": "first_seen",
        "last_active": "last_seen",
    }
    order_expr = valid_orders.get(order_by, "last_seen")
    safe_dir = "ASC" if order_dir == "asc" else "DESC"
    rows = conn.execute(
        f"""
        SELECT
            project_key,
            project_name,
            COUNT(*) as total_sessions,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_sessions,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_sessions,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_sessions,
            MIN(started_at) as first_seen,
            MAX(ended_at) as last_seen,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(cached_input_tokens), 0) as total_cached_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
            COALESCE(SUM(user_message_count), 0) as total_user_messages,
            COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages
        FROM sessions
        {where}
        GROUP BY project_key
        ORDER BY {order_expr} {safe_dir}
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()

    return [
        ProjectStats(
            project_key=r["project_key"],
            project_name=r["project_name"],
            total_sessions=r["total_sessions"],
            claude_sessions=r["claude_sessions"],
            codex_sessions=r["codex_sessions"],
            qoder_sessions=r["qoder_sessions"],
            first_seen=r["first_seen"] or "",
            last_seen=r["last_seen"] or "",
            total_input_tokens=r["total_input_tokens"],
            total_output_tokens=r["total_output_tokens"],
            total_cached_tokens=r["total_cached_tokens"],
            total_cache_write_tokens=r["total_cache_write_tokens"],
            total_tool_calls=r["total_tool_calls"],
            total_failed_tools=r["total_failed_tools"],
            total_user_messages=r["total_user_messages"],
            total_assistant_messages=r["total_assistant_messages"],
        )
        for r in rows
    ]


# --- Dashboard queries --------------------------------------------------------

# Agent scope mapping: URL value -> DB agent value
_AGENT_SCOPE_MAP = {
    "claude-code": "claude_code",
    "qoder": "qoder",
    "codex": "codex",
}


def _agent_clause(agent_scope: str | None) -> tuple[str, list]:
    """Return SQL WHERE clause and params for agent scope filtering."""
    if not agent_scope or agent_scope == "all":
        return "", []
    db_agent = _AGENT_SCOPE_MAP.get(agent_scope)
    if db_agent:
        return "WHERE agent = ?", [db_agent]
    return "", []


def get_dashboard_stats(conn: sqlite3.Connection, agent_scope: str | None = None) -> dict:
    """Get dashboard-level aggregated stats, optionally scoped to a single agent."""
    where, params = _agent_clause(agent_scope)
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) as total_sessions,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_sessions,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_sessions,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_sessions,
            COUNT(DISTINCT project_key) as project_count,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
            COALESCE(SUM(user_message_count), 0) as total_user_messages,
            COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages
        FROM sessions {where}
        """,
        params,
    ).fetchone()

    return {
        "total_sessions": row["total_sessions"],
        "claude_sessions": row["claude_sessions"],
        "codex_sessions": row["codex_sessions"],
        "qoder_sessions": row["qoder_sessions"],
        "project_count": row["project_count"],
        "total_tokens": row["total_tokens"],
        "total_fresh_input_tokens": row["total_fresh_input_tokens"],
        "total_cache_read_tokens": row["total_cache_read_tokens"],
        "total_cache_write_tokens": row["total_cache_write_tokens"],
        "total_output_tokens": row["total_output_tokens"],
        "total_tool_calls": row["total_tool_calls"],
        "total_failed_tools": row["total_failed_tools"],
        "total_user_messages": row["total_user_messages"],
        "total_assistant_messages": row["total_assistant_messages"],
    }


def get_trend_data(
    conn: sqlite3.Connection,
    days: int = 30,
    agent_scope: str | None = None,
) -> list[dict]:
    """Get daily session/trend counts for the last N days.

    Returns list of {date, claude_count, codex_count, input_tokens, output_tokens,
                      cache_read, cache_write, tool_calls, failed_tools}.
    """
    where, params = _agent_clause(agent_scope)
    # Convert WHERE to AND if needed
    where_sql = where.replace("WHERE", "AND") if where else ""
    # SQL has date('now', ?) before agent = ?, so date param must come first
    params.insert(0, f"-{days} days")
    rows = conn.execute(
        f"""
        SELECT
            COALESCE(NULLIF(DATE(ended_at), ''), DATE('now')) as day,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_count,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_count,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_count,
            COALESCE(SUM(fresh_input_tokens), 0) as fresh_input_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as cache_write_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(tool_call_count), 0) as tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as failed_tools,
            COUNT(*) as total_count
        FROM sessions
        WHERE (ended_at >= date('now', ?) OR ended_at = '' OR ended_at IS NULL)
        {where_sql}
        GROUP BY COALESCE(NULLIF(DATE(ended_at), ''), DATE('now'))
        ORDER BY day
        """,
        params,
    ).fetchall()

    return [
        {
            "date": r["day"],
            "claude_count": r["claude_count"],
            "codex_count": r["codex_count"],
            "qoder_count": r["qoder_count"],
            "fresh_input_tokens": r["fresh_input_tokens"],
            "cache_read_tokens": r["cache_read_tokens"],
            "cache_write_tokens": r["cache_write_tokens"],
            "output_tokens": r["output_tokens"],
            "total_tokens": r["total_tokens"],
            "tool_calls": r["tool_calls"],
            "failed_tools": r["failed_tools"],
            "total_count": r["total_count"],
        }
        for r in rows
    ]


def get_prompt_activity_trend(conn: sqlite3.Connection, days: int = 30, agent_scope: str | None = None) -> list[dict]:
    """Get daily user message counts for the last N days, broken down by agent.

    Returns list of {date, claude_prompts, codex_prompts, qoder_prompts, total_prompts}.
    """
    where, params = _agent_clause(agent_scope)
    where_sql = where.replace("WHERE", "AND") if where else ""
    # SQL has date('now', ?) before agent = ?, so date param must come first
    params.insert(0, f"-{days} days")
    rows = conn.execute(
        f"""
        SELECT
            COALESCE(NULLIF(DATE(ended_at), ''), DATE('now')) as day,
            COALESCE(SUM(CASE WHEN agent='claude_code' THEN user_message_count ELSE 0 END), 0) as claude_prompts,
            COALESCE(SUM(CASE WHEN agent='codex' THEN user_message_count ELSE 0 END), 0) as codex_prompts,
            COALESCE(SUM(CASE WHEN agent='qoder' THEN user_message_count ELSE 0 END), 0) as qoder_prompts,
            COALESCE(SUM(user_message_count), 0) as total_prompts
        FROM sessions
        WHERE (ended_at >= date('now', ?) OR ended_at = '' OR ended_at IS NULL)
        {where_sql}
        GROUP BY COALESCE(NULLIF(DATE(ended_at), ''), DATE('now'))
        ORDER BY day
        """,
        params,
    ).fetchall()

    return [
        {
            "date": r["day"],
            "claude_prompts": r["claude_prompts"],
            "codex_prompts": r["codex_prompts"],
            "qoder_prompts": r["qoder_prompts"],
            "total_prompts": r["total_prompts"],
        }
        for r in rows
    ]


# --- Agent queries ------------------------------------------------------------


def list_agents(conn: sqlite3.Connection) -> list[dict]:
    """List all agents with session counts.

    Returns list of {agent, session_count, last_active, total_tokens,
                     total_fresh_input_tokens, total_cache_read_tokens, total_cache_write_tokens,
                     total_output_tokens, total_tool_calls, total_failed_tools,
                     total_assistant_messages, project_count}.
    """
    rows = conn.execute(
        """
        SELECT
            agent,
            COUNT(*) as session_count,
            MAX(ended_at) as last_active,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
            COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages,
            COUNT(DISTINCT project_key) as project_count
        FROM sessions
        GROUP BY agent
        ORDER BY MAX(ended_at) DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def list_model_stats(conn: sqlite3.Connection) -> list[dict]:
    """List per-model stats with agent info.

    Returns list of {agent, model, total_sessions, total_tokens,
                     input_tokens, output_tokens, cache_read_tokens,
                     cache_write_tokens, failed_tools}.
    """
    rows = conn.execute(
        """
        SELECT
            agent,
            model,
            COUNT(*) as total_sessions,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(fresh_input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as cache_write_tokens,
            COALESCE(SUM(failed_tool_count), 0) as failed_tools
        FROM sessions
        WHERE model != ''
        GROUP BY agent, model
        """
    ).fetchall()
    return [dict(r) for r in rows]
