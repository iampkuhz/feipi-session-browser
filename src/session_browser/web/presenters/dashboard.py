"""Dashboard presenter.

Builds the complete view model for the dashboard page, supporting:
- Agent scope: all / claude-code / qoder / codex
- Time grain: day / week / month
- 6 KPI cards with secondary metrics
- 3 trend cards (Session Trend, Token Trend, Prompt Activity Trend)
- Token analysis through Token Trend and Cache Health
- All agents branch (Agent Contribution Comparison, All Agents table, Agent/Model Efficiency)
- Single agent branch (Model Mix, Tool Distribution, Failure Signals, Model Efficiency Detail, View Sessions CTA)
"""
from __future__ import annotations

import math
import sqlite3
from functools import lru_cache
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

_DB_AGENT_DISPLAY = {
    "claude_code": "Claude Code",
    "qoder": "Qoder",
    "codex": "Codex",
}

_MODEL_MIX_COLORS = [
    "#5b5ce2",
    "#22a979",
    "#f59e0b",
    "#0ea5e9",
    "#ef4444",
    "#8b5cf6",
    "#14b8a6",
    "#f97316",
]

_KPI_PRIMARY_DESCRIPTIONS = {
    "Projects": "当前 scope 下出现过 session 的 project 数量。",
    "Sessions": "当前 scope 下已索引的 session 总数。",
    "Total Tokens": "当前 scope 下 Fresh、Cache Read、Cache Write、Output 的合计。",
    "Prompt Activity": "当前 scope 下用户发起的 prompt 数量，按 user message 事件计数。",
    "Cache Read Ratio": "当前 scope 下缓存命中输入占 input-side tokens 的比例。",
    "Failed Tools": "当前 scope 下明确失败的 tool result 数量。",
}

_KPI_BADGE_DESCRIPTIONS = {
    "Projects": "最近 7 天使用的 project 数，对比上个 7 天使用的 project 数。",
    "Sessions": "当前可见时间窗口最后一个时间点的 session 数，对比前一个时间点。",
    "Total Tokens": "当前可见时间窗口最后一个时间点的 total tokens，对比前一个时间点的百分比变化。",
    "Prompt Activity": "当前可见时间窗口最后一个时间点的 user prompts 数，对比前一个时间点。",
    "Cache Read Ratio": "当前可见时间窗口最后一个可计算 Cache Read Ratio，对比前一个可计算点，单位为百分点。",
    "Failed Tools": "当前可见时间窗口最后一个时间点的 failed tool 数，对比前一个时间点；下降显示为正向颜色。",
}

_KPI_SECONDARY_DESCRIPTIONS = {
    "Active 24h": "最近 24 小时内使用过的 project 数量；同一个 project 只算一次。",
    "Active 7d": "最近 7 天内使用过的 project 数量；同一个 project 只算一次。",
    "New 7d": "最近 7 天内开始过 session 的 project 数量；同一个 project 只算一次。",
    "Today": "今天开始的 session 数，按 session started_at 的日期统计。",
    "7d Avg": "最近 7 天内结束的 session 总数除以 7，得到每日平均 session 数。",
    "Median Duration": "duration_seconds 大于 0 的 session 生命周期中位数。",
    "Avg Rounds": "assistant message 总数除以 session 总数，表示每个 session 的平均 assistant 轮数。",
    "Fresh": "本次请求实际新增/发送的输入规模，Cache Read/Write 单独展示。",
    "Cache Read": "输入侧从 provider 缓存命中的 token 数；会计入总 token。",
    "Cache Write": "输入侧写入 provider 缓存的 token 数；会计入总 token。",
    "Output": "模型输出给用户或工具链的 token 数。",
    "Assistant Turns": "assistant message 事件总数，表示模型回复轮次。",
    "Tool Calls": "tool call 事件总数，包含成功和失败的工具调用。",
    "Prompts / Session": "User Prompts / Sessions；没有 session 时显示 N/A。",
    "Eligible Sessions": "Input-side Tokens > 0 的 session 数，是 session 级缓存复用统计的样本。",
    "P50 Session Ratio": "eligible sessions 中每个 session 的 Cache Read / Input-side Tokens 的中位数。",
    "Low-read Sessions": "eligible sessions 中 cache read ratio 小于 20.0% 的 session 数。",
    "Failure Rate": "Failed Tools / Tool Calls；没有 tool call 时显示 N/A。",
    "Affected Sessions": "failed_tool_count 大于 0 的 session 数。",
    "Repeated Failure Sessions": "failed_tool_count 大于 1 的 session 数。",
}


