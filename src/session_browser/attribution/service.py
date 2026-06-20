"""LLM call attribution 统一服务入口。"""

from __future__ import annotations

from typing import Optional

from session_browser.domain.models import (
    LLMCall,
    ConversationRound,
    SessionSummary,
)
from session_browser.attribution.contracts import (
    LLMRequestAttribution,
    LLMResponseAttribution,
)
from session_browser.attribution.agents.base import BaseAttributionBuilder
from session_browser.attribution.agents.claude_code_attribution_builder import ClaudeCodeAttributionBuilder
from session_browser.attribution.agents.qoder_attribution_builder import QoderAttributionBuilder
from session_browser.attribution.agents.codex_attribution_builder import CodexAttributionBuilder


def build_llm_request_attribution(
    agent: str,
    llm_call: LLMCall,
    round_obj: ConversationRound,
    session_summary: Optional[SessionSummary] = None,
    session_context: Optional[dict] = None,
) -> LLMRequestAttribution:
    """为单个 LLM call 构造 request attribution。"""
    if agent == "claude_code":
        return ClaudeCodeAttributionBuilder(
            llm_call, round_obj, session_summary, session_context,
        ).build_request()
    elif agent == "qoder":
        return QoderAttributionBuilder(
            llm_call, round_obj, session_summary, session_context,
        ).build_request()
    elif agent == "codex":
        return CodexAttributionBuilder(
            llm_call, round_obj, session_summary, session_context,
        ).build_request()
    else:
        return BaseAttributionBuilder(
            llm_call, round_obj, session_summary, session_context,
        ).build_request()


def build_llm_response_attribution(
    agent: str,
    llm_call: LLMCall,
    round_obj: ConversationRound,
    session_summary: Optional[SessionSummary] = None,
    session_context: Optional[dict] = None,
) -> LLMResponseAttribution:
    """为单个 LLM call 构造 response attribution。"""
    if agent == "claude_code":
        return ClaudeCodeAttributionBuilder(
            llm_call, round_obj, session_summary, session_context,
        ).build_response()
    elif agent == "qoder":
        return QoderAttributionBuilder(
            llm_call, round_obj, session_summary, session_context,
        ).build_response()
    elif agent == "codex":
        return CodexAttributionBuilder(
            llm_call, round_obj, session_summary, session_context,
        ).build_response()
    else:
        return BaseAttributionBuilder(
            llm_call, round_obj, session_summary, session_context,
        ).build_response()
