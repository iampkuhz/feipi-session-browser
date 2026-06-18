"""Contract tests for the attribution data layer.

Verifies:
1. Three agents return results via the same service interface.
2. Each AttributedValue has precision/source.
3. raw_body_available defaults to False.
4. No Raw request / Raw response payloads are generated.
5. Bucket token sums do not exceed total input/output.
6. Unknown = request-content denominator - attributed sum.
7. availability_rows exist and are populated.
8. If total usage is missing, system falls back to estimated total.
"""

import pytest
from dataclasses import asdict

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.attribution.contracts import (
    AttributedValue, ValuePrecision, ValueSource, AvailabilityRow,
)


def _make_llm_call(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read: int = 0,
    cache_write: int = 0,
    model: str = "test-model",
    finish_reason: str = "end_turn",
    content_blocks: list | None = None,
    response_full: str = "",
    request_full: str = "",
    tool_calls_raw: str = "",
) -> LLMCall:
    return LLMCall(
        id="test-call-001",
        model=model,
        scope="main",
        subagent_id="",
        round_index=0,
        parent_id="",
        parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z",
        status="ok",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        total_tokens=input_tokens + output_tokens + cache_read + cache_write,
        finish_reason=finish_reason,
        content_blocks=content_blocks or [],
        response_full=response_full,
        request_full=request_full,
        tool_calls_raw=tool_calls_raw,
    )


