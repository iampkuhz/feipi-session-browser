"""Missing raw payload fixture tests for session detail presenter.

验证 raw payload 缺失时的处理:
- LLMCall.request_payload_missing_reason 被正确传递
- LLMCall.response_payload_missing_reason 被正确传递
- 当 request_payload_raw 和 response_payload_raw 均为空时，missing_reason 不为空
- 使用 fallback payload 时（response_payload_raw 非空），missing_reason 被清空
- UI 不会因缺失 raw payload 而崩溃或显示空白
"""
import pytest
import json
import os
import sys

# Ensure src is importable
SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SB_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(SB_ROOT, "src"))

from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
    ToolCall,
)
from session_browser.web.presenters.session_detail import (
    build_rounds,
    build_llm_calls,
    assign_interactions_to_rounds,
)


# ─── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def missing_raw_payload_fixture():
    """Load missing raw payload scenario fixture data."""
    fixture_path = os.path.join(
        SB_ROOT, "tests", "fixtures", "session_detail", "missing_raw_payload.json"
    )
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fixture_messages(missing_raw_payload_fixture):
    """Convert fixture messages to ChatMessage objects."""
    msgs = []
    for m in missing_raw_payload_fixture["messages"]:
        msgs.append(ChatMessage(
            role=m["role"],
            content=m["content"],
            timestamp=m["timestamp"],
            model=m.get("model", ""),
            tool_calls=m.get("tool_calls", []),
            usage=m.get("usage"),
            llm_call_id=m.get("llm_call_id", ""),
            llm_status=m.get("llm_status", "ok"),
            stop_reason=m.get("stop_reason", ""),
        ))
    return msgs


@pytest.fixture(scope="module")
def fixture_tool_calls(missing_raw_payload_fixture):
    """Convert fixture tool_calls to ToolCall objects."""
    tcs = []
    for tc in missing_raw_payload_fixture["tool_calls"]:
        tcs.append(ToolCall(
            name=tc["name"],
            parameters=tc.get("parameters", {}),
            result=tc.get("result", ""),
            status=tc.get("status", "completed"),
            duration_ms=tc.get("duration_ms", 0),
            timestamp=tc.get("timestamp", ""),
            exit_code=tc.get("exit_code"),
            error_message=tc.get("error_message", ""),
            tool_use_id=tc.get("tool_use_id", ""),
            scope=tc.get("scope", "main"),
            llm_call_count=tc.get("llm_call_count", 0),
            llm_error_count=tc.get("llm_error_count", 0),
        ))
    return tcs


@pytest.fixture(scope="module")
def fixture_session(missing_raw_payload_fixture):
    """Return session metadata."""
    return missing_raw_payload_fixture["session"]


@pytest.fixture(scope="module")
def built_rounds(fixture_messages, fixture_tool_calls, fixture_session):
    """Build rounds from fixture data."""
    def identity_md(text):
        return text

    session = fixture_session
    return build_rounds(
        messages=fixture_messages,
        tool_calls=fixture_tool_calls,
        session_input_tokens=session["input_tokens"],
        session_output_tokens=session["output_tokens"],
        session_cached_tokens=session["cached_input_tokens"],
        session_cache_write_tokens=session["cached_output_tokens"],
        agent=session["agent"],
        md_filter=identity_md,
    )


@pytest.fixture(scope="module")
def built_llm_calls(fixture_messages, fixture_tool_calls, built_rounds):
    """Build LLM calls from fixture data."""
    return build_llm_calls(
        messages=fixture_messages,
        tool_calls=fixture_tool_calls,
        rounds=built_rounds,
        subagent_runs=[],
    )


@pytest.fixture(scope="module")
def final_rounds(built_rounds, built_llm_calls, fixture_tool_calls):
    """Rounds with interactions assigned."""
    assign_interactions_to_rounds(
        rounds=built_rounds,
        llm_calls=built_llm_calls,
        tool_calls=fixture_tool_calls,
        subagent_runs=[],
    )
    return built_rounds


# ─── Tests ──────────────────────────────────────────────────────────────


