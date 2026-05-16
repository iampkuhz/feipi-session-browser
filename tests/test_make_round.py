"""Tests for round construction and token extraction in routes.py.

Verifies that _make_round correctly extracts token data for all agents
that provide per-message usage info (claude_code, qoder).
"""

from __future__ import annotations

import pytest

from session_browser.domain.models import ChatMessage, ToolCall
from session_browser.web.routes import _make_round


def _assistant_msg(usage: dict | None = None, llm_call_id: str = "msg-1") -> ChatMessage:
    return ChatMessage(
        role="assistant",
        content="test response",
        timestamp="2025-01-01T00:00:00+00:00",
        usage=usage,
        llm_call_id=llm_call_id,
    )


USER_MSG = ChatMessage(role="user", content="hello", timestamp="2025-01-01T00:00:00+00:00")

USAGE_CLAUDE = {
    "input_tokens": 100,
    "output_tokens": 50,
    "cache_read_input_tokens": 200,
    "cache_creation_input_tokens": 300,
}


class TestMakeRoundTokenExtraction:
    """Verify _make_round extracts token info for agents with per-message usage."""

    def test_claude_code_extracts_tokens(self):
        r = _make_round(USER_MSG, _assistant_msg(usage=USAGE_CLAUDE), [], 1000, "claude_code")
        assert r.total_tokens == 650  # 100 + 50 + 200 + 300
        assert r.token_ratio == pytest.approx(650 / 1000)

    def test_qoder_extracts_tokens(self):
        """Qoder sessions should have the same token extraction as Claude Code."""
        r = _make_round(USER_MSG, _assistant_msg(usage=USAGE_CLAUDE), [], 1000, "qoder")
        assert r.total_tokens == 650  # 100 + 50 + 200 + 300
        assert r.token_ratio == pytest.approx(650 / 1000)

    def test_codex_has_zero_tokens(self):
        """Codex doesn't provide per-message usage, so round tokens should be 0."""
        r = _make_round(USER_MSG, _assistant_msg(usage=USAGE_CLAUDE), [], 1000, "codex")
        assert r.total_tokens == 0
        assert r.token_ratio == 0

    def test_qoder_no_usage_dict(self):
        """Qoder with no usage dict should have zero tokens."""
        r = _make_round(USER_MSG, _assistant_msg(usage=None), [], 1000, "qoder")
        assert r.total_tokens == 0

    def test_qoder_empty_usage_dict(self):
        """Qoder with empty usage dict should have zero tokens."""
        r = _make_round(USER_MSG, _assistant_msg(usage={}), [], 1000, "qoder")
        assert r.total_tokens == 0

    def test_qoder_estimated_usage(self):
        """Qoder with estimated usage should extract tokens like Claude Code."""
        estimated_usage = {
            "input_tokens": 500,
            "output_tokens": 200,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "estimated": True,
            "estimation_method": "qoder-fast-bytes-v1",
        }
        r = _make_round(USER_MSG, _assistant_msg(usage=estimated_usage), [], 1000, "qoder")
        assert r.total_tokens == 700  # 500 + 200 + 0 + 0
        assert r.token_ratio == pytest.approx(700 / 1000)
        # Cache fields should be 0 for estimated usage
        assert r.input_tokens == 500
        assert r.output_tokens == 200
        assert r.cached_tokens == 0
        assert r.cache_write_tokens == 0

    def test_claude_no_usage_dict(self):
        """Claude with no usage dict should have zero tokens."""
        r = _make_round(USER_MSG, _assistant_msg(usage=None), [], 1000, "claude_code")
        assert r.total_tokens == 0

    def test_token_breakdown_method_uses_usage_dict(self):
        """ConversationRound.token_breakdown() reads from assistant_msg.usage directly,
        so it should work for Qoder even if total_tokens is 0."""
        r = _make_round(USER_MSG, _assistant_msg(usage=USAGE_CLAUDE), [], 1000, "qoder")
        bd = r.token_breakdown()
        assert bd["input"] == 100
        assert bd["output"] == 50
        assert bd["cache_read"] == 200
        assert bd["cache_write"] == 300
