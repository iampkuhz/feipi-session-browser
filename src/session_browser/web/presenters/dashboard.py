"""Dashboard presenter.

Builds the complete view model for the dashboard page, supporting:
- Agent scope: all / claude-code / qoder / codex
- Time grain: day / week / month
- 6 KPI cards with secondary metrics
- 3 trend cards (Session Trend, Token Trend, Prompt Activity Trend)
- Token analysis cards (Token Trend by Composition, Cache Health)
- All agents branch (Agent Contribution Comparison, All Agents table, Agent/Model Efficiency)
- Single agent branch (Model Mix, Tool Distribution, Failure Signals, Model Efficiency Detail, Agent Sessions)
"""
from __future__ import annotations

import math
import sqlite3
from typing import Any

from session_browser.index.indexer import (
    get_dashboard_stats,
    list_sessions,
    list_projects,
    get_trend_data,
    get_prompt_activity_trend,
    list_agents,
)
from session_browser.index.queries import list_model_stats
from session_browser.index.metrics import (
    get_agent_distribution,
    get_token_breakdown,
    compute_derived_metrics,
    compute_aggregate_metrics,
)
from session_browser.index.anomalies import (
    detect_all_anomalies,
    get_needs_attention,
)


# Valid agent scope values
VALID_AGENT_SCOPES = {"all", "claude-code", "qoder", "codex"}
VALID_GRAINS = {"day", "week", "month"}

# Grain -> days mapping for trend windows
GRAIN_DAYS = {
    "day": 30,
    "week": 20 * 7,  # 20 ISO weeks
    "month": 12 * 30,  # 12 months
}

_AGENT_DISPLAY = {
    "claude-code": "Claude Code",
    "qoder": "Qoder",
    "codex": "Codex",
}

_DB_AGENT = {
    "claude-code": "claude_code",
    "qoder": "qoder",
    "codex": "codex",
}


def _fmt(n: int | float) -> str:
    """Format a number with commas."""
    if n is None:
        return "0"
    return f"{int(n):,}"


def _fmt_compact(n: int | float) -> str:
    """Format token count with compact suffix (K/M/B), 1 decimal."""
    if n is None or n == 0:
        return "0"
    n = float(n)
    if n >= 1e9:
        return f"{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return str(int(n))


def _safe_ratio(num: int | float, den: int | float, fmt_func=_fmt) -> str:
    """Compute ratio safely, returning N/A when denominator is 0."""
    if not den or den == 0:
        return "N/A"
    return f"{num / den * 100:.1f}%"


def _safe_ratio_float(num: int | float, den: int | float) -> float | None:
    """Compute ratio as float, returning None when denominator is 0."""
    if not den or den == 0:
        return None
    return num / den


