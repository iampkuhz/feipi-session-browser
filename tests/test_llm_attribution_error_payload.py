"""Tests for attribution error diagnostics.

After Task 03a, attribution is built on-demand via API rather than in
_build_v11_view_model.  Error handling is now tested by
test_llm_attribution_api.py.  This file retains a regression test that
base payloads (llm.context / llm.output) are still produced even when
attribution is no longer built server-side.
"""

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


def test_base_payloads_and_attribution_fallback_present():
    """After 03a, _build_v11_view_model still builds attribution as fallback.
    Original llm.context / llm.output + attribution payloads should all be present."""
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
    # Original payloads should still be there
    assert "llm.context" in kinds
    assert "llm.output" in kinds
    assert "message.user" in kinds
    assert "tool.result" in kinds
    # Attribution fallback payloads should also be present
    assert "llm.request_attribution" in kinds
    assert "llm.response_attribution" in kinds


def test_llm_call_has_attribution_ids_and_api_url():
    """LLM call items should have attribution IDs and API URLs for
    frontend fetch-based rendering."""
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

    # Find LLM call items in trace_rows
    llm_items = []
    for row in vm["trace_rows"]:
        for item in row.get("timeline_items", []):
            if item.get("type") == "llm_call":
                llm_items.append(item)

    assert len(llm_items) >= 1
    item = llm_items[0]
    assert item.get("request_attribution_id")
    assert item.get("response_attribution_id")
    assert item.get("attribution_api_url_request")
    assert item.get("attribution_api_url_response")
    assert item.get("attribution_source") == "claude_code"
    assert item.get("attribution_session_id") == "test-session-001"
    # Verify API URL pattern
    assert "/attribution/1/1/request" in item["attribution_api_url_request"]
    assert "/attribution/1/1/response" in item["attribution_api_url_response"]
