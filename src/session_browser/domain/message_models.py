"""Chat message and conversation-round domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from session_browser.domain._validation import non_negative_int, ratio_0_to_1
from session_browser.domain.content_part import ContentPart
from session_browser.domain.llm_models import LLMCall
from session_browser.domain.tool_models import ToolCall


@dataclass
class ChatMessage:
    """A visible user or assistant message from a session transcript."""

    role: str
    content: str
    timestamp: str
    model: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: Optional[dict] = None
    token_ratio: float = 0
    llm_call_id: str = ""
    llm_status: str = "ok"
    request_full: str = ""
    stop_reason: str = ""
    content_parts: list[ContentPart] = field(default_factory=list)
    content_blocks: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.token_ratio = ratio_0_to_1("token_ratio", self.token_ratio)


@dataclass
class ConversationRound:
    """Trace grouping for one user/assistant exchange.

    This object is a domain grouping, not a UI row. Trace preview text and
    tool-chip HTML are presenter/view-model concerns.
    """

    user_msg: ChatMessage
    assistant_msg: ChatMessage
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_tokens: int = 0
    token_ratio: float = 0
    round_index: int = 0
    llm_call_count: int = 0
    llm_error_count: int = 0
    interactions: list[LLMCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.total_tokens = non_negative_int("total_tokens", self.total_tokens)
        self.token_ratio = ratio_0_to_1("token_ratio", self.token_ratio)
        self.round_index = non_negative_int("round_index", self.round_index)
        self.llm_call_count = non_negative_int("llm_call_count", self.llm_call_count)
        self.llm_error_count = non_negative_int("llm_error_count", self.llm_error_count)

    @property
    def input_tokens(self) -> int:
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get("input_tokens", 0)
        return 0

    @property
    def output_tokens(self) -> int:
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get("output_tokens", 0)
        return 0

    @property
    def cached_tokens(self) -> int:
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get(
                "cache_read_input_tokens",
                self.assistant_msg.usage.get("cached_input_tokens", 0),
            )
        return 0

    @property
    def cache_write_tokens(self) -> int:
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get("cache_creation_input_tokens", 0)
        return 0

    def token_breakdown(self) -> dict:
        """Return this round's legacy token component dict."""
        if not self.assistant_msg.usage:
            return {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
        return {
            "input": self.assistant_msg.usage.get("input_tokens", 0),
            "cache_read": self.assistant_msg.usage.get(
                "cache_read_input_tokens",
                self.assistant_msg.usage.get("cached_input_tokens", 0),
            ),
            "cache_write": self.assistant_msg.usage.get("cache_creation_input_tokens", 0),
            "output": self.assistant_msg.usage.get("output_tokens", 0),
        }
