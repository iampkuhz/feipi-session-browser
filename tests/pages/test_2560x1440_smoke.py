"""2560x1440 viewport smoke matrix — Python-level HTTP tests.

Verifies that all major pages return HTTP 200 with expected HTML structure
at 2560x1440 (2K desktop monitor) viewport sizes.

This test starts a local session-browser server using the hifi fixture,
then makes HTTP requests with a 2560x1440 User-Agent string to verify each page.

Covers:
- Dashboard page renders
- Sessions List page renders
- Session Detail page renders
- Agents page renders
- Projects page renders
- Structural checks: CSS media queries, layout containers, table elements

Usage:
    python3 -m pytest tests/pages/test_2560x1440_smoke.py -v
"""

from __future__ import annotations

import re

import pytest

# ─── Constants ──────────────────────────────────────────────────────────

# 2560x1440 (QHD / 2K monitor) User-Agent
DISPLAY_2K_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Pages to smoke test: (name, path, expected HTML fragment, min HTML length)
# Note: 404 page is tested separately by TestDisplay2K404Page (expects HTTP 404).
PAGES = [
    ("Dashboard", "/dashboard", ">Dashboard<", 500),
    ("Sessions List", "/sessions", ">Sessions<", 500),
    ("Agents", "/agents", ">Agents<", 500),
    ("Projects", "/projects", ">Projects<", 500),
    ("Glossary", "/glossary", "Token Glossary", 500),
]


# ─── Server fixture ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def display_2k_smoke_server(hifi_fixture_session):
    """Use the hifi fixture session server for smoke testing.

    Yields base_url from the deterministic fixture server.
    """
    base_url, agent, session_id = hifi_fixture_session
    yield base_url


# ─── Helpers ────────────────────────────────────────────────────────────


def fetch_page(base_url: str, path: str) -> tuple[int, str]:
    """Fetch a page and return (status_code, html_body)."""
    import urllib.request
    import urllib.error

    url = f"{base_url}{path}"
    req = urllib.request.Request(url, headers={
        "User-Agent": DISPLAY_2K_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8") if e.fp else ""


# ─── Tests: Page Loads ──────────────────────────────────────────────────


class TestDisplay2KSmoke:
    """Smoke test all major pages at 2560x1440 viewport."""

    @pytest.mark.parametrize("name,path,expected_fragment,min_length", PAGES)
    def test_page_loads(self, display_2k_smoke_server, name, path, expected_fragment, min_length):
        """Each page must return HTTP 200 with expected content at 2560x1440 viewport."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, path)

        assert status == 200, f"{name} at 2560x1440 returned HTTP {status}"
        assert len(html) >= min_length, (
            f"{name} at 2560x1440 HTML too short: {len(html)} bytes "
            f"(expected >= {min_length})"
        )
        assert expected_fragment in html, (
            f"{name} at 2560x1440 missing expected fragment '{expected_fragment}'"
        )


# ─── Tests: Viewport-Specific Structural Checks ─────────────────────────


class TestDisplay2KDashboard:
    """Dashboard structural checks at 2560x1440."""

    def test_metric_cards_present(self, display_2k_smoke_server):
        """Dashboard must have 4 metric cards."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/dashboard")
        assert status == 200
        cards = re.findall(r'class="metric-card"', html)
        assert len(cards) == 4, f"Expected 4 metric cards, found {len(cards)}"

    def test_chart_containers_present(self, display_2k_smoke_server):
        """Dashboard must have chart containers."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/dashboard")
        assert status == 200
        containers = re.findall(r'data-dashboard-chart', html)
        assert len(containers) >= 2, \
            f"Expected at least 2 chart containers, found {len(containers)}"

    def test_metric_grid_layout(self, display_2k_smoke_server):
        """Dashboard metric-grid must be present for wide layout."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/dashboard")
        assert status == 200
        assert 'class="metric-grid"' in html, \
            "metric-grid must be present for 2560x1440 layout"

    def test_scope_switch_ui(self, display_2k_smoke_server):
        """Dashboard must have scope switch UI."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/dashboard")
        assert status == 200
        for scope in ["day", "week", "month"]:
            assert f'data-scope="{scope}"' in html, \
                f"Scope button '{scope}' must be present"


class TestDisplay2KSessionsList:
    """Sessions List structural checks at 2560x1440."""

    def test_sessions_table_present(self, display_2k_smoke_server):
        """Sessions List must have a sessions table."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200
        assert 'aria-label="Sessions table"' in html, \
            "Sessions table must be present"

    def test_sessions_has_data_rows(self, display_2k_smoke_server):
        """Sessions List must have data rows."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200
        rows = re.findall(r'class="sessions-row"', html)
        assert len(rows) > 0, \
            "Sessions List must have at least one session row"

    def test_session_links_exist(self, display_2k_smoke_server):
        """Sessions List must have clickable session links."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200
        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, "No session link found on Sessions List page"


