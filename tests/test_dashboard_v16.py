"""Tests for Dashboard UI — page-head, metric grid, charts, and content contract."""

from __future__ import annotations

import os
import re

import pytest

_DASHBOARD_PATH = "src/session_browser/web/templates/dashboard.html"
_DASHBOARD_CSS_PATH = "src/session_browser/web/static/css/dashboard.css"
_DASHBOARD_JS_PATH = "src/session_browser/web/static/js/dashboard.js"
_ROUTES_PATH = "src/session_browser/web/routes.py"


def _read_dashboard_template() -> str:
    """Read dashboard.html template."""
    with open(_DASHBOARD_PATH) as f:
        return f.read()


def _read_dashboard_css() -> str:
    """Read dashboard.css."""
    with open(_DASHBOARD_CSS_PATH) as f:
        return f.read()


def _read_dashboard_js() -> str:
    """Read dashboard.js."""
    with open(_DASHBOARD_JS_PATH) as f:
        return f.read()


def _read_routes() -> str:
    """Read routes.py."""
    with open(_ROUTES_PATH) as f:
        return f.read()


class TestDashboardHttp:
    """Verify /dashboard route returns HTTP 200 (requires live server fixture)."""

    def test_dashboard_returns_200(self, live_server_url):
        """Dashboard must return HTTP 200."""
        import urllib.request
        resp = urllib.request.urlopen(f"{live_server_url}/dashboard", timeout=10)
        assert resp.status == 200


class TestDashboardPageHead:
    """Verify page-head section structure."""

    def test_has_page_head(self):
        content = _read_dashboard_template()
        assert 'class="page-head"' in content, "Dashboard must have <section class='page-head'>"

    def test_page_head_has_title(self):
        content = _read_dashboard_template()
        assert "<h1>Dashboard</h1>" in content, "Page head must have Dashboard title"

    def test_page_head_has_sub(self):
        content = _read_dashboard_template()
        assert "Local agent session overview" in content, "Page head must have subtitle"

    def test_page_head_has_scope_switch(self):
        content = _read_dashboard_template()
        assert 'class="scope-switch"' in content, "Page head must have scope switch"

    def test_scope_switch_has_three_buttons(self):
        content = _read_dashboard_template()
        assert 'data-action="scope-day"' in content
        assert 'data-action="scope-week"' in content
        assert 'data-action="scope-month"' in content


class TestDashboardMetricGrid:
    """Verify metric grid/cards structure."""

    def test_has_metric_grid(self):
        content = _read_dashboard_template()
        assert 'class="metric-grid"' in content, "Dashboard must have metric grid"

    def test_has_metric_cards(self):
        content = _read_dashboard_template()
        assert 'class="metric-card"' in content, "Dashboard must have metric cards"

    def test_metric_card_has_label_value_sub(self):
        content = _read_dashboard_template()
        assert 'class="metric-card__label"' in content
        assert 'class="metric-card__value"' in content
        assert 'metric-card__sub' in content, "Metric cards must have sub/annotation class"

    def test_metric_card_has_icon(self):
        content = _read_dashboard_template()
        assert 'class="metric-card__icon"' in content, "Metric cards must have icon"

    def test_metric_card_has_info_button(self):
        content = _read_dashboard_template()
        assert 'data-action="info-' in content, "Metric cards must have info buttons"

    def test_has_projects_metric(self):
        content = _read_dashboard_template()
        assert "Projects" in content, "Dashboard must have Projects metric"

    def test_has_sessions_metric(self):
        content = _read_dashboard_template()
        assert "Sessions" in content, "Dashboard must have Sessions metric"

    def test_has_tokens_metric(self):
        content = _read_dashboard_template()
        assert "Tokens" in content or "tokens" in content, "Dashboard must have Tokens metric"