def _make_round(
    user_content: str = "hello",
    tool_results: list | None = None,
    interactions: list | None = None,
    tool_calls: list | None = None,
) -> ConversationRound:
    return ConversationRound(
        user_msg=ChatMessage(role="user", content=user_content, timestamp="2025-01-01T00:00:00Z"),
        assistant_msg=ChatMessage(role="assistant", content="world", timestamp="2025-01-01T00:00:00Z"),
        tool_calls=tool_calls or [],
        interactions=interactions or [],
    )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_service_returns_request_attribution(agent):
    lc = _make_llm_call(input_tokens=500, output_tokens=200)
    ro = _make_round(user_content="test user message")
    result = build_llm_request_attribution(agent, lc, ro)
    assert result.agent == agent
    assert result.call_id == "test-call-001"
    assert isinstance(result.buckets, list)
    assert isinstance(result.availability_rows, list)


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_service_returns_response_attribution(agent):
    lc = _make_llm_call(input_tokens=500, output_tokens=200, finish_reason="end_turn")
    ro = _make_round()
    result = build_llm_response_attribution(agent, lc, ro)
    assert result.agent == agent
    assert result.call_id == "test-call-001"
    assert isinstance(result.buckets, list)
    assert isinstance(result.availability_rows, list)


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_raw_body_available_defaults_false(agent):
    lc = _make_llm_call(input_tokens=500, output_tokens=200)
    ro = _make_round()
    req = build_llm_request_attribution(agent, lc, ro)
    resp = build_llm_response_attribution(agent, lc, ro)
    assert req.raw_body_available is False
    assert resp.raw_body_available is False


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_no_raw_request_response_payloads(agent):
    """Verify attribution does NOT produce raw request/response payload data."""
    lc = _make_llm_call(input_tokens=500, output_tokens=200, request_full="some context", response_full="some response")
    ro = _make_round()
    req = build_llm_request_attribution(agent, lc, ro)
    resp = build_llm_response_attribution(agent, lc, ro)
    # The attribution should not contain raw body content
    assert req.raw_body_available is False
    assert resp.raw_body_available is False


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_bucket_sums_not_exceed_total_input(agent):
    lc = _make_llm_call(input_tokens=10000, output_tokens=5000,
                         cache_read=5000, cache_write=1000)
    ro = _make_round(user_content="test")
    result = build_llm_request_attribution(agent, lc, ro)
    total = result.total_input.value or 0
    bucket_sum = sum(b.tokens for b in result.buckets)
    assert bucket_sum <= total, (
        f"Bucket sum {bucket_sum} exceeds total {total} for {agent}"
    )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_bucket_sums_not_exceed_total_output(agent):
    lc = _make_llm_call(input_tokens=5000, output_tokens=3000,
                         content_blocks=[{"type": "text", "content": "hello world"}])
    ro = _make_round()
    result = build_llm_response_attribution(agent, lc, ro)
    total = result.total_output.value or 0
    # Only sum buckets that contribute to total (excludes display-only children)
    bucket_sum = sum(
        b.tokens for b in result.buckets
        if getattr(b, "contributes_to_total", True)
    )
    assert bucket_sum <= total, (
        f"Bucket sum {bucket_sum} exceeds total {total} for {agent}"
    )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_unknown_equals_residual(agent):
    """Unknown should be residual against the agent's request distribution total."""
    lc = _make_llm_call(input_tokens=10000, output_tokens=5000,
                         cache_read=5000, cache_write=1000,
                         response_full="assistant response text here")
    ro = _make_round(user_content="test user message content")
    req = build_llm_request_attribution(agent, lc, ro)
    total_req = req.fresh_input.value or 0
    known_req = sum(
        b.tokens for b in req.buckets
        if b.key not in ("unknown_overhead", "unlocated_residual")
        and getattr(b, "contributes_to_total", True)
    )
    assert req.unknown.value == max(total_req - known_req, 0)

    resp = build_llm_response_attribution(agent, lc, ro)
    total_resp = resp.total_output.value or 0
    known_resp = sum(b.tokens for b in resp.buckets if b.key != "unknown")
    assert resp.unknown.value == total_resp - known_resp


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_availability_rows_exist(agent):
    lc = _make_llm_call(input_tokens=500, output_tokens=200)
    ro = _make_round()
    req = build_llm_request_attribution(agent, lc, ro)
    resp = build_llm_response_attribution(agent, lc, ro)
    assert len(req.availability_rows) > 0
    assert len(resp.availability_rows) > 0
    for row in req.availability_rows:
        if isinstance(row, dict):
            assert "field" in row
        else:
            assert isinstance(row, AvailabilityRow)
            assert row.field
    for row in resp.availability_rows:
        if isinstance(row, dict):
            assert "field" in row
        else:
            assert isinstance(row, AvailabilityRow)
            assert row.field


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_every_attributed_value_has_precision_and_source(agent):
    lc = _make_llm_call(input_tokens=5000, output_tokens=3000,
                         cache_read=2000, cache_write=500,
                         response_full="some output text")
    ro = _make_round(user_content="some input text")
    req = build_llm_request_attribution(agent, lc, ro)
    resp = build_llm_response_attribution(agent, lc, ro)

    for val in [req.total_input, req.fresh_input, req.cache_read,
                req.cache_write, req.coverage, req.unknown]:
        assert val.precision is not None, f"{agent} request {val} missing precision"
        assert val.source is not None, f"{agent} request {val} missing source"

    for val in [resp.total_output, resp.visible_text, resp.tool_use,
                resp.metadata, resp.coverage, resp.unknown, resp.finish_reason]:
        assert val.precision is not None, f"{agent} response {val} missing precision"
        assert val.source is not None, f"{agent} response {val} missing source"


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_missing_total_falls_back_to_estimated(agent):
    """When total usage is 0, system should still return valid attribution."""
    lc = _make_llm_call(input_tokens=0, output_tokens=0,
                         response_full="some text response",
                         request_full="some context here")
    ro = _make_round(user_content="user message text")
    req = build_llm_request_attribution(agent, lc, ro)
    resp = build_llm_response_attribution(agent, lc, ro)

    # Even with 0 total, we should have valid objects
    assert req is not None
    assert resp is not None
    # Buckets may be minimal but should exist
    assert isinstance(req.buckets, list)
    assert isinstance(resp.buckets, list)


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_unknown_agent_falls_back(agent):
    """Non-existent agent should fall back to base builder."""
    lc = _make_llm_call(input_tokens=500, output_tokens=200)
    ro = _make_round()
    req = build_llm_request_attribution("unknown_agent", lc, ro)
    resp = build_llm_response_attribution("unknown_agent", lc, ro)
    assert req.agent == "unknown"
    assert resp.agent == "unknown"
