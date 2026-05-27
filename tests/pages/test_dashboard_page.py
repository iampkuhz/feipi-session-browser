"""Dashboard page-level fixture tests.

These tests use the hifi_fixture_session to spin up a live server with
deterministic fixture data, then verify the *rendered* Dashboard HTML
(not just the static template file).

Covers:
- Page renders and returns HTTP 200
- Key data/metrics are visible (stats values > 0)
- All metric cards present with populated values
- Chart containers rendered with JSON data
- Scope switch UI present
- Overlays (tooltip, popover, toast) present
- No inline onclick (accessibility gate)

T092 — Dashboard fixed fixture.
"""

from __future__ import annotations

import pytest
import json
import re

# ── Dashboard page fixture ────────────────────────────────────────────


@pytest.fixture(scope="module")
def dashboard_html(hifi_fixture_session):
    """Fetch rendered dashboard HTML from the live fixture server."""
    base_url, agent, session_id = hifi_fixture_session
    import urllib.request

    resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=10)
    assert resp.status == 200, "Dashboard must return HTTP 200"
    return resp.read().decode("utf-8")


# ── TestDashboardPageRender ──────────────────────────────────────────


class TestDashboardPageRender:
    """Verify the rendered dashboard page structure."""

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-003")
    def test_page_returns_200(self, dashboard_html):
        """Dashboard must render successfully."""
        assert len(dashboard_html) > 500, \
            "Dashboard HTML must be substantial"

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-006")
    def test_has_doctype_and_html(self, dashboard_html):
        """Page must have proper HTML structure."""
        assert "<!doctype html" in dashboard_html.lower() or "<!DOCTYPE html" in dashboard_html, \
            "Dashboard must have DOCTYPE declaration"

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-007")
    def test_title_contains_dashboard(self, dashboard_html):
        """Page title must contain 'Dashboard'."""
        assert "<title>Dashboard" in dashboard_html, \
            "Page title must contain 'Dashboard'"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_has_h1_dashboard(self, dashboard_html):
        """Page must have a visible 'Dashboard' heading."""
        # Could be in an h1 or in the page-head component
        assert "Dashboard" in dashboard_html, \
            "Dashboard text must appear in rendered page"

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-008")
    def test_has_subtitle(self, dashboard_html):
        """Page must show the subtitle."""
        assert "Local agent session overview" in dashboard_html, \
            "Subtitle 'Local agent session overview' must appear"


# ── TestDashboardMetrics ─────────────────────────────────────────────


class TestDashboardMetrics:
    """Verify rendered metric cards with actual data values."""

    _METRIC_LABELS = ["Projects", "Sessions", "Total Tokens", "Failed Tools"]

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-001")
    def test_metric_grid_present(self, dashboard_html):
        """Dashboard must have a metric-grid container."""
        assert 'class="metric-grid"' in dashboard_html, \
            "metric-grid must be present"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_four_metric_cards(self, dashboard_html):
        """Exactly 4 metric cards must be rendered."""
        cards = re.findall(r'class="metric-card"', dashboard_html)
        assert len(cards) == 4, \
            f"Expected 4 metric cards, found {len(cards)}"

    @pytest.mark.parametrize("label", ["Projects", "Sessions", "Total Tokens", "Failed Tools"])
    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_label_present(self, dashboard_html, label):
        """Each metric card must show its label."""
        assert f">{label}<" in dashboard_html or f'aria-label="{label}"' in dashboard_html, \
            f"Metric card labeled '{label}' must be visible"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_values_nonzero(self, dashboard_html):
        """Metric cards must have populated values (not zero when fixture has data)."""
        # Extract values from metric-card__value elements
        values = re.findall(
            r'class="metric-card__value">([^<]+)<',
            dashboard_html
        )
        assert len(values) == 4, \
            f"Expected 4 metric values, found {len(values)}"

        # Parse and verify at least Projects and Sessions have positive counts
        projects_val = values[0].strip().replace(",", "")
        sessions_val = values[1].strip().replace(",", "")

        assert projects_val.isdigit() and int(projects_val) > 0, \
            f"Projects count must be > 0, got '{projects_val}'"
        assert sessions_val.isdigit() and int(sessions_val) > 0, \
            f"Sessions count must be > 0, got '{sessions_val}'"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_aria_labels(self, dashboard_html):
        """Each metric card must have an aria-label for accessibility."""
        for label in self._METRIC_LABELS:
            assert f'aria-label="{label}"' in dashboard_html, \
                f"Metric card '{label}' must have aria-label"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_has_info_buttons(self, dashboard_html):
        """Each metric card must have an info button."""
        for info_key in ["projects", "sessions", "tokens", "failed-tools"]:
            assert f'data-info="{info_key}"' in dashboard_html, \
                f"Dashboard must have info button for '{info_key}'"


