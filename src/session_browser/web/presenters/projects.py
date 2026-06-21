"""说明：Projects presenter。

Extracted view-model construction logic for the projects listing and
individual project pages. Keeps data-fetching out of the HTTP handler
so it can be unit-tested in isolation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from numbers import Real
import sqlite3
from statistics import median
from typing import Any

from session_browser.web.view_models import ProjectDetailViewModel, ProjectsViewModel

from session_browser.index.indexer import (
    list_projects,
    count_projects,
    list_sessions,
    count_sessions,
    get_project_stats,
)
from session_browser.web.template_env import _display_path


# 说明：── Query parameter defaults ─────────────────────────────────────────

VALID_PAGE_SIZES = {25, 50, 100}
PROJECT_SORT_KEY_MAP = {
    "sessions": "sessions",
    "tokens": "tokens",
    "tools": "tools",
    "failed": "failed",
    "first_seen": "first_seen",
    "last_active": "last_active",
}
PROJECT_DETAIL_SESSION_SORT_KEY_MAP = {
    "tokens": "total_tokens",
    "rounds": "assistant_message_count",
    "tools": "tool_call_count",
    "subagents": "subagent_instance_count",
    "duration": "duration_seconds",
    "process-time": "process_seconds",
    "failure": "failed_tool_count",
    "created": "started_at",
    "updated": "ended_at",
}
PROJECT_TREND_GRAINS = {"day", "week", "month"}


def parse_projects_query_params(raw_params: dict[str, list[str]]) -> dict[str, Any]:
    """解析 URL query parameters，转换为 一个 typed dict，用于 projects pages.

    Args:
        raw_params: Result of urllib.parse.parse_qs().

    Returns:
        Dict with keys: page, page_size.
    """
    # 说明：Pagination — page
    try:
        page = int(raw_params.get("page", ["1"])[0])
        if page < 1:
            page = 1
    except (ValueError, IndexError):
        page = 1

    # 说明：Pagination — page_size
    raw_size = raw_params.get("page_size", ["25"])[0].strip().lower()
    try:
        page_size_int = int(raw_size)
        if page_size_int in VALID_PAGE_SIZES:
            page_size: int | str = page_size_int
        else:
            page_size = 25
    except ValueError:
        page_size = 25

    filter_q = raw_params.get("q", [""])[0].strip() or None
    raw_sort = raw_params.get("sort", ["last_active"])[0].strip().lower()
    sort_by = PROJECT_SORT_KEY_MAP.get(raw_sort, "last_active")
    sort_dir = raw_params.get("dir", ["desc"])[0].strip().lower()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"

    return {
        "page": page,
        "page_size": page_size,
        "filter_q": filter_q,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }


def compute_projects_pagination(
    total_count: int,
    page: int,
    page_size: int | str,
) -> dict[str, Any]:
    """计算 limit, offset 和 pagination metadata，用于 projects listing.

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

    # 说明：page_start / page_end
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
        "page": page,  # 说明：possibly clamped
    }


def parse_project_detail_query_params(raw_params: dict[str, list[str]]) -> dict[str, Any]:
    """解析 query parameters，用于 project detail sessions 和 trend controls."""
    params = parse_projects_query_params(raw_params)
    raw_sort = raw_params.get("sort", ["updated"])[0].strip().lower()
    params["sort_by"] = PROJECT_DETAIL_SESSION_SORT_KEY_MAP.get(raw_sort, "ended_at")
    params["sort_key"] = raw_sort if raw_sort in PROJECT_DETAIL_SESSION_SORT_KEY_MAP else "updated"
    params["filter_q"] = raw_params.get("q", [""])[0].strip() or None
    grain = raw_params.get("grain", ["day"])[0].strip().lower()
    params["grain"] = grain if grain in PROJECT_TREND_GRAINS else "day"
    return params


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fmt_percent(numerator: float, denominator: float) -> str:
    numerator = _safe_number(numerator)
    denominator = _safe_number(denominator)
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator * 100):.1f}%"


