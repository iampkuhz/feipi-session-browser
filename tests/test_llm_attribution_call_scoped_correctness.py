"""LLM attribution 的 call-scoped 正确性测试。"""

import json
import pytest
from dataclasses import asdict

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.attribution.agents.claude_code_attribution_builder import ClaudeCodeAttributionBuilder
from session_browser.attribution.agents.qoder_attribution_builder import QoderAttributionBuilder
from session_browser.attribution.agents.codex_attribution_builder import CodexAttributionBuilder
from session_browser.attribution.agents.base import BaseAttributionBuilder
from session_browser.attribution.contracts import (
    AvailabilityRow, ValuePrecision, ValueSource,
)
from session_browser.attribution.serializers import (
    request_attribution_to_payload,
    response_attribution_to_payload,
    availability_row_to_dict,
)
from session_browser.attribution.context import build_attribution_session_context


# ─── 测试帮助函数 ───────────────────────────────────────────────────────────

def _make_lc(**kwargs):
    defaults = dict(
        id="test-call-001", model="test-model", scope="main",
        subagent_id="", round_index=0, parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
        finish_reason="end_turn", content_blocks=[],
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


def _unit(candidate: str, direction: str, text: str, index: int = 1) -> dict:
    return {
        "source_id": f"test:{direction}:{candidate}:{index}",
        "dedupe_key": f"dedupe:{direction}:{candidate}:{index}",
        "origin_path": f"fixture.{candidate}",
        "canonical_source_locator": f"fixture:{candidate}:{index}",
        "unit_type": f"{candidate}_unit",
        "candidate": candidate,
        "direction": direction,
        "event_order": 1,
        "part_index": index,
        "byte_range": [0, len(text.encode("utf-8"))],
        "text": text,
        "label": candidate,
        "preview": text[:120],
    }


def _ctx(agent: str, *units: dict) -> dict | None:
    if agent in {"claude_code", "qoder"}:
        return {"normalized_call": {"call_id": "test-call-001", "source_units": list(units)}}
    return None


# ─── captured_context_fragment 去重 ────────────────────────────

@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_request_full_equal_user_message_does_not_create_captured_context_fragment(agent):
    """request_full 等于当前用户输入时不产生旧 captured_context_fragment。"""
    user_text = "This is the unique user message text for testing"
    lc = _make_lc(input_tokens=1000, request_full=user_text)
    ro = _make_ro(user_content=user_text)
    result = build_llm_request_attribution(
        agent,
        lc,
        ro,
        session_context=_ctx(agent, _unit("user_input", "request", user_text)),
    )

    user_bucket = next((b for b in result.buckets if "user" in b.key), None)
    assert user_bucket is not None, f"Missing user message bucket for {agent}"
    assert user_bucket.tokens > 0

    ctx_bucket = next((b for b in result.buckets if b.key == "captured_context_fragment"), None)
    assert ctx_bucket is None or ctx_bucket.tokens == 0, (
        f"captured_context_fragment should be absent or zero when "
        f"request_full == user_message for {agent}"
    )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_captured_context_fragment_excludes_current_user_message(agent):
    """旧 captured_context_fragment 若存在，也不能包含当前用户输入。"""
    user_text = "unique user message text"
    extra_context = "This is extra system context that is not part of the user message"
    lc = _make_lc(input_tokens=10000, request_full=user_text + "\n\n" + extra_context)
    ro = _make_ro(user_content=user_text)
    result = build_llm_request_attribution(agent, lc, ro, session_context=_ctx(agent, _unit("user_input", "request", user_text)))

    ctx_bucket = next((b for b in result.buckets if b.key == "captured_context_fragment"), None)
    if ctx_bucket is not None and ctx_bucket.tokens > 0:
        preview = ctx_bucket.content_preview or ""
        assert "unique user message text" not in preview, (
            f"captured_context_fragment should not contain current user message for {agent}"
        )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_captured_context_fragment_excludes_preceding_tool_results(agent):
    """旧 captured_context_fragment 若存在，也不能重复工具结果。"""
    user_text = "user message"
    tool_result = "This is a tool result that appears in both request_full and preceding_tool_results"
    lc = _make_lc(
        input_tokens=10000,
        request_full=tool_result + "\n\n" + user_text,
    )
    ro = _make_ro(user_content=user_text)
    ctx = {"preceding_tool_results": [tool_result]}
    if agent in {"claude_code", "qoder"}:
        ctx.update(_ctx(agent, _unit("tool_results", "request", tool_result)))
    builder_cls = {"claude_code": ClaudeCodeAttributionBuilder,
                   "qoder": QoderAttributionBuilder,
                   "codex": CodexAttributionBuilder}[agent]
    builder = builder_cls(lc, ro, session_context=ctx)
    result = builder.build_request()

    ctx_bucket = next((b for b in result.buckets if b.key == "captured_context_fragment"), None)
    if ctx_bucket is not None and ctx_bucket.tokens > 0:
        preview = ctx_bucket.content_preview or ""
        assert "This is a tool result" not in preview, (
            f"captured_context_fragment should not duplicate preceding tool result for {agent}"
        )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_short_fragment_not_removed(agent):
    """短片段不触发移除逻辑。"""
    base = BaseAttributionBuilder(_make_lc(), _make_ro())
    text = "hello world this is some text"
    result = base._remove_known_fragments(text, ["hi", "x" * 5])
    assert result == text


# ─── preceding_tool_results ─────────────────────────────────────

@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_first_llm_call_does_not_include_future_round_tool_results(agent):
    """第一个 LLM call 不包含未来工具结果。"""
    tc = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="future result")
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="test", tool_calls=[tc])
    ctx = build_attribution_session_context(
        session=None,
        round_obj=ro,
        interaction_index=0,
        interactions=[lc],
        round_tool_calls=[tc],
    )
    result = build_llm_request_attribution(agent, lc, ro, session_context=ctx)

    tr_bucket = next((b for b in result.buckets if b.key == "tool_results"), None)
    assert tr_bucket is None or tr_bucket.tokens == 0, (
        f"First LLM call should not have tool_results for {agent}"
    )

    assert ctx["preceding_tool_results"] == [], (
        f"First interaction should have empty preceding_tool_results for {agent}"
    )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_second_llm_call_uses_only_preceding_tool_results(agent):
    """第二个 LLM call 只包含之前 interaction 的工具结果。"""
    tc1 = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="result from first call")
    tc2 = ToolCall(name="Bash", parameters={"command": "echo second"}, result="result from second call")

    lc1 = _make_lc(id="call-1", input_tokens=5000, tool_calls_raw="tc1")
    lc1.tool_calls = [tc1]

    lc2 = _make_lc(id="call-2", input_tokens=8000, tool_calls_raw="tc2")
    lc2.tool_calls = [tc2]

    ro = _make_ro(user_content="test", tool_calls=[tc1, tc2], interactions=[lc1, lc2])

    ctx = build_attribution_session_context(
        session=None,
        round_obj=ro,
        interaction_index=1,
        interactions=[lc1, lc2],
        round_tool_calls=[tc1, tc2],
    )

    assert len(ctx["preceding_tool_results"]) >= 1, (
        f"Second interaction should have preceding tool results for {agent}"
    )
    assert "result from first call" in ctx["preceding_tool_results"], (
        f"Second interaction should include first call's tool result for {agent}"
    )
    assert "result from second call" not in ctx["preceding_tool_results"], (
        f"Second interaction should NOT include its own tool results for {agent}"
    )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_no_fallback_to_full_round_tool_calls(agent):
    """没有 preceding_tool_results 时不回退到完整 round tool_calls。"""
    lc = _make_lc(input_tokens=10000)
    tc = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="should not appear")
    ro = _make_ro(user_content="test", tool_calls=[tc])

    ctx = {"preceding_tool_results": []}
    if agent in {"claude_code", "qoder"}:
        ctx.update(_ctx(agent))
    result = build_llm_request_attribution(agent, lc, ro, session_context=ctx)

    tr_bucket = next((b for b in result.buckets if b.key in ("tool_results", "tool_outputs")), None)
    assert tr_bucket is None or tr_bucket.tokens == 0, (
        f"Builder should not fallback to full round tool_calls for {agent}"
    )


