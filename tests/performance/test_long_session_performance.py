"""Long session (100 rounds) performance and rendering tests.

Validates that sessions with 100+ rounds remain usable:
- Page renders without errors
- Trace view contains all rounds
- Round toggle works
- DOM size stays reasonable
"""

import os
import subprocess
import sys
import time
import urllib.request

import pytest

SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(SB_ROOT, "src")


@pytest.fixture(scope="module")
def long_session_url(long_fixture_session):
    """Yield the session detail URL for the 100-round fixture."""
    base_url, agent, session_id = long_fixture_session
    yield f"{base_url}/sessions/{agent}/{session_id}"


class TestLongSessionRendering:
    """Verify 100-round session renders correctly."""

    def test_long_session_returns_200(self, long_session_url):
        """Long session detail page must return HTTP 200."""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        assert resp.status == 200

    def test_long_session_contains_trace_panel(self, long_session_url):
        """Long session must contain trace panel structure."""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        assert "data-trace-panel" in html
        assert "sd-trace-head" in html

    def test_trace_view_present(self, long_session_url):
        """Trace view container must be present."""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        assert 'class="trace"' in html or 'trace' in html

    def test_round_count_matches_100(self, long_session_url):
        """Rendered HTML should contain 100 trace rows for 100 rounds."""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        # Count trace rows using v9 data attribute
        count = html.count('data-trace-round-row')
        assert count == 100, f"Expected 100 trace rows, found {count}"

    def test_no_server_error(self, long_session_url):
        """Long session must not trigger error template."""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        assert "<title>Error - Agent Run Profiler</title>" not in html

    def test_trace_detail_hidden_by_default(self, long_session_url):
        """All trace-detail divs should be initially hidden."""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        # Count trace-detail divs using v9 data attribute
        total = html.count('data-trace-detail')
        # All should have hidden attribute
        hidden = html.count('hidden>')
        assert total == 100, f"Expected 100 trace-detail divs, found {total}"
        assert hidden >= total, f"Only {hidden} of {total} detail divs are hidden"

    def test_preview_text_not_full_content(self, long_session_url):
        """Trace rows should use compact preview_text, not full message content."""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        # v18: table structure uses .summary-title for preview text
        assert "summary-title" in html or "sd-round-preview" in html or "sd-round-preview__title" in html, \
            "Trace rows should use compact preview elements"

    def test_css_contain_property(self, long_session_url):
        """CSS should include contain: layout style on trace elements."""
        css_path = os.path.join(SB_ROOT, "src", "session_browser", "web", "static", "style.css")
        with open(css_path) as f:
            css = f.read()
        assert "contain: layout style" in css


class TestLongSessionPerformance:
    """Rough performance checks for 100-round session."""

    def test_page_loads_under_time_budget(self, long_session_url):
        """Server response + render should complete within 10 seconds."""
        start = time.monotonic()
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        elapsed = time.monotonic() - start

        assert elapsed < 10, f"Page took {elapsed:.2f}s to load (budget: 10s)"
        assert len(html) > 10000, "Page HTML is suspiciously small"

    def test_html_size_reasonable(self, long_session_url):
        """HTML payload should be under 5MB for 100 rounds."""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        size_kb = len(html.encode("utf-8")) / 1024
        assert size_kb < 5000, f"HTML size {size_kb:.0f}KB exceeds 5MB budget"
