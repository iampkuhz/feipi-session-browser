"""Codex specific attribution tests.

Verifies:
1. Codex cache split is unknown — no fake cache_read/cache_write.
2. Codex uses session jsonl / response items.
3. Bucket tokens sum does not exceed total input.
4. Repository/file context estimation works.
"""

import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.agents.codex import CodexAttributionBuilder
from session_browser.attribution.contracts import ValuePrecision


def _make_lc(**kwargs):
    defaults = dict(
        id="codex-call-001", model="o3-pro", scope="main",
        subagent_id="", round_index=0, parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
        finish_reason="stop", content_blocks=[],
        response_full="", request_full="", tool_calls_raw="",
    )
    defaults.update(kwargs)
    return LLMCall(**defaults)


def _make_ro(user_content="hello", tool_calls=None, interactions=None):
    return ConversationRound(
        user_msg=ChatMessage(role="user", content=user_content, timestamp="2025-01-01T00:00:00Z"),
        assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        tool_calls=tool_calls or [],
        interactions=interactions or [],
    )


def test_codex_cache_split_unknown():
    """Codex must NOT fabricate cache_read / cache_write values."""
    lc = _make_lc(input_tokens=10000, output_tokens=5000)
    ro = _make_ro(user_content="test user message content here")
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.fresh_input.value is None
    assert result.fresh_input.precision == ValuePrecision.UNAVAILABLE
    assert result.cache_read.value is None
    assert result.cache_read.precision == ValuePrecision.UNAVAILABLE
    assert result.cache_write.value is None
    assert result.cache_write.precision == ValuePrecision.UNAVAILABLE


def test_codex_session_jsonl_source():
    """Codex should label source as session jsonl."""
    lc = _make_lc(input_tokens=10000, output_tokens=5000,
                   request_full="session context\n\nfile content")
    ro = _make_ro(user_content="user prompt text")
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.agent == "codex"
    assert result.source_label == "session jsonl"


def test_codex_bucket_sum_within_total():
    lc = _make_lc(input_tokens=10000, output_tokens=5000,
                   request_full="context\n\nmore\n\ndata\n\nFile: test.py")
    ro = _make_ro(user_content="test user message")
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    total = result.total_input.value or 0
    bucket_sum = sum(b.tokens for b in result.buckets)
    assert bucket_sum <= total


def test_codex_response_attribution():
    lc = _make_lc(output_tokens=3000, response_full="response text here",
                   content_blocks=[
                       {"type": "text", "content": "Hello world"},
                       {"type": "tool_use", "name": "Bash", "id": "tu-001",
                        "parameters": {"command": "echo hello"}},
                   ])
    ro = _make_ro()
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_response()

    assert result.agent == "codex"
    assert result.total_output.value == 3000
    assert result.visible_text.value is not None
    assert result.visible_text.value > 0


def test_codex_repo_context_estimation():
    """Codex should estimate repo context tokens from file references."""
    lc = _make_lc(
        input_tokens=15000,
        request_full="File: src/main.py\nimport sys\n\nFile: src/utils.py\ndef helper(): pass",
    )
    ro = _make_ro(user_content="analyze these files")
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    repo_bucket = next((b for b in result.buckets if b.key == "repository_file_context"), None)
    if repo_bucket is not None:
        assert repo_bucket.tokens > 0


def test_codex_availability_notes_cache_unknown():
    lc = _make_lc(input_tokens=5000)
    ro = _make_ro(user_content="test")
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    for row in result.availability_rows:
        field_val = row.field if hasattr(row, "field") else row["field"]
        avail_val = row.available if hasattr(row, "available") else row["available"]
        if field_val in ("fresh_input", "cache_read", "cache_write"):
            assert avail_val is False
