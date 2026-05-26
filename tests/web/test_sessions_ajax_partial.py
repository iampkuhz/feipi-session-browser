"""T017 · Sessions AJAX partial structure gate.

Verifies that /sessions with X-Requested-With: XMLHttpRequest returns an HTML
partial containing the expected structural markers (#sessions-ajax-response,
tbody, #ajax-pagination, page input).

See S-09: session list next jumps from page 1 to page 3 with empty page.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest
from bs4 import BeautifulSoup

from session_browser.web.template_env import env as _template_env


# ─── Mock session row ──────────────────────────────────────────────────

def _make_mock_session(
    index: int = 1,
    agent: str = "claude_code",
    session_id: str = None,
    title: str = None,
) -> MagicMock:
    """Create a mock session object matching the template's attribute access."""
    if session_id is None:
        session_id = f"sess-000000-{index:04d}"
    if title is None:
        title = f"Test Session {index}"
    m = MagicMock()
    m.agent = agent
    m.session_id = session_id
    m.title = title
    m.model = "sonnet-4-20250514"
    m.project_key = f"proj-{index}"
    m.project_name = f"Project {index}"
    m.cwd = f"/home/user/projects/proj-{index}"
    m.git_branch = "main"
    m.input_tokens = 1000 * index
    m.cached_input_tokens = 500 * index
    m.cached_output_tokens = 200 * index
    m.output_tokens = 300 * index
    m.assistant_message_count = 10 * index
    m.tool_call_count = 5 * index
    m.duration_seconds = 60.0 * index
    m.ended_at = f"2026-05-26T{10 + index:02d}:00:00+00:00"
    return m


# ─── Default AJAX context ──────────────────────────────────────────────

def _make_ajax_context(
    sessions: list = None,
    page: int = 2,
    page_size: int = 20,
    total_count: int = 60,
    total_pages: int = 3,
) -> dict:
    """Build the context dict that routes.py passes to the AJAX partial template."""
    if sessions is None:
        sessions = [_make_mock_session(i) for i in range(1, page_size + 1)]

    # Minimal actions mock — templates access .remove_filter_urls and .sort_urls
    actions = MagicMock()
    actions.remove_filter_urls = {}
    actions.sort_urls = {"tokens": "/sessions?sort=tokens", "rounds": "/sessions?sort=rounds",
                         "tools": "/sessions?sort=tools", "duration": "/sessions?sort=duration",
                         "updated": "/sessions?sort=updated"}

    return {
        "sessions": sessions,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "page_start": (page - 1) * page_size + 1,
        "page_end": min(page * page_size, total_count),
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "sort_key": "updated",
        "sort_dir": "desc",
        "actions": actions,
        "filter_q": "",
        "filter_agent": "",
        "filter_model": "",
        "filter_project": "",
    }


# ─── Tests ─────────────────────────────────────────────────────────────

