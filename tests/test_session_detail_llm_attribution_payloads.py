"""Session Detail LLM 归因 payload 测试。"""

import json
import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)

from session_browser.web.session_detail.preview import apply_round_preview
from session_browser.web.routes import _build_v11_view_model


class _FakeSession:
    """Minimal session object for testing."""
    def __init__(self):
        self.agent = "claude_code"
        self.session_id = "test-session-001"
        self.title = "Test Session"
        self.model = "claude-sonnet-4"
        self.git_branch = "main"
        self.started_at = "2025-01-01T00:00:00Z"
        self.project_key = "/tmp/test"
        self.project_name = "test"
        self.output_tokens = 5000
        self.fresh_input_tokens = 10000
        self.cache_read_tokens = 5000
        self.cache_write_tokens = 1000
        self.total_tokens = 21000
        self.failed_tool_count = 0


class _FakeAnomalies:
    def __init__(self):
        self.anomalies = []


def _make_round_with_llm_call():
    """Create a round with a main-agent LLM call interaction."""
    user_msg = ChatMessage(
        role="user", content="Hello, please analyze this code.",
        timestamp="2025-01-01T00:00:00Z",
    )
    assistant_msg = ChatMessage(
        role="assistant", content="Sure, let me read the file.",
        timestamp="2025-01-01T00:00:01Z",
    )

    tc = ToolCall(
        name="Read",
        parameters={"file_path": "/tmp/test.py"},
        result="import sys\nprint('hello')",
        tool_use_id="tu-001",
        round_index=0,
    )

    llm_call = LLMCall(
        id="call-001",
        model="claude-sonnet-4",
        scope="main",
        subagent_id="",
        round_index=0,
        parent_id="",
        parent_tool_name="",
        timestamp="2025-01-01T00:00:01Z",
        status="ok",
        input_tokens=5000,
        output_tokens=2000,
        cache_read_tokens=3000,
        cache_write_tokens=500,
        finish_reason="tool_use",
        content_blocks=[
            {"type": "text", "content": "Sure, let me read the file."},
            {"type": "tool_use", "name": "Read", "id": "tu-001",
             "parameters": {"file_path": "/tmp/test.py"}},
        ],
        request_full="role: user\n\nHello, please analyze this code.",
        response_full="Sure, let me read the file.",
        tool_calls=[tc],
        tool_call_count=1,
    )

    ro = ConversationRound(
        user_msg=user_msg,
        assistant_msg=assistant_msg,
        tool_calls=[tc],
        interactions=[llm_call],
        round_index=0,
    )
    apply_round_preview(ro)
    return ro, llm_call


def test_attribution_payloads_exist_in_sources():
    """Verify that attribution payloads are added to payload_sources."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    vm = _build_v11_view_model(
        session=session,
        rounds=[ro],
        llm_calls=[lc],
        tool_calls=ro.tool_calls,
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
    )

    payload_sources = vm["payload_sources"]
    kinds = {p.get("kind") for p in payload_sources}

    # Should have attribution payloads
    assert "llm.request_attribution" in kinds, (
        f"Missing llm.request_attribution in payload_sources. Kinds: {kinds}"
    )
    assert "llm.response_attribution" in kinds, (
        f"Missing llm.response_attribution in payload_sources. Kinds: {kinds}"
    )



def test_slim_initial_load_defers_attribution_payload_data():
    """Initial page load should keep attribution actions but not embed heavy payload data."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    vm = _build_v11_view_model(
        session=session,
        rounds=[ro],
        llm_calls=[lc],
        tool_calls=ro.tool_calls,
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
        slim=True,
    )

    assert vm["payload_sources"] == []
    row = vm["trace_rows"][0]
    assert row["request_attribution"]["payload_id"] == "llm-R1-IX1-request-attribution"
    assert row["request_attribution"]["kind"] == "llm.request_attribution"
    assert row["response_attribution"]["payload_id"] == "llm-R1-IX1-response-attribution"
    assert row["response_attribution"]["kind"] == "llm.response_attribution"


