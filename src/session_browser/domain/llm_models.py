"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from session_browser.domain._validation import non_negative_int

if TYPE_CHECKING:
    from session_browser.domain.token_models import NormalizedTokenBreakdown
    from session_browser.domain.tool_models import ToolCall


@dataclass(frozen=True)
class LLMCallIdentity:
    """LLMCallIdentity contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        id: Public contract field or enum value.
        model: Public contract field or enum value.
        scope: Public contract field or enum value.
        subagent_id: Public contract field or enum value.
        round_index: Public contract field or enum value.
        parent_id: Public contract field or enum value.
        parent_tool_name: Public contract field or enum value.
        timestamp: Public contract field or enum value.
        status: Public contract field or enum value.
    """

    id: str
    model: str
    scope: str
    subagent_id: str
    round_index: int
    parent_id: str
    parent_tool_name: str
    timestamp: str
    status: str


@dataclass(frozen=True)
class LLMCallUsage:
    """LLMCallUsage contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        input_tokens: Public contract field or enum value.
        output_tokens: Public contract field or enum value.
        cache_read_tokens: Public contract field or enum value.
        cache_write_tokens: Public contract field or enum value.
        total_tokens: Public contract field or enum value.
        token_breakdown_normalized: Public contract field or enum value.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    token_breakdown_normalized: NormalizedTokenBreakdown | None = None

    def __post_init__(self) -> None:
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        object.__setattr__(
            self, 'input_tokens', non_negative_int('input_tokens', self.input_tokens)
        )
        object.__setattr__(
            self, 'output_tokens', non_negative_int('output_tokens', self.output_tokens)
        )
        object.__setattr__(
            self, 'cache_read_tokens', non_negative_int('cache_read_tokens', self.cache_read_tokens)
        )
        object.__setattr__(
            self,
            'cache_write_tokens',
            non_negative_int('cache_write_tokens', self.cache_write_tokens),
        )
        object.__setattr__(
            self, 'total_tokens', non_negative_int('total_tokens', self.total_tokens)
        )


@dataclass(frozen=True)
class LLMCallPayloadRefs:
    """LLMCallPayloadRefs contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        request_payload_raw: Public contract field or enum value.
        request_payload_message_count: Public contract field or enum value.
        request_payload_bytes: Public contract field or enum value.
        request_payload_missing_reason: Public contract field or enum value.
        response_payload_raw: Public contract field or enum value.
        response_payload_missing_reason: Public contract field or enum value.
    """

    request_payload_raw: str = ''
    request_payload_message_count: int = 0
    request_payload_bytes: int = 0
    request_payload_missing_reason: str = ''
    response_payload_raw: str = ''
    response_payload_missing_reason: str = ''

    def __post_init__(self) -> None:
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        object.__setattr__(
            self,
            'request_payload_message_count',
            non_negative_int('request_payload_message_count', self.request_payload_message_count),
        )
        object.__setattr__(
            self,
            'request_payload_bytes',
            non_negative_int('request_payload_bytes', self.request_payload_bytes),
        )


@dataclass(frozen=True)
class LLMCallContent:
    """LLMCallContent contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        prompt_preview: Public contract field or enum value.
        request_preview: Public contract field or enum value.
        request_full: Public contract field or enum value.
        response_preview: Public contract field or enum value.
        response_full: Public contract field or enum value.
        finish_reason: Public contract field or enum value.
        tool_calls_raw: Public contract field or enum value.
        content_blocks: Public contract field or enum value.
    """

    prompt_preview: str = ''
    request_preview: str = ''
    request_full: str = ''
    response_preview: str = ''
    response_full: str = ''
    finish_reason: str = ''
    tool_calls_raw: str = ''
    content_blocks: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class LLMCallStats:
    """LLMCallStats contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        tool_call_count: Public contract field or enum value.
        failed_tool_count: Public contract field or enum value.
    """

    tool_call_count: int = 0
    failed_tool_count: int = 0

    def __post_init__(self) -> None:
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        object.__setattr__(
            self, 'tool_call_count', non_negative_int('tool_call_count', self.tool_call_count)
        )
        object.__setattr__(
            self, 'failed_tool_count', non_negative_int('failed_tool_count', self.failed_tool_count)
        )


@dataclass
class LLMCall:
    """LLMCall contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        id: Public contract field or enum value.
        model: Public contract field or enum value.
        scope: Public contract field or enum value.
        subagent_id: Public contract field or enum value.
        round_index: Public contract field or enum value.
        parent_id: Public contract field or enum value.
        parent_tool_name: Public contract field or enum value.
        timestamp: Public contract field or enum value.
        status: Public contract field or enum value.
        input_tokens: Public contract field or enum value.
        output_tokens: Public contract field or enum value.
        cache_read_tokens: Public contract field or enum value.
        cache_write_tokens: Public contract field or enum value.
        total_tokens: Public contract field or enum value.
        prompt_preview: Public contract field or enum value.
        request_preview: Public contract field or enum value.
        request_full: Public contract field or enum value.
        response_preview: Public contract field or enum value.
        response_full: Public contract field or enum value.
        request_payload_raw: Public contract field or enum value.
        request_payload_message_count: Public contract field or enum value.
        request_payload_bytes: Public contract field or enum value.
        request_payload_missing_reason: Public contract field or enum value.
        response_payload_raw: Public contract field or enum value.
        response_payload_missing_reason: Public contract field or enum value.
        finish_reason: Public contract field or enum value.
        tool_calls_raw: Public contract field or enum value.
        content_blocks: Public contract field or enum value.
        tool_calls: Public contract field or enum value.
        tool_call_count: Public contract field or enum value.
        failed_tool_count: Public contract field or enum value.
        token_breakdown_normalized: Public contract field or enum value.
        identity: Public contract field or enum value.
        usage: Public contract field or enum value.
        payload_refs: Public contract field or enum value.
        content: Public contract field or enum value.
        stats: Public contract field or enum value.
    """

    id: str
    model: str
    scope: str
    subagent_id: str
    round_index: int
    parent_id: str
    parent_tool_name: str
    timestamp: str
    status: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    prompt_preview: str = ''
    request_preview: str = ''
    request_full: str = ''
    response_preview: str = ''
    response_full: str = ''
    request_payload_raw: str = ''
    request_payload_message_count: int = 0
    request_payload_bytes: int = 0
    request_payload_missing_reason: str = ''
    response_payload_raw: str = ''
    response_payload_missing_reason: str = ''
    finish_reason: str = ''
    tool_calls_raw: str = ''
    content_blocks: list[dict] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_count: int = 0
    failed_tool_count: int = 0
    token_breakdown_normalized: NormalizedTokenBreakdown | None = None

    identity: LLMCallIdentity = field(init=False)
    usage: LLMCallUsage = field(init=False)
    payload_refs: LLMCallPayloadRefs = field(init=False)
    content: LLMCallContent = field(init=False)
    stats: LLMCallStats = field(init=False)

    def __post_init__(self) -> None:
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Raises:
                    ValueError: Raised when validation or file lookup rejects the input.
        """
        self.round_index = non_negative_int('round_index', self.round_index)
        self.input_tokens = non_negative_int('input_tokens', self.input_tokens)
        self.output_tokens = non_negative_int('output_tokens', self.output_tokens)
        self.cache_read_tokens = non_negative_int('cache_read_tokens', self.cache_read_tokens)
        self.cache_write_tokens = non_negative_int('cache_write_tokens', self.cache_write_tokens)
        self.total_tokens = non_negative_int('total_tokens', self.total_tokens)
        self.request_payload_message_count = non_negative_int(
            'request_payload_message_count',
            self.request_payload_message_count,
        )
        self.request_payload_bytes = non_negative_int(
            'request_payload_bytes', self.request_payload_bytes
        )
        self.tool_call_count = non_negative_int('tool_call_count', self.tool_call_count)
        self.failed_tool_count = non_negative_int('failed_tool_count', self.failed_tool_count)
        if self.tool_calls:
            actual_tool_count = len(self.tool_calls)
            actual_failed_count = sum(1 for tool in self.tool_calls if tool.is_failed)
            if self.tool_call_count not in (0, actual_tool_count):
                raise ValueError(
                    'tool_call_count must match len(tool_calls) when tool_calls are present'
                )
            if self.failed_tool_count not in (0, actual_failed_count):
                raise ValueError(
                    'failed_tool_count must match failed tools when tool_calls are present'
                )
            self.tool_call_count = actual_tool_count
            self.failed_tool_count = actual_failed_count
        if self.total_tokens == 0:
            self.total_tokens = (
                self.input_tokens
                + self.cache_read_tokens
                + self.cache_write_tokens
                + self.output_tokens
            )

        self.identity = LLMCallIdentity(
            id=self.id,
            model=self.model,
            scope=self.scope,
            subagent_id=self.subagent_id,
            round_index=self.round_index,
            parent_id=self.parent_id,
            parent_tool_name=self.parent_tool_name,
            timestamp=self.timestamp,
            status=self.status,
        )
        self.usage = LLMCallUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens,
            total_tokens=self.total_tokens,
            token_breakdown_normalized=self.token_breakdown_normalized,
        )
        self.payload_refs = LLMCallPayloadRefs(
            request_payload_raw=self.request_payload_raw,
            request_payload_message_count=self.request_payload_message_count,
            request_payload_bytes=self.request_payload_bytes,
            request_payload_missing_reason=self.request_payload_missing_reason,
            response_payload_raw=self.response_payload_raw,
            response_payload_missing_reason=self.response_payload_missing_reason,
        )
        self.content = LLMCallContent(
            prompt_preview=self.prompt_preview,
            request_preview=self.request_preview,
            request_full=self.request_full,
            response_preview=self.response_preview,
            response_full=self.response_full,
            finish_reason=self.finish_reason,
            tool_calls_raw=self.tool_calls_raw,
            content_blocks=self.content_blocks,
        )
        self.stats = LLMCallStats(
            tool_call_count=self.tool_call_count,
            failed_tool_count=self.failed_tool_count,
        )
