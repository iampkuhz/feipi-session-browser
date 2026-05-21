"""Page-specific dashboard tests for current dashboard.html.

Verifies the Jinja2 template structure, CSS/JS imports, metric cards,
chart cards, scope-switch, info buttons, chart-menu buttons, empty/error
states, and absence of inline onclick.

T066 — Dashboard page-specific pytest.
"""

from __future__ import annotations

import os
import re

import pytest

_DASHBOARD_PATH = "src/session_browser/web/templates/dashboard.html"
_DASHBOARD_CSS_PATH = "src/session_browser/web/static/css/dashboard.css"
_DASHBOARD_JS_PATH = "src/session_browser/web/static/js/dashboard.js"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_dashboard() -> str:
    return _read(_DASHBOARD_PATH)


# ── TestDashboardTemplate ─────────────────────────────────────────────

class TestDashboardTemplate:
    """Verify the dashboard Jinja2 template renders structurally."""

    def test_template_file_exists(self):
        assert os.path.isfile(_DASHBOARD_PATH), \
            f"{_DASHBOARD_PATH} must exist"

    def test_extends_base(self):
        content = _read_dashboard()
        assert '{% extends "base.html" %}' in content, \
            "Dashboard must extend base.html"

    def test_active_page_set(self):
        content = _read_dashboard()
        assert "active_page = 'dashboard'" in content, \
            "Dashboard must set active_page = 'dashboard'"

    def test_ui_primitives_imported(self):
        content = _read_dashboard()
        assert 'import "components/ui_primitives.html"' in content, \
            "Dashboard must import ui_primitives.html"

    def test_no_inline_onclick(self):
        """Dashboard must not use inline onclick handlers."""
        content = _read_dashboard()
        # Find all onclick attributes in the template body
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Dashboard must not have inline onclick, found {len(matches)} occurrences"


# ── TestDashboardImports ──────────────────────────────────────────────

class TestDashboardImports:
    """Verify CSS and JS import statements."""

    def test_css_import_dashboard_css(self):
        content = _read_dashboard()
        assert 'href="/static/css/dashboard.css"' in content, \
            "Dashboard must import dashboard.css"

    def test_js_import_dashboard_js(self):
        content = _read_dashboard()
        assert 'src="/static/js/dashboard.js"' in content, \
            "Dashboard must import dashboard.js"

    def test_css_file_exists_on_disk(self):
        assert os.path.isfile(_DASHBOARD_CSS_PATH), \
            "dashboard.css must exist on disk"

    def test_js_file_exists_on_disk(self):
        assert os.path.isfile(_DASHBOARD_JS_PATH), \
            "dashboard.js must exist on disk"


# ── TestDashboardPageHead ────────────────────────────────────────────

class TestDashboardPageHead:
    """Verify page-head structure."""

    def test_page_head_section_present(self):
        content = _read_dashboard()
        assert 'class="page-head"' in content, \
            "Dashboard must have a page-head section"

    def test_page_head_has_h1(self):
        content = _read_dashboard()
        assert "<h1>Dashboard</h1>" in content, \
            "Page-head must contain <h1>Dashboard</h1>"

    def test_page_head_has_subtitle(self):
        content = _read_dashboard()
        assert "Local agent session overview" in content, \
            "Page-head must have subtitle 'Local agent session overview'"


# ── TestDashboardMetricCards ─────────────────────────────────────────

class TestDashboardMetricCards:
    """Verify 4 metric cards with correct labels."""

    _EXPECTED_LABELS = ["Projects", "Sessions", "Total Tokens", "Failed Tools"]

    def test_metric_grid_present(self):
        content = _read_dashboard()
        assert 'class="metric-grid"' in content, \
            "Dashboard must have a metric-grid section"

    def test_four_metric_cards(self):
        content = _read_dashboard()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Dashboard must have exactly 4 metric cards, found {len(cards)}"

    @pytest.mark.parametrize("label", ["Projects", "Sessions", "Total Tokens", "Failed Tools"])
    def test_metric_card_labels(self, label):
        content = _read_dashboard()
        assert f'"{label}"' in content or f">{label}<" in content, \
            f"Dashboard must have a metric card labeled '{label}'"

    def test_metric_card_aria_labels(self):
        """Each metric card must have an aria-label."""
        content = _read_dashboard()
        for label in self._EXPECTED_LABELS:
            assert f'aria-label="{label}"' in content, \
                f"Metric card '{label}' must have aria-label"


