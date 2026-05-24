"""Error page fixture tests.

Verify the 404 and 500 error pages render correctly, display error
messages, and provide navigation links back to the dashboard.

Covers:
- 404 page renders and returns HTTP 404
- 500 page template renders with and without error context
- Error message display in the error template
- Return-to-dashboard links present on both pages
- Shared state-panel structure and CSS references

T098 -- Error page fixture.
"""

from __future__ import annotations

import os
import re
import urllib.request
import urllib.error

import pytest

# ── Paths ─────────────────────────────────────────────────────────────

SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(SB_ROOT, "src", "session_browser", "web", "templates")


# ── 404 page fixture (live server) ────────────────────────────────────


@pytest.fixture(scope="module")
def error_404_response(hifi_fixture_session):
    """Fetch a non-existent URL and capture the HTTP response."""
    base_url, agent, session_id = hifi_fixture_session
    url = f"{base_url}/__nonexistent_test_path_xyz__"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


# ── Error template rendering helpers ──────────────────────────────────


def _render_error_template(error: str | None = None) -> str:
    """Render error.html via Jinja2 (with autoescape) and return the HTML string."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
    )
    template = env.get_template("error.html")
    return template.render(error=error)


def _render_404_template() -> str:
    """Render 404.html via Jinja2 (with autoescape) and return the HTML string."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
    )
    template = env.get_template("404.html")
    return template.render()


# ── Test404Page ───────────────────────────────────────────────────────


class Test404Page:
    """Verify the 404 Not Found page renders and has correct structure."""

    def test_returns_404_status(self, error_404_response):
        """Request to an unknown path must return HTTP 404."""
        status, html = error_404_response
        assert status == 404, f"Expected HTTP 404, got {status}"

    def test_page_renders_substantial_html(self, error_404_response):
        """404 page must contain meaningful HTML content."""
        _, html = error_404_response
        assert len(html) > 200, "404 HTML must be substantial"

    def test_has_doctype(self, error_404_response):
        """404 page must have proper DOCTYPE declaration."""
        _, html = error_404_response
        assert "<!doctype html" in html.lower(), "404 page must have DOCTYPE"

    def test_title_contains_not_found(self, error_404_response):
        """Page title must indicate 'Not Found'."""
        _, html = error_404_response
        assert "Not Found" in html, "404 title must contain 'Not Found'"

    def test_has_404_icon(self, error_404_response):
        """Page must display the 404 icon."""
        _, html = error_404_response
        assert ">404<" in html or "404" in html, "404 icon must be visible"

    def test_has_page_not_found_text(self, error_404_response):
        """Page must show 'Page Not Found' heading."""
        _, html = error_404_response
        assert "Page Not Found" in html, "404 page must show 'Page Not Found'"

    def test_has_description(self, error_404_response):
        """Page must show a description of the error."""
        _, html = error_404_response
        assert "doesn't exist" in html or "has been removed" in html, \
            "404 page must describe the error"

    def test_has_state_panel_structure(self, error_404_response):
        """404 page must use the shared state-panel component."""
        _, html = error_404_response
        assert 'class="state-panel"' in html, "404 page must have state-panel container"
        assert 'role="status"' in html, "404 page must have role=status"

    def test_has_states_css_reference(self, error_404_response):
        """404 page must reference the states.css stylesheet."""
        _, html = error_404_response
        assert "states.css" in html, "404 page must reference states.css"


# ── Test404Template ───────────────────────────────────────────────────


class Test404Template:
    """Verify the 404 template directly (no server needed)."""

    def test_template_renders(self):
        """404.html must render without errors."""
        html = _render_404_template()
        assert len(html) > 100, "404 template must produce HTML"

    def test_has_dashboard_link(self):
        """404 page must contain a link back to Dashboard."""
        html = _render_404_template()
        assert '/dashboard' in html, "404 page must link to /dashboard"
        assert "Dashboard" in html, "404 page must show 'Dashboard' link text"

    def test_has_navigation_links(self):
        """404 page must offer multiple navigation options."""
        html = _render_404_template()
        nav_links = ["/dashboard", "/projects", "/sessions", "/agents"]
        for link in nav_links:
            assert link in html, f"404 page must link to {link}"

    def test_has_state_panel_links(self):
        """404 page navigation links must use state-panel__link class."""
        html = _render_404_template()
        assert 'class="state-panel__link"' in html, \
            "404 page must use state-panel__link for nav links"

    def test_has_breadcrumb(self):
        """404 page must render a breadcrumb."""
        html = _render_404_template()
        assert "sep" in html, "404 page must have breadcrumb separator"
        assert "current" in html, "404 page must mark current breadcrumb item"


# ── Test500ErrorPage ──────────────────────────────────────────────────


