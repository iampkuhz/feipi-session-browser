"""Provide the service entry points for LLM call attribution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from session_browser.attribution.agents.base import BaseAttributionBuilder
from session_browser.attribution.agents.claude_code_attribution_builder import (
    ClaudeCodeAttributionBuilder,
)
from session_browser.attribution.agents.codex_attribution_builder import CodexAttributionBuilder
from session_browser.attribution.agents.qoder_attribution_builder import QoderAttributionBuilder

if TYPE_CHECKING:
    from session_browser.attribution.contracts import (
        LLMRequestAttribution,
        LLMResponseAttribution,
    )
    from session_browser.domain.models import (
        ConversationRound,
        LLMCall,
        SessionSummary,
    )


def build_llm_request_attribution(
    agent: str,
    llm_call: LLMCall,
    round_obj: ConversationRound,
    session_summary: SessionSummary | None = None,
    session_context: dict | None = None,
) -> LLMRequestAttribution:
    """Build request-side attribution for one LLM call.

    Route and presenter code call this service when the user opens request attribution
    details. The function selects the runtime-specific builder and falls back to the
    base builder for unknown agents.

    Args:
        agent: Runtime name such as claude_code, qoder, codex, or an unknown agent.
        llm_call: Normalized LLM call to attribute.
        round_obj: Conversation round that contains the call.
        session_summary: Optional session metadata used for labels and context.
        session_context: Optional precomputed context payload for richer attribution.

    Returns:
        Request attribution contract ready for serialization.
    """
    if agent == 'claude_code':
        return ClaudeCodeAttributionBuilder(
            llm_call,
            round_obj,
            session_summary,
            session_context,
        ).build_request()
    if agent == 'qoder':
        return QoderAttributionBuilder(
            llm_call,
            round_obj,
            session_summary,
            session_context,
        ).build_request()
    if agent == 'codex':
        return CodexAttributionBuilder(
            llm_call,
            round_obj,
            session_summary,
            session_context,
        ).build_request()
    return BaseAttributionBuilder(
        llm_call,
        round_obj,
        session_summary,
        session_context,
    ).build_request()


def build_llm_response_attribution(
    agent: str,
    llm_call: LLMCall,
    round_obj: ConversationRound,
    session_summary: SessionSummary | None = None,
    session_context: dict | None = None,
) -> LLMResponseAttribution:
    """Build response-side attribution for one LLM call.

    Route and presenter code call this service when the user opens response
    attribution details. The function uses the same runtime dispatch as request
    attribution so response payloads stay aligned with agent-specific evidence.

    Args:
        agent: Runtime name such as claude_code, qoder, codex, or an unknown agent.
        llm_call: Normalized LLM call to attribute.
        round_obj: Conversation round that contains the call.
        session_summary: Optional session metadata used for labels and context.
        session_context: Optional precomputed context payload for richer attribution.

    Returns:
        Response attribution contract ready for serialization.
    """
    if agent == 'claude_code':
        return ClaudeCodeAttributionBuilder(
            llm_call,
            round_obj,
            session_summary,
            session_context,
        ).build_response()
    if agent == 'qoder':
        return QoderAttributionBuilder(
            llm_call,
            round_obj,
            session_summary,
            session_context,
        ).build_response()
    if agent == 'codex':
        return CodexAttributionBuilder(
            llm_call,
            round_obj,
            session_summary,
            session_context,
        ).build_response()
    return BaseAttributionBuilder(
        llm_call,
        round_obj,
        session_summary,
        session_context,
    ).build_response()
