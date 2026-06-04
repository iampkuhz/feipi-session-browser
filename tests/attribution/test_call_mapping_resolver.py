"""Call Mapping Resolver 单元测试。

覆盖：
- Claude Code + Anthropic usage -> anthropic_messages
- Codex + OpenAI Responses usage -> openai_responses
- Qoder + Anthropic-like usage -> qoder_broker, underlying_provider=None
- Qoder + OpenAI-like usage -> qoder_broker, underlying_provider=None
- Qoder no usage -> estimate_only
- Unknown fallback
"""

import pytest

from session_browser.attribution.mapping.call_mapping_resolver import (
    resolve_call_mapping,
    CallMappingDecision,
)
from session_browser.attribution.mapping.agent_runtime import resolve_agent_runtime
from session_browser.attribution.mapping.usage_shape_detector import detect_usage_shape


# ─── Agent Runtime resolution ──────────────────────────────────────


class TestAgentRuntimeResolution:

    def test_claude_code(self):
        assert resolve_agent_runtime("claude_code") == "claude_code"

    def test_codex(self):
        assert resolve_agent_runtime("codex") == "codex"

    def test_qoder(self):
        assert resolve_agent_runtime("qoder") == "qoder"

    def test_unknown(self):
        assert resolve_agent_runtime("some_random_agent") == "unknown"

    def test_empty(self):
        assert resolve_agent_runtime("") == "unknown"
        assert resolve_agent_runtime(None) == "unknown"  # type: ignore[arg-type]


# ─── Usage shape detection ─────────────────────────────────────────


class TestUsageShapeDetection:

    def test_anthropic_shape(self):
        usage = {
            "input_tokens": 1000,
            "cache_read_input_tokens": 500,
            "cache_creation_input_tokens": 200,
            "output_tokens": 300,
        }
        assert detect_usage_shape(usage) == "anthropic_messages_like"

    def test_openai_responses_shape(self):
        usage = {
            "input_tokens": 2000,
            "input_tokens_details": {"cached_tokens": 800},
            "output_tokens": 500,
            "output_tokens_details": {"reasoning_tokens": 200},
        }
        assert detect_usage_shape(usage) == "openai_responses_like"

    def test_openai_chat_shape(self):
        usage = {
            "prompt_tokens": 1500,
            "prompt_tokens_details": {"cached_tokens": 600},
            "completion_tokens": 400,
        }
        assert detect_usage_shape(usage) == "openai_chat_like"

    def test_token_reported_no_cache(self):
        usage = {"input_tokens": 1000, "output_tokens": 200}
        assert detect_usage_shape(usage) == "token_reported_unknown_cache"

    def test_unavailable(self):
        assert detect_usage_shape(None) == "unavailable"
        assert detect_usage_shape({}) == "unavailable"


# ─── Call Mapping Resolver: Claude Code ────────────────────────────


class TestCallMappingClaudeCode:

    def test_claude_code_with_anthropic_usage(self):
        usage = {
            "input_tokens": 1000,
            "cache_read_input_tokens": 500,
            "cache_creation_input_tokens": 200,
            "output_tokens": 300,
        }
        decision = resolve_call_mapping(
            agent="claude_code", usage=usage, model="claude-sonnet-4-20250514",
        )
        assert decision.agent_runtime == "claude_code"
        assert decision.api_family == "anthropic_messages"
        assert decision.provider_or_broker == "anthropic"
        assert decision.underlying_provider is None
        assert decision.confidence >= 0.9
        assert decision.usage_source == "provider_reported"

    def test_claude_code_no_usage(self):
        decision = resolve_call_mapping(agent="claude_code", usage=None)
        assert decision.api_family == "estimate_only"
        assert decision.usage_source == "local_reconstruction"
        assert len(decision.warnings) > 0


# ─── Call Mapping Resolver: Codex ──────────────────────────────────


class TestCallMappingCodex:

    def test_codex_with_openai_responses_usage(self):
        usage = {
            "input_tokens": 2000,
            "input_tokens_details": {"cached_tokens": 800},
            "output_tokens": 500,
            "output_tokens_details": {"reasoning_tokens": 200},
        }
        decision = resolve_call_mapping(
            agent="codex", usage=usage, model="o3",
        )
        assert decision.agent_runtime == "codex"
        assert decision.api_family == "openai_responses"
        assert decision.provider_or_broker == "openai"
        assert decision.confidence >= 0.9
        assert decision.usage_source == "provider_reported"

    def test_codex_with_basic_tokens(self):
        usage = {"input_tokens": 1000, "output_tokens": 200}
        decision = resolve_call_mapping(agent="codex", usage=usage)
        assert decision.api_family == "openai_responses"
        assert decision.usage_source == "provider_reported"

    def test_codex_no_usage(self):
        decision = resolve_call_mapping(agent="codex", usage=None)
        assert decision.api_family == "estimate_only"
        assert decision.usage_source == "local_reconstruction"


# ─── Call Mapping Resolver: Qoder ──────────────────────────────────


class TestCallMappingQoder:

    def test_qoder_anthropic_like(self):
        usage = {
            "input_tokens": 1000,
            "cache_read_input_tokens": 500,
            "cache_creation_input_tokens": 200,
            "output_tokens": 300,
        }
        decision = resolve_call_mapping(
            agent="qoder", usage=usage, model="performance-tier",
        )
        assert decision.agent_runtime == "qoder"
        assert decision.api_family == "qoder_broker"
        assert decision.provider_or_broker == "qoder"
        assert decision.underlying_provider is None  # Qoder 不推断 underlying provider
        assert decision.confidence >= 0.8
        assert "tokens" in decision.billing_units
        assert "credits" in decision.billing_units

    def test_qoder_openai_like(self):
        usage = {
            "input_tokens": 2000,
            "input_tokens_details": {"cached_tokens": 800},
            "output_tokens": 500,
        }
        decision = resolve_call_mapping(agent="qoder", usage=usage)
        assert decision.api_family == "qoder_broker"
        assert decision.underlying_provider is None  # Qoder 不推断 underlying provider

    def test_qoder_no_usage(self):
        decision = resolve_call_mapping(agent="qoder", usage=None)
        assert decision.api_family == "estimate_only"
        assert decision.usage_source == "local_reconstruction"
        assert decision.confidence < 0.5
        assert len(decision.warnings) > 0

    def test_qoder_basic_tokens_only(self):
        usage = {"input_tokens": 1000, "output_tokens": 200}
        decision = resolve_call_mapping(agent="qoder", usage=usage)
        assert decision.api_family == "qoder_broker"
        assert decision.underlying_provider is None
        assert decision.usage_source == "provider_reported"


# ─── Call Mapping Resolver: Unknown ────────────────────────────────


class TestCallMappingUnknown:

    def test_unknown_with_anthropic_usage(self):
        usage = {
            "cache_read_input_tokens": 500,
            "cache_creation_input_tokens": 200,
            "input_tokens": 1000,
        }
        decision = resolve_call_mapping(agent="unknown_agent", usage=usage)
        assert decision.api_family == "anthropic_messages_like"
        assert decision.provider_or_broker == "anthropic"

    def test_unknown_no_usage(self):
        decision = resolve_call_mapping(agent="unknown_agent", usage=None)
        assert decision.api_family == "estimate_only"
        assert decision.agent_runtime == "unknown"