class Test500ErrorPage:
    """Verify the 500 error page template renders correctly."""

    def test_template_renders_without_error(self):
        """Error page must render even without an error message."""
        html = _render_error_template(error=None)
        assert len(html) > 100, "Error template must produce HTML"

    def test_template_renders_with_error(self):
        """Error page must render with an error message."""
        html = _render_error_template(error="Test error message")
        assert len(html) > 100, "Error template must produce HTML with error"

    def test_title_contains_error(self):
        """Page title must indicate an error."""
        html = _render_error_template()
        assert "Error" in html, "Error page title must contain 'Error'"

    def test_has_something_went_wrong_text(self):
        """Page must show 'Something Went Wrong' heading."""
        html = _render_error_template()
        assert "Something Went Wrong" in html, \
            "Error page must show 'Something Went Wrong'"

    def test_has_description(self):
        """Error page must show a description of the issue."""
        html = _render_error_template()
        assert "unexpected error" in html.lower() or "An unexpected error" in html, \
            "Error page must describe the issue"

    def test_has_state_panel_structure(self):
        """Error page must use the shared state-panel component."""
        html = _render_error_template()
        assert 'class="state-panel"' in html, "Error page must have state-panel container"
        assert 'role="alert"' in html, "Error page must have role=alert"
        assert 'aria-live="assertive"' in html, "Error page must have aria-live=assertive"

    def test_has_error_icon(self):
        """Error page must display an error icon."""
        html = _render_error_template()
        assert 'state-panel__icon--error' in html, \
            "Error page must have error icon modifier class"

    def test_has_states_css_reference(self):
        """Error page must reference the states.css stylesheet."""
        html = _render_error_template()
        assert "states.css" in html, "Error page must reference states.css"


# ── TestErrorMessageDisplay ──────────────────────────────────────────


class TestErrorMessageDisplay:
    """Verify error messages are displayed correctly."""

    def test_error_message_shown_in_details(self):
        """Error message must appear in a details/summary block."""
        html = _render_error_template(error="Database connection failed")
        assert "Database connection failed" in html, \
            "Error message must be rendered in the page"
        assert "<details" in html, "Error details must be in a <details> element"
        assert "<summary>" in html, "Error details must have a <summary> label"
        assert "Error details" in html, "Summary must say 'Error details'"

    def test_error_in_pre_tag(self):
        """Error message must be wrapped in a <pre> tag for readability."""
        html = _render_error_template(error="Traceback: line 42")
        assert "<pre" in html, "Error text must be in a <pre> block"
        assert "Traceback: line 42" in html, \
            "Error message text must appear verbatim"

    def test_no_error_details_when_none(self):
        """Error details block must be hidden when no error is provided."""
        html = _render_error_template(error=None)
        # Jinja2 {% if error %} should suppress the block entirely
        assert "<details" not in html, \
            "Error details block must not render when error is None"
        # Note: <pre> and <script> come from the base template (payload modal, JS),
        # so we only check for the error-specific <details> element.

    def test_html_escaped_in_error(self):
        """Error message containing HTML should be escaped in the output."""
        html = _render_error_template(error="<script>alert('xss')</script>")
        # Jinja2 auto-escapes; the injected <script> should not appear as raw HTML.
        # Instead it should appear as &lt;script&gt; within the pre/details block.
        # Note: other <script> tags come from the base template JS includes,
        # so we check that our specific XSS payload is escaped.
        assert "&lt;script&gt;" in html, \
            "Error message must HTML-escape script tags"
        # The raw unescaped <script>alert should NOT be present in the error area
        assert "<script>alert" not in html, \
            "Error message must not contain unescaped script tag"


# ── TestReturnToDashboard ─────────────────────────────────────────────


class TestReturnToDashboard:
    """Verify both error pages provide a link back to the dashboard."""

    def test_404_has_dashboard_link(self):
        """404 page must have a link back to Dashboard."""
        html = _render_404_template()
        assert '/dashboard' in html, "404 page must link to /dashboard"
        # Verify it looks like a proper navigation link
        assert 'class="state-panel__link"' in html, \
            "404 dashboard link must use state-panel__link class"

    def test_500_has_dashboard_link(self):
        """500 error page must have a link back to Dashboard."""
        html = _render_error_template()
        assert '/dashboard' in html, "Error page must link to /dashboard"
        assert 'class="state-panel__link"' in html, \
            "Error dashboard link must use state-panel__link class"
        assert "Dashboard" in html, "Error page must show 'Dashboard' link text"

    def test_404_has_back_arrow(self):
        """404 page dashboard link should have a back arrow indicator."""
        html = _render_404_template()
        # &larr; renders as the left arrow
        assert "&larr;" in html or "←" in html, \
            "404 page should have a back arrow on the Dashboard link"

    def test_500_has_back_arrow(self):
        """500 error page dashboard link should have a back arrow indicator."""
        html = _render_error_template()
        assert "&larr;" in html or "←" in html, \
            "Error page should have a back arrow on the Dashboard link"
