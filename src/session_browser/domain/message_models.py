"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from session_browser.domain._validation import non_negative_int, ratio_0_to_1

if TYPE_CHECKING:
    from session_browser.domain.content_part import ContentPart
    from session_browser.domain.llm_models import LLMCall
    from session_browser.domain.tool_models import ToolCall


@dataclass
class ChatMessage:
    """ChatMessage contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        role: Public contract field or enum value.
        content: Public contract field or enum value.
        timestamp: Public contract field or enum value.
        model: Public contract field or enum value.
        tool_calls: Public contract field or enum value.
        usage: Public contract field or enum value.
        token_ratio: Public contract field or enum value.
        llm_call_id: Public contract field or enum value.
        llm_status: Public contract field or enum value.
        request_full: Public contract field or enum value.
        stop_reason: Public contract field or enum value.
        content_parts: Public contract field or enum value.
        content_blocks: Public contract field or enum value.
    """

    role: str
    content: str
    timestamp: str
    model: str = ''
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict | None = None
    token_ratio: float = 0
    llm_call_id: str = ''
    llm_status: str = 'ok'
    request_full: str = ''
    stop_reason: str = ''
    content_parts: list[ContentPart] = field(default_factory=list)
    content_blocks: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        self.token_ratio = ratio_0_to_1('token_ratio', self.token_ratio)


@dataclass
class ConversationRound:
    """ConversationRound contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        user_msg: Public contract field or enum value.
        assistant_msg: Public contract field or enum value.
        tool_calls: Public contract field or enum value.
        total_tokens: Public contract field or enum value.
        token_ratio: Public contract field or enum value.
        round_index: Public contract field or enum value.
        llm_call_count: Public contract field or enum value.
        llm_error_count: Public contract field or enum value.
        interactions: Public contract field or enum value.
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
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        self.total_tokens = non_negative_int('total_tokens', self.total_tokens)
        self.token_ratio = ratio_0_to_1('token_ratio', self.token_ratio)
        self.round_index = non_negative_int('round_index', self.round_index)
        self.llm_call_count = non_negative_int('llm_call_count', self.llm_call_count)
        self.llm_error_count = non_negative_int('llm_error_count', self.llm_error_count)

    @property
    def input_tokens(self) -> int:
        """input_tokens method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get('input_tokens', 0)
        return 0

    @property
    def output_tokens(self) -> int:
        """output_tokens method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get('output_tokens', 0)
        return 0

    @property
    def cached_tokens(self) -> int:
        """cached_tokens method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get(
                'cache_read_input_tokens',
                self.assistant_msg.usage.get('cached_input_tokens', 0),
            )
        return 0

    @property
    def cache_write_tokens(self) -> int:
        """cache_write_tokens method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get('cache_creation_input_tokens', 0)
        return 0

    def token_breakdown(self) -> dict:
        """token_breakdown method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        if not self.assistant_msg.usage:
            return {'input': 0, 'cache_read': 0, 'cache_write': 0, 'output': 0}
        return {
            'input': self.assistant_msg.usage.get('input_tokens', 0),
            'cache_read': self.assistant_msg.usage.get(
                'cache_read_input_tokens',
                self.assistant_msg.usage.get('cached_input_tokens', 0),
            ),
            'cache_write': self.assistant_msg.usage.get('cache_creation_input_tokens', 0),
            'output': self.assistant_msg.usage.get('output_tokens', 0),
        }