def test_request_attribution_payload_structure():
    """Verify request attribution payload has expected fields."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    vm = _build_v11_view_model(
        session=session,
        rounds=[ro],
        llm_calls=[lc],
        tool_calls=ro.tool_calls,
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
    )

    req_payload = None
    for p in vm["payload_sources"]:
        if p.get("kind") == "llm.request_attribution":
            req_payload = p
            break

    assert req_payload is not None
    data = req_payload.get("data", {})
    assert "agent" in data
    assert "model" in data
    assert "source_label" in data
    assert "confidence_label" in data
    assert "raw_body_available" in data
    assert data["raw_body_available"] is False
    assert "usage" in data
    assert "buckets" in data
    assert "availability_rows" in data

    # Check usage fields
    usage = data["usage"]
    assert "provider_request_input" in usage
    assert "input_side_component_total" in usage
    assert "request_content_denominator" in usage
    assert "fresh" in usage
    assert "cache_read" in usage
    assert "cache_write" in usage


def test_response_attribution_payload_structure():
    """Verify response attribution payload has expected fields."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    vm = _build_v11_view_model(
        session=session,
        rounds=[ro],
        llm_calls=[lc],
        tool_calls=ro.tool_calls,
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
    )

    resp_payload = None
    for p in vm["payload_sources"]:
        if p.get("kind") == "llm.response_attribution":
            resp_payload = p
            break

    assert resp_payload is not None
    data = resp_payload.get("data", {})
    assert "agent" in data
    assert "model" in data
    assert "source_label" in data
    assert "confidence_label" in data
    assert "raw_body_available" in data
    assert data["raw_body_available"] is False
    assert "usage" in data
    assert "buckets" in data
    assert "availability_rows" in data

    usage = data["usage"]
    assert "total_output" in usage
    assert "visible_text" in usage
    assert "tool_use" in usage
    assert "metadata" in usage
    assert "finish_reason" in usage


def test_qoder_attribution_payload_has_no_cache():
    """Qoder attribution should not have cache_read/cache_write values."""
    session = _FakeSession()
    session.agent = "qoder"
    ro, lc = _make_round_with_llm_call()
    lc.model = "qwen3.6-plus"
    # Clear cache fields for qoder
    lc.cache_read_tokens = 0
    lc.cache_write_tokens = 0

    vm = _build_v11_view_model(
        session=session,
        rounds=[ro],
        llm_calls=[lc],
        tool_calls=ro.tool_calls,
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
    )

    req_payload = None
    for p in vm["payload_sources"]:
        if p.get("kind") == "llm.request_attribution":
            req_payload = p
            break

    assert req_payload is not None
    data = req_payload.get("data", {})
    usage = data.get("usage", {})
    assert usage["fresh"]["value"] == lc.input_tokens
    assert usage["cache_read"]["value"] in (0, None) or usage["cache_read"]["precision"] == "unavailable"
    assert usage["cache_write"]["value"] in (0, None) or usage["cache_write"]["precision"] == "unavailable"


def test_codex_attribution_payload_has_no_cache():
    """Codex attribution should keep Fresh but not fabricate cache values."""
    session = _FakeSession()
    session.agent = "codex"
    ro, lc = _make_round_with_llm_call()
    lc.model = "o3-pro"
    lc.cache_read_tokens = 0
    lc.cache_write_tokens = 0

    vm = _build_v11_view_model(
        session=session,
        rounds=[ro],
        llm_calls=[lc],
        tool_calls=ro.tool_calls,
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
    )

    req_payload = None
    for p in vm["payload_sources"]:
        if p.get("kind") == "llm.request_attribution":
            req_payload = p
            break

    assert req_payload is not None
    data = req_payload.get("data", {})
    usage = data.get("usage", {})
    assert usage["fresh"]["value"] == lc.input_tokens
    assert usage["fresh"]["precision"] == "provider_reported"
    assert usage["cache_read"]["value"] is None or usage["cache_read"]["precision"] == "unavailable"
    assert usage["cache_write"]["value"] is None or usage["cache_write"]["precision"] == "unavailable"


def test_attribution_does_not_break_existing_payloads():
    """Adding attribution should not remove or corrupt existing payload types."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    vm = _build_v11_view_model(
        session=session,
        rounds=[ro],
        llm_calls=[lc],
        tool_calls=ro.tool_calls,
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
    )

    kinds = {p.get("kind") for p in vm["payload_sources"]}

    # Existing payload types should still be present
    assert "llm.context" in kinds
    assert "llm.output" in kinds
    assert "message.user" in kinds
    assert "tool.result" in kinds


def test_payload_sources_is_list():
    """payload_sources should remain a list (not dict)."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    vm = _build_v11_view_model(
        session=session,
        rounds=[ro],
        llm_calls=[lc],
        tool_calls=ro.tool_calls,
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
    )

    assert isinstance(vm["payload_sources"], list)