def build_dashboard_view_model(
    conn: sqlite3.Connection,
    agent_scope: str | None = None,
    grain: str | None = None,
) -> dict[str, Any]:
    """Build the complete view model for the dashboard page.

    Args:
        conn: SQLite connection.
        agent_scope: 'all', 'claude-code', 'qoder', 'codex'. Defaults to 'all'.
        grain: 'day', 'week', 'month'. Defaults to 'day'.

    Returns:
        Dict ready for Jinja template rendering.
    """
    # Normalize inputs
    agent_scope = agent_scope or "all"
    if agent_scope not in VALID_AGENT_SCOPES:
        agent_scope = "all"
    grain = grain or "day"
    if grain not in VALID_GRAINS:
        grain = "day"

    is_single_agent = agent_scope != "all"
    db_agent = _DB_AGENT.get(agent_scope)

    # ── Core stats ─────────────────────────────────────────────────────
    stats = get_dashboard_stats(conn, agent_scope=agent_scope)

    # ── Trend data ─────────────────────────────────────────────────────
    days = GRAIN_DAYS[grain]
    trend = get_trend_data(conn, days=days, agent_scope=agent_scope)
    prompt_activity = get_prompt_activity_trend(conn, days=days, agent_scope=agent_scope)

    # ── KPIs ───────────────────────────────────────────────────────────
    kpis = _compute_kpis(stats, conn, agent_scope)

    # ── All agents branch data ─────────────────────────────────────────
    all_agents_branch = None
    if not is_single_agent:
        all_agents_branch = _compute_all_agents_branch(conn)

    # ── Single agent branch data ───────────────────────────────────────
    single_agent_branch = None
    if is_single_agent and db_agent:
        single_agent_branch = _compute_single_agent_branch(conn, db_agent, agent_scope)

    # ── Anomaly / needs attention (only for all agents) ────────────────
    needs_attention = []
    if not is_single_agent:
        all_sessions_raw = list_sessions(conn, limit=2000, order_by="ended_at")
        sessions_data = []
        for s in all_sessions_raw:
            sessions_data.append(compute_derived_metrics(s.to_dict()))
        anomalies_map = detect_all_anomalies(sessions_data)
        # Convert list to dict lookup keyed by session_key
        sessions_lookup = {s.get("session_key", ""): s for s in sessions_data}
        needs_attention = get_needs_attention(anomalies_map, sessions_lookup, limit=8)

    # ── Cache Health stats ─────────────────────────────────────────
    cache_health = _compute_cache_health_stats(trend)

    return {
        "agent_scope": agent_scope,
        "grain": grain,
        "is_single_agent": is_single_agent,
        "stats": stats,
        "kpis": kpis,
        "trend": trend,
        "prompt_activity": prompt_activity,
        "all_agents_branch": all_agents_branch,
        "single_agent_branch": single_agent_branch,
        "needs_attention": needs_attention,
        "cache_health": cache_health,
        "active_page": "dashboard",
    }


def _compute_kpis(
    stats: dict,
    conn: sqlite3.Connection,
    agent_scope: str,
) -> list[dict]:
    """Compute 6 KPI cards with secondary metrics."""
    total_sessions = stats.get("total_sessions", 0)
    project_count = stats.get("project_count", 0)
    total_tokens = stats.get("total_tokens", 0)
    total_fresh = stats.get("total_fresh_input_tokens", 0)
    total_cache_read = stats.get("total_cache_read_tokens", 0)
    total_cache_write = stats.get("total_cache_write_tokens", 0)
    total_output = stats.get("total_output_tokens", 0)
    total_tool_calls = stats.get("total_tool_calls", 0)
    total_failed_tools = stats.get("total_failed_tools", 0)
    total_user_messages = stats.get("total_user_messages", 0)
    total_assistant_messages = stats.get("total_assistant_messages", 0)

    input_side = total_fresh + total_cache_read + total_cache_write

    kpis = []

    # 1. Projects
    kpis.append({
        "label": "Projects",
        "value": _fmt(project_count),
        "secondary": [
            {"label": "Active 24h", "value": _fmt(_count_active_projects(conn, agent_scope, 1))},
            {"label": "Active 7d", "value": _fmt(_count_active_projects(conn, agent_scope, 7))},
            {"label": "New 7d", "value": _fmt(_count_new_projects(conn, agent_scope, 7))},
        ],
    })

    # 2. Sessions
    median_duration = _median_duration(conn, agent_scope)
    avg_rounds = total_assistant_messages / total_sessions if total_sessions > 0 else 0
    kpis.append({
        "label": "Sessions",
        "value": _fmt(total_sessions),
        "secondary": [
            {"label": "Today", "value": _fmt(_count_today_sessions(conn, agent_scope))},
            {"label": "7d Avg", "value": _fmt_compact(_avg_daily_sessions(conn, agent_scope, 7))},
            {"label": "Median Duration", "value": _format_duration(median_duration)},
            {"label": "Avg Rounds", "value": f"{avg_rounds:.1f}"},
        ],
    })

    # 3. Total Tokens
    kpis.append({
        "label": "Total Tokens",
        "value": _fmt_compact(total_tokens),
        "secondary": [
            {"label": "Fresh", "value": _fmt_compact(total_fresh)},
            {"label": "Cache Read", "value": _fmt_compact(total_cache_read)},
            {"label": "Cache Write", "value": _fmt_compact(total_cache_write)},
            {"label": "Output", "value": _fmt_compact(total_output)},
        ],
    })

    # 4. Prompt Activity
    prompts_per_session = total_user_messages / total_sessions if total_sessions > 0 else 0
    kpis.append({
        "label": "Prompt Activity",
        "value": _fmt(total_user_messages),
        "secondary": [
            {"label": "Assistant Turns", "value": _fmt(total_assistant_messages)},
            {"label": "Tool Calls", "value": _fmt(total_tool_calls)},
            {"label": "Prompts / Session", "value": f"{prompts_per_session:.1f}" if total_sessions > 0 else "N/A"},
        ],
    })

    # 5. Cache Read Ratio
    cache_ratio = _safe_ratio_float(total_cache_read, input_side)
    eligible_sessions = _count_eligible_sessions(conn, agent_scope)
    p50_ratio = _p50_cache_ratio(conn, agent_scope)
    low_read_sessions = _count_low_read_sessions(conn, agent_scope)
    kpis.append({
        "label": "Cache Read Ratio",
        "value": f"{cache_ratio * 100:.1f}%" if cache_ratio is not None else "N/A",
        "secondary": [
            {"label": "Eligible Sessions", "value": _fmt(eligible_sessions)},
            {"label": "P50 Session Ratio", "value": f"{p50_ratio * 100:.1f}%" if p50_ratio is not None else "N/A"},
            {"label": "Low-read Sessions", "value": _fmt(low_read_sessions)},
        ],
    })

    # 6. Failed Tools
    failure_rate = _safe_ratio_float(total_failed_tools, total_tool_calls)
    affected_sessions = _count_affected_failure_sessions(conn, agent_scope)
    repeated_failure = _count_repeated_failure_sessions(conn, agent_scope)
    kpis.append({
        "label": "Failed Tools",
        "value": _fmt(total_failed_tools),
        "secondary": [
            {"label": "Failure Rate", "value": f"{failure_rate * 100:.1f}%" if failure_rate is not None else "N/A"},
            {"label": "Affected Sessions", "value": _fmt(affected_sessions)},
            {"label": "Repeated Failure Sessions", "value": _fmt(repeated_failure)},
        ],
    })

    return kpis