_GRAIN_NOTE_LABELS = {
    "day": "按天",
    "week": "按周",
    "month": "按月",
}


def _build_chart_notes(agent_scope: str, grain: str) -> dict[str, str]:
    """Build chart notes that match the active scope and grain controls."""
    grain_label = _GRAIN_NOTE_LABELS.get(grain, "按天")
    agent_label = _AGENT_DISPLAY.get(agent_scope, "")
    if agent_scope == "all":
        session_note = f"{grain_label}新增的 session 总数，按照不同 agent 堆叠。"
        token_note = f"{grain_label}展示 total tokens，按照 Fresh、Cache Read、Cache Write、Output 组成展示。"
        prompt_note = f"{grain_label}展示 user prompts 总数，并用折线显示每个 session 的平均 prompts。"
        cache_note = f"{grain_label}展示整体和各 agent 的 Cache Read Ratio；Average 为全局平均。"
    else:
        session_note = f"{grain_label}新增的 {agent_label} session 数量。"
        token_note = f"{grain_label}展示 {agent_label} 的 total tokens，按 token 类型组成展示。"
        prompt_note = f"{grain_label}展示 {agent_label} 的 user prompts 数量，并用折线显示每个 session 的平均 prompts。"
        cache_note = f"{grain_label}展示 {agent_label} 的 Cache Read Ratio。"

    return {
        "sessions": session_note,
        "tokens": token_note,
        "prompts": prompt_note,
        "cache_health": cache_note,
        "model_mix": "当前 agent 下模型 token 占比和 session 分布。",
        "tool_dist": "当前 agent 下工具调用分布；缺少工具名称明细时显示空态。",
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


def _fmt_percent_share(value: float) -> str:
    """Format a share while preserving non-zero tiny contributors."""
    if value > 0 and value < 0.1:
        return "<0.1%"
    return f"{value:.1f}%"


def build_dashboard_view_model(
    conn: sqlite3.Connection,
    agent_scope: str | None = None,
    grain: str | None = None,
    page: int | None = None,
    page_size: int = 20,
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
    kpis = _compute_kpis(stats, conn, agent_scope, trend, prompt_activity)

    # ── All agents branch data ─────────────────────────────────────────
    all_agents_branch = None
    if not is_single_agent:
        all_agents_branch = _compute_all_agents_branch(conn)

    # ── Single agent branch data ───────────────────────────────────────
    single_agent_branch = None
    if is_single_agent and db_agent:
        single_agent_branch = _compute_single_agent_branch(
            conn, db_agent, agent_scope, page=page, page_size=page_size,
        )

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
    cache_health_series = _compute_cache_health_series(conn, days)
    cache_health = _compute_cache_health_stats(cache_health_series, agent_scope)
    chart_notes = _build_chart_notes(agent_scope, grain)

    # ── Single-agent sessions count for View Sessions CTA ─────────
    total_agent_sessions = 0
    total_pages = 1
    current_page = 1
    if is_single_agent and db_agent:
        total_agent_sessions = _count_agent_sessions(conn, db_agent)
        current_page = max(1, page or 1)
        total_pages = max(1, math.ceil(total_agent_sessions / page_size))

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
        "chart_notes": chart_notes,
        "active_page": "dashboard",
        "agent_sessions_page": current_page,
        "agent_sessions_total_pages": total_pages,
        "agent_sessions_total": total_agent_sessions,
        "agent_sessions_page_size": page_size,
    }


def _compute_kpis(
    stats: dict,
    conn: sqlite3.Connection,
    agent_scope: str,
    trend: list[dict] | None = None,
    prompt_activity: list[dict] | None = None,
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

    project_recent_7d = _count_active_projects_window(conn, agent_scope, 7, 0)
    project_previous_7d = _count_active_projects_window(conn, agent_scope, 14, 7)
    project_badge_delta = project_recent_7d - project_previous_7d
    project_new_7d = _count_new_projects(conn, agent_scope, 7)

    # 1. Projects
    kpis.append({
        "label": "Projects",
        "value": _fmt(project_count),
        "badge": _format_delta_badge(project_badge_delta, suffix=""),
        "badge_tone": _badge_tone(project_badge_delta),
        "secondary": [
            {"label": "Active 24h", "value": _fmt(_count_active_projects(conn, agent_scope, 1))},
            {"label": "Active 7d", "value": _fmt(_count_active_projects(conn, agent_scope, 7))},
            {"label": "New 7d", "value": _fmt(project_new_7d)},
        ],
    })

    # 2. Sessions
    median_duration = _median_duration(conn, agent_scope)
    avg_rounds = total_assistant_messages / total_sessions if total_sessions > 0 else 0
    kpis.append({
        "label": "Sessions",
        "value": _fmt(total_sessions),
        "badge": _series_delta_badge(trend or [], "total_count", as_percent=False),
        "badge_tone": _series_delta_tone(trend or [], "total_count"),
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
        "badge": _series_delta_badge(trend or [], "total_tokens", as_percent=True),
        "badge_tone": _series_delta_tone(trend or [], "total_tokens"),
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
        "badge": _series_delta_badge(prompt_activity or [], "total_prompts", as_percent=False),
        "badge_tone": _series_delta_tone(prompt_activity or [], "total_prompts"),
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
        "badge": _cache_ratio_delta_badge(trend or []),
        "badge_tone": _cache_ratio_delta_tone(trend or []),
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
        "badge": _series_delta_badge(trend or [], "failed_tools", as_percent=False),
        "badge_tone": _series_delta_tone(trend or [], "failed_tools", inverse=True),
        "secondary": [
            {"label": "Failure Rate", "value": f"{failure_rate * 100:.1f}%" if failure_rate is not None else "N/A"},
            {"label": "Affected Sessions", "value": _fmt(affected_sessions)},
            {"label": "Repeated Failure Sessions", "value": _fmt(repeated_failure)},
        ],
    })

    return [_attach_kpi_descriptions(kpi) for kpi in kpis]


def _attach_kpi_descriptions(kpi: dict[str, Any]) -> dict[str, Any]:
    """Attach concrete tooltip descriptions to KPI secondary metrics."""
    kpi = dict(kpi)
    label = kpi.get("label", "")
    kpi["description"] = _KPI_PRIMARY_DESCRIPTIONS.get(
        label,
        f"{label or 'KPI'} 的统计口径。",
    )
    kpi["badge_description"] = _KPI_BADGE_DESCRIPTIONS.get(
        label,
        f"{label or 'KPI'} badge 的比较口径。",
    )
    secondary = []
    for item in kpi.get("secondary", []):
        enriched = dict(item)
        enriched["description"] = _KPI_SECONDARY_DESCRIPTIONS.get(
            item.get("label", ""),
            f"{item.get('label', 'Metric')} 的统计口径。",
        )
        secondary.append(enriched)
    kpi["secondary"] = secondary
    return kpi


def _format_delta_badge(delta: int | float | None, suffix: str = "") -> str:
    """Format a compact KPI badge value."""
    if delta is None:
        return "N/A"
    if delta > 0:
        return f"+{_fmt_compact(delta)}{suffix}"
    if delta < 0:
        return f"-{_fmt_compact(abs(delta))}{suffix}"
    return f"0{suffix}"


def _badge_tone(delta: int | float | None, inverse: bool = False) -> str:
    """Map delta to a visual badge tone."""
    if delta is None or delta == 0:
        return "neutral"
    positive = delta > 0
    if inverse:
        positive = not positive
    return "positive" if positive else "negative"


def _last_two_values(series: list[dict], key: str) -> tuple[float, float] | None:
    values = [float(row.get(key) or 0) for row in series if row.get(key) is not None]
    if len(values) < 2:
        return None
    return values[-2], values[-1]


def _series_delta_badge(series: list[dict], key: str, as_percent: bool = False) -> str:
    pair = _last_two_values(series, key)
    if pair is None:
        return "N/A"
    prev, current = pair
    delta = current - prev
    if as_percent:
        if prev == 0:
            return "N/A" if current == 0 else "+100.0%"
        return f"{delta / prev * 100:+.1f}%"
    return _format_delta_badge(delta)


def _series_delta_tone(series: list[dict], key: str, inverse: bool = False) -> str:
    pair = _last_two_values(series, key)
    if pair is None:
        return "neutral"
    prev, current = pair
    return _badge_tone(current - prev, inverse=inverse)


def _cache_ratio_value(row: dict) -> float | None:
    input_side = (
        (row.get("fresh_input_tokens") or 0)
        + (row.get("cache_read_tokens") or 0)
        + (row.get("cache_write_tokens") or 0)
    )
    if input_side <= 0:
        return None
    return (row.get("cache_read_tokens") or 0) / input_side


def _cache_ratio_delta_badge(series: list[dict]) -> str:
    ratios = [_cache_ratio_value(row) for row in series]
    ratios = [r for r in ratios if r is not None]
    if len(ratios) < 2:
        return "N/A"
    return f"{(ratios[-1] - ratios[-2]) * 100:+.1f}pp"


def _cache_ratio_delta_tone(series: list[dict]) -> str:
    ratios = [_cache_ratio_value(row) for row in series]
    ratios = [r for r in ratios if r is not None]
    if len(ratios) < 2:
        return "neutral"
    return _badge_tone(ratios[-1] - ratios[-2])


def _count_active_projects(conn: sqlite3.Connection, agent_scope: str, days: int) -> int:
    """Count distinct projects with session events in the last N days."""
    where, params = _build_agent_where(agent_scope)
    row = conn.execute(
        f"SELECT COUNT(DISTINCT project_key) FROM sessions {where} AND ended_at >= date('now', '-{days} days')",
        params,
    ).fetchone()
    return row[0] if row else 0


def _count_active_projects_window(
    conn: sqlite3.Connection,
    agent_scope: str,
    start_days_ago: int,
    end_days_ago: int,
) -> int:
    """Count distinct projects active in a relative day window."""
    where, params = _build_agent_where(agent_scope)
    upper_bound = (
        f"AND ended_at < date('now', '-{end_days_ago} days')"
        if end_days_ago > 0 else ""
    )
    row = conn.execute(
        f"""SELECT COUNT(DISTINCT project_key) FROM sessions {where}
            AND ended_at >= date('now', '-{start_days_ago} days')
            {upper_bound}""",
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


def _build_model_donut_gradient(model_rows: list[dict[str, Any]]) -> str:
    """Build a CSS conic-gradient for model token share."""
    if not model_rows:
        return "conic-gradient(#cbd5e1 0% 100%)"

    stops = []
    cursor = 0.0
    total_share = sum(
        max(0.0, float(row.get("token_share_raw", 0) or 0))
        for row in model_rows
    )

    if total_share <= 0:
        share = 100.0 / len(model_rows)
        for row in model_rows:
            next_cursor = min(100.0, cursor + share)
            stops.append(f"{row.get('color', '#5b5ce2')} {cursor:.2f}% {next_cursor:.2f}%")
            cursor = next_cursor
        return "conic-gradient(" + ", ".join(stops) + ")"

    for row in model_rows:
        share = max(0.0, float(row.get("token_share_raw", 0) or 0)) / total_share * 100
        next_cursor = min(100.0, cursor + share)
        stops.append(f"{row.get('color', '#5b5ce2')} {cursor:.2f}% {next_cursor:.2f}%")
        cursor = next_cursor

    if cursor < 100:
        stops.append(f"#e2e8f0 {cursor:.2f}% 100%")
    return "conic-gradient(" + ", ".join(stops) + ")"


_QODER_CACHE_METRIC_KEYS = (
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "cached_tokens",
    "cache_read_tokens",
    "qoder_input_tokens_total",
)


@lru_cache(maxsize=4096)
def _qoder_file_reports_cache_metrics(file_path: str) -> bool:
    """Return whether a Qoder raw session contains provider cache fields."""
    if not file_path:
        return False
    try:
        with open(file_path, encoding="utf-8") as fh:
            for line in fh:
                if any(key in line for key in _QODER_CACHE_METRIC_KEYS):
                    return True
    except OSError:
        return False
    return False


def _compute_cache_health_series(conn: sqlite3.Connection, days: int) -> list[dict]:
    """Compute daily token inputs for Average and each known agent."""
    agent_keys = ["claude_code", "qoder", "codex"]
    fields = ["fresh_input_tokens", "cache_read_tokens", "cache_write_tokens"]
    try:
        rows = conn.execute(
            """
            SELECT
                COALESCE(NULLIF(DATE(ended_at), ''), DATE('now')) as day,
                agent,
                COALESCE(fresh_input_tokens, 0) as fresh_input_tokens,
                COALESCE(cache_read_tokens, 0) as cache_read_tokens,
                COALESCE(cache_write_tokens, 0) as cache_write_tokens,
                COALESCE(file_path, '') as file_path
            FROM sessions
            WHERE (ended_at >= date('now', ?) OR ended_at = '' OR ended_at IS NULL)
              AND agent IN ('claude_code', 'qoder', 'codex')
            ORDER BY day
            """,
            [f"-{days} days"],
        ).fetchall()
    except Exception:
        return []

    by_day: dict[str, dict] = {}
    for row in rows:
        day = row["day"]
        point = by_day.setdefault("{}".format(day), {"date": day})
        agent = row["agent"]
        input_side = sum(row[field] or 0 for field in fields)
        if agent == "qoder" and not _qoder_file_reports_cache_metrics(row["file_path"]):
            point["qoder_unreported_input_side_tokens"] = (
                point.get("qoder_unreported_input_side_tokens", 0) + input_side
            )
            continue
        for field in fields:
            value = row[field] or 0
            point[f"{agent}_{field}"] = point.get(f"{agent}_{field}", 0) + value
            point[f"average_{field}"] = point.get(f"average_{field}", 0) + value

    series = []
    for day in sorted(by_day):
        point = by_day[day]
        for agent in agent_keys:
            for field in fields:
                point.setdefault(f"{agent}_{field}", 0)
        qoder_known_input = sum(point.get(f"qoder_{field}", 0) for field in fields)
        qoder_unreported = point.get("qoder_unreported_input_side_tokens", 0)
        if qoder_unreported > 0 and qoder_known_input == 0:
            point["qoder_cache_metric_known"] = False
        else:
            point.setdefault("qoder_cache_metric_known", True)
        for field in fields:
            point.setdefault(f"average_{field}", 0)
        series.append(point)
    return series


def _compute_cache_health_stats(series: list[dict], agent_scope: str) -> dict:
    """Compute Cache Health card stats from highlighted cache-ratio series."""
    if not series:
        return {"latest_ratio": "N/A", "lowest_ratio": "N/A", "series": []}

    prefix = _DB_AGENT.get(agent_scope, "average")
    values = []
    latest_ratio = None
    for point in series:
        if point.get(f"{prefix}_cache_metric_known") is False:
            continue
        fresh = point.get(f"{prefix}_fresh_input_tokens", 0)
        read = point.get(f"{prefix}_cache_read_tokens", 0)
        write = point.get(f"{prefix}_cache_write_tokens", 0)
        input_side = fresh + read + write
        ratio = read / input_side if input_side > 0 else None
        if ratio is not None:
            values.append(ratio)
            latest_ratio = ratio

    return {
        "latest_ratio": f"{latest_ratio * 100:.1f}%" if latest_ratio is not None else "N/A",
        "lowest_ratio": f"{min(values) * 100:.1f}%" if values else "N/A",
        "series": series,
    }


def _count_agent_sessions(conn: sqlite3.Connection, db_agent: str) -> int:
    """Count total sessions for a specific agent (for pagination)."""
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE agent = ?", [db_agent],
        ).fetchone()
        return int(row[0]) if row else 0
    except (TypeError, ValueError):
        return 0


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
        display = _DB_AGENT_DISPLAY.get(db_agent, "Unknown")
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
                "display": _DB_AGENT_DISPLAY.get(db_a, db_a),
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
            "sessions_raw": a["sessions"],
            "session_share": _fmt_percent_share(session_share),
            "tokens": _fmt_compact(a["tokens"]),
            "tokens_raw": a["tokens"],
            "token_share": _fmt_percent_share(token_share),
            "token_share_value": token_share,
            "token_fresh": _fmt_compact(a.get("fresh", 0)),
            "token_cache_read": _fmt_compact(a.get("cache_read", 0)),
            "token_cache_write": _fmt_compact(a.get("cache_write", 0)),
            "token_output": _fmt_compact(a.get("output", 0)),
            "fresh_pct": round(a.get("fresh", 0) / max(1, a["tokens"]) * 100, 1),
            "read_pct": round(a.get("cache_read", 0) / max(1, a["tokens"]) * 100, 1),
            "write_pct": round(a.get("cache_write", 0) / max(1, a["tokens"]) * 100, 1),
            "output_pct": round(a.get("output", 0) / max(1, a["tokens"]) * 100, 1),
            "prompts": a.get("prompts", 0),
            "prompts_raw": a.get("prompts", 0),
            "prompt_share": _fmt_percent_share(prompt_share),
            "projects": a.get("projects", 0),
            "projects_raw": a.get("projects", 0),
            "failed": a["failed"],
            "failed_raw": a["failed"],
            "failure_rate": f"{failure_rate:.1f}%",
            "failure_rate_raw": failure_rate,
            "last_active": last_active_display,
            "last_active_raw": last_active,
        })

    # Agent / Model Efficiency
    model_stats = list_model_stats(conn)
    efficiency_rows = []
    for m in model_stats:
        db_agent = m.get("agent", "")
        display = _DB_AGENT_DISPLAY.get(db_agent, db_agent)
        total_sessions = m.get("total_sessions", 0)
        total_tokens = m.get("total_tokens", 0)
        input_side_tokens = (
            m.get("fresh_input_tokens", 0)
            + m.get("cache_read_tokens", 0)
            + m.get("cache_write_tokens", 0)
        )
        output_tokens = m.get("output_tokens", 0)
        cache_read = m.get("cache_read_tokens", 0)
        failed_tools = m.get("failed_tools", 0)

        tokens_per_session = total_tokens / total_sessions if total_sessions > 0 else 0
        cache_ratio = _safe_ratio_float(cache_read, input_side_tokens)
        failure_per_session = failed_tools / total_sessions if total_sessions > 0 else 0

        efficiency_rows.append({
            "agent": display,
            "db_agent": db_agent,
            "model": m.get("model", "Unknown model"),
            "sessions": total_sessions,
            "sessions_raw": total_sessions,
            "tokens_per_session": _fmt_compact(tokens_per_session),
            "tokens_per_session_raw": tokens_per_session,
            "input_side_tokens": _fmt_compact(input_side_tokens),
            "output_tokens": _fmt_compact(output_tokens),
            "cache_read": f"{cache_ratio * 100:.1f}%" if cache_ratio is not None else "N/A",
            "cache_read_raw": cache_ratio if cache_ratio is not None else -1,
            "failure": f"{failure_per_session:.2f} / session",
            "failure_raw": failure_per_session,
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


def _compute_single_agent_branch(conn: sqlite3.Connection, db_agent: str, scope_key: str, page: int | None = None, page_size: int = 20) -> dict:
    """Compute data for single agent mode: Model Mix, Tool Distribution, Failure Signals, etc."""
    display_name = _AGENT_DISPLAY.get(scope_key, db_agent)

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

    model_index = 0
    for m in model_stats:
        if m.get("agent") != db_agent:
            continue
        total_sessions = m.get("total_sessions", 0)
        total_tokens = m.get("total_tokens", 0)
        input_side = (
            m.get("fresh_input_tokens", 0)
            + m.get("cache_read_tokens", 0)
            + m.get("cache_write_tokens", 0)
        )
        cache_read = m.get("cache_read_tokens", 0)
        failed_tools = m.get("failed_tools", 0)
        tool_calls = m.get("tool_calls", 0)
        process_seconds = m.get("process_seconds", 0) or 0
        avg_process_seconds = m.get("avg_process_seconds", 0) or (
            process_seconds / total_sessions if total_sessions > 0 else 0
        )

        token_share = total_tokens / total_agent_tokens * 100 if total_agent_tokens > 0 else 0
        cache_ratio = _safe_ratio_float(cache_read, input_side)
        failed_per = failed_tools / total_sessions if total_sessions > 0 else 0
        session_share = total_sessions / max(1, total_agent_sessions) * 100
        tool_calls_per_session = tool_calls / total_sessions if total_sessions > 0 else 0
        color = _MODEL_MIX_COLORS[model_index % len(_MODEL_MIX_COLORS)]
        model_index += 1

        model_rows.append({
            "model": m.get("model", "Unknown model"),
            "sessions": total_sessions,
            "sessions_raw": total_sessions,
            "session_share": f"{session_share:.1f}%",
            "session_share_raw": session_share,
            "tokens": total_tokens,
            "tokens_display": _fmt_compact(total_tokens),
            "token_share": f"{token_share:.1f}%",
            "token_share_raw": token_share,
            "avg_tokens_raw": total_tokens / total_sessions if total_sessions > 0 else 0,
            "avg_tokens_display": _fmt_compact(total_tokens / total_sessions) if total_sessions > 0 else "0",
            "cache_read": f"{cache_ratio * 100:.1f}%" if cache_ratio is not None else "N/A",
            "cache_read_raw": cache_ratio * 100 if cache_ratio is not None else -1,
            "tool_calls": tool_calls,
            "tool_calls_per_session": f"{tool_calls_per_session:.1f}",
            "tool_calls_per_session_raw": tool_calls_per_session,
            "failed_per_session": f"{failed_per:.2f}/session",
            "failed_per_session_raw": failed_per,
            "avg_process_time": _format_duration(avg_process_seconds),
            "avg_process_seconds_raw": avg_process_seconds,
            "color": color,
        })

    model_rows.sort(key=lambda x: x["tokens"], reverse=True)
    for idx, row in enumerate(model_rows):
        row["color"] = _MODEL_MIX_COLORS[idx % len(_MODEL_MIX_COLORS)]

    model_rows_by_sessions = sorted(model_rows, key=lambda x: x["sessions"], reverse=True)
    model_donut_gradient = _build_model_donut_gradient(model_rows)

    # Model Efficiency Detail
    eff_rows = []
    for m in model_rows:
        sessions_count = m["sessions"]

        # Determine notes per spec
        notes = []
        avg_tokens_val = m["tokens"] // max(1, m["sessions"]) if m["sessions"] > 0 else 0
        if sessions_count >= 10:
            notes.append("Primary model")
        if avg_tokens_val > 50000:
            notes.append("High input")
        cache_pct = m.get("cache_read", "0%").replace("%", "")
        try:
            cache_val = float(cache_pct)
        except (ValueError, TypeError):
            cache_val = 0
        if cache_val < 20 and sessions_count >= 3:
            notes.append("Low cache reuse")
        failed_str = m.get("failed_per_session", "0/session")
        try:
            failed_val = float(failed_str.split("/")[0])
        except (ValueError, IndexError):
            failed_val = 0
        if failed_val > 0.5:
            notes.append("High failure")
        if sessions_count < 3:
            notes.append("Low sample")
        if not notes:
            notes.append("Normal")

        eff_rows.append({
            "model": m["model"],
            "sessions": m["sessions"],
            "avg_tokens": m["avg_tokens_display"],
            "avg_process_time": m["avg_process_time"],
            "cache_read": m["cache_read"],
            "tool_calls_per_session": m["tool_calls_per_session"],
            "failure": m["failed_per_session"],
            "notes": ", ".join(notes) if notes else "Normal",
        })

    return {
        "display_name": display_name,
        "model_rows": model_rows,
        "model_rows_by_sessions": model_rows_by_sessions,
        "model_donut_gradient": model_donut_gradient,
        "model_count": len(model_rows),
        "agent_session_rows": [],
        "efficiency_rows": eff_rows,
        "page": max(1, page or 1),
        "page_size": page_size,
    }
