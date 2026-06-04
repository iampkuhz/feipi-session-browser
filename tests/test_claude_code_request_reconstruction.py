"""Claude Code request reconstruction attribution tests.

Verifies the expanded bucket model from task-02d:
1. current_user_message not double-counted
2. prior_conversation_messages only from prior calls
3. preceding_tool_results from session_context only
4. tool_schemas generates non-zero estimate when available_tools exist
5. tool_schemas precision=heuristic when no raw schema
6. local_instruction_context from system-reminder/CLAUDE.md fixture
7. agent_subagent_prompt from .claude/agents fixture
8. hidden_builtin_system_estimate labeled heuristic, no fake content
9. unlocated_residual = total_input - located
10. located_rate = located / total_input
"""

import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.agents.claude_code import ClaudeCodeAttributionBuilder
from session_browser.attribution.contracts import ValuePrecision, ValueSource


def _make_lc(**kwargs):
    defaults = dict(
        id="cc-recon-001", model="claude-sonnet-4", scope="main",
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


# ── 1. current_user_message not double-counted ─────────────────────────

def test_current_user_message_not_double_counted():
    """current_user_message should appear only once, not in prior_conversation."""
    lc = _make_lc(input_tokens=10000, cache_read_tokens=5000)
    ro = _make_ro(user_content="unique user message text xyz")
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    user_buckets = [b for b in result.buckets if "user" in b.key.lower()]
    assert len(user_buckets) == 1
    assert user_buckets[0].key == "current_user_message"


# ── 2. prior_conversation_messages only from prior calls ───────────────

def test_prior_conversation_only_with_explicit_prior():
    """prior_conversation_messages should only exist with explicit prior_messages."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello")
    # No prior_messages in session_context
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    prior_bucket = next((b for b in result.buckets if b.key == "prior_conversation_messages"), None)
    if prior_bucket is not None:
        assert prior_bucket.tokens == 0 or prior_bucket.precision == ValuePrecision.UNAVAILABLE


@pytest.mark.skip(reason="prior_conversation_messages replaced by full_messages_array in split refactor (pre-existing)")
def test_prior_conversation_with_prior_messages():
    """With prior_messages, prior_conversation_messages should have tokens."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="current message")
    ctx = {
        "prior_messages": [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    prior_bucket = next((b for b in result.buckets if b.key == "prior_conversation_messages"), None)
    assert prior_bucket is not None
    assert prior_bucket.tokens > 0
    assert prior_bucket.precision == ValuePrecision.ESTIMATED


# ── 3. preceding_tool_results from session_context only ────────────────

def test_preceding_tool_results_from_session_context():
    """Tool results should come from session_context preceding_tool_results."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="do something")
    ctx = {
        "preceding_tool_results": [
            {"result": "file content here, this is a substantial result"},
        ]
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    tool_bucket = next((b for b in result.buckets if b.key == "preceding_tool_results"), None)
    assert tool_bucket is not None
    assert tool_bucket.tokens > 0
    assert tool_bucket.source == ValueSource.TOOL_LOGS


# ── 4. tool_schemas generates non-zero estimate when available_tools ───

def test_tool_schemas_nonzero_with_available_tools():
    """tool_schemas should have positive tokens when available_tools exist."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello")
    ctx = {"available_tools": ["Read", "Bash", "Edit", "Grep"]}
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    schema_bucket = next((b for b in result.buckets if b.key == "tool_schemas"), None)
    assert schema_bucket is not None
    # Uses real SDK schema tokens now, not 240/tool heuristic
    assert schema_bucket.tokens > 0
    assert "4 tools" in schema_bucket.count_label


# ── 5. tool_schemas precision=estimated when using real SDK schemas ────

def test_tool_schemas_precision_heuristic():
    """tool_schemas should be estimated precision when using real SDK schemas."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello")
    ctx = {"available_tools": ["Read", "Bash"]}
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    schema_bucket = next((b for b in result.buckets if b.key == "tool_schemas"), None)
    assert schema_bucket is not None
    # Now uses real SDK schemas, so precision is 'estimated' not 'heuristic'
    assert schema_bucket.precision == ValuePrecision.ESTIMATED
    assert schema_bucket.source == ValueSource.TOOL_LIST


# ── 6. local_instruction_context from system-reminder ──────────────────

def test_local_instruction_context_from_system_reminder():
    """local_instruction_context should use system_reminder_content from ctx."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello")
    ctx = {
        "system_reminder_content": "# CLAUDE.md\n\nYou are a helpful assistant.\n\n" * 10,
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    local_bucket = next((b for b in result.buckets if b.key == "local_instruction_context"), None)
    assert local_bucket is not None
    assert local_bucket.tokens > 0
    assert local_bucket.precision == ValuePrecision.HEURISTIC
    assert local_bucket.source == ValueSource.LOCAL_RULES


def test_local_instruction_from_local_instructions():
    """local_instruction_context should use local_instructions from ctx."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello")
    ctx = {
        "local_instructions": "Always use Python for code generation.\n" * 5,
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    local_bucket = next((b for b in result.buckets if b.key == "local_instruction_context"), None)
    assert local_bucket is not None
    assert local_bucket.tokens > 0


# ── 7. agent_subagent_prompt from fixture ──────────────────────────────

def test_agent_subagent_prompt_from_ctx():
    """agent_subagent_prompt should use agent_prompt_file or subagent_prompt from ctx."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello")
    ctx = {
        "subagent_prompt": "You are a code reviewer. Review the code for bugs.\n" * 5,
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    agent_bucket = next((b for b in result.buckets if b.key == "agent_subagent_prompt"), None)
    assert agent_bucket is not None
    assert agent_bucket.tokens > 0
    assert agent_bucket.source == ValueSource.LOCAL_RULES


# ── 8. hidden_builtin_system_estimate labeled heuristic, no fake content

def test_hidden_builtin_system_heuristic_label():
    """hidden_builtin_system_estimate should be heuristic with no fake content."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello")
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    builtin_bucket = next((b for b in result.buckets if b.key == "hidden_builtin_system_estimate"), None)
    assert builtin_bucket is not None
    assert builtin_bucket.precision == ValuePrecision.HEURISTIC
    assert builtin_bucket.source == ValueSource.HEURISTIC
    # Should NOT have actual content_preview
    assert builtin_bucket.content_preview == ""


# ── 9. unlocated_residual = total_input - located ──────────────────────

def test_unlocated_residual_equals_total_minus_located():
    """unlocated_residual should be total_input minus sum of all other buckets."""
    lc = _make_lc(input_tokens=8200, cache_read_tokens=5000, cache_write_tokens=500)
    ro = _make_ro(user_content="hello world")
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    total = result.total_input.value
    residual_bucket = next(b for b in result.buckets if b.key == "unlocated_residual")
    other_sum = sum(b.tokens for b in result.buckets if b.key != "unlocated_residual")

    assert residual_bucket.tokens == max(total - other_sum, 0)


# ── 10. located_rate = located / total_input ───────────────────────────

def test_located_rate_calculation():
    """Coverage (located_rate) should be located / total_input."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="hello world test message")
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    total = result.total_input.value
    if total > 0:
        located = sum(
            b.tokens for b in result.buckets
            if b.key != "unlocated_residual" and b.contributes_to_total
        )
        expected_coverage = min(located / total, 1.0)
        assert abs(result.coverage.value - expected_coverage) < 0.001


# ── Timing fields ──────────────────────────────────────────────────────

def test_timing_fields_present():
    """build_request should include timing dict with request_at, response_at, duration."""
    lc = _make_lc(input_tokens=10000, timestamp="2025-01-01T00:00:01Z")
    ro = _make_ro(user_content="hello")
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert hasattr(result, "timing")
    assert result.timing["request_at"] == "2025-01-01T00:00:01Z"
    assert result.timing["response_at"] == "—"
    assert result.timing["duration"] == "—"


# ── Bucket ordering ────────────────────────────────────────────────────

def test_bucket_order():
    """Buckets should be ordered by determinism from high to low, unlocated_residual last."""
    lc = _make_lc(input_tokens=10000, cache_read_tokens=5000)
    ro = _make_ro(user_content="hello")
    ctx = {"available_tools": ["Read"]}
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    keys = [b.key for b in result.buckets]
    assert keys[-1] == "unlocated_residual"

    # Check that current_user_message comes before unlocated_residual
    assert "current_user_message" in keys
    assert keys.index("current_user_message") < keys.index("unlocated_residual")
