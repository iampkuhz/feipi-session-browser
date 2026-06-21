"""Resolve the final mapping decision for one LLM call.

The resolver runs when attribution has an agent name plus optional model, raw request,
raw response, and provider or broker usage payload. It keeps four decisions separate:
agent runtime, API family, provider or broker, and billing units. The output boundary is
a CallMappingDecision consumed by downstream attribution and token accounting stages.

Decision precedence is raw request and response payloads, usage shape, model string,
agent runtime defaults, and finally heuristic fallback for calls without usable evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

from session_browser.attribution.mapping.agent_runtime import resolve_agent_runtime
from session_browser.attribution.mapping.usage_shape_detector import detect_usage_shape


@dataclass
class CallMappingDecision:
    """Final API family, provider, billing, and evidence result for one LLM call.

    Attributes:
        agent_runtime: Normalized runtime such as ``claude_code``, ``codex``, or ``qoder``.
        api_family: Selected API family for accounting semantics.
        provider_or_broker: Provider or broker responsible for the call.
        underlying_provider: Provider behind a broker when known.
        model: Model string associated with the call when available.
        billing_units: Units used for billing, such as tokens or credits.
        usage_source: Evidence source for the usage decision.
        confidence: Confidence score between ``0.0`` and ``1.0``.
        reasons: Human-readable decision reasons for downstream explanations.
        warnings: Human-readable warnings about weak or estimated evidence.
    """

    agent_runtime: str
    api_family: str
    provider_or_broker: str
    underlying_provider: str | None
    model: str | None
    billing_units: list[str]
    usage_source: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def resolve_call_mapping(
    *,
    agent: str,
    usage: dict[str, Any] | None = None,
    model: str | None = None,
    raw_request: dict[str, Any] | None = None,
    raw_response: dict[str, Any] | None = None,
) -> CallMappingDecision:
    """Resolve API family and accounting metadata for one LLM call.

    Args:
        agent: Runtime identifier such as ``claude_code``, ``qoder``, or ``codex``.
        usage: Provider or broker usage payload, when captured for this call.
        model: Model string reported by the agent or provider.
        raw_request: Raw request payload used before provider submission.
        raw_response: Raw provider or broker response payload.

    Returns:
        Mapping decision with the selected API family, billing units, confidence,
        and reason strings for the downstream attribution pipeline.
    """
    agent_runtime = resolve_agent_runtime(agent)
    reasons: list[str] = []
    warnings: list[str] = []
    confidence = 0.5
    usage_source = 'unavailable'
    provider_or_broker = 'unknown'
    underlying_provider = None
    api_family = 'unknown'
    billing_units: list[str] = ['tokens']

    if agent_runtime == 'claude_code':
        resolver_module = import_module(
            'session_browser.attribution.mapping.agents.claude_code_token_accounting_mapping'
        )
        return resolver_module.ClaudeCodeCallMappingResolver().resolve(
            usage=usage,
            model=model,
            raw_request=raw_request,
            raw_response=raw_response,
        )
    if agent_runtime == 'codex':
        resolver_module = import_module(
            'session_browser.attribution.mapping.agents.codex_token_accounting_mapping'
        )
        return resolver_module.CodexCallMappingResolver().resolve(
            usage=usage,
            model=model,
            raw_request=raw_request,
            raw_response=raw_response,
        )
    if agent_runtime == 'qoder':
        resolver_module = import_module(
            'session_browser.attribution.mapping.agents.qoder_token_accounting_mapping'
        )
        return resolver_module.QoderCallMappingResolver().resolve(
            usage=usage,
            model=model,
            raw_request=raw_request,
            raw_response=raw_response,
        )

    usage_shape = detect_usage_shape(usage)
    if usage_shape == 'anthropic_messages_like':
        api_family = 'anthropic_messages_like'
        provider_or_broker = 'anthropic'
        confidence = 0.7
        usage_source = 'provider_reported'
        reasons.append('unknown agent with Anthropic-like usage')
    elif usage_shape in ('openai_responses_like', 'openai_chat_like'):
        api_family = 'openai_like'
        provider_or_broker = 'openai'
        confidence = 0.7
        usage_source = 'provider_reported'
        reasons.append('unknown agent with OpenAI-like usage')
    else:
        api_family = 'estimate_only'
        confidence = 0.3
        usage_source = 'local_reconstruction'
        reasons.append('unknown agent, no usage -> estimate_only')

    return CallMappingDecision(
        agent_runtime=agent_runtime,
        api_family=api_family,
        provider_or_broker=provider_or_broker,
        underlying_provider=underlying_provider,
        model=model,
        billing_units=billing_units,
        usage_source=usage_source,
        confidence=confidence,
        reasons=reasons,
        warnings=warnings,
    )
