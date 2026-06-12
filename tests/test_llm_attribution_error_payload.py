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


def test_round_row_has_attribution_payload_actions():
    """Round rows should carry attribution payload actions without LLM cards."""
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

    row = vm["trace_rows"][0]
    item_types = {item.get("type") for item in row.get("timeline_items", [])}
    assert "llm_summary" not in item_types
    assert "llm_call" not in item_types

    request_action = row["request_attribution"]
    response_action = row["response_attribution"]
    assert request_action["payload_id"].endswith("-request-attribution")
    assert response_action["payload_id"].endswith("-response-attribution")
    assert request_action["kind"] == "llm.request_attribution"
    assert response_action["kind"] == "llm.response_attribution"

    payload_ids = {p.get("payload_id") for p in vm["payload_sources"]}
    assert request_action["payload_id"] in payload_ids
    assert response_action["payload_id"] in payload_ids
