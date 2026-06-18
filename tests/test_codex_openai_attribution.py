"""Comprehensive Codex OpenAI/Responses API token attribution tests.

Covers:
1. Codex flat usage normalization (section 8.1)
2. OpenAI Responses nested usage normalization/extraction (section 8.2)
3. No usage fallback (section 8.3)
4. previous_response_id residual (section 8.4)
5. Tool schemas from raw request (section 8.5)
6. Reasoning tokens are not visible text (section 8.6)
7. Flat Codex usage variants (section 8.7)
"""

import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
    NormalizedTokenBreakdown, TokenPrecision, TokenSourceKind,
)
from session_browser.domain.token_normalizer import normalize_tokens
from session_browser.attribution.agents.codex import (
    CodexAttributionBuilder,
    _extract_codex_usage_from_raw,
)
from session_browser.attribution.contracts import ValuePrecision
from session_browser.sources.codex import _extract_codex_usage
from session_browser.web.presenters.session_detail import _normalize_codex_usage


def _make_lc(**kwargs):
    defaults = dict(
        id="codex-call-001", model="gpt-5.1-codex-max", scope="main",
        subagent_id="", round_index=0, parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
        finish_reason="stop", content_blocks=[],
        response_full="", request_full="", tool_calls_raw="",
        token_breakdown_normalized=None,
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


# ── 8.1 Codex flat usage normalization ──────────────────────────────────────

class TestCodexFlatUsage:
    """Test section 8.1: Codex flat usage normalization."""

    def test_flat_usage_extraction(self):
        usage = {
            "input_tokens": 24763,
            "cached_input_tokens": 24448,
            "output_tokens": 122,
            "reasoning_output_tokens": 10,
            "total_tokens": 24885,
        }
        result = _extract_codex_usage(usage)
        assert result["input_tokens"] == 24763
        assert result["cached_input_tokens"] == 24448
        assert result["output_tokens"] == 122
        assert result["reasoning_output_tokens"] == 10
        assert result["total_tokens"] == 24885

    def test_flat_normalization(self):
        usage = {
            "input_tokens": 24763,
            "cached_input_tokens": 24448,
            "output_tokens": 122,
            "reasoning_output_tokens": 10,
            "total_tokens": 24885,
        }
        bd = normalize_tokens(usage, provider="codex")
        assert bd.fresh_input_tokens == 315
        assert bd.cache_read_tokens == 24448
        assert bd.cache_write_tokens == 0
        assert bd.output_tokens == 122
        assert bd.total_tokens == 24885
        assert bd.raw_fields.get("reasoning_output_tokens") == 10
        assert bd.precision == TokenPrecision.PROVIDER_REPORTED

    def test_normalization_via_source_extractor(self):
        """Ensure _extract_codex_usage + normalize_tokens chain works."""
        usage = {
            "input_tokens": 24763,
            "cached_input_tokens": 24448,
            "output_tokens": 122,
            "reasoning_output_tokens": 10,
            "total_tokens": 24885,
        }
        extracted = _extract_codex_usage(usage)
        bd = normalize_tokens(extracted, provider="codex")
        assert bd.fresh_input_tokens == 315
        assert bd.cache_read_tokens == 24448
        assert bd.cache_write_tokens == 0
        assert bd.output_tokens == 122


# ── 8.2 OpenAI Responses nested usage normalization ─────────────────────────

class TestOpenAINestedUsage:
    """Test section 8.2: OpenAI Responses nested usage."""

    def test_nested_extraction_from_response(self):
        raw_response = {
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 700},
                "output_tokens": 80,
                "output_tokens_details": {"reasoning_tokens": 30},
                "total_tokens": 1080,
            }
        }
        extracted = _extract_codex_usage_from_raw(raw_response)
        assert extracted["input_tokens"] == 1000
        assert extracted["cached_input_tokens"] == 700
        assert extracted["output_tokens"] == 80
        assert extracted["reasoning_output_tokens"] == 30
        assert extracted["total_tokens"] == 1080

    def test_nested_normalization(self):
        usage = {
            "input_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 700},
            "output_tokens": 80,
            "output_tokens_details": {"reasoning_tokens": 30},
            "total_tokens": 1080,
        }
        bd = normalize_tokens(usage, provider="codex")
        assert bd.fresh_input_tokens == 300
        assert bd.cache_read_tokens == 700
        assert bd.cache_write_tokens == 0
        assert bd.output_tokens == 80
        assert bd.total_tokens == 1080
        # raw_fields captures flat numeric fields; nested details are consumed
        assert bd.raw_fields.get("input_tokens") == 1000
        assert bd.raw_fields.get("output_tokens") == 80

    def test_openai_chat_usage_fields(self):
        """Test prompt_tokens_details / completion_tokens_details parsing."""
        usage = {
            "prompt_tokens": 2000,
            "prompt_tokens_details": {"cached_tokens": 1500},
            "completion_tokens": 100,
            "completion_tokens_details": {"reasoning_tokens": 40},
        }
        extracted = _extract_codex_usage(usage)
        assert extracted["input_tokens"] == 2000
        assert extracted["cached_input_tokens"] == 1500
        assert extracted["output_tokens"] == 100
        assert extracted["reasoning_output_tokens"] == 40