# ── TestDashboardChartCards ──────────────────────────────────────────

class TestDashboardChartCards:
    """Verify chart cards (2 in current production: Session Trend + Token Trend)."""

    def test_chart_cards_present(self):
        content = _read_dashboard()
        cards = re.findall(r'data-chart-card="[^"]*"', content)
        assert len(cards) >= 2, \
            f"Dashboard must have at least 2 chart cards, found {len(cards)}"

    def test_session_trend_chart(self):
        content = _read_dashboard()
        assert "Session Trend" in content, \
            "Dashboard must have Session Trend chart"
        assert 'data-chart-card="sessions"' in content, \
            "Session Trend chart must have data-chart-card='sessions'"

    def test_token_trend_chart(self):
        content = _read_dashboard()
        assert "Token Trend" in content, \
            "Dashboard must have Token Trend chart"
        assert 'data-chart-card="tokens"' in content, \
            "Token Trend chart must have data-chart-card='tokens'"

    def test_chart_has_legend(self):
        """Charts must show legend with agent names."""
        content = _read_dashboard()
        for agent in ["Claude Code", "Codex", "Qoder"]:
            assert agent in content, \
                f"Chart legend must contain '{agent}'"


# ── TestDashboardScopeSwitch ─────────────────────────────────────────

class TestDashboardScopeSwitch:
    """Verify scope-switch buttons (Day / Week / Month)."""

    def test_scope_switch_container(self):
        content = _read_dashboard()
        assert 'class="scope-switch"' in content, \
            "Dashboard must have a scope-switch container"

    def test_scope_switch_day_button(self):
        content = _read_dashboard()
        assert 'data-scope="day"' in content, \
            "Scope-switch must have Day button"
        assert ">Day<" in content

    def test_scope_switch_week_button(self):
        content = _read_dashboard()
        assert 'data-scope="week"' in content, \
            "Scope-switch must have Week button"
        assert ">Week<" in content

    def test_scope_switch_month_button(self):
        content = _read_dashboard()
        assert 'data-scope="month"' in content, \
            "Scope-switch must have Month button"
        assert ">Month<" in content

    def test_scope_switch_default_active(self):
        """Day button must be is-active by default."""
        content = _read_dashboard()
        # The day button should have is-active class
        assert 'data-scope="day"' in content and "is-active" in content, \
            "Day scope button must be is-active by default"


# ── TestDashboardInfoButtons ────────────────────────────────────────

class TestDashboardInfoButtons:
    """Verify info (ℹ️) buttons on each metric and chart."""

    def test_metric_info_buttons(self):
        """Each metric card must have an info button."""
        content = _read_dashboard()
        for info_key in ["projects", "sessions", "tokens", "failed-tools"]:
            assert f'data-info="{info_key}"' in content, \
                f"Dashboard must have info button for '{info_key}'"

    def test_chart_info_buttons(self):
        """Each chart card must have an info button."""
        content = _read_dashboard()
        for info_key in ["chart-sessions", "chart-tokens"]:
            assert f'data-info="{info_key}"' in content, \
                f"Dashboard must have info button for '{info_key}'"

    def test_info_button_uses_icon_button_class(self):
        """Info buttons must use icon-button--info class."""
        content = _read_dashboard()
        assert "icon-button--info" in content, \
            "Info buttons must use icon-button--info class"


# ── TestDashboardChartMenuButtons ────────────────────────────────────