class TestDashboardCharts:
    """Verify trend chart content."""

    def test_has_session_trend(self):
        content = _read_dashboard_template()
        assert "Session Trend" in content, "Dashboard must contain Session Trend chart"

    def test_has_token_trend(self):
        content = _read_dashboard_template()
        assert "Token Trend" in content, "Dashboard must contain Token Trend chart"

    def test_has_prompt_activity_trend(self):
        content = _read_dashboard_template()
        assert "Prompt Activity Trend" in content, "Dashboard must contain Prompt Activity Trend"

    def test_chart_has_legend(self):
        content = _read_dashboard_template()
        assert "Claude Code" in content
        assert "Codex" in content
        assert "Qoder" in content

    def test_chart_uses_variable_data(self):
        content = _read_dashboard_template()
        assert "{{ trend | tojson }}" in content, \
            "Chart data must come from {{ trend | tojson }}, not hardcoded"


class TestDashboardChartBars:
    """Verify chart bar tooltip DOM structure (rendered by dashboard.js)."""

    def test_bar_template_has_tooltip(self):
        content = _read_dashboard_js()
        assert 'dashboard-tooltip' in content, \
            "Chart bars must contain .dashboard-tooltip DOM structure (rendered by JS)"

    def test_tooltip_has_dot_classes(self):
        content = _read_dashboard_js()
        assert "tooltip-dot--claude" in content
        assert "tooltip-dot--codex" in content
        assert "tooltip-dot--qoder" in content
        assert "tooltip-dot--total" in content

    def test_tooltip_has_row_structure(self):
        content = _read_dashboard_js()
        assert "tooltip-row" in content
        assert "tooltip-label" in content
        assert "tooltip-value" in content


class TestDashboardNoRecentActivity:
    """Verify Recent Activity section has been removed."""

    def test_no_recent_activity(self):
        content = _read_dashboard_template()
        assert "Recent Activity" not in content, \
            "Dashboard must not contain Recent Activity section"

    def test_no_needs_attention_section(self):
        content = _read_dashboard_template()
        assert "needs_attention" not in content, \
            "Dashboard must not render needs_attention"


class TestDashboardNoCompact:
    """Verify dashboard does NOT contain compact/tight mode references."""

    def test_no_compact_chinese(self):
        content = _read_dashboard_template()
        assert "紧凑" not in content, \
            "Dashboard must not contain Chinese '紧凑' (compact mode)"

    def test_density_toggle_not_in_dashboard(self):
        content = _read_dashboard_template()
        assert "density-toggle" not in content, \
            "Dashboard must not have density-toggle class"


class TestDashboardTrendDataSource:
    """Verify token trend data comes from backend, not hardcoded."""

    def test_trend_variable_passed_to_template(self):
        routes = _read_routes()
        serve_func = routes.split("def _serve_dashboard")[1].split("def _")[0]
        assert "trend=" in serve_func, \
            "_serve_dashboard must pass trend= to template"

    def test_get_trend_data_called(self):
        routes = _read_routes()
        serve_func = routes.split("def _serve_dashboard")[1].split("def _")[0]
        assert "get_trend_data" in serve_func, \
            "_serve_dashboard must call get_trend_data"

    def test_trend_not_hardcoded(self):
        content = _read_dashboard_template()
        assert 'id="dashboard-chart-data"' in content, \
            "Chart data must be provided via JSON data block"
        assert "{{ trend | tojson }}" in content, \
            "Chart data must come from {{ trend | tojson }}"

    def test_token_data_from_same_trend(self):
        content = _read_dashboard_js()
        assert "function renderTokenChart" in content, \
            "Token chart must be rendered via renderTokenChart function"
        assert "rawData" in content.split("function renderTokenChart")[1].split("function ")[0], \
            "Token chart must use rawData from backend, not hardcoded"


class TestDashboardFooter:
    """Verify footer structure."""

    def test_base_template_has_footer(self):
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert '<footer class="footer"' in content, \
            "Base template must have footer element"


class TestDashboardCSS:
    """Verify dashboard CSS file exists and has required rules."""

    def test_css_file_exists(self):
        assert os.path.exists(_DASHBOARD_CSS_PATH), f"CSS file not found: {_DASHBOARD_CSS_PATH}"

    def test_chart_card_defined(self):
        css = _read_dashboard_css()
        assert "chart-card" in css, "CSS must define .chart-card"

    def test_metric_grid_defined(self):
        css = _read_dashboard_css()
        assert "metric-grid" in css or "metric-grid" in css, "CSS must define .metric-grid"