# ─── Response attribution 不包含 tool_result ──────────────

@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_response_attribution_does_not_include_tool_result(agent):
    """Response attribution 只包含 assistant output / tool_use。"""
    lc = _make_lc(
        output_tokens=3000,
        response_full="This is my response",
        content_blocks=[{"type": "text", "content": "This is my response"}],
    )
    ro = _make_ro(user_content="test")
    result = build_llm_response_attribution(agent, lc, ro, session_context=_ctx(agent, _unit("assistant_output", "response", "This is my response")))

    for b in result.buckets:
        assert "result" not in b.key.lower() or "tool_result" not in b.key.lower(), (
            f"Response bucket {b.key} should not be tool_result"
        )


# ─── AvailabilityRow dataclass ──────────────────────────────────

def test_avail_returns_availability_row_dataclass():
    """_avail() 返回 AvailabilityRow dataclass。"""
    builder = BaseAttributionBuilder(_make_lc(), _make_ro())
    row = builder._avail("test_field", "Test Label", True, exact=False)
    assert isinstance(row, AvailabilityRow), (
        f"_avail 应返回 AvailabilityRow，实际为 {type(row)}"
    )
    assert row.field == "test_field"
    assert row.label == "Test Label"
    assert row.available is True


def test_serializer_handles_availability_row_dataclass_and_dict():
    """Serializer 同时处理 AvailabilityRow dataclass 和 dict。"""
    row_dc = AvailabilityRow(
        field="test", label="Test", exact=True, available=True,
        precision="exact", source="transcript", fill_strategy="direct",
    )
    result = availability_row_to_dict(row_dc)
    assert isinstance(result, dict)
    assert result["field"] == "test"

    row_dict = {"field": "legacy", "label": "Legacy", "exact": False,
                "available": True, "precision": "estimated",
                "source": "heuristic", "fill_strategy": "n/a", "note": ""}
    result = availability_row_to_dict(row_dict)
    assert result == row_dict


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_serialized_payload_has_availability_rows_as_dicts(agent):
    """序列化后 availability_rows 应为 dict 列表。"""
    lc = _make_lc(input_tokens=5000, output_tokens=2000)
    ro = _make_ro(user_content="test")
    req = build_llm_request_attribution(agent, lc, ro)
    payload = request_attribution_to_payload(req)

    assert "availability_rows" in payload
    assert isinstance(payload["availability_rows"], list)
    assert len(payload["availability_rows"]) > 0
    for row in payload["availability_rows"]:
        assert isinstance(row, dict), (
            f"序列化 availability row 应为 dict，实际为 {type(row)}"
        )


