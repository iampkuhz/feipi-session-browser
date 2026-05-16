"""Metrics aggregation utilities for session-browser."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3


@dataclass
class TokenBreakdown:
    """Token usage breakdown across all sessions."""

    total_input: int = 0
    total_output: int = 0
    total_cached_input: int = 0  # cache read
    total_cached_output: int = 0  # cache write
    total_tool_calls: int = 0
    total_failed_tools: int = 0


@dataclass
class ModelDistribution:
    """Count of sessions per model."""

    distribution: dict[str, int] = None

    def __post_init__(self):
        if self.distribution is None:
            self.distribution = {}


def get_token_breakdown(conn: sqlite3.Connection) -> TokenBreakdown:
    """Get total token usage across all indexed sessions."""
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(input_tokens), 0) as total_input,
            COALESCE(SUM(output_tokens), 0) as total_output,
            COALESCE(SUM(cached_input_tokens), 0) as total_cached_input,
            COALESCE(SUM(cached_output_tokens), 0) as total_cached_output,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools
        FROM sessions
        """
    ).fetchone()
    return TokenBreakdown(
        total_input=row[0],
        total_output=row[1],
        total_cached_input=row[2],
        total_cached_output=row[3],
        total_tool_calls=row[4],
        total_failed_tools=row[5],
    )


def get_model_distribution(conn: sqlite3.Connection) -> ModelDistribution:
    """Get session count per model."""
    rows = conn.execute(
        """
        SELECT model, COUNT(*) as cnt
        FROM sessions
        WHERE model != ''
        GROUP BY model
        ORDER BY cnt DESC
        """
    ).fetchall()
    return ModelDistribution(
        distribution={r[0]: r[1] for r in rows}
    )


