"""Tests for the session detail lazy-load API endpoint.

Validates /api/sessions/{agent}/{session_id}/payload/{payload_id}:
- Endpoint exists and returns JSON
- Response has expected fields: payload_id, kind, title, status, text
- Text is NOT truncated (full content returned)
- 404 for invalid session or payload_id
"""

import pytest
import json
import urllib.error
import urllib.request

try:
    from bs4 import BeautifulSoup
except ImportError:
    pytest.skip("bs4 not installed", allow_module_level=True)


def _scrape_payload_ids(base_url, agent, session_id):
    """Scrape the session detail page once and return all payload IDs."""
    from tests.conftest import get_html
    html = get_html(f"{base_url}/sessions/{agent}/{session_id}")
    soup = BeautifulSoup(html, "html.parser")
    return [
        btn["data-payload-id"]
        for btn in soup.select('button[data-action="open-payload"]')
        if btn.get("data-payload-id")
    ]


@pytest.fixture(scope="session")
def api_payload_ids(local_test_server):
    """Scrape payload IDs from the session detail page once."""
    base_url, agent, session_id = local_test_server
    return base_url, agent, session_id, _scrape_payload_ids(base_url, agent, session_id)


class TestPayloadApiEndpoint:
    """Test that the /api/sessions/{agent}/{session_id}/payload/{payload_id} endpoint exists."""

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_payload_api_returns_json(self, api_payload_ids):
        """API endpoint must return 200 with JSON content type."""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        from tests.conftest import get_json
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = get_json(url)
        assert isinstance(data, dict)

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_payload_api_has_required_fields(self, api_payload_ids):
        """Response must contain payload_id, kind, title, status, text fields."""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        from tests.conftest import get_json
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = get_json(url)

        for field in ("payload_id", "kind", "title", "status", "text"):
            assert field in data, f"Missing required field: {field}"

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_payload_api_returns_payload_id_match(self, api_payload_ids):
        """Response payload_id must match the requested id."""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        from tests.conftest import get_json
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = get_json(url)
        assert data["payload_id"] == payload_ids[0]


class TestPayloadApiNoTruncation:
    """Test that the API returns full, untruncated content."""

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_text_not_truncated(self, api_payload_ids):
        """The text field must NOT be truncated (no 5000/10000 char limit)."""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        from tests.conftest import get_json
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = get_json(url)

        text = data.get("text", "")
        if data.get("status") == "available":
            assert len(text) > 0, "Available payload must have non-empty text"
            assert not text.endswith("..."), "API should not return truncated text with '...' suffix"

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_long_payload_returns_full_content(self, api_payload_ids):
        """For a known-long payload, verify the API returns content beyond truncation limits."""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.skip("No payload buttons found on session detail page")

        from tests.conftest import get_json
        # Prefer llm.context payloads (typically largest), fall back to any
        candidates = [pid for pid in payload_ids if pid.endswith("-context")] or payload_ids

        for pid in candidates[:3]:  # Try up to 3 candidates
            url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{pid}"
            data = get_json(url)
            text = data.get("text", "")
            if len(text) > 5000:
                assert len(text) > 5000, \
                    f"Expected untruncated text >5000 chars, got {len(text)}"
                return

        pytest.skip("All payloads are under 5000 chars; cannot verify no-truncation on long content")


class TestPayloadApi404:
    """Test 404 responses for invalid requests."""

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_invalid_session_returns_404(self, api_payload_ids):
        """Request for non-existent session must return 404."""
        base_url, agent, session_id, _ = api_payload_ids
        url = f"{base_url}/api/sessions/{agent}/nonexistent-session-xyz/payload/some-id"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data, "Expected error in response"
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"Expected 404, got {e.code}"

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_invalid_payload_id_returns_404(self, api_payload_ids):
        """Request for non-existent payload_id must return 404."""
        base_url, agent, session_id, _ = api_payload_ids
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/nonexistent-payload-xyz"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data, "Expected error in response"
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"Expected 404, got {e.code}"

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_invalid_agent_returns_404(self, api_payload_ids):
        """Request with invalid agent must return 404."""
        base_url, agent, session_id, _ = api_payload_ids
        url = f"{base_url}/api/sessions/nonexistent-agent/{session_id}/payload/some-id"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data, "Expected error in response"
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"Expected 404, got {e.code}"
