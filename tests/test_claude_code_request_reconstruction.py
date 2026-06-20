"""Claude Code 最终版 request attribution source_units 测试。"""

from session_browser.attribution.agents.claude_code_attribution_builder import ClaudeCodeAttributionBuilder
from session_browser.attribution.contracts import ValuePrecision, ValueSource
from session_browser.domain.models import ChatMessage, ConversationRound, LLMCall


def _make_lc(**kwargs):
    defaults = dict(
        id="cc-recon-001", model="claude-sonnet-4", scope="main",
        subagent_id="", round_index=0, parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=10000, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
        finish_reason="end_turn", content_blocks=[],
        response_full="", request_full="", tool_calls_raw="",
    )
    defaults.update(kwargs)
    return LLMCall(**defaults)


def _make_ro(user_content="hello"):
    return ConversationRound(
        user_msg=ChatMessage(role="user", content=user_content, timestamp="2025-01-01T00:00:00Z"),
        assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        tool_calls=[],
        interactions=[],
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


def _ctx(*units: dict) -> dict:
    return {"normalized_call": {"call_id": "cc-recon-001", "source_units": list(units)}}


def _build_request(*units: dict, input_tokens: int = 10000):
    return ClaudeCodeAttributionBuilder(
        _make_lc(input_tokens=input_tokens),
        _make_ro("unique user message text xyz"),
        session_context=_ctx(*units),
    ).build_request()


def test_user_input_source_unit_not_double_counted_as_history():
    """user_input candidate 只映射到 current_user_input bucket。"""
    result = _build_request(_unit("user_input", "request", "unique user message text xyz"))

    user_buckets = [b for b in result.buckets if b.key == "current_user_input"]
    history_buckets = [b for b in result.buckets if b.key == "conversation_messages"]
    assert len(user_buckets) == 1
    assert history_buckets == []


def test_conversation_history_source_units_create_history_bucket():
    """conversation_history candidate 映射到 conversation_messages bucket。"""
    result = _build_request(
        _unit("conversation_history", "request", "What is Python?", 1),
        _unit("conversation_history", "request", "Python is a language.", 2),
    )

    bucket = next(b for b in result.buckets if b.key == "conversation_messages")
    assert bucket.tokens > 0
    assert bucket.details["kind"] == "source_units"
    assert len(bucket.details["items"]) == 2


def test_tool_results_source_units_create_tool_result_bucket():
    """tool_results candidate 映射到 tool_result_context bucket。"""
    result = _build_request(_unit("tool_results", "request", "file content here"))

    bucket = next(b for b in result.buckets if b.key == "tool_result_context")
    assert bucket.tokens > 0
    assert bucket.source == ValueSource.TRANSCRIPT


def test_tool_definitions_from_source_units():
    """tool_definitions 来自 normalized source_units，不从 available_tools fallback。"""
    result = _build_request(_unit("tool_definitions", "request", "Read Bash Edit schema"))

    bucket = next(b for b in result.buckets if b.key == "tool_definitions")
    assert bucket.tokens > 0
    assert bucket.precision == ValuePrecision.ESTIMATED
    assert bucket.details["candidate"] == "tool_definitions"


def test_system_instruction_source_units_create_instruction_bucket():
    """system_instructions candidate 映射到 instruction_context bucket。"""
    result = _build_request(_unit("system_instructions", "request", "Always use Python."))

    bucket = next(b for b in result.buckets if b.key == "instruction_context")
    assert bucket.tokens > 0
    assert bucket.source == ValueSource.TRANSCRIPT


def test_no_source_units_keeps_low_confidence_residual_only():
    """没有 normalized source_units 时不维护旧 reconstruction fallback。"""
    result = ClaudeCodeAttributionBuilder(_make_lc(input_tokens=10000), _make_ro()).build_request()

    assert result.source_label == "normalized source_units unavailable"
    assert [b.key for b in result.buckets] == ["unlocated_residual"]
    assert result.buckets[0].tokens == 10000


def test_unlocated_residual_equals_fresh_minus_candidates():
    """unlocated_residual 使用 fresh_input 减去已定位 candidates。"""
    result = _build_request(_unit("user_input", "request", "hello world"), input_tokens=1000)

    residual = next(b for b in result.buckets if b.key == "unlocated_residual")
    known = sum(b.tokens for b in result.buckets if b.key != "unlocated_residual")
    assert residual.tokens == max(1000 - known, 0)


def test_timing_fields_present():
    """build_request 保留 timing 字段。"""
    result = ClaudeCodeAttributionBuilder(
        _make_lc(input_tokens=10000, timestamp="2025-01-01T00:00:01Z"),
        _make_ro(),
        session_context=_ctx(_unit("user_input", "request", "hello")),
    ).build_request()

    assert result.timing["request_at"] == "2025-01-01T00:00:01Z"
    assert result.timing["response_at"] == "—"
    assert result.timing["duration"] == "—"


def test_bucket_order_keeps_residual_last():
    """兼容 bucket 列表中 residual 保持最后。"""
    result = _build_request(_unit("user_input", "request", "hello"))

    keys = [b.key for b in result.buckets]
    assert keys[-1] == "unlocated_residual"
    assert keys.index("current_user_input") < keys.index("unlocated_residual")
