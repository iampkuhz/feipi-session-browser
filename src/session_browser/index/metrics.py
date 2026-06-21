"""Aggregate indexed session metrics for dashboard and analysis views."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3


@dataclass
class TokenBreakdown:
    """Aggregate token and tool counters for indexed sessions.

    Dashboard metric queries create this DTO after summing the sessions table. The
    fields preserve the current SQLite column semantics and use zero when the source
    aggregate is empty.

    Attributes:
        total_fresh_input: Sum of fresh input tokens across all indexed sessions.
        total_output: Sum of output tokens across all indexed sessions.
        total_cache_read: Sum of cache read tokens across all indexed sessions.
        total_cache_write: Sum of cache write tokens across all indexed sessions.
        total_tool_calls: Sum of recorded tool calls across all indexed sessions.
        total_failed_tools: Sum of failed tool calls across all indexed sessions.
    """

    total_fresh_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    total_tool_calls: int = 0
    total_failed_tools: int = 0


@dataclass
class ModelDistribution:
    """Map model names to indexed session counts.

    Metric readers return this wrapper so callers can distinguish an empty result
    from a missing query. The mapping is always initialized before it leaves the
    module.

    Attributes:
        distribution: Session count keyed by non-empty model name.
    """

    distribution: dict[str, int] | None = None

    def __post_init__(self) -> None:
        """Initialize an empty distribution when callers omit the mapping."""
        if self.distribution is None:
            self.distribution = {}


def get_token_breakdown(conn: sqlite3.Connection) -> TokenBreakdown:
    """Summarize token and tool counters across all indexed sessions.

    The metrics layer calls this query for dashboard cards. It reads only the
    sessions table and converts null SQLite sums to zero counters.

    Args:
        conn: Open SQLite connection configured with the session index schema.

    Returns:
        TokenBreakdown containing aggregate token and tool counters.
    """
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input,
            COALESCE(SUM(output_tokens), 0) as total_output,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools
        FROM sessions
        """
    ).fetchone()
    return TokenBreakdown(
        total_fresh_input=row[0],
        total_output=row[1],
        total_cache_read=row[2],
        total_cache_write=row[3],
        total_tool_calls=row[4],
        total_failed_tools=row[5],
    )


def get_model_distribution(conn: sqlite3.Connection) -> ModelDistribution:
    """Count indexed sessions for each non-empty model.

    The dashboard model filter uses this query to rank models by frequency without
    changing session ordering elsewhere.

    Args:
        conn: Open SQLite connection configured with the session index schema.

    Returns:
        ModelDistribution keyed by model name in descending count order.
    """
    rows = conn.execute(
        """
        SELECT model, COUNT(*) as cnt
        FROM sessions
        WHERE model != ''
        GROUP BY model
        ORDER BY cnt DESC
        """
    ).fetchall()
    return ModelDistribution(distribution={r[0]: r[1] for r in rows})


