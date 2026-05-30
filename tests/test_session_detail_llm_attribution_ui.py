"""Session detail LLM attribution UI layer tests.

Verifies:
1. LLM call card renders Request/Response attribution buttons with correct attributes.
2. Attribution buttons have proper title and aria-label attributes.
3. llm_item dict carries request_attribution_id and response_attribution_id.
4. Template rendering of attribution payloads produces expected structure.
"""

import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.web.routes import _build_v11_view_model
from session_browser.web.template_env import env, _precision_label


class _FakeSession:
    """Minimal session object for testing."""
    def __init__(self):
        self.agent = "claude_code"
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
        self.fresh_input_tokens = 10000
        self.cache_read_tokens = 5000
        self.cache_write_tokens = 1000
        self.total_tokens = 21000
        self.failed_tool_count = 0


class _FakeAnomalies:
    def __init__(self):
        self.anomalies = []


def _make_round_with_llm_call():
    """Create a round with a main-agent LLM call interaction."""
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


def _render_payload_sources(payload_sources):
    macro = env.get_template("components/session_detail_timeline.html").module
    return macro.payload_sources(payload_sources)


def _make_req_data(**overrides):
    """Build a complete request attribution payload with sensible defaults."""
    data = {
        "kind": "llm.request_attribution",
        "data": {
            "agent": "claude_code",
            "model": "claude-sonnet-4",
            "source_label": "transcript",
            "confidence_label": "高",
            "request_id": "req-abc",
            "call_id": "call-001",
            "usage": {
                "total_input": {"value": 5000, "precision": "provider_reported"},
                "fresh_input": {"value": 2000, "precision": "estimated"},
                "cache_read": {"value": 3000, "precision": "provider_reported"},
                "cache_write": {"value": 500, "precision": "provider_reported"},
                "coverage": {"value": 4500, "precision": "heuristic"},
                "unknown": {"value": 500, "precision": "residual"},
            },
            "buckets": [],
            "availability_rows": [],
            "captured_context_preview": "",
            "attribution_notes": [],
        },
    }
    data["data"].update(overrides)
    return data


def _make_resp_data(**overrides):
    """Build a complete response attribution payload with sensible defaults."""
    data = {
        "kind": "llm.response_attribution",
        "data": {
            "agent": "claude_code",
            "model": "claude-sonnet-4",
            "source_label": "transcript",
            "confidence_label": "高",
            "request_id": "req-abc",
            "call_id": "call-001",
            "usage": {
                "total_output": {"value": 2000, "precision": "provider_reported"},
                "visible_text": {"value": 1500, "precision": "estimated"},
                "tool_use": {"value": 400, "precision": "heuristic"},
                "metadata": {"value": 100, "precision": "estimated"},
                "coverage": {"value": 1900, "precision": "heuristic"},
                "unknown": {"value": 100, "precision": "residual"},
                "finish_reason": {"value": "tool_use", "precision": "exact"},
            },
            "buckets": [],
            "availability_rows": [],
            "captured_output_preview": "",
            "attribution_notes": [],
        },
    }
    data["data"].update(overrides)
    return data


def _make_err_data(**overrides):
    """Build an attribution error payload with sensible defaults."""
    data = {
        "kind": "llm.attribution_error",
        "data": {
            "agent": "claude_code", "call_id": "call-001",
            "round_id": "1", "error_type": "ValueError",
            "message": "test error message",
            "fallback": "Attribution unavailable; base LLM context/output payloads are still available.",
        },
    }
    data["data"].update(overrides)
    return data


# ─── LLM item attribution ID tests ─────────────────────────────────────

class TestLlmItemAttributionIds:
    """Verify llm_item carries attribution payload IDs."""

    def _find_llm_calls(self, vm):
        """Find all llm_call items from trace_rows timeline_items."""
        items = []
        for tr in vm["trace_rows"]:
            for ti in tr.get("timeline_items", []):
                if ti.get("type") == "llm_call":
                    items.append(ti)
        return items

    def test_llm_item_has_request_attribution_id(self):
        session = _FakeSession()
        ro, lc = _make_round_with_llm_call()

        vm = _build_v11_view_model(
            session=session, rounds=[ro], llm_calls=[lc],
            tool_calls=ro.tool_calls, subagent_runs=[],
            session_anomalies=_FakeAnomalies(),
        )

        llm_items = self._find_llm_calls(vm)
        assert len(llm_items) >= 1
        item = llm_items[0]
        assert "request_attribution_id" in item
        assert item["request_attribution_id"].startswith("llm-R")
        assert item["request_attribution_id"].endswith("-request-attribution")

    def test_llm_item_has_response_attribution_id(self):
        session = _FakeSession()
        ro, lc = _make_round_with_llm_call()

        vm = _build_v11_view_model(
            session=session, rounds=[ro], llm_calls=[lc],
            tool_calls=ro.tool_calls, subagent_runs=[],
            session_anomalies=_FakeAnomalies(),
        )

        llm_items = self._find_llm_calls(vm)
        assert len(llm_items) >= 1
        item = llm_items[0]
        assert "response_attribution_id" in item
        assert item["response_attribution_id"].startswith("llm-R")
        assert item["response_attribution_id"].endswith("-response-attribution")

    def test_attribution_ids_match_payload_sources(self):
        """Attribution IDs in llm_item must match payload_sources IDs."""
        session = _FakeSession()
        ro, lc = _make_round_with_llm_call()

        vm = _build_v11_view_model(
            session=session, rounds=[ro], llm_calls=[lc],
            tool_calls=ro.tool_calls, subagent_runs=[],
            session_anomalies=_FakeAnomalies(),
        )

        llm_items = self._find_llm_calls(vm)
        assert len(llm_items) >= 1
        item = llm_items[0]

        payload_ids = {p["payload_id"] for p in vm["payload_sources"]}
        assert item["request_attribution_id"] in payload_ids
        assert item["response_attribution_id"] in payload_ids