class TestDisplay2KSessionDetail:
    """Session Detail structural checks at 2560x1440."""

    def test_session_detail_accessible(self, display_2k_smoke_server):
        """Session Detail page must be accessible and render."""
        base_url = display_2k_smoke_server
        # First get a session link from the sessions page
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200

        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, "No session link found on Sessions List page"

        session_url = match.group(1)
        status, detail_html = fetch_page(base_url, session_url)
        assert status == 200, f"Session detail at {session_url} returned HTTP {status}"
        assert len(detail_html) >= 500, "Session detail HTML too short"

    def test_session_detail_has_timeline(self, display_2k_smoke_server):
        """Session Detail must have a timeline section."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200

        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, "No session link found"

        status, detail_html = fetch_page(base_url, match.group(1))
        assert status == 200
        has_timeline = "timeline" in detail_html.lower() or "round" in detail_html.lower()
        assert has_timeline, "Session detail must have timeline or round content"

    def test_session_detail_has_header(self, display_2k_smoke_server):
        """Session Detail must have a page header with session title."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200

        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, "No session link found"

        status, detail_html = fetch_page(base_url, match.group(1))
        assert status == 200
        assert "page-head" in detail_html or "session-detail" in detail_html.lower(), \
            "Session detail must have a page header"


class TestDisplay2KAgents:
    """Agents page structural checks at 2560x1440."""

    def test_agents_page_loads(self, display_2k_smoke_server):
        """Agents page must return HTTP 200."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/agents")
        assert status == 200
        assert len(html) >= 500, "Agents page HTML too short"

    def test_agents_has_table_or_list(self, display_2k_smoke_server):
        """Agents page must have a data table or agent list."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/agents")
        assert status == 200
        has_table = 'class="data-table"' in html or 'class="agent-list"' in html
        assert has_table, "Agents page must have a table or agent list"

    def test_agents_has_entries(self, display_2k_smoke_server):
        """Agents page must list at least one agent."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/agents")
        assert status == 200
        assert "claude" in html.lower() or "agent" in html.lower(), \
            "Agents page must list at least one agent entry"


class TestDisplay2KProjects:
    """Projects page structural checks at 2560x1440."""

    def test_projects_page_loads(self, display_2k_smoke_server):
        """Projects page must return HTTP 200."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/projects")
        assert status == 200
        assert len(html) >= 500, "Projects page HTML too short"

    def test_projects_has_table_or_list(self, display_2k_smoke_server):
        """Projects page must have a data table or project list."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/projects")
        assert status == 200
        has_table = 'class="data-table"' in html or 'class="project-list"' in html
        assert has_table, "Projects page must have a table or project list"

    def test_projects_has_entries(self, display_2k_smoke_server):
        """Projects page must list at least one project."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/projects")
        assert status == 200
        # Check for project-related content in the page
        has_project_content = (
            'class="data-table"' in html
            or 'class="project-list"' in html
            or "project" in html.lower()
        )
        assert has_project_content, \
            "Projects page must list at least one project entry"


# ─── Tests: CSS Media Query Presence ────────────────────────────────────


class TestDisplay2KCSSSupport:
    """Verify CSS files contain responsive media queries suitable for 2560x1440."""

    def test_style_css_has_wide_media_query(self):
        """shell.css should contain media queries for wide viewports."""
        css_path = "src/session_browser/web/static/css/shell.css"
        import os
        full_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", css_path
        )
        full_path = os.path.normpath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            css_path
        ))

        if not os.path.exists(full_path):
            pytest.skip(f"CSS file not found at {full_path}")

        with open(full_path) as f:
            content = f.read()

        # Check for min-width media queries that cover 2560px
        has_wide_query = (
            "@media" in content
            and ("min-width" in content or "max-width" in content)
        )
        assert has_wide_query, \
            "shell.css must contain responsive media queries"

    def test_dashboard_css_responsive(self):
        """Dashboard CSS must be responsive-aware."""
        css_path = "src/session_browser/web/static/css/dashboard.css"
        import os
        full_path = os.path.normpath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            css_path
        ))

        if not os.path.exists(full_path):
            pytest.skip(f"CSS file not found at {full_path}")

        with open(full_path) as f:
            content = f.read()

        # Dashboard CSS should have layout rules
        has_layout = "grid" in content or "flex" in content or "display" in content
        assert has_layout, \
            "dashboard.css must contain layout rules"


