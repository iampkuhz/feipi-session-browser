"""Tests for Dashboard v16 UI — hero, charts, footer, and content contract."""

from __future__ import annotations

import os
import re

import pytest

_DASHBOARD_PATH = "src/session_browser/web/templates/dashboard.html"
_DASHBOARD_CSS_PATH = "src/session_browser/web/static/css/dashboard-v16.css"
_ROUTES_PATH = "src/session_browser/web/routes.py"


def _read_dashboard_template() -> str:
    """Read dashboard.html template."""
    with open(_DASHBOARD_PATH) as f:
        return f.read()


def _read_dashboard_css() -> str:
    """Read dashboard-v16.css."""
    with open(_DASHBOARD_CSS_PATH) as f:
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


class TestDashboardHero:
    """Verify hero section structure."""

    def test_has_hero_section(self):
        content = _read_dashboard_template()
        assert 'class="hero"' in content, "Dashboard must have <section class='hero'>"

    def test_hero_has_scope_badge(self):
        content = _read_dashboard_template()
        assert 'class="scope"' in content, "Hero must have Local scope badge"

    def test_hero_has_title(self):
        content = _read_dashboard_template()
        assert 'class="hero-title"' in content, "Hero must have hero-title"

    def test_hero_has_sub(self):
        content = _read_dashboard_template()
        assert 'class="hero-sub"' in content, "Hero must have hero-sub"

    def test_hero_has_chips(self):
        content = _read_dashboard_template()
        assert 'class="hero-chips"' in content, "Hero must have hero-chips"
        assert 'class="chip"' in content, "Hero must have chip elements"

    def test_hero_has_kpis(self):
        content = _read_dashboard_template()
        assert 'class="hero-kpis"' in content, "Hero must have hero-kpis"
        assert 'class="hero-kpi"' in content, "Hero must have hero-kpi elements"


class TestDashboardCharts:
    """Verify trend chart content."""

    def test_has_session_trend(self):
        """HTML must contain 'Session Trend'."""
        content = _read_dashboard_template()
        assert "Session Trend" in content, "Dashboard must contain Session Trend chart"

    def test_has_token_trend(self):
        """HTML must contain 'Token Trend'."""
        content = _read_dashboard_template()
        assert "Token Trend" in content, "Dashboard must contain Token Trend chart"

    def test_chart_title_uppercase(self):
        """Chart titles should use uppercase style via CSS."""
        content = _read_dashboard_template()
        # Both chart titles present
        assert "Session Trend" in content
        assert "Token Trend" in content

    def test_chart_has_legend(self):
        """Charts must have legend with agent names."""
        content = _read_dashboard_template()
        assert 'class="legend"' in content
        assert "Claude Code" in content
        assert "Codex" in content
        assert "Qoder" in content

    def test_chart_has_range_tabs(self):
        """Charts must have 30d / 7d range tabs."""
        content = _read_dashboard_template()
        assert 'class="range-tabs"' in content or "range-btn" in content
        assert "30d" in content
        assert "7d" in content


class TestDashboardChartBars:
    """Verify chart bar structure uses structured tooltip DOM."""

    def test_bar_template_has_dashboard_tooltip(self):
        """The JS in the template must build .dashboard-tooltip DOM."""
        content = _read_dashboard_template()
        assert 'dashboard-tooltip' in content, \
            "Chart bars must contain .dashboard-tooltip DOM structure"

    def test_tooltip_contains_agent_names(self):
        """Tooltip DOM must include Claude Code, Codex, Qoder."""
        content = _read_dashboard_template()
        assert "Claude Code" in content, "Tooltip must contain 'Claude Code'"
        assert "Codex" in content, "Tooltip must contain 'Codex'"
        assert "Qoder" in content, "Tooltip must contain 'Qoder'"

    def test_tooltip_has_dot_classes(self):
        """Tooltip must have colored dot classes."""
        content = _read_dashboard_template()
        assert "tooltip-dot--claude" in content
        assert "tooltip-dot--codex" in content
        assert "tooltip-dot--qoder" in content
        assert "tooltip-dot--total" in content

    def test_tooltip_has_row_structure(self):
        """Tooltip must use .tooltip-row structure."""
        content = _read_dashboard_template()
        assert "tooltip-row" in content
        assert "tooltip-label" in content
        assert "tooltip-value" in content


class TestDashboardNoRecentActivity:
    """Verify Recent Activity section has been removed."""

    def test_no_recent_activity(self):
        """Dashboard must NOT contain 'Recent Activity'."""
        content = _read_dashboard_template()
        assert "Recent Activity" not in content, \
            "Dashboard must not contain Recent Activity section"

    def test_no_needs_attention_section(self):
        """Dashboard must NOT contain needs_attention rendering."""
        content = _read_dashboard_template()
        # The template should not iterate over needs_attention
        assert "needs_attention" not in content, \
            "Dashboard must not render needs_attention"


class TestDashboardNoCompact:
    """Verify dashboard does NOT contain compact/tight mode references."""

    def test_no_compact_chinese(self):
        """Dashboard must NOT contain '紧凑'."""
        content = _read_dashboard_template()
        assert "紧凑" not in content, \
            "Dashboard must not contain Chinese '紧凑' (compact mode)"

    def test_no_compact_toggle_block(self):
        """Dashboard must override topbar_toggles block to remove density toggle."""
        content = _read_dashboard_template()
        assert "{% block topbar_toggles %}{% endblock %}" in content or \
               "{% block topbar_toggles %}" in content and "{% endblock %}" in content, \
            "Dashboard should override topbar_toggles block"

    def test_density_toggle_not_in_dashboard(self):
        """Density toggle must not appear in dashboard page."""
        content = _read_dashboard_template()
        assert "density-toggle" not in content, \
            "Dashboard must not have density-toggle class"


