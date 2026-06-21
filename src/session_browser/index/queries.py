"""Read indexed sessions and aggregates for routes and dashboard views."""

from __future__ import annotations

from typing import TYPE_CHECKING

from session_browser.domain.models import ProjectStats, SessionSummary
from session_browser.index.writers import _row_to_summary

if TYPE_CHECKING:
    import sqlite3

# Single session queries.


def get_session(conn: sqlite3.Connection, session_key: str) -> SessionSummary | None:
    """Read one indexed session by stable session key.

    Routes and presenters call this query for detail pages. It returns None when the
    key is absent and otherwise delegates row conversion to the writer helper.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        session_key: Stable session key stored in the sessions table.

    Returns:
        Converted SessionSummary, or None when no matching row exists.
    """
    row = conn.execute("SELECT * FROM sessions WHERE session_key = ?", (session_key,)).fetchone()
    if row is None:
        return None
    return _row_to_summary(row)


# Session list queries.


def list_sessions(  # noqa: PLR0913 - Public query API mirrors existing route filters.
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
    """Read a filtered and paginated session list.

    The session index route calls this query with optional UI filters. User supplied
    sort fields are mapped through a fixed allowlist before SQL is assembled.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        agent: Optional exact agent filter.
        project_key: Optional exact project key filter.
        model: Optional exact model filter.
        title_like: Optional case-insensitive title or session id search fragment.
        failure_status: Optional failed or no-failures filter.
        limit: Maximum number of sessions to return.
        offset: Number of matching sessions to skip.
        order_by: Public sort key mapped to a safe SQL expression.
        order_dir: Sort direction, where asc maps to ASC and all other values map to DESC.

    Returns:
        SessionSummary rows converted with truncated titles for list display.
    """
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
        # NOTE: title_like searches both title and session_id case-insensitively.
        clauses.append("(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))")
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
        "fresh_input_tokens": "fresh_input_tokens",
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


def count_sessions(  # noqa: PLR0913 - Public query API mirrors existing route filters.
    conn: sqlite3.Connection,
    agent: str | None = None,
    project_key: str | None = None,
    model: str | None = None,
    title_like: str | None = None,
    failure_status: str | None = None,
) -> int:
    """Count sessions that match the list filters.

    Pagination controls call this companion query with the same filtering semantics
    as list_sessions.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        agent: Optional exact agent filter.
        project_key: Optional exact project key filter.
        model: Optional exact model filter.
        title_like: Optional case-insensitive title or session id search fragment.
        failure_status: Optional failed or no-failures filter.

    Returns:
        Number of sessions matching the filters.
    """
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
        # NOTE: title_like searches both title and session_id case-insensitively.
        clauses.append("(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))")
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


def get_sessions_list_aggregate(  # noqa: PLR0913 - Shares filter shape with list queries.
    conn: sqlite3.Connection,
    agent: str | None = None,
    project_key: str | None = None,
    model: str | None = None,
    title_like: str | None = None,
    failure_status: str | None = None,
) -> dict:
    """Summarize totals for the filtered session list.

    The session list header calls this query to show counts and token totals aligned
    with the active filters.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        agent: Optional exact agent filter.
        project_key: Optional exact project key filter.
        model: Optional exact model filter.
        title_like: Optional case-insensitive title or session id search fragment.
        failure_status: Optional failed or no-failures filter.

    Returns:
        Dictionary with session_count, project_count, and total_tokens values.
    """
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
        # NOTE: title_like searches both title and session_id case-insensitively.
        clauses.append("(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))")
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


# Project queries.


def get_project_stats(conn: sqlite3.Connection, project_key: str) -> ProjectStats:
    """Read aggregate statistics for one project.

    Project detail routes call this query with a project key. Missing projects return
    an empty ProjectStats object to preserve existing caller behavior.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        project_key: Stable project key stored in the sessions table.

    Returns:
        ProjectStats populated from matching sessions, or an empty stats object.
    """
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
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
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
        total_fresh_input_tokens=row["total_fresh_input_tokens"],
        total_output_tokens=row["total_output_tokens"],
        total_cache_read_tokens=row["total_cache_read_tokens"],
        total_cache_write_tokens=row["total_cache_write_tokens"],
        total_tool_calls=row["total_tool_calls"],
        total_failed_tools=row["total_failed_tools"],
        total_user_messages=row["total_user_messages"],
        total_assistant_messages=row["total_assistant_messages"],
    )


