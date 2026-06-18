"""Payload contract tests：验证 v2 serializer 输出符合预期 contract。"""

from __future__ import annotations

import pytest
from session_browser.attribution.contracts import (
    AttributedValue,
    LLMRequestAttribution,
    LLMResponseAttribution,
    RequestAttributionBucket,
    ResponseAttributionBucket,
    ValuePrecision,
    ValueSource,
)
from session_browser.attribution.serializers import (
    request_attribution_to_payload,
    response_attribution_to_payload,
    attributed_value_to_dict,
)


def _make_request_attribution() -> LLMRequestAttribution:
    """构建最小 request attribution 用于测试。"""
    return LLMRequestAttribution(
        agent="claude_code",
        model="claude-sonnet-4-20250514",
        request_id="test-req-001",
        call_id="test-call-001",
        source_label="provider",
        confidence_label="高",
        raw_body_available=True,
        total_input=AttributedValue(
            value=1000, unit="tokens", precision=ValuePrecision.PROVIDER_REPORTED,
            source=ValueSource.PROVIDER_USAGE, fill_strategy="provider",
        ),
        fresh_input=AttributedValue(
            value=600, unit="tokens", precision=ValuePrecision.PROVIDER_REPORTED,
            source=ValueSource.PROVIDER_USAGE, fill_strategy="provider",
        ),
        cache_read=AttributedValue(
            value=400, unit="tokens", precision=ValuePrecision.PROVIDER_REPORTED,
            source=ValueSource.PROVIDER_USAGE, fill_strategy="provider",
        ),
        cache_write=AttributedValue(
            value=0, unit="tokens", precision=ValuePrecision.PROVIDER_REPORTED,
            source=ValueSource.PROVIDER_USAGE, fill_strategy="provider",
        ),
        coverage=AttributedValue(
            value=0.9, unit="ratio", precision=ValuePrecision.ESTIMATED,
            source=ValueSource.HEURISTIC, fill_strategy="buckets/total",
        ),
        unknown=AttributedValue(
            value=100, unit="tokens", precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL, fill_strategy="total - known",
        ),
        buckets=[
            RequestAttributionBucket(
                key="current_user_prompt", label="当前用户输入",
                tokens=200, percent=20.0, precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT, confidence_label="高",
                summary="用户 prompt", contributes_to_total=True,
            ),
        ],
        captured_context_preview="test preview",
        attribution_notes=["test note"],
        availability_rows=[],
    )


def _make_response_attribution() -> LLMResponseAttribution:
    """构建最小 response attribution 用于测试。"""
    return LLMResponseAttribution(
        agent="claude_code",
        model="claude-sonnet-4-20250514",
        request_id="test-req-001",
        call_id="test-call-001",
        source_label="provider",
        confidence_label="高",
        raw_body_available=True,
        total_output=AttributedValue(
            value=500, unit="tokens", precision=ValuePrecision.PROVIDER_REPORTED,
            source=ValueSource.PROVIDER_USAGE, fill_strategy="provider",
        ),
        visible_text=AttributedValue(
            value=300, unit="tokens", precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TRANSCRIPT, fill_strategy="text estimate",
        ),
        tool_use=AttributedValue(
            value=100, unit="tokens", precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TRANSCRIPT, fill_strategy="JSON estimate",
        ),
        metadata=AttributedValue(
            value=10, unit="tokens", precision=ValuePrecision.HEURISTIC,
            source=ValueSource.SESSION_METADATA, fill_strategy="heuristic",
        ),
        coverage=AttributedValue(
            value=0.82, unit="ratio", precision=ValuePrecision.ESTIMATED,
            source=ValueSource.HEURISTIC, fill_strategy="buckets/total",
        ),
        unknown=AttributedValue(
            value=90, unit="tokens", precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL, fill_strategy="total - known",
        ),
        finish_reason=AttributedValue(
            value="end_turn", unit="str", precision=ValuePrecision.EXACT,
            source=ValueSource.TRANSCRIPT, fill_strategy="from llm_call",
        ),
        buckets=[
            ResponseAttributionBucket(
                key="assistant_text", label="Assistant text",
                tokens=300, percent=60.0, precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT, confidence_label="中",
                summary="助手文本", contributes_to_total=True,
            ),
        ],
        blocks=[],
        captured_output_preview="response preview",
        attribution_notes=[],
        availability_rows=[],
    )