def _count_active_projects(conn: sqlite3.Connection, agent_scope: str, days: int) -> int:
    """Count distinct projects with session events in the last N days."""
    where, params = _build_agent_where(agent_scope)
    row = conn.execute(
        f"SELECT COUNT(DISTINCT project_key) FROM sessions {where} AND ended_at >= date('now', '-{days} days')",
        params,
    ).fetchone()
    return row[0] if row else 0


def _count_new_projects(conn: sqlite3.Connection, agent_scope: str, days: int) -> int:
    """Count distinct projects first seen in the last N days."""
    where, params = _build_agent_where(agent_scope)
    row = conn.execute(
        f"SELECT COUNT(DISTINCT project_key) FROM sessions {where} AND started_at >= date('now', '-{days} days')",
        params,
    ).fetchone()
    return row[0] if row else 0


def _count_today_sessions(conn: sqlite3.Connection, agent_scope: str) -> int:
    """Count sessions with first user message today."""
    where, params = _build_agent_where(agent_scope)
    row = conn.execute(
        f"SELECT COUNT(*) FROM sessions {where} AND DATE(started_at) = DATE('now')",
        params,
    ).fetchone()
    return row[0] if row else 0


def _avg_daily_sessions(conn: sqlite3.Connection, agent_scope: str, days: int) -> float:
    """Average daily session count over last N days."""
    where, params = _build_agent_where(agent_scope)
    row = conn.execute(
        f"SELECT COUNT(*) FROM sessions {where} AND ended_at >= date('now', '-{days} days')",
        params,
    ).fetchone()
    total = row[0] if row else 0
    return total / days


def _median_duration(conn: sqlite3.Connection, agent_scope: str) -> float:
    """Median session duration in seconds."""
    where, params = _build_agent_where(agent_scope)
    rows = conn.execute(
        f"SELECT duration_seconds FROM sessions {where} AND duration_seconds > 0 ORDER BY duration_seconds",
        params,
    ).fetchall()
    if not rows:
        return 0
    durations = [r["duration_seconds"] for r in rows]
    n = len(durations)
    if n == 0:
        return 0
    mid = n // 2
    if n % 2 == 0:
        return (durations[mid - 1] + durations[mid]) / 2
    return durations[mid]