def get_agent_distribution(conn: sqlite3.Connection) -> dict[str, int]:
    """Count indexed sessions by agent value.

    Agent navigation uses this helper to build the current distribution from the
    sessions table.

    Args:
        conn: Open SQLite connection configured with the session index schema.

    Returns:
        Mapping from agent identifier to session count in descending count order.
    """
    rows = conn.execute(
        """
        SELECT agent, COUNT(*) as cnt
        FROM sessions
        GROUP BY agent
        ORDER BY cnt DESC
        """
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_tool_distribution(conn: sqlite3.Connection) -> dict[str, int]:
    """Return the sessions with the largest recorded tool counts.

    The metrics view calls this for a top-session widget. It intentionally reports
    per-session tool totals, not per-tool-name totals, because tool names require
    raw event parsing.

    Args:
        conn: Open SQLite connection configured with the session index schema.

    Returns:
        Mapping keyed by session key with title and tool call count payloads.
    """
    rows = conn.execute(
        """
        SELECT session_key, title, tool_call_count
        FROM sessions
        WHERE tool_call_count > 0
        ORDER BY tool_call_count DESC
        LIMIT 20
        """
    ).fetchall()
    return {r[0]: {"title": r[1], "tool_call_count": r[2]} for r in rows}


def get_top_projects_by_tokens(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """List projects ranked by aggregate token usage.

    The project summary panel calls this query to highlight high-volume projects.
    Rows are grouped by project key and limited by the caller.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        limit: Maximum number of project rows to return.

    Returns:
        Project dictionaries ordered by total token usage descending.
    """
    rows = conn.execute(
        """
        SELECT
            project_key,
            project_name,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COUNT(*) as session_count
        FROM sessions
        GROUP BY project_key
        ORDER BY total_tokens DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_top_projects_by_tools(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """List projects ranked by aggregate tool call count.

    The project summary panel calls this query to highlight tool-heavy projects and
    failed tool totals.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        limit: Maximum number of project rows to return.

    Returns:
        Project dictionaries ordered by total tool calls descending.
    """
    rows = conn.execute(
        """
        SELECT
            project_key,
            project_name,
            COALESCE(SUM(tool_call_count), 0) as total_tools,
            COALESCE(SUM(failed_tool_count), 0) as failed_tools,
            COUNT(*) as session_count
        FROM sessions
        GROUP BY project_key
        ORDER BY total_tools DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_slowest_sessions(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """List sessions with the longest positive duration.

    The metrics page calls this query to surface slow sessions while preserving the
    existing duration ordering and result shape.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        limit: Maximum number of session rows to return.

    Returns:
        Session dictionaries ordered by duration descending.
    """
    rows = conn.execute(
        """
        SELECT session_key, title, agent, model, duration_seconds, project_name
        FROM sessions
        WHERE duration_seconds > 0
        ORDER BY duration_seconds DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_failed_tool_sessions(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """List sessions that recorded failed tool calls.

    The metrics page calls this query to surface sessions that need failure review.
    Only sessions with positive failed tool counts are returned.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        limit: Maximum number of session rows to return.

    Returns:
        Session dictionaries ordered by failed tool count descending.
    """
    rows = conn.execute(
        """
        SELECT session_key, title, agent, model, failed_tool_count, project_name
        FROM sessions
        WHERE failed_tool_count > 0
        ORDER BY failed_tool_count DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_high_cache_read_sessions(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """List sessions with the highest cache read share.

    The metrics page calls this query to show sessions that reused the cache most
    heavily among sessions with cache reads.

    Args:
        conn: Open SQLite connection configured with the session index schema.
        limit: Maximum number of session rows to return.

    Returns:
        Session dictionaries ordered by computed cache hit percentage descending.
    """
    rows = conn.execute(
        """
        SELECT
            session_key,
            title,
            agent,
            model,
            cache_read_tokens,
            fresh_input_tokens,
            project_name,
            CASE
                WHEN fresh_input_tokens + cache_read_tokens > 0
                THEN ROUND(100.0 * cache_read_tokens / (fresh_input_tokens + cache_read_tokens), 1)
                ELSE 0
            END as cache_hit_pct
        FROM sessions
        WHERE cache_read_tokens > 0
        ORDER BY cache_hit_pct DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# Derived metrics.


def safe_div(a: int | float | None, b: int | float | None) -> float | None:
    """Divide two optional numeric values without raising for empty denominators.

    Derived metric helpers use this guard so missing SQLite aggregates or zero
    round counts produce null metric values instead of exceptions.

    Args:
        a: Numerator value to divide.
        b: Denominator value; zero and None both suppress the division.

    Returns:
        Quotient as a float, or None when either input is None or the denominator is zero.
    """
    if a is None or b is None or b == 0:
        return None
    return a / b


def compute_derived_metrics(session_row: dict) -> dict:
    """Add derived ratios and rates to one session row in place.

    Session detail and list presenters call this helper after reading a session row.
    It preserves the original mapping and adds derived token, cache, round, and
    per-minute fields using None for undefined ratios.

    Args:
        session_row: Mutable session dictionary using index column names.

    Returns:
        The same dictionary enriched with derived metric keys.
    """
    fresh_input_tokens = session_row.get("fresh_input_tokens", 0) or 0
    output_tokens = session_row.get("output_tokens", 0) or 0
    cache_read = session_row.get("cache_read_tokens", 0) or 0
    cache_write = session_row.get("cache_write_tokens", 0) or 0
    tools = session_row.get("tool_call_count", 0) or 0
    duration = session_row.get("duration_seconds", 0) or 0
    rounds = session_row.get("assistant_message_count", 0) or 0

    input_side_total = fresh_input_tokens + cache_read + cache_write

    cache_reuse_ratio = safe_div(cache_read, input_side_total)
    cache_write_ratio = safe_div(cache_write, input_side_total)
    output_ratio = safe_div(output_tokens, input_side_total)
    tools_per_round = safe_div(tools, rounds)
    tokens_per_round = safe_div(input_side_total + output_tokens, rounds)
    tokens_per_minute = (
        safe_div(input_side_total + output_tokens, duration / 60.0) if duration > 0 else None
    )
    output_per_minute = safe_div(output_tokens, duration / 60.0) if duration > 0 else None

    session_row["input_side_total"] = input_side_total
    session_row["cache_reuse_ratio"] = (
        round(cache_reuse_ratio, 4) if cache_reuse_ratio is not None else None
    )
    session_row["cache_write_ratio"] = (
        round(cache_write_ratio, 4) if cache_write_ratio is not None else None
    )
    session_row["output_ratio"] = round(output_ratio, 4) if output_ratio is not None else None
    session_row["tools_per_round"] = (
        round(tools_per_round, 2) if tools_per_round is not None else None
    )
    session_row["tokens_per_round"] = (
        round(tokens_per_round, 1) if tokens_per_round is not None else None
    )
    session_row["tokens_per_minute"] = (
        round(tokens_per_minute, 1) if tokens_per_minute is not None else None
    )
    session_row["output_per_minute"] = (
        round(output_per_minute, 1) if output_per_minute is not None else None
    )

    return session_row


def compute_aggregate_metrics(conn: sqlite3.Connection) -> dict:
    """Compute dashboard-level derived metrics across all sessions.

    The dashboard metrics endpoint calls this query after basic aggregate cards. It
    uses total input-side tokens as the shared denominator for cache and output
    ratios.

    Args:
        conn: Open SQLite connection configured with the session index schema.

    Returns:
        Dictionary containing aggregate input totals, ratios, and per-round rates.
    """
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input,
            COALESCE(SUM(output_tokens), 0) as total_output,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write,
            COALESCE(SUM(tool_call_count), 0) as total_tools,
            COALESCE(SUM(assistant_message_count), 0) as total_rounds
        FROM sessions
        """
    ).fetchone()

    total_fresh_input = row["total_fresh_input"]
    total_output = row["total_output"]
    total_cache_read = row["total_cache_read"]
    total_cache_write = row["total_cache_write"]
    total_tools = row["total_tools"]
    total_rounds = row["total_rounds"]

    input_side_total = total_fresh_input + total_cache_read + total_cache_write

    cache_reuse = safe_div(total_cache_read, input_side_total)
    cache_write = safe_div(total_cache_write, input_side_total)
    output_ratio = safe_div(total_output, input_side_total)
    tools_per_round = safe_div(total_tools, total_rounds)
    tokens_per_round = safe_div(input_side_total + total_output, total_rounds)

    return {
        "input_side_total": input_side_total,
        "cache_reuse_ratio": round(cache_reuse, 4) if cache_reuse else None,
        "cache_write_ratio": round(cache_write, 4) if cache_write else None,
        "output_ratio": round(output_ratio, 4) if output_ratio else None,
        "tools_per_round": round(tools_per_round, 2) if tools_per_round else None,
        "tokens_per_round": round(tokens_per_round, 1) if tokens_per_round else None,
    }


def compute_agent_efficiency(conn: sqlite3.Connection) -> list[dict]:
    """Compute efficiency metrics grouped by agent and model.

    The dashboard efficiency table calls this query to compare agent/model groups.
    It preserves the existing grouping, ordering, and percentile approximation.

    Args:
        conn: Open SQLite connection configured with the session index schema.

    Returns:
        List of dictionaries with session counts, durations, tool rates, cache reuse,
        and failure rates per agent/model group.
    """
    rows = conn.execute(
        """
        SELECT
            agent,
            COALESCE(model, 'unknown') as model,
            COUNT(*) as session_count,
            AVG(duration_seconds) as avg_duration,
            COALESCE(
                SUM(fresh_input_tokens + cache_read_tokens + cache_write_tokens), 0
            ) as total_input_side,
            COALESCE(SUM(tool_call_count), 0) as total_tools,
            COALESCE(SUM(assistant_message_count), 0) as total_rounds,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read,
            COALESCE(SUM(failed_tool_count), 0) as total_failed
        FROM sessions
        GROUP BY agent, model
        ORDER BY session_count DESC
        """
    ).fetchall()

    # Keep the existing duration samples per agent/model for P95.
    duration_rows = conn.execute(
        """
        SELECT agent, COALESCE(model, 'unknown') as model, duration_seconds
        FROM sessions
        WHERE duration_seconds > 0
        ORDER BY agent, model, duration_seconds
        """
    ).fetchall()

    durations: dict[str, list[float]] = defaultdict(list)
    for r in duration_rows:
        key = f"{r['agent']}|||{r['model']}"
        durations[key].append(r["duration_seconds"])

    def p95(values: list[float]) -> float:
        """Return the existing nearest-rank P95 approximation for duration values.

        Args:
            values: Duration values collected for a single agent/model pair.

        Returns:
            The selected P95 duration, or zero when no positive durations exist.
        """
        if not values:
            return 0
        s = sorted(values)
        idx = int(0.95 * (len(s) - 1))
        return s[idx]

    result = []
    for r in rows:
        key = f"{r['agent']}|||{r['model']}"
        session_count = r["session_count"]
        avg_duration = r["avg_duration"] or 0
        p95_duration = p95(durations.get(key, []))
        total_input_side = r["total_input_side"]
        total_tools = r["total_tools"]
        total_rounds = r["total_rounds"]
        total_cache_read = r["total_cache_read"]
        total_failed = r["total_failed"]

        cache_reuse = safe_div(total_cache_read, total_input_side)
        tpr = safe_div(total_tools, total_rounds)
        failed_per_session = safe_div(total_failed, session_count)

        result.append(
            {
                "agent": r["agent"],
                "model": r["model"],
                "session_count": session_count,
                "avg_duration": round(avg_duration, 1),
                "p95_duration": round(p95_duration, 1),
                "avg_input_side": total_input_side,
                "avg_tools": round(safe_div(total_tools, session_count), 1)
                if session_count > 0
                else 0,
                "tools_per_round": round(tpr, 2) if tpr else None,
                "cache_reuse_ratio": round(cache_reuse, 4) if cache_reuse else None,
                "failed_per_session": round(failed_per_session, 4) if failed_per_session else None,
            }
        )

    return result