# ─── Content precision 一致性 ──────────────────────────────

@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_content_availability_rows_use_exact_precision_not_estimated(agent):
    """exact=True 的 content field 不应使用 estimated precision。"""
    lc = _make_lc(
        input_tokens=10000, output_tokens=3000,
        response_full="response text",
    )
    ro = _make_ro(user_content="user message text")
    req = build_llm_request_attribution(agent, lc, ro)
    resp = build_llm_response_attribution(agent, lc, ro)

    for row in req.availability_rows:
        exact = row.exact if hasattr(row, "exact") else row.get("exact", False)
        precision = row.precision if hasattr(row, "precision") else row.get("precision", "")
        if exact and "content" in (row.field if hasattr(row, "field") else row.get("field", "")):
            assert precision != ValuePrecision.ESTIMATED, (
                f"Content field '{row.field if hasattr(row, 'field') else row.get('field', '')}' "
                f"exact=True 但 precision=estimated，agent={agent}"
            )

    for row in resp.availability_rows:
        exact = row.exact if hasattr(row, "exact") else row.get("exact", False)
        precision = row.precision if hasattr(row, "precision") else row.get("precision", "")
        if exact and "content" in (row.field if hasattr(row, "field") else row.get("field", "")):
            assert precision != ValuePrecision.ESTIMATED, (
                f"Content field '{row.field if hasattr(row, 'field') else row.get('field', '')}' "
                f"exact=True 但 precision=estimated，agent={agent}"
            )


def test_token_estimated_fields_have_exact_false():
    """token 估算 field 应设置 exact=False。"""
    lc = _make_lc(input_tokens=5000, output_tokens=2000)
    ro = _make_ro(user_content="test user")
    req = build_llm_request_attribution("claude_code", lc, ro)

    for row in req.availability_rows:
        field = row.field if hasattr(row, "field") else row["field"]
        if "tokens" in field:
            exact = row.exact if hasattr(row, "exact") else row["exact"]
            assert exact is False, (
                f"Token field '{field}' 应设置 exact=False"
            )


# ─── captured_context_preview 使用去重后的片段 ────────

@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_captured_context_preview_empty_when_request_full_equals_user_message(agent):
    """request_full 等于当前用户输入时 captured_context_preview 为空。"""
    user_text = "unique user message content here"
    lc = _make_lc(input_tokens=1000, request_full=user_text)
    ro = _make_ro(user_content=user_text)
    result = build_llm_request_attribution(agent, lc, ro)

    assert result.captured_context_preview == "", (
        f"没有额外上下文时 captured_context_preview 应为空，agent={agent}"
    )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_captured_context_preview_shows_only_extra_context(agent):
    """captured_context_preview 只展示额外上下文，不重复当前用户输入。"""
    user_text = "this is the complete user message content for the test"
    extra = "extra system context information that should appear in preview"
    lc = _make_lc(input_tokens=10000, request_full=user_text + "\n\n" + extra)
    ro = _make_ro(user_content=user_text)
    result = build_llm_request_attribution(agent, lc, ro)

    preview = result.captured_context_preview or ""
    if preview:
        assert user_text not in preview, (
            f"captured_context_preview 不应包含当前用户输入，agent={agent}"
        )