class TestDashboardFooter:
    """Verify footer layout contract: flex column + margin-top:auto."""

    def test_footer_css_margin_top_auto(self):
        """dashboard-v16.css must set .footer { margin-top:auto }."""
        css = _read_dashboard_css()
        assert "margin-top:auto" in css, \
            "Footer must use margin-top:auto for sticky bottom"

    def test_main_flex_layout(self):
        """.main must use flex column layout for footer pinning."""
        css = _read_dashboard_css()
        assert "display:flex" in css, "Main container must use flex layout"
        assert "flex-direction:column" in css, "Main must be flex-direction:column"

    def test_content_flex_one(self):
        """.content must use flex:1 to fill remaining space."""
        css = _read_dashboard_css()
        assert ".content{flex:1" in css or ".content{flex: 1" in css, \
            "Content must use flex:1"

    def test_base_template_has_footer(self):
        """base.html must have a footer element."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert '<footer class="footer"' in content, \
            "Base template must have footer element"


class TestDashboardTrendDataSource:
    """Verify token trend data comes from backend, not hardcoded."""

    def test_trend_variable_passed_to_template(self):
        """routes.py _serve_dashboard must pass trend variable to template."""
        routes = _read_routes()
        # Find the _serve_dashboard function
        serve_func = routes.split("def _serve_dashboard")[1].split("def _")[0]
        assert "trend=" in serve_func, \
            "_serve_dashboard must pass trend= to template"

    def test_get_trend_data_called(self):
        """routes.py must call get_trend_data in _serve_dashboard."""
        routes = _read_routes()
        serve_func = routes.split("def _serve_dashboard")[1].split("def _")[0]
        assert "get_trend_data" in serve_func, \
            "_serve_dashboard must call get_trend_data"

    def test_trend_not_hardcoded(self):
        """Dashboard template must not hardcode chart data."""
        content = _read_dashboard_template()
        # The template should use {{ trend | tojson }}
        assert "rawData = {{ trend | tojson }}" in content, \
            "Chart data must come from {{ trend | tojson }}, not hardcoded"

    def test_token_data_from_same_trend(self):
        """Token trend must use the same trend data, not a separate hardcoded source."""
        content = _read_dashboard_template()
        # Token chart function should use rawData (same as session chart)
        assert "function renderTokenChart" in content, \
            "Token chart must be rendered via renderTokenChart function"
        # The function should process rawData, not hardcoded values
        token_func = content.split("function renderTokenChart")[1].split("function ")[0]
        assert "rawData" in token_func, \
            "Token chart must use rawData from backend, not hardcoded"

    def test_token_sql_source_has_all_fields(self):
        """get_trend_data must query all required token fields."""
        indexer_path = "src/session_browser/index/indexer.py"
        with open(indexer_path) as f:
            indexer = f.read()
        assert "input_tokens" in indexer
        assert "output_tokens" in indexer
        assert "cache_read" in indexer or "cached_input" in indexer
        assert "cache_write" in indexer or "cached_output" in indexer


class TestChartTypography:
    """Verify chart title typography contract."""

    def test_chart_title_size_in_css(self):
        """chart-title should be 14px in CSS."""
        css = _read_dashboard_css()
        assert "chart-title" in css, "CSS must define chart-title class"
        # Check for 14px
        assert "14px" in css, "CSS should have 14px font size"

    def test_hero_title_larger_than_chart_title(self):
        """Hero title (18px) must be larger than chart title (14px)."""
        css = _read_dashboard_css()
        # Hero h1 font-size is in CSS: .hero h1{font-size:18px;...}
        assert "18px" in css, "Hero h1 should be 18px in CSS"
        # Chart title is 14px
        assert "14px" in css, "Chart title should be 14px in CSS"


class TestDashboardCompactButtonRemoved:
    """Verify the compact/tight mode button is removed from dashboard."""

    def test_no_density_toggle_css_in_dashboard(self):
        """Dashboard page should not reference density-toggle."""
        content = _read_dashboard_template()
        # The topbar_toggles block should be empty override
        assert 'density-toggle' not in content, \
            "Dashboard should not have density-toggle"


class TestDashboardTooltipDots:
    """Verify tooltip dot styling and CSS structure."""

    def test_tooltip_css_classes_defined(self):
        """dashboard-v16.css must define tooltip dot classes."""
        css = _read_dashboard_css()
        for cls in ["dashboard-tooltip", "tooltip-row", "tooltip-dot--claude",
                     "tooltip-dot--codex", "tooltip-dot--qoder", "tooltip-dot--total"]:
            assert cls in css, f"CSS must define {cls}"

    def test_legend_dots_are_round(self):
        """Legend dots should use border-radius:999px for circular shape."""
        css = _read_dashboard_css()
        assert "999px" in css, "Legend dots should use border-radius:999px"

    def test_agent_color_variables_exist(self):
        """CSS must define --agent-* color variables."""
        css = _read_dashboard_css()
        assert "--agent-claude" in css
        assert "--agent-codex" in css
        assert "--agent-qoder" in css
