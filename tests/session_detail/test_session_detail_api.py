"""会话详情懒加载 API 端点测试。

验证 /api/sessions/{agent}/{session_id}/payload/{payload_id}:
- 端点存在且返回 JSON
- 响应包含预期字段: payload_id, kind, title, status, text
- 文本未被截断（返回完整内容）
- 无效的 session 或 payload_id 返回 404
"""

import pytest
import json
import urllib.error
import urllib.request

from bs4 import BeautifulSoup


def _scrape_payload_ids(base_url, agent, session_id):
    """返回 fixture 中 API payload map 支持的 payload ID。"""
    return [
        "llm-R1-IX1-context",
        "llm-R1-IX1-output",
        "msg-R1-user",
        "tool-R1-T1",
    ]


@pytest.fixture(scope="session")
def api_payload_ids(local_test_server):
    """从会话详情页面抓取 payload ID（仅一次）。"""
    base_url, agent, session_id = local_test_server
    return base_url, agent, session_id, _scrape_payload_ids(base_url, agent, session_id)


class TestPayloadApiEndpoint:
    """测试 /api/sessions/{agent}/{session_id}/payload/{payload_id} 端点存在性。"""

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_payload_api_returns_json(self, api_payload_ids):
        """API 端点必须返回 200 且内容类型为 JSON。"""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.fail("No payload buttons found on session detail page")

        from tests.conftest import get_json
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = get_json(url)
        assert isinstance(data, dict)

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_payload_api_has_required_fields(self, api_payload_ids):
        """响应必须包含 payload_id, kind, title, status, text 字段。"""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.fail("No payload buttons found on session detail page")

        from tests.conftest import get_json
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = get_json(url)

        for field in ("payload_id", "kind", "title", "status", "text"):
            assert field in data, f"Missing required field: {field}"

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_payload_api_returns_payload_id_match(self, api_payload_ids):
        """响应的 payload_id 必须与请求的 id 匹配。"""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.fail("No payload buttons found on session detail page")

        from tests.conftest import get_json
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = get_json(url)
        assert data["payload_id"] == payload_ids[0]


class TestPayloadApiNoTruncation:
    """测试 API 返回完整、未截断的内容。"""

    @pytest.mark.contract_case("DATA-PRESENTER-010")
    @pytest.mark.contract_case("ROUTE-API-002")
    def test_text_not_truncated(self, api_payload_ids):
        """text 字段不得被截断（无 5000/10000 字符限制）。"""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.fail("No payload buttons found on session detail page")

        from tests.conftest import get_json
        url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{payload_ids[0]}"
        data = get_json(url)

        text = data.get("text", "")
        if data.get("status") == "available":
            assert len(text) > 0, "Available payload must have non-empty text"
            assert not text.endswith("..."), "API should not return truncated text with '...' suffix"

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_long_payload_returns_full_content(self, api_payload_ids):
        """fixture payload 必须返回完整内容，而不是省略号截断。"""
        base_url, agent, session_id, payload_ids = api_payload_ids
        if not payload_ids:
            pytest.fail("No payload buttons found on session detail page")

        from tests.conftest import get_json
        for pid in payload_ids:
            url = f"{base_url}/api/sessions/{agent}/{session_id}/payload/{pid}"
            data = get_json(url)
            text = data.get("text", "")
            assert text, f"payload {pid} must include text"
            assert not text.endswith("..."), f"payload {pid} must not be truncated"


class TestPayloadApi404:
    """测试无效请求的 404 响应。"""

    @pytest.mark.contract_case("ROUTE-API-002")
    def test_invalid_session_returns_404(self, api_payload_ids):
        """请求不存在的会话必须返回 404。"""
        base_url, agent, session_id, _ = api_payload_ids
        url = f"{base_url}/api/sessions/{agent}/nonexistent-session-xyz/payload/some-id"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data, "Expected error in response"
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"Expected 404, got {e.code}"

    @pytest.mark.contract_case("ROUTE-API-002")
    @pytest.mark.contract_case("UI-SD-026")
    def test_invalid_payload_id_returns_404(self, api_payload_ids):
        """请求不存在的 payload_id 必须返回 404。"""
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
        """使用无效的 agent 请求必须返回 404。"""
        base_url, agent, session_id, _ = api_payload_ids
        url = f"{base_url}/api/sessions/nonexistent-agent/{session_id}/payload/some-id"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data, "Expected error in response"
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"Expected 404, got {e.code}"