class TestDashboardChartMenuButtons:
    """Verify chart-menu (⋯) buttons on each chart card."""

    def test_chart_menu_buttons_present(self):
        """Each chart card must have a chart-menu button."""
        content = _read_dashboard()
        menus = re.findall(r'data-action="chart-menu"', content)
        assert len(menus) >= 2, \
            f"Dashboard must have at least 2 chart-menu buttons, found {len(menus)}"

    def test_chart_menu_sessions(self):
        content = _read_dashboard()
        assert 'data-chart="sessions"' in content, \
            "Chart-menu button for sessions must exist"

    def test_chart_menu_tokens(self):
        content = _read_dashboard()
        assert 'data-chart="tokens"' in content, \
            "Chart-menu button for tokens must exist"

    def test_chart_menu_uses_ghost_class(self):
        """Chart-menu buttons must use icon-button--ghost class."""
        content = _read_dashboard()
        assert "icon-button--ghost" in content, \
            "Chart-menu buttons must use icon-button--ghost class"


# ── TestDashboardEmptyState ──────────────────────────────────────────

class TestDashboardEmptyState:
    """Verify empty state renders when stats.total_sessions == 0."""

    def test_empty_state_condition(self):
        content = _read_dashboard()
        assert "stats.total_sessions == 0" in content, \
            "Dashboard must check stats.total_sessions == 0 for empty state"

    def test_empty_state_uses_ui_macro(self):
        content = _read_dashboard()
        assert "ui.empty_state" in content, \
            "Empty state must use ui.empty_state macro"

    def test_empty_state_has_action_button(self):
        content = _read_dashboard()
        assert "Run Scan" in content, \
            "Empty state must have 'Run Scan' action button"


# ── TestDashboardErrorState ──────────────────────────────────────────

class TestDashboardErrorState:
    """Verify error state renders when error variable is set."""

    def test_error_state_condition(self):
        content = _read_dashboard()
        assert "{% if error %}" in content, \
            "Dashboard must check for error variable"

    def test_error_state_uses_ui_macro(self):
        content = _read_dashboard()
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro"

    def test_error_state_has_dashboard_link(self):
        content = _read_dashboard()
        assert "/dashboard" in content, \
            "Error state must link back to /dashboard"


# ── TestDashboardFloatingOverlays ────────────────────────────────────

class TestDashboardFloatingOverlays:
    """Verify floating overlay elements (tooltip, popover, drawer, toast)."""

    def test_tooltip_element(self):
        content = _read_dashboard()
        assert 'id="chartTooltip"' in content, \
            "Dashboard must have chartTooltip element"

    def test_info_popover(self):
        content = _read_dashboard()
        assert 'id="infoPopover"' in content, \
            "Dashboard must have infoPopover element"

    def test_menu_popover(self):
        content = _read_dashboard()
        assert 'id="menuPopover"' in content, \
            "Dashboard must have menuPopover element"

    def test_toast_element(self):
        content = _read_dashboard()
        assert 'id="toast"' in content, \
            "Dashboard must have toast element"

    def test_settings_drawer(self):
        content = _read_dashboard()
        assert 'id="settingsDrawer"' in content, \
            "Dashboard must have settingsDrawer element"


# ── TestDashboardNoHeroV16 ───────────────────────────────────────────

class TestDashboardNoHeroV16:
    """Verify old v16 hero section is NOT present."""

    def test_no_hero_section(self):
        content = _read_dashboard()
        assert 'class="hero"' not in content, \
            "Dashboard must not have v16 hero section"

    def test_no_hero_title(self):
        content = _read_dashboard()
        assert 'class="hero-title"' not in content, \
            "Dashboard must not have v16 hero-title"

    def test_no_hero_kpis(self):
        content = _read_dashboard()
        assert 'class="hero-kpis"' not in content, \
            "Dashboard must not have v16 hero-kpis"

    def test_no_hero_chips(self):
        content = _read_dashboard()
        assert 'class="hero-chips"' not in content, \
            "Dashboard must not have v16 hero-chips"

    def test_no_range_tabs(self):
        content = _read_dashboard()
        assert 'class="range-tabs"' not in content, \
            "Dashboard must not have v16 range-tabs"