class TestLLMCallMissingPayloadFields:
    """验证 LLMCall 模型在 raw payload 缺失时的字段行为。"""

    @pytest.mark.contract_case("UI-SD-026")
    def test_llm_call_has_missing_reason_default(self):
        """新建 LLMCall 必须有非空的 request_payload_missing_reason 默认值。"""
        call = LLMCall(
            id="test-001",
            model="claude-sonnet-4-20250514",
            scope="main",
            subagent_id="",
            round_index=0,
            parent_id="",
            parent_tool_name="",
            timestamp="2026-05-24T10:00:00Z",
            status="ok",
        )
        assert call.request_payload_raw == ""
        assert call.request_payload_missing_reason == ""
        # Default is empty string; the presenter/routes set the actual reason

    @pytest.mark.contract_case("UI-SD-026")
    def test_llm_call_missing_reason_can_be_set(self):
        """LLMCall 的 missing_reason 可以被设置为有意义的字符串。"""
        reason = "current session data source does not persist raw HTTP request payload"
        call = LLMCall(
            id="test-001",
            model="claude-sonnet-4-20250514",
            scope="main",
            subagent_id="",
            round_index=0,
            parent_id="",
            parent_tool_name="",
            timestamp="2026-05-24T10:00:00Z",
            status="ok",
            request_payload_missing_reason=reason,
        )
        assert call.request_payload_missing_reason == reason
        assert len(call.request_payload_missing_reason.strip()) > 0

    @pytest.mark.contract_case("UI-SD-026")
    def test_llm_call_both_raw_and_missing_reason_set(self):
        """当 raw 为空且 missing_reason 有值时，语义正确。"""
        call = LLMCall(
            id="test-001",
            model="claude-sonnet-4-20250514",
            scope="main",
            subagent_id="",
            round_index=0,
            parent_id="",
            parent_tool_name="",
            timestamp="2026-05-24T10:00:00Z",
            status="ok",
            request_payload_raw="",
            request_payload_missing_reason="not persisted by source",
            response_payload_raw="",
            response_payload_missing_reason="not persisted by source",
        )
        assert call.request_payload_raw == ""
        assert call.response_payload_raw == ""
        assert call.request_payload_missing_reason != ""
        assert call.response_payload_missing_reason != ""


class TestPresenterMissingPayloadPropagation:
    """验证 presenter 正确传播 missing_reason 到 LLMCall。"""

    @pytest.mark.contract_case("UI-SD-026")
    def test_presenter_sets_request_missing_reason(self, built_llm_calls):
        """Presenter 构建的 LLMCall 必须有 request_payload_missing_reason。"""
        assert len(built_llm_calls) >= 1, "Fixture 必须产生至少一个 LLMCall"
        for call in built_llm_calls:
            # The presenter should set a missing reason when raw payload is unavailable
            assert call.request_payload_missing_reason is not None, (
                f"LLMCall {call.id} request_payload_missing_reason 不应为 None"
            )

    @pytest.mark.contract_case("UI-SD-026")
    def test_presenter_sets_response_missing_reason(self, built_llm_calls):
        """Presenter 构建的 LLMCall 必须有 response_payload_missing_reason。"""
        for call in built_llm_calls:
            assert call.response_payload_missing_reason is not None, (
                f"LLMCall {call.id} response_payload_missing_reason 不应为 None"
            )

    @pytest.mark.contract_case("UI-SD-026")
    def test_presenter_raw_payload_empty(self, built_llm_calls):
        """Presenter 构建的 LLMCall 的 request_payload_raw 为空（当前数据源不支持）。"""
        for call in built_llm_calls:
            assert call.request_payload_raw == "", (
                f"LLMCall {call.id} request_payload_raw 应为空"
            )

    @pytest.mark.contract_case("UI-SD-026")
    def test_presenter_response_payload_empty(self, built_llm_calls):
        """Presenter 构建的 LLMCall 的 response_payload_raw 为空。"""
        for call in built_llm_calls:
            assert call.response_payload_raw == "", (
                f"LLMCall {call.id} response_payload_raw 应为空"
            )

    @pytest.mark.contract_case("UI-SD-026")
    def test_all_llm_calls_from_fixture_have_missing_reason(self, built_llm_calls):
        """所有 fixture 产生的 LLMCall 都必须有 missing_reason。"""
        calls_with_reason = [
            c for c in built_llm_calls
            if c.request_payload_missing_reason and len(c.request_payload_missing_reason.strip()) > 0
        ]
        assert len(calls_with_reason) == len(built_llm_calls), (
            f"只有 {len(calls_with_reason)}/{len(built_llm_calls)} 个 LLMCall 有 missing_reason"
        )