def get_agent_distribution(conn: sqlite3.Connection) -> dict[str, int]:
    """Get session count per agent type."""
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
    """Get total tool call count per session (top sessions by tool usage).

    This returns per-session tool counts, not per-tool-name counts.
    Per-tool-name breakdown requires parsing raw events.
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
    """Get top projects by total token usage."""
    rows = conn.execute(
        """
        SELECT
            project_key,
            project_name,
            COALESCE(SUM(input_tokens + output_tokens + cached_input_tokens + cached_output_tokens), 0) as total_tokens,
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
    """Get top projects by tool call count."""
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
    """Get sessions with longest duration."""
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
    """Get sessions with failed tool calls."""
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
    """Get sessions with highest cache read ratio."""
    rows = conn.execute(
        """
        SELECT
            session_key,
            title,
            agent,
            model,
            cached_input_tokens,
            input_tokens,
            project_name,
            CASE
                WHEN input_tokens + cached_input_tokens > 0
                THEN ROUND(100.0 * cached_input_tokens / (input_tokens + cached_input_tokens), 1)
                ELSE 0
            END as cache_hit_pct
        FROM sessions
        WHERE cached_input_tokens > 0
        ORDER BY cache_hit_pct DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ─── Derived metrics ─────────────────────────────────────────────────────


def safe_div(a: int | float | None, b: int | float | None) -> float | None:
    """Safe division: returns None when denominator is 0 or inputs are None."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def compute_derived_metrics(session_row: dict) -> dict:
    """Compute derived metrics for a single session row.

    Adds: input_side_total, cache_reuse_ratio, cache_write_ratio,
          output_ratio, tools_per_round, tokens_per_round, tokens_per_minute, output_per_minute.

    Args:
        session_row: Dict with session fields.

    Returns:
        Original dict enriched with derived metrics (mutated in place).
    """
    input_tokens = session_row.get("input_tokens", 0) or 0
    output_tokens = session_row.get("output_tokens", 0) or 0
    cache_read = session_row.get("cached_input_tokens", 0) or 0
    cache_write = session_row.get("cached_output_tokens", 0) or 0
    tools = session_row.get("tool_call_count", 0) or 0
    duration = session_row.get("duration_seconds", 0) or 0
    rounds = session_row.get("assistant_message_count", 0) or 0

    input_side_total = input_tokens + cache_read + cache_write

    cache_reuse_ratio = safe_div(cache_read, input_side_total)
    cache_write_ratio = safe_div(cache_write, input_side_total)
    output_ratio = safe_div(output_tokens, input_side_total)
    tools_per_round = safe_div(tools, rounds)
    tokens_per_round = safe_div(input_side_total + output_tokens, rounds)
    tokens_per_minute = safe_div(input_side_total + output_tokens, duration / 60.0) if duration > 0 else None
    output_per_minute = safe_div(output_tokens, duration / 60.0) if duration > 0 else None

    session_row["input_side_total"] = input_side_total
    session_row["cache_reuse_ratio"] = round(cache_reuse_ratio, 4) if cache_reuse_ratio is not None else None
    session_row["cache_write_ratio"] = round(cache_write_ratio, 4) if cache_write_ratio is not None else None
    session_row["output_ratio"] = round(output_ratio, 4) if output_ratio is not None else None
    session_row["tools_per_round"] = round(tools_per_round, 2) if tools_per_round is not None else None
    session_row["tokens_per_round"] = round(tokens_per_round, 1) if tokens_per_round is not None else None
    session_row["tokens_per_minute"] = round(tokens_per_minute, 1) if tokens_per_minute is not None else None
    session_row["output_per_minute"] = round(output_per_minute, 1) if output_per_minute is not None else None

    return session_row


def compute_aggregate_metrics(conn: sqlite3.Connection) -> dict:
    """Compute dashboard-level aggregate derived metrics.

    Returns dict with cache_reuse, output_ratio, tools_per_round, etc.
    """
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(input_tokens), 0) as total_input,
            COALESCE(SUM(output_tokens), 0) as total_output,
            COALESCE(SUM(cached_input_tokens), 0) as total_cache_read,
            COALESCE(SUM(cached_output_tokens), 0) as total_cache_write,
            COALESCE(SUM(tool_call_count), 0) as total_tools,
            COALESCE(SUM(assistant_message_count), 0) as total_rounds
        FROM sessions
        """
    ).fetchone()

    total_input = row["total_input"]
    total_output = row["total_output"]
    total_cache_read = row["total_cache_read"]
    total_cache_write = row["total_cache_write"]
    total_tools = row["total_tools"]
    total_rounds = row["total_rounds"]

    input_side_total = total_input + total_cache_read + total_cache_write

    return {
        "input_side_total": input_side_total,
        "cache_reuse_ratio": round(safe_div(total_cache_read, input_side_total), 4) if safe_div(total_cache_read, input_side_total) else None,
        "cache_write_ratio": round(safe_div(total_cache_write, input_side_total), 4) if safe_div(total_cache_write, input_side_total) else None,
        "output_ratio": round(safe_div(total_output, input_side_total), 4) if safe_div(total_output, input_side_total) else None,
        "tools_per_round": round(safe_div(total_tools, total_rounds), 2) if safe_div(total_tools, total_rounds) else None,
        "tokens_per_round": round(safe_div(input_side_total + total_output, total_rounds), 1) if safe_div(input_side_total + total_output, total_rounds) else None,
    }


def compute_agent_efficiency(conn: sqlite3.Connection) -> list[dict]:
    """Compute per-agent/model efficiency metrics.

    Returns list of {agent, model, session_count, avg_duration, p95_duration,
                     avg_input_side, avg_tools, tools_per_round, cache_reuse_ratio,
                     failed_per_session, anomaly_rate}.
    """
    rows = conn.execute(
        """
        SELECT
            agent,
            COALESCE(model, 'unknown') as model,
            COUNT(*) as session_count,
            AVG(duration_seconds) as avg_duration,
            COALESCE(SUM(input_tokens + cached_input_tokens + cached_output_tokens), 0) as total_input_side,
            COALESCE(SUM(tool_call_count), 0) as total_tools,
            COALESCE(SUM(assistant_message_count), 0) as total_rounds,
            COALESCE(SUM(cached_input_tokens), 0) as total_cache_read,
            COALESCE(SUM(failed_tool_count), 0) as total_failed
        FROM sessions
        GROUP BY agent, model
        ORDER BY session_count DESC
        """
    ).fetchall()

    # Get duration values per agent/model for P95
    duration_rows = conn.execute(
        """
        SELECT agent, COALESCE(model, 'unknown') as model, duration_seconds
        FROM sessions
        WHERE duration_seconds > 0
        ORDER BY agent, model, duration_seconds
        """
    ).fetchall()

    # Build duration lists per (agent, model)
    from collections import defaultdict
    durations: dict[str, list] = defaultdict(list)
    for r in duration_rows:
        key = f"{r['agent']}|||{r['model']}"
        durations[key].append(r["duration_seconds"])

    # Compute P95
    def p95(values):
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

        result.append({
            "agent": r["agent"],
            "model": r["model"],
            "session_count": session_count,
            "avg_duration": round(avg_duration, 1),
            "p95_duration": round(p95_duration, 1),
            "avg_input_side": total_input_side,
            "avg_tools": round(safe_div(total_tools, session_count), 1) if session_count > 0 else 0,
            "tools_per_round": round(tpr, 2) if tpr else None,
            "cache_reuse_ratio": round(cache_reuse, 4) if cache_reuse else None,
            "failed_per_session": round(failed_per_session, 4) if failed_per_session else None,
        })

    return result