def count_projects(conn: sqlite3.Connection, title_like: str | None = None) -> int:
    """Count distinct projects that match the optional search filter.

    Project pagination calls this query before list_projects. The search filter
    matches project name, project key, or cwd using the current SQL expression.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        title_like: Optional case-insensitive project search fragment.

    Returns:
        Number of distinct project keys matching the filter.
    """
    clauses = []
    params: list = []
    if title_like:
        clauses.append(
            "(LOWER(project_name) LIKE LOWER(?) OR LOWER(project_key) LIKE LOWER(?) "
            "OR LOWER(cwd) LIKE LOWER(?))"
        )
        pattern = f"%{title_like}%"
        params.extend([pattern, pattern, pattern])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute(
        f"SELECT COUNT(DISTINCT project_key) FROM sessions {where}",
        params,
    ).fetchone()
    return row[0]


def list_projects(  # noqa: PLR0913 - Public query API mirrors existing route filters.
    conn: sqlite3.Connection,
    title_like: str | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "last_active",
    order_dir: str = "desc",
) -> list[ProjectStats]:
    """List project aggregates with pagination and safe sorting.

    The projects route calls this query for the project table. Sort keys are mapped
    through a fixed allowlist before they are interpolated into SQL.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        title_like: Optional case-insensitive project search fragment.
        limit: Maximum number of project rows to return.
        offset: Number of matching projects to skip.
        order_by: Public sort key mapped to a safe aggregate expression.
        order_dir: Sort direction, where asc maps to ASC and all other values map to DESC.

    Returns:
        ProjectStats rows ordered and paginated according to the supplied options.
    """
    clauses = []
    params: list = []
    if title_like:
        clauses.append(
            "(LOWER(project_name) LIKE LOWER(?) OR LOWER(project_key) LIKE LOWER(?) "
            "OR LOWER(cwd) LIKE LOWER(?))"
        )
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
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
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
            total_fresh_input_tokens=r["total_fresh_input_tokens"],
            total_output_tokens=r["total_output_tokens"],
            total_cache_read_tokens=r["total_cache_read_tokens"],
            total_cache_write_tokens=r["total_cache_write_tokens"],
            total_tool_calls=r["total_tool_calls"],
            total_failed_tools=r["total_failed_tools"],
            total_user_messages=r["total_user_messages"],
            total_assistant_messages=r["total_assistant_messages"],
        )
        for r in rows
    ]


# Dashboard queries.

# Agent scope mapping: URL value -> DB agent value.
_AGENT_SCOPE_MAP = {
    "claude-code": "claude_code",
    "qoder": "qoder",
    "codex": "codex",
}


def _agent_clause(agent_scope: str | None) -> tuple[str, list]:
    """Build the SQL agent filter fragment for dashboard scope values.

    Dashboard trend helpers call this shared helper before appending additional date
    predicates. Unknown scopes intentionally produce no filter.

    Args:
        agent_scope: URL-facing scope value such as all, claude-code, codex, or qoder.

    Returns:
        Tuple of SQL WHERE fragment and bound parameter list.
    """
    if not agent_scope or agent_scope == "all":
        return "", []
    db_agent = _AGENT_SCOPE_MAP.get(agent_scope)
    if db_agent:
        return "WHERE agent = ?", [db_agent]
    return "", []