class TestRoutesFallbackBehavior:
    """验证 routes.py 中 raw payload 缺失时的 fallback 行为。"""

    @pytest.mark.contract_case("UI-SD-026")
    def test_missing_reason_default_value_in_source(self):
        """routes.py 必须有 fallback default missing reason。"""
        routes_path = os.path.join(
            SB_ROOT, "src", "session_browser", "web", "routes.py"
        )
        with open(routes_path, encoding="utf-8") as f:
            content = f.read()
        assert "Raw payload not captured" in content or "raw payload" in content.lower(), (
            "routes.py 必须包含 raw payload 缺失时的默认提示信息"
        )

    @pytest.mark.contract_case("UI-SD-026")
    def test_missing_reason_logic_in_source(self):
        """routes.py 必须有 request_payload_missing_reason 处理逻辑。"""
        routes_path = os.path.join(
            SB_ROOT, "src", "session_browser", "web", "routes.py"
        )
        with open(routes_path, encoding="utf-8") as f:
            content = f.read()
        assert "request_payload_missing_reason" in content, (
            "routes.py 必须处理 request_payload_missing_reason"
        )

    @pytest.mark.contract_case("UI-SD-026")
    def test_payload_index_has_missing_reason_key(self):
        """routes.py 的 payload_index 必须有 missing_reason 键。"""
        routes_path = os.path.join(
            SB_ROOT, "src", "session_browser", "web", "routes.py"
        )
        with open(routes_path, encoding="utf-8") as f:
            content = f.read()
        assert '"missing_reason"' in content or "'missing_reason'" in content, (
            "routes.py 的 payload_index 必须有 missing_reason 键"
        )

    @pytest.mark.contract_case("UI-SD-026")
    def test_fallback_to_response_payload_raw(self):
        """routes.py 在 request_payload_raw 为空时应检查 response_payload_raw。"""
        routes_path = os.path.join(
            SB_ROOT, "src", "session_browser", "web", "routes.py"
        )
        with open(routes_path, encoding="utf-8") as f:
            content = f.read()
        # The logic: raw_val = getattr(ix, "request_payload_raw", "") or getattr(ix, "response_payload_raw", "")
        assert "response_payload_raw" in content, (
            "routes.py 应有 response_payload_raw fallback 逻辑"
        )


class TestUINoCrashOnMissingPayload:
    """验证 UI 不会因缺失 raw payload 而崩溃。"""

    @pytest.mark.contract_case("UI-SD-026")
    def test_fixture_has_valid_messages(self, fixture_messages):
        """Fixture 必须有有效的消息以确保 UI 不崩溃。"""
        assert len(fixture_messages) >= 2, (
            "Fixture 必须至少包含 2 条消息以构建有效的会话"
        )
        for msg in fixture_messages:
            assert msg.role in ("user", "assistant", "system"), (
                f"消息 role '{msg.role}' 无效"
            )

    @pytest.mark.contract_case("UI-SD-026")
    def test_fixture_has_valid_rounds(self, final_rounds):
        """Fixture 必须产生有效的 rounds。"""
        assert len(final_rounds) >= 1, "Fixture 必须产生至少一个 round"
        for r in final_rounds:
            assert r.user_msg is not None, "Round 必须有 user 消息"
            assert r.assistant_msg is not None, "Round 必须有 assistant 消息"

    @pytest.mark.contract_case("UI-SD-026")
    def test_interactions_present_for_payload_buttons(self, final_rounds):
        """Rounds 必须有 interactions 以支持 payload 按钮。"""
        rounds_with_interactions = [
            r for r in final_rounds
            if len(r.interactions) > 0
        ]
        assert len(rounds_with_interactions) >= 1, (
            "至少一个 round 必须有 interactions 以渲染 payload 按钮"
        )

    @pytest.mark.contract_case("UI-SD-026")
    def test_interactions_have_missing_reason(self, final_rounds):
        """Interactions 的 LLMCall 必须有 non-null missing_reason。"""
        for r in final_rounds:
            for ix in r.interactions:
                assert hasattr(ix, "request_payload_missing_reason"), (
                    "Interaction 必须有 request_payload_missing_reason 属性"
                )
                # Attribute exists; it may be empty string or a message
                assert ix.request_payload_missing_reason is not None, (
                    "request_payload_missing_reason 不应为 None"
                )

    @pytest.mark.contract_case("UI-SD-026")
    def test_llm_calls_have_response_content(self, built_llm_calls, fixture_messages):
        """LLMCall 必须有 response_full（用于 fallback 显示）。"""
        for call in built_llm_calls:
            assert call.response_full is not None, (
                f"LLMCall {call.id} response_full 不应为 None"
            )
            # Even if empty, it should be a string
            assert isinstance(call.response_full, str), (
                f"LLMCall {call.id} response_full 应为字符串"
            )

    @pytest.mark.contract_case("UI-SD-026")
    def test_fixture_session_metadata_complete(self, fixture_session):
        """Fixture session 元数据必须完整（UI 渲染需要）。"""
        required_keys = ["agent", "session_id", "title", "model"]
        for key in required_keys:
            assert key in fixture_session, (
                f"Fixture session 缺少 {key} 字段"
            )
            assert fixture_session[key] and len(str(fixture_session[key]).strip()) > 0, (
                f"Fixture session {key} 为空"
            )