def _fmt_seconds(value: float) -> str:
    seconds = int(value or 0)
    if seconds <= 0:
        return "0s"
    hours, rem = divmod(seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _session_input_side(session: Any) -> int:
    return int(
        getattr(session, "fresh_input_tokens", 0)
        + getattr(session, "cache_read_tokens", 0)
        + getattr(session, "cache_write_tokens", 0)
    )


def _session_total_tokens(session: Any) -> int:
    return int(_session_input_side(session) + getattr(session, "output_tokens", 0))


def _project_attr(project: Any, name: str, default: Any = 0) -> Any:
    if isinstance(project, dict):
        return project.get(name, default)
    return getattr(project, name, default)


def _safe_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, Real):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return float(default)
    return float(default)


def _project_number(project: Any, name: str, default: float = 0.0) -> float:
    return _safe_number(_project_attr(project, name, default), default)


def _bucket_for_grain(dt: datetime, grain: str) -> str:
    if grain == "month":
        return dt.strftime("%Y-%m")
    if grain == "week":
        start = dt - timedelta(days=dt.weekday())
        return start.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d")


def _build_project_token_trend(sessions: list[Any], grain: str) -> dict[str, Any]:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {
        "fresh": 0,
        "cache_read": 0,
        "cache_write": 0,
        "output": 0,
        "total": 0,
    })
    for session in sessions:
        dt = _parse_dt(getattr(session, "started_at", ""))
        if not dt:
            continue
        key = _bucket_for_grain(dt, grain)
        bucket = buckets[key]
        fresh = int(getattr(session, "fresh_input_tokens", 0))
        read = int(getattr(session, "cache_read_tokens", 0))
        write = int(getattr(session, "cache_write_tokens", 0))
        output = int(getattr(session, "output_tokens", 0))
        bucket["fresh"] += fresh
        bucket["cache_read"] += read
        bucket["cache_write"] += write
        bucket["output"] += output
        bucket["total"] += fresh + read + write + output

    points = [{"label": k, **v} for k, v in sorted(buckets.items())]
    max_total = max((p["total"] for p in points), default=0)
    layers = []
    keys = [
        ("fresh", "Fresh"),
        ("cache_read", "Cache Read"),
        ("cache_write", "Cache Write"),
        ("output", "Output"),
    ]
    if points and max_total > 0:
        n = len(points)
        cumulative_lower = [0.0 for _ in points]
        for key, label in keys:
            upper = []
            lower = []
            for idx, point in enumerate(points):
                x = 0 if n == 1 else idx / (n - 1) * 100
                low = cumulative_lower[idx]
                high = low + point[key] / max_total * 100
                lower.append((x, 100 - low))
                upper.append((x, 100 - high))
                cumulative_lower[idx] = high
            path = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in upper)
            path += " L " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in reversed(lower))
            path += " Z"
            layers.append({"key": key, "label": label, "path": path})

    return {
        "grain": grain,
        "points": points,
        "layers": layers,
        "max_total": max_total,
        "has_data": bool(points and max_total > 0),
    }