# ── 8.3 No usage fallback ───────────────────────────────────────────────────

class TestNoUsageFallback:
    """Test section 8.3: No usage, transcript-only estimation."""

    def test_no_usage_request_attribution(self):
        """When no usage data, buckets estimate from text."""
        lc = _make_lc(
            request_full="some context\n\nFile: test.py\nimport os",
        )
        ro = _make_ro(user_content="hello world")
        builder = CodexAttributionBuilder(lc, ro)
        result = builder.build_request()

        # Total input should be UNAVAILABLE (no provider usage)
        assert result.total_input.value == 0
        assert result.total_input.precision == ValuePrecision.UNAVAILABLE
        # Buckets may still estimate from text
        assert len(result.buckets) > 0

    def test_no_usage_response_attribution(self):
        """When no output usage, response estimates from text."""
        lc = _make_lc(
            response_full="This is a response with some text content.",
        )
        ro = _make_ro()
        builder = CodexAttributionBuilder(lc, ro)
        result = builder.build_response()

        # Without usage, total_output is estimated
        assert result.total_output.value > 0
        assert result.total_output.precision == ValuePrecision.ESTIMATED
        assert result.visible_text.value > 0


# ── 8.4 previous_response_id residual ───────────────────────────────────────

class TestPreviousResponseIdResidual:
    """Test section 8.4: previous_response_id residual handling."""

    def test_large_residual_with_previous_response_id(self):
        raw_request = {
            "model": "gpt-5.1-codex-max",
            "previous_response_id": "resp_abc",
            "input": [{"role": "user", "content": "continue"}],
        }
        raw_response = {
            "usage": {
                "input_tokens": 50000,
                "output_tokens": 100,
            }
        }
        lc = _make_lc(
            input_tokens=50000,
            output_tokens=100,
            cache_read_tokens=49500,  # large cached = large residual
            request_payload_raw='{"model":"gpt-5.1-codex-max","previous_response_id":"resp_abc","input":[{"role":"user","content":"continue"}]}',
            response_payload_raw='{"usage":{"input_tokens":50000,"output_tokens":100}}',
        )
        ro = _make_ro(user_content="continue")
        builder = CodexAttributionBuilder(lc, ro)
        result = builder.build_request()

        # Verify previous_response_id is detected
        avail_fields = {r.field if hasattr(r, "field") else r["field"]
                        for r in result.availability_rows}
        assert "responses_previous_response_id" in avail_fields

        # Check notes mention previous_response_id or server-side
        notes_text = " ".join(result.attribution_notes)
        assert "previous_response_id" in notes_text or "server-side" in notes_text

        # Residual should be significant (input=50000 but visible input is tiny)
        unknown_bucket = next((b for b in result.buckets if b.key == "unknown_overhead"), None)
        assert unknown_bucket is not None
        assert unknown_bucket.tokens > 0


# ── 8.5 Tool schemas from raw request ────────────────────────────────────────

