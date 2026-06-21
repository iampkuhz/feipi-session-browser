"""TypedDict contracts for web presenter view models.

These types document top-level template contracts without forcing every nested
agent/runtime-specific detail into rigid classes. They reduce accidental key
shape drift while keeping presenter code simple.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class PaginationViewModel(TypedDict):
    """Shared pagination fields consumed by list page templates.

    Attributes:
        page: Normalized one-based page number.
        current_page: Alias used by legacy templates for the active page.
        page_size: Page-size selector value, including the ``all`` option.
        total_pages: Number of pages available for the current filter set.
        total_count: Total rows matching the current filter set.
        page_start: One-based display index for the first row on the page.
        page_end: One-based display index for the last row on the page.
        has_prev: Whether a previous page navigation target exists.
        has_next: Whether a next page navigation target exists.
    """

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
    """Template contract for the global sessions listing page.

    Attributes:
        sessions: Enriched session rows displayed in the table.
        active_page: Navigation key for highlighting the sessions tab.
        filter_agent: Selected agent filter value.
        filter_model: Selected model filter value.
        filter_project: Selected project filter value.
        filter_q: Free-text title or project search query.
        filter_status: Selected failure-status filter value.
        sort_by: UI sort key used by the table header.
        sort_dir: Sort direction, usually ``asc`` or ``desc``.
        sessions_aggregate: Aggregate metrics for the filtered result set.
        model_list: Available model filter options.
        project_list: Available project filter options.
    """

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
    """Template contract for dashboard analytics widgets.

    Attributes:
        agent_scope: Agent filter used by dashboard charts.
        grain: Time bucket size used by trend series.
        is_single_agent: Whether the dashboard is scoped to one agent.
        stats: Raw aggregate metrics for the active scope.
        kpis: KPI cards rendered near the top of the dashboard.
        trend: Time-series data for the primary trend chart.
        prompt_activity: Prompt activity rows or buckets.
        all_agents_branch: Optional branch model for all-agent dashboards.
        single_agent_branch: Optional branch model for single-agent dashboards.
        needs_attention: Sessions or metrics requiring user attention.
        cache_health: Cache utilization and health metrics.
        chart_notes: Human-readable notes keyed by chart identifier.
        active_page: Navigation key for highlighting the dashboard tab.
        agent_sessions_page: One-based page for the embedded sessions table.
        agent_sessions_total_pages: Total pages in the embedded sessions table.
        agent_sessions_total: Total rows in the embedded sessions table.
        agent_sessions_page_size: Page size for the embedded sessions table.
    """

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
    """Template contract for the projects listing page.

    Attributes:
        projects: Project rows displayed in the projects table.
        active_page: Navigation key for highlighting the projects tab.
        filter_q: Free-text project search query.
        sort_by: UI sort key used by the projects table.
        sort_dir: Sort direction, usually ``asc`` or ``desc``.
    """

    projects: list[Any]
    active_page: str
    filter_q: str
    sort_by: str
    sort_dir: str


class ProjectDetailViewModel(PaginationViewModel, total=False):
    """Template contract for a single project detail page.

    Attributes:
        project: Project summary row selected by the route.
        sessions: Session rows associated with the project.
        project_key: Project identifier decoded from the route.
        active_page: Navigation key for highlighting the projects tab.
        filter_q: Free-text query applied to project sessions.
        sort_by: UI sort key used by the sessions table.
        sort_dir: Sort direction, usually ``asc`` or ``desc``.
        trend_grain: Time bucket size used by the project trend chart.
        error: Optional error message when the project cannot be resolved.
        project_detail_stats: Optional aggregate metrics for the project.
    """

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
    """Payload source contract used by session detail attribution panels.

    Attributes:
        payload_id: Stable key used by lazy payload APIs.
        kind: Payload category such as request, response, or tool result.
        title: Human-readable payload title.
        status: Payload availability or truncation status.
        size: Display size label for the payload.
        text: Plain-text preview or full payload content.
        html: Rendered HTML preview for rich payload content.
        warning: Optional warning shown next to the payload.
        data: Structured payload data for JSON-driven components.
        token_estimate: Estimated token count for the payload.
        token_estimate_precision: Precision label for the token estimate.
        token_estimate_source: Source label for the token estimate.
    """

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
    """Timeline row contract for one session round in the detail page.

    Attributes:
        round_id: One-based round identifier displayed in the timeline.
        title: Primary row title.
        status_key: Machine-readable status key for CSS and actions.
        status_label: Human-readable status label.
        status_tone: Visual tone used by badges and row accents.
        preview_title: Short title used by collapsed previews.
        preview_subtitle: Secondary preview text for the round.
        request_attribution: Request attribution payload for the row.
        response_attribution: Response attribution payload for the row.
    """

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
    """Top-level session detail template contract.

    Attributes:
        session_summary: Normalized session summary values for the hero area.
        hero_metrics: Metric cards rendered at the top of the page.
        issue_links: Links to warnings, anomalies, or related diagnostics.
        trace_rows: Timeline rows grouped by session round.
        payload_sources: Payload entries available for lazy detail loading.
        active_page: Navigation key for highlighting the active section.
    """

    session_summary: dict[str, Any]
    hero_metrics: list[dict[str, Any]]
    issue_links: list[dict[str, Any]]
    trace_rows: list[TraceRowViewModel]
    payload_sources: list[PayloadSourceViewModel]
    active_page: str