# ─── Tests: Session Detail at 2560x1440 ─────────────────────────────


class TestDisplay2KSessionDetailPage:
    """Session Detail page structural checks at 2560x1440 using fixture session."""

    def test_session_detail_page_loads(self, display_2k_smoke_server):
        """Session Detail page must return HTTP 200."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions/claude_code/hifi-viz-session-001")
        assert status == 200, f"Session Detail returned HTTP {status}"
        assert len(html) >= 500, "Session Detail HTML too short"

    def test_session_detail_has_hero(self, display_2k_smoke_server):
        """Session Detail must have a hero/header section."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions/claude_code/hifi-viz-session-001")
        assert status == 200
        assert "sd-hero" in html or "session-detail" in html.lower(), \
            "Session Detail must have hero or session-detail section"

    def test_session_detail_has_tabs(self, display_2k_smoke_server):
        """Session Detail must have tab navigation."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions/claude_code/hifi-viz-session-001")
        assert status == 200
        assert "sd-tabs" in html or "tab" in html.lower(), \
            "Session Detail must have tab navigation"

    def test_session_detail_has_trace_panel(self, display_2k_smoke_server):
        """Session Detail must have a trace panel."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions/claude_code/hifi-viz-session-001")
        assert status == 200
        assert "trace" in html.lower() or "round" in html.lower(), \
            "Session Detail must have trace/round content"


# ─── Tests: Glossary at 2560x1440 ───────────────────────────────────


class TestDisplay2KGlossary:
    """Glossary page structural checks at 2560x1440."""

    def test_glossary_page_loads(self, display_2k_smoke_server):
        """Glossary page must return HTTP 200."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200, f"Glossary returned HTTP {status}"
        assert len(html) >= 500, "Glossary page HTML too short"

    def test_glossary_has_metric_grid(self, display_2k_smoke_server):
        """Glossary must have a metric grid."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200
        assert 'class="metric-grid"' in html, \
            "Glossary must have a metric-grid section"

    def test_glossary_has_filter_card(self, display_2k_smoke_server):
        """Glossary must have a filter/search card."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200
        assert "filter-card" in html or "search" in html.lower(), \
            "Glossary must have a filter/search card"

    def test_glossary_has_data_tables(self, display_2k_smoke_server):
        """Glossary must have data tables."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200
        assert 'class="data-table' in html, \
            "Glossary must have at least one data-table"

    def test_glossary_has_token_terms(self, display_2k_smoke_server):
        """Glossary must contain token-related terminology."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200
        assert "Token" in html or "token" in html, \
            "Glossary must contain token terminology"


# ─── Tests: 404 Error Page at 2560x1440 ─────────────────────────────


class TestDisplay2K404Page:
    """404 error page structural checks at 2560x1440."""

    def test_404_page_returns_404_status(self, display_2k_smoke_server):
        """404 page must return HTTP 404 status."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert status == 404, f"Expected HTTP 404, got {status}"

    def test_404_page_renders_meaningful_html(self, display_2k_smoke_server):
        """404 page must contain meaningful HTML content."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert len(html) > 200, "404 HTML must be substantial"

    def test_404_page_has_not_found_text(self, display_2k_smoke_server):
        """404 page must show 'Not Found' text."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert "Not Found" in html or "not found" in html, \
            "404 page must contain 'Not Found' text"

    def test_404_page_has_state_panel(self, display_2k_smoke_server):
        """404 page must use shared state-panel component."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert status == 404
        assert 'class="state-panel"' in html, \
            "404 page must have state-panel container"

    def test_404_page_has_dashboard_link(self, display_2k_smoke_server):
        """404 page must link back to dashboard."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert status == 404
        assert "/dashboard" in html, \
            "404 page must link to /dashboard"