def _count_eligible_sessions(conn: sqlite3.Connection, agent_scope: str) -> int:
    """Count sessions with input-side tokens > 0."""
    where, params = _build_agent_where(agent_scope)
    row = conn.execute(
        f"SELECT COUNT(*) FROM sessions {where} AND (fresh_input_tokens + cache_read_tokens + cache_write_tokens) > 0",
        params,
    ).fetchone()
    return row[0] if row else 0


def _p50_cache_ratio(conn: sqlite3.Connection, agent_scope: str) -> float | None:
    """Median per-session cache read ratio."""
    where, params = _build_agent_where(agent_scope)
    rows = conn.execute(
        f"""SELECT cache_read_tokens * 1.0 / NULLIF(fresh_input_tokens + cache_read_tokens + cache_write_tokens, 0) as ratio
            FROM sessions {where}
            AND (fresh_input_tokens + cache_read_tokens + cache_write_tokens) > 0
            ORDER BY ratio""",
        params,
    ).fetchall()
    if not rows:
        return None
    ratios = [r["ratio"] for r in rows if r["ratio"] is not None]
    if not ratios:
        return None
    n = len(ratios)
    mid = n // 2
    if n % 2 == 0:
        return (ratios[mid - 1] + ratios[mid]) / 2
    return ratios[mid]


def _count_low_read_sessions(conn: sqlite3.Connection, agent_scope: str) -> int:
    """Count eligible sessions with cache read ratio < 20%."""
    where, params = _build_agent_where(agent_scope)
    row = conn.execute(
        f"""SELECT COUNT(*) FROM sessions {where}
            AND (fresh_input_tokens + cache_read_tokens + cache_write_tokens) > 0
            AND cache_read_tokens * 1.0 / (fresh_input_tokens + cache_read_tokens + cache_write_tokens) < 0.2""",
        params,
    ).fetchone()
    return row[0] if row else 0


def _count_affected_failure_sessions(conn: sqlite3.Connection, agent_scope: str) -> int:
    """Count sessions with failed_tool_count > 0."""
    where, params = _build_agent_where(agent_scope)
    row = conn.execute(
        f"SELECT COUNT(*) FROM sessions {where} AND failed_tool_count > 0",
        params,
    ).fetchone()
    return row[0] if row else 0


def _count_repeated_failure_sessions(conn: sqlite3.Connection, agent_scope: str) -> int:
    """Count sessions with failed_tool_count > 1."""
    where, params = _build_agent_where(agent_scope)
    row = conn.execute(
        f"SELECT COUNT(*) FROM sessions {where} AND failed_tool_count > 1",
        params,
    ).fetchone()
    return row[0] if row else 0


def _format_duration(seconds: float) -> str:
    """Format seconds to human-readable duration."""
    if seconds <= 0:
        return "0s"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"


def _compute_cache_health_stats(trend: list) -> dict:
    """Compute Cache Health card stats from trend data."""
    if not trend:
        return {"latest_ratio": "N/A", "lowest_ratio": "N/A", "fresh_spikes": "0"}

    # Latest ratio
    last = trend[-1]
    input_side = (last.get("fresh_input_tokens", 0) +
                  last.get("cache_read_tokens", 0) +
                  last.get("cache_write_tokens", 0))
    if input_side > 0:
        latest_ratio = f"{last.get('cache_read_tokens', 0) / input_side * 100:.1f}%"
    else:
        latest_ratio = "N/A"

    # Lowest ratio across all points
    ratios = []
    for d in trend:
        inp = (d.get("fresh_input_tokens", 0) +
               d.get("cache_read_tokens", 0) +
               d.get("cache_write_tokens", 0))
        if inp > 0:
            ratios.append(d.get("cache_read_tokens", 0) / inp)
    if ratios:
        lowest_ratio = f"{min(ratios) * 100:.1f}%"
    else:
        lowest_ratio = "N/A"

    # Fresh spikes (simplified: points where fresh > 1.5x median fresh)
    fresh_vals = [d.get("fresh_input_tokens", 0) for d in trend if d.get("fresh_input_tokens", 0) > 0]
    spike_count = 0
    if len(fresh_vals) >= 3:
        sorted_fresh = sorted(fresh_vals)
        median_idx = len(sorted_fresh) // 2
        median_fresh = sorted_fresh[median_idx]
        threshold = max(1.8 * median_fresh, median_fresh + 2 * _mad(fresh_vals)) if median_fresh > 0 else 0
        if threshold > 0:
            spike_count = sum(1 for v in fresh_vals if v > threshold)
    fresh_spikes = str(spike_count)

    return {
        "latest_ratio": latest_ratio,
        "lowest_ratio": lowest_ratio,
        "fresh_spikes": fresh_spikes,
    }


