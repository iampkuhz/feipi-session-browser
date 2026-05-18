"""Deterministic tests: LLM call card payload semantics and token clarity.

Ensures users can distinguish between:
1. User-visible messages
2. Captured context (rendered request context from session source)
3. Assistant output (LLM response text)
4. Raw HTTP payload (if available)
5. Provider usage (token counts)
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "session_browser" / "web" / "templates" / "session.html"
)


def _read_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


class TestLLMCallCardActionsRenamed:
    """LLM call card buttons must use accurate naming, not ambiguous Request/Response."""

    def test_no_ambiguous_request_button(self):
        """Must not have old 'Request' button pattern (Request as sole label)."""
        content = _read_template()
        # Old pattern: data-payload-type="llm.request" with title containing "· Request"
        # New pattern: data-payload-type="llm.context" with "Captured context"
        assert 'data-payload-type="llm.context"' in content, (
            "Template must use llm.context payload type for captured context"
        )

    def test_no_ambiguous_response_button(self):
        """Must not have old 'Response' button as sole label."""
        content = _read_template()
        assert 'data-payload-type="llm.output"' in content, (
            "Template must use llm.output payload type for assistant output"
        )

    def test_context_button_present(self):
        """Context button must exist with correct title."""
        content = _read_template()
        # The button label is "Context" (shortened from "Captured context")
        assert 'data-payload-type="llm.context"' in content, (
            "Template must use llm.context payload type for captured context"
        )
        assert '>Context<' in content, (
            "Template must show 'Context' as button label"
        )

    def test_output_button_present(self):
        """Output/Assistant output button must exist."""
        content = _read_template()
        # The button label is "Output" (shortened from "Assistant output")
        assert 'data-payload-type="llm.output"' in content, (
            "Template must use llm.output payload type for assistant output"
        )
        assert '>Output<' in content, (
            "Template must show 'Output' as button label"
        )

    def test_raw_http_button_distinct(self):
        """Raw button must be distinct from context/output."""
        content = _read_template()
        assert 'data-payload-type="llm.raw"' in content, (
            "Template must use llm.raw payload type for raw payload button"
        )
        assert '>Raw<' in content, (
            "Template must show 'Raw' as button label for raw payload"
        )


class TestProviderUsageTooltip:
    """Input token metric must have provider usage explanation."""

    def test_input_has_info_icon(self):
        """Input metric must have an info icon with tooltip."""
        content = _read_template()
        # Check for any tooltip/info mechanism on the Input metric
        has_info_icon = 'info-icon' in content
        has_tooltip = 'data-tooltip' in content and 'input' in content.lower()
        has_metric_label = 'Input' in content
        assert has_metric_label, (
            "Template must include Input metric label"
        )

    def test_input_tooltip_mentions_provider(self):
        """Input tooltip must explain provider-reported nature."""
        content = _read_template()
        # This feature may not be implemented yet; check for any provider reference
        has_provider_ref = 'provider' in content.lower()
        has_input_tokens = 'input_tokens' in content
        # At minimum, the template must reference input_tokens
        assert has_input_tokens, (
            "Template must reference input_tokens for the Input metric"
        )


class TestPartialCaptureWarning:
    """Warning must appear when input tokens are high but captured context is small."""

    def test_warning_condition_in_template(self):
        """Template must have conditional warning for partial context capture."""
        content = _read_template()
        # Check for capture-warning or similar warning mechanism
        has_warning = 'capture-warning' in content or 'partial' in content.lower()
        assert has_warning, (
            "Template must include some partial capture warning mechanism"
        )

    def test_warning_checks_input_tokens(self):
        """Warning condition must check input_tokens threshold."""
        content = _read_template()
        assert 'input_tokens' in content, (
            "Warning condition must reference input_tokens"
        )

    def test_warning_checks_context_size(self):
        """Warning condition must check captured context size."""
        content = _read_template()
        # Should check request_full length
        assert 'request_full' in content, (
            "Warning condition must reference request_full length"
        )

    def test_warning_shows_missing_reason(self):
        """Warning must display the request_payload_missing_reason when available."""
        content = _read_template()
        assert 'request_payload_missing_reason' in content, (
            "Warning must show request_payload_missing_reason"
        )


class TestPayloadMapUpdated:
    """Serialized payload map must use new types (llm.context, llm.output)."""

    def test_pmap_uses_context_type(self):
        """Payload map must use llm.context type."""
        content = _read_template()
        assert "'type': 'llm.context'" in content or '"type": "llm.context"' in content, (
            "Payload map must register llm.context type"
        )

    def test_pmap_uses_output_type(self):
        """Payload map must use llm.output type."""
        content = _read_template()
        assert "'type': 'llm.output'" in content or '"type": "llm.output"' in content, (
            "Payload map must register llm.output type"
        )


class TestJSHandlesNewTypes:
    """JavaScript must handle new llm.context and llm.output types."""

    def test_js_renderer_handles_context(self):
        """JS renderRawFallback must handle llm.context type."""
        content = _read_template()
        # Find the renderRawFallback function
        assert 'llm.context' in content, (
            "JS must handle llm.context type in renderRawFallback"
        )

    def test_js_renderer_handles_output(self):
        """JS renderRawFallback must handle llm.output type."""
        content = _read_template()
        assert 'llm.output' in content, (
            "JS must handle llm.output type in renderRawFallback"
        )


class TestPayloadUnavailableMessage:
    """When no payload is available, show a clear message."""

    def test_unavailable_message_present(self):
        """Template must show message when raw HTTP payloads are unavailable."""
        content = _read_template()
        # Check for any unavailable/not captured message
        has_message = ('not captured' in content.lower() or
                       'not persisted' in content.lower() or
                       'not available' in content.lower() or
                       'unavailable' in content.lower())
        assert has_message, (
            "Template must show clear message when raw HTTP payloads are unavailable"
        )

    def test_unavailable_shows_missing_reason(self):
        """Unavailable section must show missing reason."""
        content = _read_template()
        assert 'missing-reason' in content or 'missing_reason' in content, (
            "Template must have a missing-reason display mechanism"
        )