class TestToolSchemasFromRawRequest:
    """Test section 8.5: Tool schemas from raw request."""

    def test_raw_request_tool_definitions(self):
        raw_request = {
            "model": "gpt-5.1-codex-max",
            "input": [{"role": "user", "content": "fix this"}],
            "tools": [
                {"type": "function", "name": "shell",
                 "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}},
                {"type": "function", "name": "read_file",
                 "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
            ],
        }
        lc = _make_lc(
            input_tokens=5000,
            cache_read_tokens=3000,
            request_payload_raw='{"model":"gpt-5.1-codex-max","input":[{"role":"user","content":"fix this"}],"tools":[{"type":"function","name":"shell","parameters":{"type":"object","properties":{"command":{"type":"string"}}}},{"type":"function","name":"read_file","parameters":{"type":"object","properties":{"path":{"type":"string"}}}}]}',
        )
        ro = _make_ro(user_content="fix this")
        builder = CodexAttributionBuilder(lc, ro)
        result = builder.build_request()

        tool_schema_bucket = next((b for b in result.buckets if b.key == "tool_definitions"), None)
        assert tool_schema_bucket is not None
        assert tool_schema_bucket.tokens > 0

    def test_no_raw_tools_uses_codex_builtin_catalog(self):
        """When raw tools are unavailable, Codex uses builtin schema fallback."""
        lc = _make_lc(
            input_tokens=10000,
        )
        ro = _make_ro(user_content="hello")
        builder = CodexAttributionBuilder(
            lc,
            ro,
            session_context={"available_tools": ["exec_command", "apply_patch"]},
        )
        result = builder.build_request()

        tool_schema_bucket = next((b for b in result.buckets if b.key == "tool_definitions"), None)
        assert tool_schema_bucket is not None
        assert tool_schema_bucket.tokens >= 3000
        assert tool_schema_bucket.count_label == "5 tools"
        assert tool_schema_bucket.precision == ValuePrecision.ESTIMATED
        assert "Codex builtin tool catalog" in tool_schema_bucket.summary
        assert "observed tools" not in tool_schema_bucket.summary
        assert tool_schema_bucket.details["kind"] == "tools"
        assert tool_schema_bucket.details["total_items"] == 5
        item_names = {item["name"] for item in tool_schema_bucket.details["items"]}
        assert {"exec_command", "apply_patch", "write_stdin", "update_plan", "view_image"} <= item_names


# ── 8.6 Reasoning tokens are not visible text ────────────────────────────────

class TestReasoningTokensNotVisible:
    """Test section 8.6: Reasoning tokens should not be attributed to visible text."""

    def test_reasoning_separate_from_visible_text(self):
        """output_tokens=100, reasoning_output_tokens=60, short response_full."""
        bd = NormalizedTokenBreakdown(
            fresh_input_tokens=200,
            cache_read_tokens=800,
            cache_write_tokens=0,
            output_tokens=100,
            total_tokens=1100,
            precision=TokenPrecision.PROVIDER_REPORTED,
            source_kind=TokenSourceKind.CODEX_ROLLOUT_TOKEN_COUNT,
            raw_fields={"reasoning_output_tokens": 60},
        )
        lc = _make_lc(
            input_tokens=1000,
            output_tokens=100,
            cache_read_tokens=800,
            total_tokens=1100,
            response_full="short",
            token_breakdown_normalized=bd,
        )
        ro = _make_ro(user_content="analyze")
        builder = CodexAttributionBuilder(lc, ro)
        result = builder.build_response()

        assert result.total_output.value == 100

        # Check reasoning bucket exists
        reasoning_bucket = next((b for b in result.buckets
                                 if b.key == "reasoning_output_tokens"), None)
        assert reasoning_bucket is not None
        assert reasoning_bucket.tokens == 60
        assert reasoning_bucket.precision == ValuePrecision.PROVIDER_REPORTED
        assert reasoning_bucket.contributes_to_total is True

        # Visible text should only reflect the short response
        assert result.visible_text.value is not None
        # "short" is very small, visible_text should be small

    def test_reasoning_only_no_output_fallback(self):
        """When only reasoning_output_tokens and no output_tokens, use reasoning as output."""
        usage = {
            "input_tokens": 1000,
            "cached_input_tokens": 500,
            "reasoning_output_tokens": 80,
        }
        bd = normalize_tokens(usage, provider="codex")
        assert bd.output_tokens == 80  # fallback to reasoning
        assert bd.fresh_input_tokens == 500


# ── 8.7 Flat Codex usage variants ───────────────────────────────────────────

class TestFlatCodexUsageVariants:
    """Test section 8.7: flat Codex usage payload variants."""

    def test_flat_codex_usage_without_reasoning(self):
        """Codex usage with input/output totals and no reasoning field."""
        usage = {
            "input_tokens": 5000,
            "cached_input_tokens": 3000,
            "output_tokens": 2000,
        }
        extracted = _extract_codex_usage(usage)
        assert extracted["input_tokens"] == 5000
        assert extracted["cached_input_tokens"] == 3000
        assert extracted["output_tokens"] == 2000
        assert extracted["reasoning_output_tokens"] == 0

        bd = normalize_tokens(usage, provider="codex")
        assert bd.fresh_input_tokens == 2000
        assert bd.cache_read_tokens == 3000
        assert bd.output_tokens == 2000
        assert bd.total_tokens == 7000

    def test_codex_cumulative_delta_keeps_provider_input_size_for_normalizer(self):
        cumulative = {
            "input_tokens": 5000,
            "cached_input_tokens": 3000,
            "output_tokens": 2000,
        }
        state = {
            "input_tokens": 4200,
            "cached_input_tokens": 2500,
            "output_tokens": 1800,
        }

        delta = _normalize_codex_usage(cumulative, state)

        assert delta["input_tokens"] == 800
        assert delta["cache_read_input_tokens"] == 500
        assert delta["output_tokens"] == 200

    def test_existing_codex_attribution_test_still_passes(self):
        """Ensure existing test patterns still work with new builder."""
        lc = _make_lc(input_tokens=10000, output_tokens=5000,
                       request_full="context\n\nmore\n\ndata\n\nFile: test.py")
        ro = _make_ro(user_content="test user message")
        builder = CodexAttributionBuilder(lc, ro)
        result = builder.build_request()

        total = result.total_input.value or 0
        bucket_sum = sum(b.tokens for b in result.buckets)
        assert bucket_sum <= total

    def test_existing_response_attribution_test(self):
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

    def test_claude_code_normalization_unchanged(self):
        """Ensure Claude Code normalization is untouched."""
        usage = {
            "input_tokens": 1000,
            "cache_read_input_tokens": 2000,
            "cache_creation_input_tokens": 500,
            "output_tokens": 300,
        }
        from session_browser.domain.models import TokenProvider
        bd = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)
        assert bd.fresh_input_tokens == 1000
        assert bd.cache_read_tokens == 2000
        assert bd.cache_write_tokens == 500
        assert bd.output_tokens == 300
        assert bd.total_tokens == 3800

    def test_openai_normalization_uses_request_input(self):
        """OpenAI Fresh is the non-cached input component; cached is separate."""
        usage = {
            "input_tokens": 4000,
            "output_tokens": 600,
            "input_tokens_details": {"cached_tokens": 2000},
            "output_tokens_details": {"reasoning_tokens": 200},
        }
        from session_browser.domain.models import TokenProvider
        bd = normalize_tokens(usage, provider=TokenProvider.OPENAI)
        assert bd.fresh_input_tokens == 2000
        assert bd.cache_read_tokens == 2000
        assert bd.output_tokens == 400
        assert bd.total_tokens == 4400


# ── Context builder Codex fixes ─────────────────────────────────────────────

class TestCodexContextBuilder:
    """Test that Codex context builder does not return Claude Code defaults."""

    def test_no_claude_default_tools_for_codex(self):
        from session_browser.attribution.context import _build_available_tools
        result = _build_available_tools(None, agent_name="codex")
        assert result == []

    def test_observed_tools_for_codex(self):
        from session_browser.attribution.context import _build_available_tools
        tool_calls = [ToolCall(name="shell", parameters={})]
        result = _build_available_tools(tool_calls, agent_name="codex")
        assert result == ["shell"]

    def test_claude_default_tools_for_claude_code(self):
        from session_browser.attribution.context import _build_available_tools
        result = _build_available_tools(None, agent_name="claude_code")
        assert len(result) > 0
        assert "Read" in result
        assert "Bash" in result


# ── extract_codex_usage source priority tests ───────────────────────────────

class TestExtractCodexUsageSourcePriority:
    """Test _extract_codex_usage handles various source structures."""

    def test_turn_completed_usage(self):
        raw = {"type": "turn.completed", "usage": {
            "input_tokens": 24763, "cached_input_tokens": 24448,
            "output_tokens": 122, "reasoning_output_tokens": 0,
        }}
        result = _extract_codex_usage(raw)
        assert result["input_tokens"] == 24763
        assert result["_usage_source"] == "usage"

    def test_response_usage(self):
        raw = {"response": {"usage": {
            "input_tokens": 1000, "output_tokens": 50,
        }}}
        result = _extract_codex_usage(raw)
        assert result["input_tokens"] == 1000
        assert result["_usage_source"] == "response.usage"

    def test_payload_info_last_token_usage(self):
        raw = {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 1000,
                        "cached_input_tokens": 800,
                        "output_tokens": 50,
                    }
                }
            }
        }
        result = _extract_codex_usage(raw)
        assert result["input_tokens"] == 1000
        assert result["cached_input_tokens"] == 800
        assert result["_usage_source"] == "payload.info.last_token_usage"

    def test_payload_info_total_token_usage_cumulative(self):
        raw = {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 3000,
                        "cached_input_tokens": 2300,
                        "output_tokens": 200,
                    }
                }
            }
        }
        result = _extract_codex_usage(raw)
        assert result["input_tokens"] == 3000
        assert result.get("_is_cumulative") is True

    def test_empty_dict(self):
        assert _extract_codex_usage({}) == {}

    def test_non_dict(self):
        assert _extract_codex_usage([]) == {}
        assert _extract_codex_usage("text") == {}
        assert _extract_codex_usage(None) == {}  # type: ignore[arg-type]
