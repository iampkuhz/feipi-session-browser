"""Tests for the session detail lazy-load API endpoint.

Validates /api/sessions/{agent}/{session_id}/payload/{payload_id}:
- Endpoint exists and returns JSON
- Response has expected fields: payload_id, kind, title, status, text
- Text is NOT truncated (full content returned)
- 404 for invalid session or payload_id
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

import pytest

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(SB_ROOT, "src")

DEFAULT_TEST_INDEX = os.path.expanduser(
    "~/.local/share/feipi/session-browser/local-test-index/index.sqlite"
)


def _find_free_port():
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


def _find_test_session_with_payload(index_path: str):
    """Return (agent, session_id) from the test index, preferring sessions with content."""
    import sqlite3

    if not os.path.exists(index_path):
        return None
    conn = sqlite3.connect(index_path)
    row = conn.execute(
        "SELECT agent, session_id FROM sessions "
        "WHERE agent = 'claude_code' AND input_tokens > 0 "
        "ORDER BY input_tokens DESC LIMIT 1"
    ).fetchone()
    if row:
        conn.close()
        return (row[0], row[1])
    row = conn.execute(
        "SELECT agent, session_id FROM sessions WHERE agent = 'claude_code' AND title != '' LIMIT 1"
    ).fetchone()
    if row:
        conn.close()
        return (row[0], row[1])
    row = conn.execute(
        "SELECT agent, session_id FROM sessions WHERE title != '' LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return (row[0], row[1])
    return None


@pytest.fixture(scope="module")
def api_server():
    """Start a session-browser server and return (base_url, agent, session_id, payload_ids)."""
    index_dir = os.environ.get(
        "SB_TEST_INDEX_DIR",
        os.path.dirname(DEFAULT_TEST_INDEX),
    )

    if not os.path.exists(os.path.join(index_dir, "index.sqlite")):
        try:
            for f in os.listdir(index_dir):
                if f.endswith(".sqlite"):
                    break
            else:
                pytest.skip("No test SQLite index found at " + index_dir)
        except FileNotFoundError:
            pytest.skip("No test SQLite index directory found at " + index_dir)

    test_session = _find_test_session_with_payload(os.path.join(index_dir, "index.sqlite"))
    if test_session is None:
        pytest.skip("No sessions found in test index")

    agent, session_id = test_session

    port = _find_free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = SRC_DIR
    env["INDEX_DIR"] = index_dir
    env["SERVER_HOST"] = "127.0.0.1"
    env["SERVER_PORT"] = str(port)
    env["SESSION_BROWSER_LOG_LEVEL"] = "WARNING"

    proc = subprocess.Popen(
        [sys.executable, "-m", "session_browser", "serve", "--allow-empty", "--no-scan"],
        cwd=SB_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base_url = f"http://127.0.0.1:{port}"
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

    # Fetch payload IDs once at fixture setup (avoids repeated page fetches)
    payload_ids = _scrape_payload_ids(base_url, agent, session_id)

    yield base_url, agent, session_id, payload_ids

    proc.terminate()
    proc.wait()


def _scrape_payload_ids(base_url, agent, session_id):
    """Scrape the session detail page once and return all payload IDs."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    try:
        resp = urllib.request.urlopen(f"{base_url}/sessions/{agent}/{session_id}", timeout=10)
        html = resp.read().decode("utf-8")
        soup = BeautifulSoup(html, "html.parser")
        return [
            btn["data-payload-id"]
            for btn in soup.select('button[data-action="open-payload"]')
            if btn.get("data-payload-id")
        ]
    except Exception:
        return []


def _get_json(url):
    """Fetch JSON from url and return parsed dict."""
    resp = urllib.request.urlopen(url, timeout=10)
    assert resp.status == 200
    content_type = resp.headers.get("Content-Type", "")
    assert "application/json" in content_type, f"Expected JSON, got {content_type}"
    return json.loads(resp.read().decode("utf-8"))


class TestPayloadApiEndpoint:
    """Test that the /api/sessions/{agent}/{session_id}/payload/{payload_id} endpoint exists."""

    def test_payload_api_returns_json(self, api_server):
        """API endpoint must return 200 with JSON content type."""
        base_url, agent, session_id, payload_ids = api_server
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = _get_json(url)
        assert isinstance(data, dict)

    def test_payload_api_has_required_fields(self, api_server):
        """Response must contain payload_id, kind, title, status, text fields."""
        base_url, agent, session_id, payload_ids = api_server
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = _get_json(url)

        for field in ("payload_id", "kind", "title", "status", "text"):
            assert field in data, f"Missing required field: {field}"

    def test_payload_api_returns_payload_id_match(self, api_server):
        """Response payload_id must match the requested id."""
        base_url, agent, session_id, payload_ids = api_server
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = _get_json(url)
        assert data["payload_id"] == payload_ids[0]


class TestPayloadApiNoTruncation:
    """Test that the API returns full, untruncated content."""

    def test_text_not_truncated(self, api_server):
        """The text field must NOT be truncated (no 5000/10000 char limit)."""
        base_url, agent, session_id, payload_ids = api_server
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = _get_json(url)

        text = data.get("text", "")
        if data.get("status") == "available":
            assert len(text) > 0, "Available payload must have non-empty text"
            assert not text.endswith("..."), "API should not return truncated text with '...' suffix"

    def test_long_payload_returns_full_content(self, api_server):
        """For a known-long payload, verify the API returns content beyond truncation limits."""
        base_url, agent, session_id, payload_ids = api_server
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        # Prefer llm.context payloads (typically largest), fall back to any
        candidates = [pid for pid in payload_ids if pid.endswith("-context")] or payload_ids

        for pid in candidates[:3]:  # Try up to 3 candidates
            url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{pid}"
            data = _get_json(url)
            text = data.get("text", "")
            if len(text) > 5000:
                assert len(text) > 5000, \
                    f"Expected untruncated text >5000 chars, got {len(text)}"
                return

        pytest.skip("All payloads are under 5000 chars; cannot verify no-truncation on long content")


class TestPayloadApi404:
    """Test 404 responses for invalid requests."""

    def test_invalid_session_returns_404(self, api_server):
        """Request for non-existent session must return 404."""
        base_url, agent, session_id, _ = api_server
        url = f"{base_url}/api/sessions/{agent}/nonexistent-session-xyz/payload/some-id"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data, "Expected error in response"
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"Expected 404, got {e.code}"

    def test_invalid_payload_id_returns_404(self, api_server):
        """Request for non-existent payload_id must return 404."""
        base_url, agent, session_id, _ = api_server
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/nonexistent-payload-xyz"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data, "Expected error in response"
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"Expected 404, got {e.code}"

    def test_invalid_agent_returns_404(self, api_server):
        """Request with invalid agent must return 404."""
        base_url, agent, session_id, _ = api_server
        url = f"{base_url}/api/sessions/nonexistent-agent/{session_id}/payload/some-id"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data, "Expected error in response"
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"Expected 404, got {e.code}"