def _build_project_detail_stats(project: Any, sessions: list[Any], grain: str) -> dict[str, Any]:
    today = datetime.now().date()
    recent_days = {today - timedelta(days=i): 0 for i in range(7)}
    durations = []
    process_times = []
    eligible_sessions = 0
    low_read_sessions = 0
    affected_sessions = 0
    repeated_failure_sessions = 0
    agent_counts: Counter[str] = Counter()
    agent_tokens: Counter[str] = Counter()
    agent_failed: Counter[str] = Counter()

    for session in sessions:
        dt = _parse_dt(getattr(session, "started_at", ""))
        if dt and dt.date() in recent_days:
            recent_days[dt.date()] += 1
        duration = float(getattr(session, "duration_seconds", 0) or 0)
        process = float(getattr(session, "model_execution_seconds", 0) or 0) + float(getattr(session, "tool_execution_seconds", 0) or 0)
        if duration > 0:
            durations.append(duration)
        if process > 0:
            process_times.append(process)
        input_side = _session_input_side(session)
        read = int(getattr(session, "cache_read_tokens", 0) or 0)
        if input_side > 0:
            eligible_sessions += 1
            if read / input_side < 0.2:
                low_read_sessions += 1
        failed = int(getattr(session, "failed_tool_count", 0) or 0)
        if failed > 0:
            affected_sessions += 1
        if failed > 1:
            repeated_failure_sessions += 1
        agent = getattr(session, "agent", "") or "unknown"
        agent_counts[agent] += 1
        agent_tokens[agent] += _session_total_tokens(session)
        agent_failed[agent] += failed

    input_side_total = int(
        _project_number(project, "total_fresh_input_tokens", 0)
        + _project_number(project, "total_cache_read_tokens", 0)
        + _project_number(project, "total_cache_write_tokens", 0)
    )
    total_tokens = int(input_side_total + _project_number(project, "total_output_tokens", 0))
    agent_rows = []
    for agent_key, label, scope in [
        ("claude_code", "Claude Code", "claude"),
        ("qoder", "Qoder", "qoder"),
        ("codex", "Codex", "codex"),
    ]:
        count = agent_counts.get(agent_key, 0)
        tokens = agent_tokens.get(agent_key, 0)
        failed = agent_failed.get(agent_key, 0)
        agent_rows.append({
            "key": agent_key,
            "label": label,
            "scope": scope,
            "sessions": count,
            "tokens": tokens,
            "failed": failed,
            "session_share": count / _project_number(project, "total_sessions", 0) * 100 if _project_number(project, "total_sessions", 0) else 0,
            "token_share": tokens / total_tokens * 100 if total_tokens else 0,
        })

    return {
        "active_period": f"Active: {_project_attr(project, 'first_seen', '')[:10] or 'N/A'} to {_project_attr(project, 'last_seen', '')[:10] or 'N/A'}",
        "sessions_kpi": {
            "today": recent_days.get(today, 0),
            "avg_7d": sum(recent_days.values()) / 7,
            "median_duration": _fmt_seconds(median(durations)) if durations else "0s",
            "median_process_time": _fmt_seconds(median(process_times)) if process_times else "0s",
        },
        "agents_kpi": {
            "count": sum(1 for count in agent_counts.values() if count > 0),
            "claude_code": agent_counts.get("claude_code", 0),
            "qoder": agent_counts.get("qoder", 0),
            "codex": agent_counts.get("codex", 0),
        },
        "tokens_kpi": {
            "total": total_tokens,
            "fresh": int(_project_number(project, "total_fresh_input_tokens", 0)),
            "cache_read": int(_project_number(project, "total_cache_read_tokens", 0)),
            "cache_write": int(_project_number(project, "total_cache_write_tokens", 0)),
            "output": int(_project_number(project, "total_output_tokens", 0)),
        },
        "cache_kpi": {
            "ratio": _fmt_percent(_project_number(project, "total_cache_read_tokens", 0), input_side_total),
            "eligible_sessions": eligible_sessions,
            "low_read_sessions": low_read_sessions,
        },
        "failure_kpi": {
            "failed_tools": int(_project_number(project, "total_failed_tools", 0)),
            "failure_rate": _fmt_percent(_project_number(project, "total_failed_tools", 0), _project_number(project, "total_tool_calls", 0)),
            "affected_sessions": affected_sessions,
            "repeated_failure_sessions": repeated_failure_sessions,
        },
        "agent_mix": agent_rows,
        "token_trend": _build_project_token_trend(sessions, grain),
        "tool_hotspots_available": False,
        "tool_hotspots_reason": "Tool name breakdown is not stored in the current session index.",
    }