def get_dashboard_stats(conn: sqlite3.Connection, agent_scope: str | None = None) -> dict:
    """Read dashboard aggregate counters, optionally scoped to one agent.

    The dashboard route calls this query for the top-level metric cards. Agent scope
    uses the same URL-to-database mapping as trend queries.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        agent_scope: Optional URL-facing agent scope filter.

    Returns:
        Dictionary of session, project, token, tool, and message aggregate counters.
    """
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
    """Read daily token and session trend data for recent activity.

    Dashboard charts call this query with a day window and optional agent scope. The
    date lower bound remains the first bound parameter before any agent filter.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        days: Number of recent days to include in the date filter.
        agent_scope: Optional URL-facing agent scope filter.

    Returns:
        List of daily dictionaries with per-agent counts, token totals, and tool totals.
    """
    where, params = _agent_clause(agent_scope)
    # Convert WHERE to AND when an agent filter is present.
    where_sql = where.replace("WHERE", "AND") if where else ""
    # SQL has date('now', ?) before agent = ?, so the date param must come first.
    params.insert(0, f"-{days} days")
    rows = conn.execute(
        f"""
        SELECT
            COALESCE(NULLIF(DATE(ended_at), ''), DATE('now')) as day,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_count,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_count,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_count,
            COALESCE(
                SUM(CASE WHEN agent='claude_code' THEN total_tokens ELSE 0 END), 0
            ) as claude_tokens,
            COALESCE(SUM(CASE WHEN agent='codex' THEN total_tokens ELSE 0 END), 0) as codex_tokens,
            COALESCE(SUM(CASE WHEN agent='qoder' THEN total_tokens ELSE 0 END), 0) as qoder_tokens,
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
            "claude_tokens": r["claude_tokens"],
            "codex_tokens": r["codex_tokens"],
            "qoder_tokens": r["qoder_tokens"],
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


def get_prompt_activity_trend(
    conn: sqlite3.Connection,
    days: int = 30,
    agent_scope: str | None = None,
) -> list[dict]:
    """Read daily prompt activity counts for recent sessions.

    Dashboard charts call this query with a day window and optional agent scope. It
    keeps prompt, assistant turn, and tool totals grouped by calendar day.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        days: Number of recent days to include in the date filter.
        agent_scope: Optional URL-facing agent scope filter.

    Returns:
        List of daily dictionaries with per-agent prompt counts and activity totals.
    """
    where, params = _agent_clause(agent_scope)
    where_sql = where.replace("WHERE", "AND") if where else ""
    # SQL has date('now', ?) before agent = ?, so the date param must come first.
    params.insert(0, f"-{days} days")
    rows = conn.execute(
        f"""
        SELECT
            COALESCE(NULLIF(DATE(ended_at), ''), DATE('now')) as day,
            COALESCE(
                SUM(CASE WHEN agent='claude_code' THEN user_message_count ELSE 0 END), 0
            ) as claude_prompts,
            COALESCE(
                SUM(CASE WHEN agent='codex' THEN user_message_count ELSE 0 END), 0
            ) as codex_prompts,
            COALESCE(
                SUM(CASE WHEN agent='qoder' THEN user_message_count ELSE 0 END), 0
            ) as qoder_prompts,
            COALESCE(SUM(user_message_count), 0) as total_prompts,
            COALESCE(SUM(assistant_message_count), 0) as assistant_turns,
            COALESCE(SUM(tool_call_count), 0) as tool_calls
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
            "assistant_turns": r["assistant_turns"],
            "tool_calls": r["tool_calls"],
        }
        for r in rows
    ]


# Agent queries.


def list_agents(conn: sqlite3.Connection) -> list[dict]:
    """List agent aggregates for the agent overview.

    The agent overview route calls this query to rank agents by last activity while
    including token, tool, message, and project counts.

    Args:
        conn: Open SQLite connection configured with the session index schema.

    Returns:
        Agent aggregate dictionaries ordered by latest indexed activity descending.
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
    """List token and tool aggregates grouped by agent and model.

    The model statistics view calls this query to compare non-empty model names. It
    preserves the current grouping and does not synthesize unknown model rows.

    Args:
        conn: Open SQLite connection configured with the session index schema.

    Returns:
        Dictionaries containing agent, model, token totals, tool totals, and process timing.
    """
    rows = conn.execute(
        """
        SELECT
            agent,
            model,
            COUNT(*) as total_sessions,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(fresh_input_tokens), 0) as fresh_input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as cache_write_tokens,
            COALESCE(SUM(tool_call_count), 0) as tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as failed_tools,
            COALESCE(SUM(model_execution_seconds + tool_execution_seconds), 0) as process_seconds,
            COALESCE(
                AVG(model_execution_seconds + tool_execution_seconds), 0
            ) as avg_process_seconds
        FROM sessions
        WHERE model != ''
        GROUP BY agent, model
        """
    ).fetchall()
    return [dict(r) for r in rows]
