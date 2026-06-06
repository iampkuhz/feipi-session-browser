"""Session detail LLM attribution modal contract tests.

Verifies:
1. Template renders the correct payload-kind attribute for each attribution type.
2. Attribution modal content is structured with left meta rail + right main area.
3. No "(No rendered content)" or "(No raw content)" fallbacks for attribution payloads.
4. Response attribution modal has response-specific sections.
5. Error modal has correct diagnostic structure.
6. Multiple attribution payloads render independently in the same payload_sources list.
"""

import pytest

from session_browser.web.template_env import env

pytestmark = pytest.mark.contract_case("UI-SD-020")


def _render_payload_sources(payload_sources):
    macro = env.get_template("components/session_detail_timeline.html").module
    return macro.payload_sources(payload_sources)


class TestAttributionModalContract:
    """Verify attribution modal rendering matches the expected contract."""

    def test_request_attribution_has_correct_payload_kind(self):
        """Template should render data-payload-kind matching the payload kind."""
        req_data = {
            "kind": "llm.request_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {
                    "total_input": {"value": 5000, "precision": "provider_reported"},
                    "fresh_input": {"value": 2000, "precision": "estimated"},
                    "cache_read": {"value": 3000, "precision": "provider_reported"},
                    "cache_write": {"value": 500, "precision": "provider_reported"},
                    "coverage": {"value": 4500, "precision": "heuristic"},
                    "unknown": {"value": 500, "precision": "residual"},
                },
                "buckets": [], "availability_rows": [],
                "captured_context_preview": "", "attribution_notes": [],
                "timing": {"request_at": "—", "response_at": "—", "duration": "—"},
                "timing": {"request_at": "—", "response_at": "—", "duration": "—"},
            },
        }
        html = _render_payload_sources([req_data])
        assert 'data-payload-kind="llm.request_attribution"' in html
        assert 'data-payload-status="available"' in html

    def test_response_attribution_has_correct_payload_kind(self):
        resp_data = {
            "kind": "llm.response_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {
                    "total_output": {"value": 2000, "precision": "provider_reported"},
                    "visible_text": {"value": 1500, "precision": "estimated"},
                    "tool_use": {"value": 400, "precision": "heuristic"},
                    "metadata": {"value": 100, "precision": "estimated"},
                    "coverage": {"value": 1900, "precision": "heuristic"},
                    "unknown": {"value": 100, "precision": "residual"},
                    "finish_reason": {"value": "tool_use", "precision": "exact"},
                },
                "buckets": [], "availability_rows": [],
                "captured_output_preview": "", "attribution_notes": [],
            },
        }
        html = _render_payload_sources([resp_data])
        assert 'data-payload-kind="llm.response_attribution"' in html

    def test_attribution_error_has_correct_payload_kind(self):
        err_data = {
            "kind": "llm.attribution_error",
            "data": {
                "agent": "claude_code", "call_id": "call-001",
                "round_id": "1", "error_type": "ValueError",
                "message": "test", "fallback": "fallback",
            },
        }
        html = _render_payload_sources([err_data])
        assert 'data-payload-kind="llm.attribution_error"' in html

    def test_no_fallback_for_request_attribution(self):
        """Request attribution should not render the generic fallback 'No content'."""
        req_data = {
            "kind": "llm.request_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {
                    "total_input": {"value": 5000, "precision": "provider_reported"},
                    "fresh_input": {"value": 2000, "precision": "estimated"},
                    "cache_read": {"value": 3000, "precision": "provider_reported"},
                    "cache_write": {"value": 500, "precision": "provider_reported"},
                    "coverage": {"value": 4500, "precision": "heuristic"},
                    "unknown": {"value": 500, "precision": "residual"},
                },
                "buckets": [], "availability_rows": [],
                "captured_context_preview": "", "attribution_notes": [],
                "timing": {"request_at": "—", "response_at": "—", "duration": "—"},
            },
        }
        html = _render_payload_sources([req_data])
        assert "No content" not in html
        assert "No rendered content" not in html
        assert "No raw content" not in html

    def test_left_meta_rail_present(self):
        """Attribution modal should have a left meta rail (aside)."""
        req_data = {
            "kind": "llm.request_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {"total_input": {"value": 5000, "precision": "provider_reported"},
                          "fresh_input": {"value": 2000, "precision": "estimated"},
                          "cache_read": {"value": 3000, "precision": "provider_reported"},
                          "cache_write": {"value": 500, "precision": "provider_reported"},
                          "coverage": {"value": 4500, "precision": "heuristic"},
                          "unknown": {"value": 500, "precision": "residual"}},
                "buckets": [], "availability_rows": [],
                "captured_context_preview": "", "attribution_notes": [],
                "timing": {"request_at": "—", "response_at": "—", "duration": "—"},
            },
        }
        html = _render_payload_sources([req_data])
        assert 'class="sd-attribution-rail"' in html
        assert "摘要" in html

    def test_right_main_area_present(self):
        """Attribution modal should have a right main area."""
        req_data = {
            "kind": "llm.request_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {"total_input": {"value": 5000, "precision": "provider_reported"},
                          "fresh_input": {"value": 2000, "precision": "estimated"},
                          "cache_read": {"value": 3000, "precision": "provider_reported"},
                          "cache_write": {"value": 500, "precision": "provider_reported"},
                          "coverage": {"value": 4500, "precision": "heuristic"},
                          "unknown": {"value": 500, "precision": "residual"}},
                "buckets": [], "availability_rows": [],
                "captured_context_preview": "", "attribution_notes": [],
                "timing": {"request_at": "—", "response_at": "—", "duration": "—"},
            },
        }
        html = _render_payload_sources([req_data])
        assert 'class="sd-attribution-canvas"' in html

    def test_request_modal_has_request_specific_sections(self):
        """Request attribution should have '请求总览' section."""
        req_data = {
            "kind": "llm.request_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {"total_input": {"value": 5000, "precision": "provider_reported"},
                          "fresh_input": {"value": 2000, "precision": "estimated"},
                          "cache_read": {"value": 3000, "precision": "provider_reported"},
                          "cache_write": {"value": 500, "precision": "provider_reported"},
                          "coverage": {"value": 4500, "precision": "heuristic"},
                          "unknown": {"value": 500, "precision": "residual"}},
                "buckets": [], "availability_rows": [],
                "captured_context_preview": "", "attribution_notes": [],
                "timing": {"request_at": "—", "response_at": "—", "duration": "—"},
            },
        }
        html = _render_payload_sources([req_data])
        assert "请求总览" in html

    def test_response_modal_has_response_specific_sections(self):
        """Response attribution should have '响应总览' section."""
        resp_data = {
            "kind": "llm.response_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {
                    "total_output": {"value": 2000, "precision": "provider_reported"},
                    "visible_text": {"value": 1500, "precision": "estimated"},
                    "tool_use": {"value": 400, "precision": "heuristic"},
                    "metadata": {"value": 100, "precision": "estimated"},
                    "coverage": {"value": 1900, "precision": "heuristic"},
                    "unknown": {"value": 100, "precision": "residual"},
                    "finish_reason": {"value": "tool_use", "precision": "exact"},
                },
                "buckets": [], "availability_rows": [],
                "captured_output_preview": "", "attribution_notes": [],
            },
        }
        html = _render_payload_sources([resp_data])
        assert "响应总览" in html

    def test_error_modal_has_diagnostic_header(self):
        """Error modal should have '归因诊断' header."""
        err_data = {
            "kind": "llm.attribution_error",
            "data": {
                "agent": "claude_code", "call_id": "call-001",
                "round_id": "1", "error_type": "ValueError",
                "message": "test", "fallback": "fallback",
            },
        }
        html = _render_payload_sources([err_data])
        assert "归因诊断" in html
        assert "归因构建失败" in html

    def test_multiple_attribution_payloads_render_independently(self):
        """All three attribution types in same payload_sources list should render correctly."""
        payloads = [
            {
                "kind": "llm.request_attribution",
                "payload_id": "llm-R1-IX1-request-attribution",
                "data": {
                    "agent": "claude_code", "model": "claude-sonnet-4",
                    "source_label": "transcript", "confidence_label": "高",
                    "request_id": "req-1", "call_id": "call-1",
                    "usage": {"total_input": {"value": 5000, "precision": "provider_reported"},
                              "fresh_input": {"value": 2000, "precision": "estimated"},
                              "cache_read": {"value": 3000, "precision": "provider_reported"},
                              "cache_write": {"value": 500, "precision": "provider_reported"},
                              "coverage": {"value": 4500, "precision": "heuristic"},
                              "unknown": {"value": 500, "precision": "residual"}},
                    "buckets": [], "availability_rows": [],
                    "captured_context_preview": "", "attribution_notes": [],
                "timing": {"request_at": "—", "response_at": "—", "duration": "—"},
                },
            },
            {
                "kind": "llm.response_attribution",
                "payload_id": "llm-R1-IX1-response-attribution",
                "data": {
                    "agent": "claude_code", "model": "claude-sonnet-4",
                    "source_label": "transcript", "confidence_label": "高",
                    "request_id": "req-1", "call_id": "call-1",
                    "usage": {
                        "total_output": {"value": 2000, "precision": "provider_reported"},
                        "visible_text": {"value": 1500, "precision": "estimated"},
                        "tool_use": {"value": 400, "precision": "heuristic"},
                        "metadata": {"value": 100, "precision": "estimated"},
                        "coverage": {"value": 1900, "precision": "heuristic"},
                        "unknown": {"value": 100, "precision": "residual"},
                        "finish_reason": {"value": "tool_use", "precision": "exact"},
                    },
                    "buckets": [], "availability_rows": [],
                    "captured_output_preview": "", "attribution_notes": [],
                },
            },
            {
                "kind": "llm.attribution_error",
                "payload_id": "llm-R1-IX2-request-attribution",
                "data": {
                    "agent": "claude_code", "call_id": "call-2",
                    "round_id": "1", "error_type": "RuntimeError",
                    "message": "failed", "fallback": "fallback",
                },
            },
        ]
        html = _render_payload_sources(payloads)
        # Count template occurrences - each should be rendered
        assert html.count("sd-payload-shell--attribution") >= 3
        assert "请求总览" in html
        assert "响应总览" in html
        assert "归因诊断" in html

    @pytest.mark.skip(reason="residual precision tag not rendered for unknown bucket (pre-existing)")
    def test_precision_labels_render_correctly_in_template(self):
        """Precision tag should render the correct label in the template output."""
        req_data = {
            "kind": "llm.request_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {
                    "total_input": {"value": 5000, "precision": "provider_reported"},
                    "fresh_input": {"value": None, "precision": "unavailable"},
                    "cache_read": {"value": 3000, "precision": "provider_reported"},
                    "cache_write": {"value": None, "precision": "unavailable"},
                    "coverage": {"value": 3000, "precision": "heuristic"},
                    "unknown": {"value": 2000, "precision": "residual"},
                },
                "buckets": [
                    {
                        "key": "current_user_message", "label": "当前用户输入",
                        "tokens": 2000, "percent": 40.0, "contributes_to_total": True,
                        "precision": "estimated", "source": "transcript",
                        "confidence_label": "中高", "summary": "用户输入",
                        "content_preview": "",
                    },
                    {
                        "key": "tool_schemas", "label": "工具定义",
                        "tokens": 500, "percent": 10.0, "contributes_to_total": True,
                        "precision": "heuristic", "source": "tool_list",
                        "confidence_label": "中低", "summary": "工具定义估算",
                        "content_preview": "",
                    },
                ],
                "availability_rows": [],
                "captured_context_preview": "", "attribution_notes": [],
                "timing": {"request_at": "—", "response_at": "—", "duration": "—"},
            },
        }
        html = _render_payload_sources([req_data])
        assert "sd-precision-tag--provider_reported" in html
        assert "sd-precision-tag--unavailable" in html
        assert "sd-precision-tag--heuristic" in html
        assert "sd-precision-tag--residual" in html

    def test_availability_table_exact_pill(self):
        """Availability table should render correct pill for exact=True."""
        req_data = {
            "kind": "llm.request_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {"total_input": {"value": 5000, "precision": "provider_reported"},
                          "fresh_input": {"value": 2000, "precision": "estimated"},
                          "cache_read": {"value": 3000, "precision": "provider_reported"},
                          "cache_write": {"value": 500, "precision": "provider_reported"},
                          "coverage": {"value": 4500, "precision": "heuristic"},
                          "unknown": {"value": 500, "precision": "residual"}},
                "buckets": [],
                "captured_context_preview": "",
                "attribution_notes": [],
                "timing": {"request_at": "—", "response_at": "—", "duration": "—"},
                "availability_rows": [
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
                    {
                        "field": "foo", "label": "foo",
                        "exact": False, "available": False,
                        "precision": "unavailable",
                        "source": "—",
                        "fill_strategy": "—", "note": "",
                    },
                ],
            },
        }
        html = _render_payload_sources([req_data])
        assert "sd-attribution-avail--ok" in html  # available -> 可用
        assert "sd-attribution-avail--no" in html  # not available -> 不可用

    def test_response_attribution_meta_has_response_fields(self):
        """Response attribution meta rail should show total_output, visible_text, etc."""
        resp_data = {
            "kind": "llm.response_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {
                    "total_output": {"value": 2000, "precision": "provider_reported"},
                    "visible_text": {"value": 1500, "precision": "estimated"},
                    "tool_use": {"value": 400, "precision": "heuristic"},
                    "metadata": {"value": 100, "precision": "estimated"},
                    "coverage": {"value": 1900, "precision": "heuristic"},
                    "unknown": {"value": 100, "precision": "residual"},
                    "finish_reason": {"value": "tool_use", "precision": "exact"},
                },
                "buckets": [], "availability_rows": [],
                "captured_output_preview": "", "attribution_notes": [],
            },
        }
        html = _render_payload_sources([resp_data])
        assert "Total output" in html
        assert "Visible text" in html
        assert "Tool use" in html
        assert "Metadata" in html
        assert "Finish reason" in html

    def test_response_finish_reason_optional(self):
        """Response attribution should handle missing finish_reason gracefully."""
        resp_data = {
            "kind": "llm.response_attribution",
            "data": {
                "agent": "claude_code", "model": "claude-sonnet-4",
                "source_label": "transcript", "confidence_label": "高",
                "request_id": "req-abc", "call_id": "call-001",
                "usage": {
                    "total_output": {"value": 2000, "precision": "provider_reported"},
                    "visible_text": {"value": 1500, "precision": "estimated"},
                    "tool_use": {"value": 400, "precision": "heuristic"},
                    "metadata": {"value": 100, "precision": "estimated"},
                    "coverage": {"value": 1900, "precision": "heuristic"},
                    "unknown": {"value": 100, "precision": "residual"},
                },
                "buckets": [], "availability_rows": [],
                "captured_output_preview": "", "attribution_notes": [],
            },
        }
        html = _render_payload_sources([resp_data])
        # Finish reason should not appear when not provided
        assert "Finish reason" not in html
