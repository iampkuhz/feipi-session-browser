"""Tests for attribution error diagnostics.

Verifies:
1. When build_llm_request_attribution raises, payload_sources contains llm.attribution_error.
2. When build_llm_response_attribution raises, payload_sources contains llm.attribution_error.
3. Original llm.context / llm.output payloads are preserved even on attribution failure.
4. Error payload does NOT include full traceback in the page-visible message.
"""

import json
import pytest
from unittest.mock import patch

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.web.routes import _build_v11_view_model


class _FakeSession:
    def __init__(self, agent="claude_code"):
        self.agent = agent
        self.session_id = "test-session-001"
        self.title = "Test Session"
        self.model = "claude-sonnet-4"
        self.git_branch = "main"
        self.started_at = "2025-01-01T00:00:00Z"
        self.project_key = "/tmp/test"
        self.project_name = "test"
        self.input_tokens = 10000
        self.output_tokens = 5000
        self.cached_input_tokens = 5000
        self.cached_output_tokens = 1000
        self.total_tokens = 21000
        self.failed_tool_count = 0


class _FakeAnomalies:
    def __init__(self):
        self.anomalies = []


def _make_round_with_llm_call():
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
    ro.compute_preview()
    return ro, llm_call


def test_request_attribution_error_generates_diagnostic_payload():
    """When build_llm_request_attribution raises, payload_sources should
    contain llm.attribution_error for the request."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    with patch(
        "session_browser.web.routes.build_llm_request_attribution",
        side_effect=ValueError("simulated attribution failure"),
    ):
        vm = _build_v11_view_model(
            session=session,
            rounds=[ro],
            llm_calls=[lc],
            tool_calls=ro.tool_calls,
            subagent_runs=[],
            session_anomalies=_FakeAnomalies(),
        )

    kinds = {p.get("kind") for p in vm["payload_sources"]}
    # Should have error payload for request
    error_payloads = [p for p in vm["payload_sources"] if p.get("kind") == "llm.attribution_error"]
    assert len(error_payloads) >= 1, (
        f"Expected at least 1 llm.attribution_error payload, got kinds: {kinds}"
    )

    # Check error payload structure
    err = error_payloads[0]
    data = err.get("data", err)
    assert data.get("error_type") == "ValueError"
    assert "simulated attribution failure" in data.get("message", "")
    assert "fallback" in data


def test_response_attribution_error_generates_diagnostic_payload():
    """When build_llm_response_attribution raises, payload_sources should
    contain llm.attribution_error for the response."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    with patch(
        "session_browser.web.routes.build_llm_response_attribution",
        side_effect=RuntimeError("response attribution failed"),
    ):
        vm = _build_v11_view_model(
            session=session,
            rounds=[ro],
            llm_calls=[lc],
            tool_calls=ro.tool_calls,
            subagent_runs=[],
            session_anomalies=_FakeAnomalies(),
        )

    error_payloads = [p for p in vm["payload_sources"] if p.get("kind") == "llm.attribution_error"]
    assert len(error_payloads) >= 1

    err = error_payloads[0]
    data = err.get("data", err)
    assert data.get("error_type") == "RuntimeError"


def test_base_payloads_preserved_on_attribution_error():
    """Original llm.context / llm.output payloads should still be present
    even when attribution fails."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    with patch(
        "session_browser.web.routes.build_llm_request_attribution",
        side_effect=ValueError("attribution error"),
    ), patch(
        "session_browser.web.routes.build_llm_response_attribution",
        side_effect=ValueError("attribution error"),
    ):
        vm = _build_v11_view_model(
            session=session,
            rounds=[ro],
            llm_calls=[lc],
            tool_calls=ro.tool_calls,
            subagent_runs=[],
            session_anomalies=_FakeAnomalies(),
        )

    kinds = {p.get("kind") for p in vm["payload_sources"]}
    # Original payloads should still be there
    assert "llm.context" in kinds
    assert "llm.output" in kinds
    assert "message.user" in kinds
    assert "tool.result" in kinds
    # Error payloads should also exist
    assert "llm.attribution_error" in kinds


def test_error_payload_no_full_traceback():
    """Error payload message should NOT include full traceback — only
    error type and short message."""
    session = _FakeSession()
    ro, lc = _make_round_with_llm_call()

    with patch(
        "session_browser.web.routes.build_llm_request_attribution",
        side_effect=ValueError("short error message"),
    ):
        vm = _build_v11_view_model(
            session=session,
            rounds=[ro],
            llm_calls=[lc],
            tool_calls=ro.tool_calls,
            subagent_runs=[],
            session_anomalies=_FakeAnomalies(),
        )

    error_payloads = [p for p in vm["payload_sources"] if p.get("kind") == "llm.attribution_error"]
    assert len(error_payloads) >= 1

    data = error_payloads[0].get("data", error_payloads[0])
    msg = data.get("message", "")
    # Should be short (routes.py truncates to 200 chars)
    assert len(msg) <= 200
    # Should NOT contain traceback patterns
    assert "Traceback" not in msg
    assert "File \"" not in msg