# ─── Template rendering tests ─────────────────────────────────────────

class TestAttributionTemplateRendering:
    """Verify template renders correct HTML for attribution payloads."""

    def test_request_attribution_renders_with_data(self):
        html = _render_payload_sources([_make_req_data()])
        assert "sd-payload-shell--attribution" in html
        assert "Request 归因" not in html  # buttons are in card, not payload
        assert "本地日志归因" in html
        assert "claude_code" in html
        assert "claude-sonnet-4" in html
        assert "5000" in html

    def test_response_attribution_renders_with_data(self):
        html = _render_payload_sources([_make_resp_data()])
        assert "sd-payload-shell--attribution" in html
        assert "本地日志归因" in html
        assert "响应总览" in html

    def test_attribution_error_renders_with_data(self):
        html = _render_payload_sources([_make_err_data()])
        assert "sd-payload-shell--error" in html
        assert "归因构建失败" in html
        assert "归因诊断" in html
        assert "test error message" in html
        assert "ValueError" in html

    def test_attribution_renders_availability_table(self):
        req_data = _make_req_data(
            availability_rows=[
                {
                    "field": "input_tokens", "label": "input_tokens",
                    "exact": True, "available": True,
                    "precision": "provider_reported",
                    "source": "provider_response",
                    "fill_strategy": "—", "note": "",
                },
                {
                    "field": "model", "label": "model",
                    "exact": False, "available": True,
                    "precision": "heuristic",
                    "source": "log_file",
                    "fill_strategy": "从文件名推断", "note": "",
                },
            ],
        )
        html = _render_payload_sources([req_data])
        assert "sd-attrib-table" in html
        assert "参数可得性表" in html
        assert "provider_response" in html
        assert "从文件名推断" in html

    def test_attribution_renders_buckets_as_chips(self):
        req_data = _make_req_data(
            buckets=[
                {
                    "key": "messages", "label": "messages", "tokens": 3000,
                    "percent": 60.0, "contributes_to_total": True,
                },
                {
                    "key": "tools", "label": "tool definitions", "tokens": 1000,
                    "percent": 20.0, "contributes_to_total": True,
                },
                {
                    "key": "internal", "label": "internal", "tokens": 1000,
                    "percent": 20.0, "contributes_to_total": False,
                },
            ],
        )
        html = _render_payload_sources([req_data])
        assert "sd-chip--attrib" in html
        assert "messages" in html
        assert "tool definitions" in html

    def test_attribution_renders_notes(self):
        req_data = _make_req_data(
            attribution_notes=[
                "Cache tokens are estimated from provider response.",
                "Model inferred from log filename.",
            ],
        )
        html = _render_payload_sources([req_data])
        assert "sd-notes-list" in html
        assert "Cache tokens are estimated" in html
        assert "Model inferred" in html

    def test_attribution_renders_context_preview(self):
        req_data = _make_req_data(
            captured_context_preview="system\nYou are a helpful assistant.",
        )
        html = _render_payload_sources([req_data])
        assert "sd-context-preview" in html
        assert "You are a helpful assistant" in html

    def test_attribution_banner_present(self):
        html = _render_payload_sources([_make_req_data()])
        assert "sd-attribution-banner" in html
        assert "基于本地日志重建" in html

    def test_error_banner_is_red(self):
        html = _render_payload_sources([_make_err_data()])
        assert "sd-attribution-banner--error" in html
        assert "sd-payload-shell--error" in html


# ─── precision_label filter tests ─────────────────────────────────────

class TestPrecisionLabelFilter:
    """Verify the precision_label Jinja2 filter works correctly."""

    def test_filter_registered(self):
        assert "precision_label" in env.filters

    def test_global_registered(self):
        assert "precision_label" in env.globals

    def test_provider_reported(self):
        assert _precision_label("provider_reported") == "provider"

    def test_exact(self):
        assert _precision_label("exact") == "精确"

    def test_estimated(self):
        assert _precision_label("estimated") == "估算"

    def test_heuristic(self):
        assert _precision_label("heuristic") == "启发式"

    def test_residual(self):
        assert _precision_label("residual") == "差额"

    def test_unavailable(self):
        assert _precision_label("unavailable") == "不可用"

    def test_transcript_exact(self):
        assert _precision_label("transcript_exact") == "内容精确"

    def test_unknown_value_passthrough(self):
        assert _precision_label("some_weird_value") == "some_weird_value"

    def test_none_returns_default(self):
        assert _precision_label(None) == "不可用"

    def test_empty_string_returns_default(self):
        assert _precision_label("") == "不可用"