class TestRequestAttributionPayloadV2:
    """Request attribution payload v2 contract tests。"""

    def test_schema_version_present(self):
        attr = _make_request_attribution()
        payload = request_attribution_to_payload(attr)
        assert payload["schema_version"] == "llm_attribution_v2"

    def test_payload_has_no_legacy_compatible_marker(self):
        attr = _make_request_attribution()
        payload = request_attribution_to_payload(attr)
        assert "legacy_compatible" not in payload

    def test_call_identity_fields(self):
        attr = _make_request_attribution()
        payload = request_attribution_to_payload(attr)
        ci = payload["call_identity"]
        assert "agent_runtime" in ci
        assert "api_family" in ci
        assert "provider_or_broker" in ci
        assert "billing_units" in ci
        assert ci["agent_runtime"] == "claude_code"

    def test_usage_summary_attributed_values(self):
        attr = _make_request_attribution()
        payload = request_attribution_to_payload(attr)
        us = payload["usage_summary"]
        for key in ("total_input", "fresh_input", "cache_read", "cache_write", "output"):
            assert key in us
            av = us[key]
            assert "value" in av
            assert "unit" in av
            assert "precision" in av
            assert "source" in av

    def test_ordered_spans_is_list(self):
        attr = _make_request_attribution()
        payload = request_attribution_to_payload(attr)
        assert isinstance(payload["ordered_spans"], list)

    def test_semantic_buckets_is_list(self):
        attr = _make_request_attribution()
        payload = request_attribution_to_payload(attr)
        assert isinstance(payload["semantic_buckets"], list)

    def test_coverage_fields(self):
        attr = _make_request_attribution()
        payload = request_attribution_to_payload(attr)
        cov = payload["coverage"]
        assert "provider_total_input" in cov
        assert "request_content_total" in cov
        assert "accounting_cache_read_tokens" in cov
        assert "reconstructed_total" in cov
        assert "coverage_ratio" in cov
        assert "residual_tokens" in cov
        assert "residual_likely_sources" in cov
        assert cov["provider_total_input"] == 1000
        assert cov["request_content_total"] == 600
        assert cov["accounting_cache_read_tokens"] == 400
        assert "unclassified overhead" not in cov["residual_likely_sources"]

    def test_route_payload_fields_present(self):
        attr = _make_request_attribution()
        payload = request_attribution_to_payload(attr)
        assert payload["kind"] == "llm.request_attribution"
        assert payload["agent"] == "claude_code"
        assert "model" in payload
        assert "request_id" in payload
        assert "call_id" in payload
        assert "usage" in payload
        assert "buckets" in payload
        assert isinstance(payload["buckets"], list)
        assert len(payload["buckets"]) > 0

    def test_diagnostics_invariants(self):
        attr = _make_request_attribution()
        payload = request_attribution_to_payload(attr)
        diag = payload["diagnostics"]
        assert "invariants" in diag
        assert isinstance(diag["invariants"], list)


class TestResponseAttributionPayloadV2:
    """Response attribution payload v2 contract tests。"""

    def test_schema_version_present(self):
        attr = _make_response_attribution()
        payload = response_attribution_to_payload(attr)
        assert payload["schema_version"] == "llm_attribution_v2"

    def test_payload_has_no_legacy_compatible_marker(self):
        attr = _make_response_attribution()
        payload = response_attribution_to_payload(attr)
        assert "legacy_compatible" not in payload

    def test_call_identity_fields(self):
        attr = _make_response_attribution()
        payload = response_attribution_to_payload(attr)
        ci = payload["call_identity"]
        assert "agent_runtime" in ci
        assert "api_family" in ci
        assert ci["agent_runtime"] == "claude_code"

    def test_usage_summary_attributed_values(self):
        attr = _make_response_attribution()
        payload = response_attribution_to_payload(attr)
        us = payload["usage_summary"]
        for key in ("total_output", "visible_text", "tool_use", "hidden_reasoning", "metadata", "residual"):
            assert key in us
            av = us[key]
            assert "value" in av
            assert "unit" in av
            assert "precision" in av

    def test_response_spans_is_list(self):
        attr = _make_response_attribution()
        payload = response_attribution_to_payload(attr)
        assert isinstance(payload["response_spans"], list)

    def test_legacy_fields_preserved(self):
        attr = _make_response_attribution()
        payload = response_attribution_to_payload(attr)
        assert payload["kind"] == "llm.response_attribution"
        assert payload["agent"] == "claude_code"
        assert "usage" in payload
        assert "buckets" in payload
        assert "blocks" in payload

    def test_diagnostics_invariants(self):
        attr = _make_response_attribution()
        payload = response_attribution_to_payload(attr)
        diag = payload["diagnostics"]
        assert "invariants" in diag
        assert "tool_schema_counted_as_output" in diag


class TestAttributedValueContract:
    """AttributedValue 字段 contract 测试。"""

    def test_all_required_fields(self):
        av = AttributedValue(
            value=100, unit="tokens", precision=ValuePrecision.EXACT,
            source=ValueSource.PROVIDER_USAGE, fill_strategy="provider",
        )
        d = attributed_value_to_dict(av)
        for key in ("value", "unit", "precision", "source", "fill_strategy", "note"):
            assert key in d, f"Missing field: {key}"


class TestQoderPayloadContract:
    """Qoder payload contract tests。"""

    def test_qoder_call_identity_has_credits(self):
        attr = _make_request_attribution()
        attr.agent = "qoder"
        payload = request_attribution_to_payload(attr)
        ci = payload["call_identity"]
        assert ci["agent_runtime"] == "qoder"
        assert "credits" in ci["billing_units"]

    def test_qoder_api_family_is_qoder_broker(self):
        attr = _make_request_attribution()
        attr.agent = "qoder"
        payload = request_attribution_to_payload(attr)
        ci = payload["call_identity"]
        assert ci["api_family"] == "qoder_broker"