# ── TestDashboardCharts ──────────────────────────────────────────────


class TestDashboardCharts:
    """Verify rendered chart cards and embedded data."""

    _CHART_TITLES = ["Session Trend", "Token Trend", "Prompt Activity Trend"]

    @pytest.mark.parametrize("title", ["Session Trend", "Token Trend", "Prompt Activity Trend"])
    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_title_present(self, dashboard_html, title):
        """Each chart card must show its title."""
        assert title in dashboard_html, \
            f"Chart '{title}' must be present"

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-005")
    def test_chart_containers_rendered(self, dashboard_html):
        """Charts must have dedicated container elements."""
        containers = re.findall(r'data-dashboard-chart', dashboard_html)
        assert len(containers) >= 2, \
            f"Expected at least 2 chart containers, found {len(containers)}"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_json_data_embedded(self, dashboard_html):
        """Dashboard must embed chart data as JSON."""
        # Look for the script tag with chart data
        assert 'id="dashboard-chart-data"' in dashboard_html, \
            "Dashboard must embed chart JSON data"
        assert 'id="dashboard-prompt-data"' in dashboard_html, \
            "Dashboard must embed prompt activity JSON data"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_json_parseable(self, dashboard_html):
        """Embedded chart JSON must be valid JSON."""
        match = re.search(
            r'id="dashboard-chart-data">(\[.*?\])</script>',
            dashboard_html,
            re.DOTALL,
        )
        assert match, "Chart data script must contain a JSON array"
        data = json.loads(match.group(1))
        assert isinstance(data, list), "Chart data must be a list"
        assert len(data) > 0, "Chart data must not be empty when fixture has sessions"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_has_legend(self, dashboard_html):
        """Charts must display a legend."""
        # The chart_legend macro renders a legend-row div with legend-item spans
        assert 'class="legend-row"' in dashboard_html or "legend-row" in dashboard_html, \
            "Dashboard must render chart legend"
        assert "Claude Code" in dashboard_html, \
            "Chart legend must include Claude Code"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_subtitles(self, dashboard_html):
        """Each chart must have a subtitle."""
        subtitles = [
            "Daily session count by agent",
            "Daily token usage by agent",
            "Daily user-initiated inputs by agent",
        ]
        for sub in subtitles:
            assert sub in dashboard_html, \
                f"Chart subtitle '{sub}' must be present"


# ── TestDashboardScopeSwitch ─────────────────────────────────────────


class TestDashboardScopeSwitch:
    """Verify scope-switch UI is rendered."""

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-002")
    def test_scope_switch_present(self, dashboard_html):
        """Dashboard must render scope switch controls."""
        assert 'data-scope="day"' in dashboard_html, \
            "Day scope button must be present"
        assert 'data-scope="week"' in dashboard_html, \
            "Week scope button must be present"
        assert 'data-scope="month"' in dashboard_html, \
            "Month scope button must be present"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_scope_button_labels(self, dashboard_html):
        """Scope buttons must show correct labels."""
        for label in ["Day", "Week", "Month"]:
            assert f">{label}<" in dashboard_html, \
                f"Scope button '{label}' must be visible"


# ── TestDashboardOverlays ────────────────────────────────────────────


class TestDashboardOverlays:
    """Verify floating overlay elements."""

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-004")
    def test_tooltip_present(self, dashboard_html):
        """Chart tooltip element must exist."""
        assert 'id="chartTooltip"' in dashboard_html, \
            "chartTooltip element must be present"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_popover_present(self, dashboard_html):
        """Info popover element must exist."""
        assert 'id="infoPopover"' in dashboard_html, \
            "infoPopover element must be present"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_toast_present(self, dashboard_html):
        """Toast notification element must exist."""
        assert 'id="toast"' in dashboard_html, \
            "toast element must be present"


# ── TestDashboardAccessibility ───────────────────────────────────────


class TestDashboardAccessibility:
    """Accessibility gates on the rendered dashboard."""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_no_inline_onclick(self, dashboard_html):
        """Dashboard must not use inline onclick handlers."""
        matches = re.findall(r'\bonclick\s*=', dashboard_html, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Dashboard must not have inline onclick, found {len(matches)} occurrences"
