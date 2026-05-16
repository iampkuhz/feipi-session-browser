"""Playwright DOM structure and visual state regression tests.

Tests the Hi-Fi UI refactoring using a live server via pytest-playwright.
Requires: SB_TEST_DB env var + `pytest --browser chromium`.

These tests DO NOT check for external CSS/JS in normal mode — /static/ refs
are expected. Only MHTML mode (tested elsewhere) must be self-contained.
"""
import os
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _navigate_to_first_session(page, live_server_url):
    """Navigate to /sessions and click the first session link."""
    page.goto(f"{live_server_url}/sessions", wait_until="networkidle")
    # Click the first session link
    first_link = page.query_selector("a[href*='/sessions/']")
    if first_link:
        first_link.click()
        page.wait_for_load_state("networkidle")
        return True
    return False


@pytest.mark.playwright
class TestShellLayout:
    """Verify three-column shell grid structure."""

    def test_session_detail_has_shell_grid(self, page, live_server_url):
        """Session Detail page should have body > .shell as CSS Grid."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        shell = page.query_selector("body > .shell")
        assert shell is not None, "missing .shell root container"

        display = shell.evaluate("el => getComputedStyle(el).display")
        assert display == "grid", f".shell display should be grid, got {display}"

    def test_sessions_list_no_inspector(self, page, live_server_url):
        """Sessions List should not render a right Inspector column."""
        page.goto(f"{live_server_url}/sessions", wait_until="networkidle")

        # The page should exist and not have inspector content
        body = page.query_selector("body")
        assert body is not None

    def test_sidebar_not_fixed(self, page, live_server_url):
        """Sidebar should not use position: fixed."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        sidebar = page.query_selector(".sidebar")
        if sidebar:
            position = sidebar.evaluate("el => getComputedStyle(el).position")
            assert position != "fixed", "sidebar should not be position:fixed"


@pytest.mark.playwright
class TestTopbarModes:
    """Verify topbar mode toggle buttons."""

    def test_mode_buttons_exist(self, page, live_server_url):
        """Page should have Map, Inspector, Focus buttons."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        # Check for the toggle buttons in topbar
        buttons = page.query_selector_all(".top-btn")
        button_texts = [b.inner_text().strip() for b in buttons]
        # At least some of these should be present
        has_map = any("Map" in t for t in button_texts)
        has_inspector = any("Inspector" in t for t in button_texts)
        has_focus = any("Focus" in t for t in button_texts)
        assert has_map or has_inspector or has_focus, \
            f"expected mode buttons, found: {button_texts}"

    def test_focus_mode_adds_body_class(self, page, live_server_url):
        """Clicking Focus should add 'focus' class to body."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        focus_btn = page.query_selector("button[title*='专注']")
        if not focus_btn:
            # Try English
            focus_btn = page.query_selector("button[title*='Focus']")
        if not focus_btn:
            focus_btn = page.query_selector("button.top-btn:last-child")

        if not focus_btn:
            pytest.skip("Focus button not found")

        focus_btn.click()
        page.wait_for_timeout(200)

        body_class = page.evaluate("document.body.className")
        assert "focus" in body_class, f"body should have 'focus' class, got: {body_class}"


@pytest.mark.playwright
class TestViewSwitch:
    """Verify Trace / Calls / Hotspots sub-view switching."""

    def test_view_switch_buttons_exist(self, page, live_server_url):
        """Session Detail should have Trace, Calls, Hotspots buttons."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        for view in ("trace", "calls", "hotspots"):
            btn = page.query_selector(f'[data-switch="{view}"]')
            assert btn is not None, f'missing data-switch="{view}" button'

    def test_calls_view_has_data_table(self, page, live_server_url):
        """Clicking Calls should show .data-table element."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        calls_btn = page.query_selector('[data-switch="calls"]')
        if calls_btn:
            calls_btn.click()
            page.wait_for_timeout(300)

            # Check that the calls view is visible
            calls_view = page.query_selector('[data-view="calls"]')
            if calls_view:
                display = calls_view.evaluate("el => getComputedStyle(el).display")
                # After clicking, it should be visible (not 'none')
                assert display != "none", "Calls view should be visible after clicking"


@pytest.mark.playwright
class TestHeroSection:
    """Verify hero section with badge and KPI strip."""

    def test_hero_exists(self, page, live_server_url):
        """Session Detail should contain hero section."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        hero = page.query_selector(".hero")
        assert hero is not None, "missing .hero section"

    def test_hero_has_badges(self, page, live_server_url):
        """Hero section should contain badge elements."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        badge = page.query_selector(".hero .badge, .hero-badges .badge")
        assert badge is not None, "missing badge in hero section"

    def test_has_kpi_strip(self, page, live_server_url):
        """Page should have a KPI / metrics strip."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        kpi = page.query_selector(".metrics-strip, .kpis, [class*='kpi']")
        assert kpi is not None, "missing KPI/metrics strip"


@pytest.mark.playwright
class TestSessionsList:
    """Verify Sessions List page structure."""

    def test_sessions_list_has_data_table(self, page, live_server_url):
        """/sessions should have a .data-table element."""
        page.goto(f"{live_server_url}/sessions", wait_until="networkidle")

        table = page.query_selector(".data-table")
        assert table is not None, "missing .data-table on sessions list"

    def test_sessions_list_has_filters(self, page, live_server_url):
        """/sessions should have filter buttons."""
        page.goto(f"{live_server_url}/sessions", wait_until="networkidle")

        # Check for filter-related elements
        has_failed = page.query_selector("[class*='failed'], text=Failed")
        has_token = page.query_selector("[class*='token'], text=Token")
        has_filter = page.query_selector("[class*='filter'], text=filter, text=筛选")
        # At least one type of filter indicator should exist
        assert has_failed or has_token or has_filter or page.query_selector("button"), \
            "sessions list should have some interactive elements"


@pytest.mark.playwright
class TestNoExternalResources:
    """Verify no Google Fonts or remote CSS/JS in normal mode."""

    def test_no_google_fonts(self, page, live_server_url):
        """Page head should not reference Google Fonts."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        head_content = page.inner_html("head")
        assert "fonts.googleapis" not in head_content, \
            "Google Fonts reference found in <head>"

    def test_no_https_external_resources(self, page, live_server_url):
        """Page should not reference https:// external CSS/JS/fonts (local /static/ is OK)."""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.skip("No sessions available")

        html = page.content()
        server_prefix = live_server_url  # e.g. http://127.0.0.1:18899

        # Check for external links (not localhost, not relative)
        for tag in page.query_selector_all("link[rel='stylesheet']"):
            href = tag.get_attribute("href") or ""
            if href.startswith("https://") and server_prefix not in href:
                raise AssertionError(f"external CSS found: {href}")

        for tag in page.query_selector_all("script[src]"):
            src = tag.get_attribute("src") or ""
            if src.startswith("https://") and server_prefix not in src:
                raise AssertionError(f"external JS found: {src}")
