"""Claude Code attribution builder class.

Thin class that delegates build_request and build_response to
extracted modules in claude_code_parts.
"""

from __future__ import annotations

from session_browser.attribution.contracts import (
    LLMRequestAttribution,
    LLMResponseAttribution,
)
from session_browser.attribution.agents.base import BaseAttributionBuilder
from session_browser.attribution.agents.claude_code_parts.request_builder import (
    build_request as _build_request,
)
from session_browser.attribution.agents.claude_code_parts.response_builder import (
    build_response as _build_response,
)


class ClaudeCodeAttributionBuilder(BaseAttributionBuilder):
    """Request / response attribution for Claude Code sessions."""

    def build_request(self) -> LLMRequestAttribution:
        """Build request attribution for a Claude Code LLM call."""
        return _build_request(self)

    def build_response(self) -> LLMResponseAttribution:
        """Build response attribution for a Claude Code LLM call."""
        return _build_response(self)
