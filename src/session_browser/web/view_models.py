"""TypedDict contracts for web presenter view models.

These types document top-level template contracts without forcing every nested
agent/runtime-specific detail into rigid classes. They reduce accidental key
shape drift while keeping presenter code simple.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class PaginationViewModel(TypedDict):
    page: int
    current_page: int
    page_size: int | str
    total_pages: int
    total_count: int
    page_start: int
    page_end: int
    has_prev: bool
    has_next: bool


class SessionsViewModel(PaginationViewModel, total=False):
    sessions: list[Any]
    active_page: str
    filter_agent: str
    filter_model: str
    filter_project: str
    filter_q: str
    filter_status: str
    sort_by: str
    sort_dir: str
    sessions_aggregate: dict[str, Any]
    model_list: list[str]
    project_list: list[str]


class DashboardViewModel(TypedDict):
    agent_scope: str
    grain: str
    is_single_agent: bool
    stats: dict[str, Any]
    kpis: list[dict[str, Any]]
    trend: list[dict[str, Any]]
    prompt_activity: list[dict[str, Any]]
    all_agents_branch: dict[str, Any] | None
    single_agent_branch: dict[str, Any] | None
    needs_attention: list[dict[str, Any]]
    cache_health: dict[str, Any]
    chart_notes: dict[str, str]
    active_page: str
    agent_sessions_page: int
    agent_sessions_total_pages: int
    agent_sessions_total: int
    agent_sessions_page_size: int


class ProjectsViewModel(PaginationViewModel, total=False):
    projects: list[Any]
    active_page: str
    filter_q: str
    sort_by: str
    sort_dir: str


class ProjectDetailViewModel(PaginationViewModel, total=False):
    project: Any
    sessions: list[Any]
    project_key: str
    active_page: str
    filter_q: str
    sort_by: str
    sort_dir: str
    trend_grain: str
    error: NotRequired[str]
    project_detail_stats: NotRequired[dict[str, Any]]


class PayloadSourceViewModel(TypedDict, total=False):
    payload_id: str
    kind: str
    title: str
    status: str
    size: str
    text: str
    html: str
    warning: str
    data: dict[str, Any]
    token_estimate: int
    token_estimate_precision: str
    token_estimate_source: str


class TraceRowViewModel(TypedDict, total=False):
    round_id: int
    title: str
    status_key: str
    status_label: str
    status_tone: str
    preview_title: str
    preview_subtitle: str
    request_attribution: dict[str, Any]
    response_attribution: dict[str, Any]


class SessionDetailViewModel(TypedDict, total=False):
    session_summary: dict[str, Any]
    hero_metrics: list[dict[str, Any]]
    issue_links: list[dict[str, Any]]
    trace_rows: list[TraceRowViewModel]
    payload_sources: list[PayloadSourceViewModel]
    active_page: str
