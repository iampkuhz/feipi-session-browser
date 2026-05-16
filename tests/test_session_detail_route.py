"""TASK: Session detail route smoke test.

Starts a real HTTP server on a test port, requests a session detail URL,
and asserts the page renders successfully (HTTP 200, key DOM elements present).
"""

import os
import subprocess
import sys
import time
import urllib.request

import pytest

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(SB_ROOT, "src")

# Use the local test index if it exists
DEFAULT_TEST_INDEX = os.path.expanduser(
    "~/.local/share/feipi/session-browser/local-test-index/index.sqlite"
)

TEST_PORT = 18897  # Unique port to avoid conflicts


def _find_test_session(index_path: str) -> tuple[str, str] | None:
    """Return (agent, session_id) from the test index."""
    import sqlite3

    if not os.path.exists(index_path):
        return None
    conn = sqlite3.connect(index_path)
    row = conn.execute(
        "SELECT agent, session_id FROM sessions WHERE title != '' LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return (row[0], row[1])
    return None


@pytest.fixture(scope="module")
def session_detail_url():
    """Start a session-browser server and return a session detail URL.

    Uses INDEX_DIR env var to point to a test SQLite index.
    Skips if no test index is available.
    """
    index_dir = os.environ.get(
        "SB_TEST_INDEX_DIR",
        os.path.dirname(DEFAULT_TEST_INDEX),
    )

    if not os.path.exists(os.path.join(index_dir, "index.sqlite")):
        # Try to find any .sqlite file in the dir
        for f in os.listdir(index_dir):
            if f.endswith(".sqlite"):
                break
        else:
            pytest.skip("No test SQLite index found at " + index_dir)

    test_session = _find_test_session(os.path.join(index_dir, "index.sqlite"))
    if test_session is None:
        pytest.skip("No sessions found in test index")

    agent, session_id = test_session

    env = os.environ.copy()
    env["PYTHONPATH"] = SRC_DIR
    env["INDEX_DIR"] = index_dir
    env["SERVER_HOST"] = "127.0.0.1"
    env["SERVER_PORT"] = str(TEST_PORT)
    env["SESSION_BROWSER_LOG_LEVEL"] = "WARNING"

    proc = subprocess.Popen(
        [sys.executable, "-m", "session_browser", "serve", "--allow-empty", "--no-scan"],
        cwd=SB_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for server to be ready
    base_url = f"http://127.0.0.1:{TEST_PORT}"
    for _ in range(30):
        try:
            resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=2)
            if resp.status == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        proc.wait()
        pytest.fail("Server did not start within 15 seconds")

    yield f"{base_url}/sessions/{agent}/{session_id}"

    proc.terminate()
    proc.wait()


class TestSessionDetailRoute:
    """Smoke test for the session detail HTTP route."""

    def test_session_detail_returns_200(self, session_detail_url):
        """Session detail page must return HTTP 200, not 5xx."""
        resp = urllib.request.urlopen(session_detail_url, timeout=10)
        assert resp.status == 200

    def test_session_detail_contains_workbench(self, session_detail_url):
        """Session detail page must contain the workbench container."""
        resp = urllib.request.urlopen(session_detail_url, timeout=10)
        html = resp.read().decode("utf-8")
        assert 'class="wb-head"' in html or 'wb-head' in html, \
            "Session detail must contain workbench head"
        assert 'wb-body' in html, \
            "Session detail must contain workbench body"

    def test_session_detail_contains_metrics(self, session_detail_url):
        """Session detail page must contain the metrics strip."""
        resp = urllib.request.urlopen(session_detail_url, timeout=10)
        html = resp.read().decode("utf-8")
        assert 'metrics-strip' in html, \
            "Session detail must contain metrics strip"

    def test_session_detail_contains_view_switches(self, session_detail_url):
        """Session detail page must contain view switch buttons."""
        resp = urllib.request.urlopen(session_detail_url, timeout=10)
        html = resp.read().decode("utf-8")
        for view in ("trace", "calls", "hotspots"):
            assert f'data-switch="{view}"' in html, \
                f"Session detail must contain switch button for {view}"

    def test_session_detail_no_server_error(self, session_detail_url):
        """Session detail page must not render the error.html template."""
        resp = urllib.request.urlopen(session_detail_url, timeout=10)
        html = resp.read().decode("utf-8")
        # The error template sets <title>Error - Agent Run Profiler>
        assert "<title>Error - Agent Run Profiler</title>" not in html, \
            "Session detail must not render the error page"
        # Check for the error state panel that error.html renders
        assert "state-panel__icon--error" not in html, \
            "Session detail must not contain error state panel"


class TestStaticAssets:
    """Smoke test for static asset serving."""

    @pytest.fixture(scope="class")
    def static_base_url(self):
        """Start a minimal server for static asset testing."""
        env = os.environ.copy()
        env["PYTHONPATH"] = SRC_DIR
        env["INDEX_DIR"] = os.path.dirname(DEFAULT_TEST_INDEX)
        env["SERVER_HOST"] = "127.0.0.1"
        env["SERVER_PORT"] = str(TEST_PORT + 1)
        env["SESSION_BROWSER_LOG_LEVEL"] = "WARNING"

        proc = subprocess.Popen(
            [sys.executable, "-m", "session_browser", "serve", "--allow-empty", "--no-scan"],
            cwd=SB_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        base_url = f"http://127.0.0.1:{TEST_PORT + 1}"
        for _ in range(30):
            try:
                resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=2)
                if resp.status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            proc.terminate()
            proc.wait()
            pytest.fail("Server did not start for static asset tests")

        yield base_url

        proc.terminate()
        proc.wait()

    def test_css_asset_returns_200(self, static_base_url):
        """style.css must be served with HTTP 200."""
        resp = urllib.request.urlopen(f"{static_base_url}/static/style.css", timeout=5)
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "text/css" in content_type

    def test_js_app_asset_returns_200(self, static_base_url):
        """js/app.js must be served with HTTP 200."""
        resp = urllib.request.urlopen(f"{static_base_url}/static/js/app.js", timeout=5)
        assert resp.status == 200

    def test_js_inspector_asset_returns_200(self, static_base_url):
        """js/inspector.js must be served with HTTP 200."""
        resp = urllib.request.urlopen(f"{static_base_url}/static/js/inspector.js", timeout=5)
        assert resp.status == 200
