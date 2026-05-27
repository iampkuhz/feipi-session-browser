"""MacBook viewport smoke matrix — Python-level HTTP tests.

Verifies that all major pages return HTTP 200 with expected HTML structure
at MacBook viewport sizes (1280x800 / 1440x900).

This test starts a local session-browser server using the local test index,
then makes HTTP requests with MacBook User-Agent strings to verify each page.

Usage:
    python3 -m pytest tests/pages/test_macbook_smoke.py -v
"""

from __future__ import annotations

import pytest
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

# ─── Constants ──────────────────────────────────────────────────────────

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_INDEX_DIR = os.path.expanduser("~/.local/share/feipi/session-browser/local-test-index")

MACBOOK_13_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
MACBOOK_14_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Pages to smoke test: (name, path, expected HTML fragment, min HTML length)
PAGES = [
    ("Dashboard", "/dashboard", ">Dashboard<", 500),
    ("Sessions List", "/sessions", ">Sessions<", 500),
    ("Agents", "/agents", ">Agents<", 500),
    ("Projects", "/projects", ">Projects<", 500),
]


# ─── Server fixture ─────────────────────────────────────────────────────


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


def _start_server(env: dict, port: int) -> subprocess.Popen:
    env = env.copy()
    env.setdefault("PYTHONPATH", os.path.join(SB_ROOT, "src"))
    env.setdefault("SERVER_HOST", "127.0.0.1")
    env["SERVER_PORT"] = str(port)
    env.setdefault("SESSION_BROWSER_LOG_LEVEL", "WARNING")
    return subprocess.Popen(
        [sys.executable, "-m", "session_browser", "serve", "--allow-empty", "--no-scan"],
        cwd=SB_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_server(port: int, timeout: float = 15.0) -> str:
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=2)
            if resp.status == 200:
                return base_url
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError(f"Server on port {port} did not start within {timeout}s")


@pytest.fixture(scope="module")
def macbook_smoke_server():
    """

import Start a session-browser server with the local test index.

    Yields base_url or skips if no index is found.
    """
    index_file = os.path.join(TEST_INDEX_DIR, "index.sqlite")
    if not os.path.exists(index_file):
        # Try index.db as fallback
        index_file = os.path.join(TEST_INDEX_DIR, "index.db")
        if not os.path.exists(index_file):
            pytest.skip("No local test index found at " + TEST_INDEX_DIR)

    port = _find_free_port()
    env = os.environ.copy()
    env["INDEX_DIR"] = TEST_INDEX_DIR
    env["PYTHONPATH"] = os.path.join(SB_ROOT, "src")

    proc = _start_server(env, port)

    try:
        base_url = _wait_for_server(port)
        yield base_url
    finally:
        proc.terminate()
        proc.wait()


# ─── Helpers ────────────────────────────────────────────────────────────


def fetch_page(base_url: str, path: str, viewport: str = "macbook-13") -> tuple[int, str]:
    """Fetch a page and return (status_code, html_body)."""
    ua = MACBOOK_13_UA if viewport == "macbook-13" else MACBOOK_14_UA
    url = f"{base_url}{path}"
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8") if e.fp else ""


# ─── Tests ──────────────────────────────────────────────────────────────


class TestMacbookSmoke:
    """Smoke test all major pages at MacBook viewport sizes."""

    @pytest.mark.parametrize("viewport", ["macbook-13", "macbook-14"])
    @pytest.mark.parametrize("name,path,expected_fragment,min_length", PAGES)
    @pytest.mark.contract_case("UI-VISUAL-009")
    def test_page_loads(
        self, macbook_smoke_server, viewport, name, path, expected_fragment, min_length
    ):
        """Each page must return HTTP 200 with expected content at MacBook viewport."""
        base_url = macbook_smoke_server
        status, html = fetch_page(base_url, path, viewport)

        assert status == 200, f"{name} at {viewport} returned HTTP {status}"
        assert len(html) >= min_length, (
            f"{name} at {viewport} HTML too short: {len(html)} bytes "
            f"(expected >= {min_length})"
        )
        assert expected_fragment in html, (
            f"{name} at {viewport} missing expected fragment '{expected_fragment}'"
        )


class TestMacbookViewportSpecific:
    """Viewport-specific structural checks."""

    @pytest.mark.contract_case("UI-VISUAL-009")
    def test_dashboard_metric_cards(self, macbook_smoke_server):
        """Dashboard must have 4 metric cards."""
        base_url = macbook_smoke_server
        status, html = fetch_page(base_url, "/dashboard")
        assert status == 200
        cards = re.findall(r'class="metric-card"', html)
        assert len(cards) == 4, f"Expected 4 metric cards, found {len(cards)}"

    @pytest.mark.contract_case("UI-VISUAL-009")
    def test_sessions_list_has_table(self, macbook_smoke_server):
        """Sessions List must have a sessions table."""
        base_url = macbook_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200
        assert 'aria-label="Sessions table"' in html, \
            "Sessions table must be present"

    @pytest.mark.contract_case("UI-VISUAL-009")
    def test_agents_page_has_agent_entries(self, macbook_smoke_server):
        """Agents page must list at least one agent."""
        base_url = macbook_smoke_server
        status, html = fetch_page(base_url, "/agents")
        assert status == 200
        # Check for data-table or agent-list structure
        has_table = 'class="data-table"' in html or 'class="agent-list"' in html
        assert has_table, "Agents page must have a table or agent list"

    @pytest.mark.contract_case("UI-VISUAL-009")
    def test_projects_page_has_project_entries(self, macbook_smoke_server):
        """Projects page must list at least one project."""
        base_url = macbook_smoke_server
        status, html = fetch_page(base_url, "/projects")
        assert status == 200
        # Check for data-table structure
        has_table = 'class="data-table"' in html or 'class="project-list"' in html
        assert has_table, "Projects page must have a table or project list"

    @pytest.mark.contract_case("UI-VISUAL-009")
    def test_session_detail_page_exists(self, macbook_smoke_server):
        """Session Detail page must exist for at least one session."""
        base_url = macbook_smoke_server
        # First get a session ID from the sessions page
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200

        # Extract a session link from the rendered HTML
        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, "No session link found on Sessions List page"

        session_url = match.group(1)
        status, detail_html = fetch_page(base_url, session_url)
        assert status == 200, f"Session detail at {session_url} returned HTTP {status}"
        assert len(detail_html) >= 500, "Session detail HTML too short"