def build_projects_view_model(
    raw_params: dict[str, list[str]] | None = None,
    conn: sqlite3.Connection | None = None,
) -> ProjectsViewModel:
    """构建 该 complete view model，用于 该 projects listing page.

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
            "page_size": 25,
            "filter_q": "",
            "sort_by": "last_active",
            "sort_dir": "desc",
            "total_pages": 1,
            "total_count": 0,
            "page_start": 0,
            "page_end": 0,
            "has_prev": False,
            "has_next": False,
        }

    params = parse_projects_query_params(raw_params)

    # 说明：Get total count first
    total_count = int(count_projects(conn, title_like=params["filter_q"]))

    # 计算 pagination
    pagination = compute_projects_pagination(
        total_count=total_count,
        page=params["page"],
        page_size=params["page_size"],
    )

    # 说明：Fetch paginated projects
    projects = list_projects(
        conn,
        title_like=params["filter_q"],
        limit=pagination["limit"],
        offset=pagination["offset"],
        order_by=params["sort_by"],
        order_dir=params["sort_dir"],
    )

    # 计算 display_path，用于 each project: use cwd (actual filesystem path)
    # with ~ substitution, falling back to project_key，如果 cwd is empty.
    for p in projects:
        raw_path = p.cwd if hasattr(p, 'cwd') and p.cwd else p.project_key
        p.display_path = _display_path(raw_path)

    return {
        "projects": projects,
        "active_page": "projects",
        "page": pagination["page"],
        "current_page": pagination["page"],
        "page_size": params["page_size"],
        "filter_q": params["filter_q"] or "",
        "sort_by": params["sort_by"],
        "sort_dir": params["sort_dir"],
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
) -> ProjectDetailViewModel:
    """构建 该 complete view model，用于 一个 single project page.

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

    params = parse_project_detail_query_params(raw_params)

    pstats = get_project_stats(conn, project_key)
    if not _project_attr(pstats, "project_name", "") and _project_attr(pstats, "total_sessions", 0) == 0:
        return {
            "project": pstats,
            "sessions": [],
            "project_key": project_key,
            "active_page": "projects",
            "error": "Project not found",
            "page": 1,
            "current_page": 1,
            "page_size": 25,
            "filter_q": "",
            "sort_by": "updated",
            "sort_dir": "desc",
            "trend_grain": "day",
            "total_pages": 1,
            "total_count": 0,
            "page_start": 0,
            "page_end": 0,
            "has_prev": False,
            "has_next": False,
        }

    # Get total count，用于 this project
    total_count = int(count_sessions(conn, project_key=project_key, title_like=params["filter_q"]))

    # 计算 pagination
    pagination = compute_projects_pagination(
        total_count=total_count,
        page=params["page"],
        page_size=params["page_size"],
    )

    # Fetch paginated sessions，用于 this project
    sessions = list_sessions(
        conn,
        project_key=project_key,
        title_like=params["filter_q"],
        limit=pagination["limit"],
        offset=pagination["offset"],
        order_by=params["sort_by"],
        order_dir=params["sort_dir"],
    )
    all_project_sessions = list_sessions(
        conn,
        project_key=project_key,
        limit=max(int(_project_number(pstats, "total_sessions", 0) or 0), 1),
        offset=0,
        order_by="started_at",
        order_dir="asc",
    )
    project_detail = _build_project_detail_stats(pstats, all_project_sessions, params["grain"])

    return {
        "project": pstats,
        "project_detail": project_detail,
        "sessions": sessions,
        "project_key": project_key,
        "active_page": "projects",
        "error": None,
        "page": pagination["page"],
        "current_page": pagination["page"],
        "page_size": params["page_size"],
        "filter_q": params["filter_q"] or "",
        "sort_by": params["sort_key"],
        "sort_dir": params["sort_dir"],
        "trend_grain": params["grain"],
        "total_pages": pagination["total_pages"],
        "total_count": total_count,
        "page_start": pagination["page_start"],
        "page_end": pagination["page_end"],
        "has_prev": pagination["has_prev"],
        "has_next": pagination["has_next"],
    }
