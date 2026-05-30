"""Session context builder for attribution.

Provides ``build_attribution_session_context`` which constructs a call-scoped
context dict that attribution builders use to determine:
- preceding_tool_results: tool results that occurred before the current LLM call
- prior_messages: conversation history before this call
- available_tools: tool schemas available to the model

This avoids passing session_context=None and enables proper call-scoped
attribution rather than attributing the entire round's tool results to
every LLM call.
"""

from __future__ import annotations

from session_browser.domain.models import (
    ConversationRound,
    LLMCall,
    SessionSummary,
    ToolCall,
)


def build_attribution_session_context(
    *,
    session: SessionSummary,
    round_obj: ConversationRound,
    interaction_index: int,
    interactions: list[LLMCall],
    round_tool_calls: list[ToolCall],
    existing_context: dict | None = None,
) -> dict:
    """Build a call-scoped session context for attribution builders.

    Args:
        session: The session summary object.
        round_obj: The current conversation round.
        interaction_index: 0-based index of the current LLM interaction within the round.
        interactions: List of LLM interactions in the current round.
        round_tool_calls: All tool calls associated with this round.
        existing_context: Optional pre-existing context to extend (unused in v1).

    Returns:
        A dict with at least:
        - interaction_index: the 0-based index
        - preceding_tool_results: list of tool result texts from interactions
          that occurred BEFORE the current one
        - prior_messages: reserved for future use (currently [])
        - available_tools: reserved for future use (currently [])
    """
    preceding_tool_results: list[str] = []

    if interaction_index > 0:
        # Gather tool results from prior interactions in this round
        for ix in interactions[:interaction_index]:
            if hasattr(ix, "tool_calls") and ix.tool_calls:
                for tc in ix.tool_calls:
                    if tc.result and not getattr(tc, "subagent_id", ""):
                        preceding_tool_results.append(tc.result)
    # else: first LLM call — no preceding tool results

    return {
        "interaction_index": interaction_index,
        "preceding_tool_results": preceding_tool_results,
        # TODO: populate prior_messages from session transcript when source parser exposes it.
        "prior_messages": [],
        # TODO: populate available_tools from agent source metadata when parser exposes it.
        "available_tools": [],
    }