def _mad(values: list) -> float:
    """Median Absolute Deviation."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    median = sorted_vals[mid] if n % 2 == 1 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    abs_devs = sorted([abs(v - median) for v in values])
    mid = n // 2
    return abs_devs[mid] if n % 2 == 1 else (abs_devs[mid - 1] + abs_devs[mid]) / 2


def _build_agent_where(agent_scope: str) -> tuple[str, list]:
    """Build WHERE clause for agent filtering.

    Always returns a valid WHERE prefix so callers can safely append 'AND'.
    For 'all' scope, returns 'WHERE 1=1' as a no-op filter.
    """
    db_agent = _DB_AGENT.get(agent_scope)
    if db_agent:
        return "WHERE agent = ?", [db_agent]
    return "WHERE 1=1", []


def _compute_all_agents_branch(conn: sqlite3.Connection) -> dict:
    """Compute data for All agents mode: contribution comparison, all agents table, efficiency."""
    agents = list_agents(conn)
    agent_map = {}
    for a in agents:
        db_agent = a.get("agent", "")
        display = "Unknown"
        if db_agent == "claude_code":
            display = "Claude Code"
        elif db_agent == "qoder":
            display = "Qoder"
        elif db_agent == "codex":
            display = "Codex"
        agent_map[db_agent] = {
            "display": display,
            "db_agent": db_agent,
            "sessions": a.get("session_count", 0),
            "tokens": a.get("total_tokens", 0),
            "fresh": a.get("total_fresh_input_tokens", 0),
            "cache_read": a.get("total_cache_read_tokens", 0),
            "cache_write": a.get("total_cache_write_tokens", 0),
            "output": a.get("total_output_tokens", 0),
            "prompts": 0,  # will be filled
            "projects": a.get("project_count", 0),
            "failed": a.get("total_failed_tools", 0),
            "tools": a.get("total_tool_calls", 0),
            "last_active": a.get("last_active", ""),
            "rounds": a.get("total_assistant_messages", 0),
        }

    # Fill prompts from prompt activity
    total_prompts_data = get_prompt_activity_trend(conn, days=365)
    # Ensure all agent entries exist with full defaults
    for db_a in ["claude_code", "codex", "qoder"]:
        if db_a not in agent_map:
            agent_map[db_a] = {
                "display": _AGENT_DISPLAY.get(_DB_AGENT.get(db_a, ""), db_a),
                "db_agent": db_a,
                "sessions": 0, "tokens": 0, "fresh": 0,
                "cache_read": 0, "cache_write": 0, "output": 0,
                "prompts": 0, "projects": 0, "failed": 0, "tools": 0,
                "last_active": "", "rounds": 0,
            }
    for day_data in total_prompts_data:
        for db_a, key in [("claude_code", "claude_prompts"), ("codex", "codex_prompts"), ("qoder", "qoder_prompts")]:
            if db_a in agent_map:
                agent_map[db_a]["prompts"] = agent_map.get(db_a, {}).get("prompts", 0) + day_data.get(key, 0)

    # Build agent rows
    total_sessions_all = sum(a["sessions"] for a in agent_map.values())
    total_tokens_all = sum(a["tokens"] for a in agent_map.values())
    total_prompts_all = sum(a.get("prompts", 0) for a in agent_map.values())

    agent_rows = []
    for db_agent in ["claude_code", "qoder", "codex"]:
        a = agent_map.get(db_agent, {})
        if not a.get("display"):
            continue
        session_share = a["sessions"] / total_sessions_all * 100 if total_sessions_all > 0 else 0
        token_share = a["tokens"] / total_tokens_all * 100 if total_tokens_all > 0 else 0
        prompt_share = a.get("prompts", 0) / total_prompts_all * 100 if total_prompts_all > 0 else 0
        failure_rate = a["failed"] / a["tools"] * 100 if a.get("tools", 0) > 0 else 0

        last_active = a.get("last_active", "")
        last_active_display = ""
        if last_active:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                diff = (datetime.now(dt.tzinfo) - dt).total_seconds() if dt.tzinfo else (datetime.utcnow() - dt.replace(tzinfo=None)).total_seconds()
                if diff < 60:
                    last_active_display = "Just now"
                elif diff < 3600:
                    last_active_display = f"{int(diff // 60)} min ago"
                elif diff < 86400:
                    last_active_display = f"{int(diff // 3600)}h ago"
                else:
                    last_active_display = f"{int(diff // 86400)}d ago"
            except Exception:
                last_active_display = last_active[:10]

        agent_rows.append({
            "display": a["display"],
            "db_agent": db_agent,
            "sessions": a["sessions"],
            "session_share": f"{session_share:.1f}%",
            "tokens": _fmt_compact(a["tokens"]),
            "token_share": f"{token_share:.1f}%",
            "token_fresh": _fmt_compact(a.get("fresh", 0)),
            "token_cache_read": _fmt_compact(a.get("cache_read", 0)),
            "token_cache_write": _fmt_compact(a.get("cache_write", 0)),
            "token_output": _fmt_compact(a.get("output", 0)),
            "prompts": a.get("prompts", 0),
            "prompt_share": f"{prompt_share:.1f}%",
            "projects": a.get("projects", 0),
            "failed": a["failed"],
            "failure_rate": f"{failure_rate:.1f}%",
            "last_active": last_active_display,
        })

    # Agent / Model Efficiency
    model_stats = list_model_stats(conn)
    efficiency_rows = []
    for m in model_stats:
        db_agent = m.get("agent", "")
        display = _AGENT_DISPLAY.get(_DB_AGENT.get(db_agent, ""), db_agent)
        total_sessions = m.get("total_sessions", 0)
        total_tokens = m.get("total_tokens", 0)
        input_tokens = m.get("input_tokens", 0) + m.get("cache_read_tokens", 0) + m.get("cache_write_tokens", 0)
        output_tokens = m.get("output_tokens", 0)
        cache_read = m.get("cache_read_tokens", 0)
        failed_tools = m.get("failed_tools", 0)

        tokens_per_session = total_tokens / total_sessions if total_sessions > 0 else 0
        cache_ratio = _safe_ratio_float(cache_read, input_tokens)
        failure_per_session = failed_tools / total_sessions if total_sessions > 0 else 0

        efficiency_rows.append({
            "agent": display,
            "db_agent": db_agent,
            "model": m.get("model", "Unknown model"),
            "sessions": total_sessions,
            "tokens_per_session": _fmt_compact(tokens_per_session),
            "input_tokens": _fmt_compact(input_tokens),
            "output_tokens": _fmt_compact(output_tokens),
            "cache_read": f"{cache_ratio * 100:.1f}%" if cache_ratio is not None else "N/A",
            "failure": f"{failure_per_session:.2f} / session",
        })

    # Sort by sessions desc
    efficiency_rows.sort(key=lambda x: x["sessions"], reverse=True)

    return {
        "agent_rows": agent_rows,
        "efficiency_rows": efficiency_rows,
        "total_sessions_all": total_sessions_all,
        "total_tokens_all": total_tokens_all,
        "total_prompts_all": total_prompts_all,
    }


def _compute_single_agent_branch(conn: sqlite3.Connection, db_agent: str, scope_key: str) -> dict:
    """Compute data for single agent mode: Model Mix, Tool Distribution, Failure Signals, etc."""
    display_name = _AGENT_DISPLAY.get(scope_key, db_agent)

    # Get agent-scoped sessions
    where, params = _build_agent_where(scope_key)

    # Model Mix data
    model_stats = list_model_stats(conn)
    model_rows = []
    total_agent_tokens = 0
    for m in model_stats:
        if m.get("agent") != db_agent:
            continue
        total_agent_tokens += m.get("total_tokens", 0)

    total_agent_sessions = sum(
        m.get("total_sessions", 0) for m in model_stats if m.get("agent") == db_agent
    )

    for m in model_stats:
        if m.get("agent") != db_agent:
            continue
        total_sessions = m.get("total_sessions", 0)
        total_tokens = m.get("total_tokens", 0)
        input_side = m.get("input_tokens", 0) + m.get("cache_read_tokens", 0) + m.get("cache_write_tokens", 0)
        cache_read = m.get("cache_read_tokens", 0)
        failed_tools = m.get("failed_tools", 0)

        token_share = total_tokens / total_agent_tokens * 100 if total_agent_tokens > 0 else 0
        cache_ratio = _safe_ratio_float(cache_read, input_side)
        failed_per = failed_tools / total_sessions if total_sessions > 0 else 0
        session_share = total_sessions / max(1, total_agent_sessions) * 100

        model_rows.append({
            "model": m.get("model", "Unknown model"),
            "sessions": total_sessions,
            "session_share": f"{session_share:.1f}%",
            "tokens": total_tokens,
            "token_share": f"{token_share:.1f}%",
            "cache_read": f"{cache_ratio * 100:.1f}%" if cache_ratio is not None else "N/A",
            "failed_per_session": f"{failed_per:.2f}/session",
        })

    model_rows.sort(key=lambda x: x["tokens"], reverse=True)

    # Agent Sessions table
    agent_sessions = list_sessions(
        conn, agent=db_agent, limit=2000, order_by="ended_at",
    )
    agent_session_rows = []
    for s in agent_sessions:
        total_tok = s.total_tokens or (s.input_tokens + s.cached_input_tokens + s.cached_output_tokens + s.output_tokens)
        agent_session_rows.append({
            "title": (s.title or "")[:80] or f"Untitled ({s.session_id[-8:]})",
            "session_id": s.session_id,
            "project": s.project_key or "",
            "project_name": s.project_name or s.project_key,
            "model": s.model or "Unknown",
            "agent": s.agent,
            "tokens": total_tok,
            "tokens_display": _fmt_compact(total_tok),
            "fresh": s.fresh_input_tokens or s.input_tokens,
            "cache_read": s.cache_read_tokens or s.cached_input_tokens,
            "cache_write": s.cache_write_tokens or s.cached_output_tokens,
            "output": s.output_tokens,
            "rounds": s.assistant_message_count,
            "tools": s.tool_call_count,
            "subagents": s.subagent_instance_count or 0,
            "duration": _format_duration(s.duration_seconds or 0),
            "process_time": _format_duration(getattr(s, 'process_time_seconds', 0) or 0),
            "failure": s.failed_tool_count,
            "failure_display": f"{s.failed_tool_count} failed" if s.failed_tool_count > 0 else "No failures",
            "updated": s.ended_at,
            "created": s.started_at,
        })

    # Model Efficiency Detail
    eff_rows = []
    for m in model_rows:
        input_side_val = 0
        output_val = 0
        tools_per_session = 0
        cache_ratio_val = None
        sessions_count = m["sessions"]
        total_tok_val = m["tokens"]

        # Compute additional details
        avg_input = 0
        avg_output = 0
        if sessions_count > 0:
            avg_input = total_tok_val / sessions_count
            avg_output = 0  # would need more detailed query

        # Determine notes
        notes = []
        if sessions_count > 0:
            notes.append("Normal")

        eff_rows.append({
            "model": m["model"],
            "sessions": m["sessions"],
            "avg_tokens": m["tokens"] // max(1, m["sessions"]),
            "cache_tools": m["cache_read"],
            "failure": m["failed_per_session"],
            "notes": ", ".join(notes) if notes else "Normal",
        })

    return {
        "display_name": display_name,
        "model_rows": model_rows,
        "agent_session_rows": agent_session_rows,
        "efficiency_rows": eff_rows,
    }