class TestSessionsAjaxPartialStructure:
    """Render sessions_ajax_page.html and assert structural markers."""

    def _render_ajax(self, **overrides) -> str:
        ctx = _make_ajax_context(**overrides)
        return _template_env.get_template("partials/sessions_ajax_page.html").render(**ctx)

    def test_outer_wrapper_exists(self):
        html = self._render_ajax()
        soup = BeautifulSoup(html, "html.parser")
        wrapper = soup.find(id="sessions-ajax-response")
        assert wrapper is not None, "Missing #sessions-ajax-response wrapper"

    def test_tbody_exists(self):
        html = self._render_ajax()
        soup = BeautifulSoup(html, "html.parser")
        tbody = soup.find("tbody")
        assert tbody is not None, "Missing <tbody> in AJAX partial"

    def test_pagination_exists(self):
        html = self._render_ajax()
        soup = BeautifulSoup(html, "html.parser")
        pagination = soup.find(id="ajax-pagination")
        assert pagination is not None, "Missing #ajax-pagination in AJAX partial"

    def test_tbody_has_rows(self):
        html = self._render_ajax()
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find("tbody").find_all("tr")
        assert len(rows) >= 1, "Expected at least 1 row in tbody"

    def test_page_input_value_matches_requested_page(self):
        """Page 2 AJAX response: page input should show 2."""
        html = self._render_ajax(page=2, total_count=60, total_pages=3)
        soup = BeautifulSoup(html, "html.parser")
        # The pagination macro renders a page input — look for the input
        # with value matching the current page inside #ajax-pagination
        pagination = soup.find(id="ajax-pagination")
        assert pagination is not None
        inputs = pagination.find_all("input")
        page_inputs = [i for i in inputs if i.get("type") == "text" or i.get("type") == "number" or (i.get("value") and i.get("value").isdigit())]
        assert len(page_inputs) >= 1, "No page input found in pagination"
        # The primary page input should have value == current page
        # (may have hidden inputs too; filter by presence of numeric value)
        found_page_2 = any(
            inp.get("value") == "2"
            for inp in page_inputs
        )
        assert found_page_2, (
            f"Page input value should be 2, found values: {[i.get('value') for i in page_inputs]}"
        )

    def test_page_input_value_page_3(self):
        """Page 3 AJAX response: page input should show 3."""
        html = self._render_ajax(page=3, total_count=100, total_pages=5)
        soup = BeautifulSoup(html, "html.parser")
        pagination = soup.find(id="ajax-pagination")
        assert pagination is not None
        inputs = pagination.find_all("input")
        page_inputs = [i for i in inputs if i.get("value") and i.get("value").isdigit()]
        found_page_3 = any(inp.get("value") == "3" for inp in page_inputs)
        assert found_page_3, (
            f"Page input value should be 3, found values: {[i.get('value') for i in page_inputs]}"
        )


class TestSessionsAjaxPartialEmptyState:
    """AJAX partial when no sessions exist."""

    def test_empty_tbody_shows_message(self):
        html = _template_env.get_template("partials/sessions_ajax_page.html").render(
            **_make_ajax_context(sessions=[], total_count=0, total_pages=1)
        )
        soup = BeautifulSoup(html, "html.parser")
        tbody = soup.find("tbody")
        assert tbody is not None
        # Empty state should contain a text message about no sessions
        text = tbody.get_text()
        assert "no sessions" in text.lower() or "no sessions" in text.lower(), (
            f"Empty tbody should show 'no sessions' message, got: {text[:200]}"
        )

    def test_empty_has_no_pagination_div(self):
        """When total_count=0, no #ajax-pagination div should render."""
        html = _template_env.get_template("partials/sessions_ajax_page.html").render(
            **_make_ajax_context(sessions=[], total_count=0, total_pages=1)
        )
        soup = BeautifulSoup(html, "html.parser")
        pagination = soup.find(id="ajax-pagination")
        assert pagination is None, (
            "Expected no #ajax-pagination when total_count=0"
        )


class TestSessionsAjaxPartialMultiPage:
    """AJAX partial with multiple pages of sessions."""

    def test_page_2_has_20_rows(self):
        sessions = [_make_mock_session(i) for i in range(21, 41)]
        html = _template_env.get_template("partials/sessions_ajax_page.html").render(
            **_make_ajax_context(sessions=sessions, page=2, total_count=60, total_pages=3)
        )
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find("tbody").find_all("tr")
        assert len(rows) == 20

    def test_session_rows_have_data_attributes(self):
        sessions = [_make_mock_session(1)]
        html = _template_env.get_template("partials/sessions_ajax_page.html").render(
            **_make_ajax_context(sessions=sessions, page=1, total_count=1, total_pages=1)
        )
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr", class_="sessions-row")
        assert row is not None
        assert row.get("data-agent") == "claude_code"
        assert row.get("data-session-id") is not None
        assert row.get("data-project") is not None
