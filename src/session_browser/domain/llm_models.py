"""LLM-call domain models and composition objects."""

from __future__ import annotations

from dataclasses import dataclass, field

from session_browser.domain._validation import non_negative_int
from session_browser.domain.token_models import NormalizedTokenBreakdown
from session_browser.domain.tool_models import ToolCall


@dataclass(frozen=True)
class LLMCallIdentity:
    """Stable identity and call placement for a logical LLM API call."""

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
    """Token usage associated with a logical LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    token_breakdown_normalized: NormalizedTokenBreakdown | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_tokens", non_negative_int("input_tokens", self.input_tokens))
        object.__setattr__(self, "output_tokens", non_negative_int("output_tokens", self.output_tokens))
        object.__setattr__(self, "cache_read_tokens", non_negative_int("cache_read_tokens", self.cache_read_tokens))
        object.__setattr__(self, "cache_write_tokens", non_negative_int("cache_write_tokens", self.cache_write_tokens))
        object.__setattr__(self, "total_tokens", non_negative_int("total_tokens", self.total_tokens))


@dataclass(frozen=True)
class LLMCallPayloadRefs:
    """Raw provider payload availability metadata.

    The raw JSON strings are optional evidence references, not the rendered
    request/response text shown in the UI.
    """

    request_payload_raw: str = ""
    request_payload_message_count: int = 0
    request_payload_bytes: int = 0
    request_payload_missing_reason: str = ""
    response_payload_raw: str = ""
    response_payload_missing_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_payload_message_count",
            non_negative_int("request_payload_message_count", self.request_payload_message_count),
        )
        object.__setattr__(
            self,
            "request_payload_bytes",
            non_negative_int("request_payload_bytes", self.request_payload_bytes),
        )


@dataclass(frozen=True)
class LLMCallContent:
    """Visible request/response content and provider block metadata."""

    prompt_preview: str = ""
    request_preview: str = ""
    request_full: str = ""
    response_preview: str = ""
    response_full: str = ""
    finish_reason: str = ""
    tool_calls_raw: str = ""
    content_blocks: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class LLMCallStats:
    """Derived tool statistics for a logical LLM call."""

    tool_call_count: int = 0
    failed_tool_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_call_count", non_negative_int("tool_call_count", self.tool_call_count))
        object.__setattr__(self, "failed_tool_count", non_negative_int("failed_tool_count", self.failed_tool_count))


@dataclass
class LLMCall:
    """A logical LLM call by the main agent or a subagent.

    The public fields remain constructor-compatible with the historical model.
    New code should prefer the composed ``identity``, ``usage``, ``payload_refs``,
    ``content`` and ``stats`` objects created in ``__post_init__``.
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
    prompt_preview: str = ""
    request_preview: str = ""
    request_full: str = ""
    response_preview: str = ""
    response_full: str = ""
    request_payload_raw: str = ""
    request_payload_message_count: int = 0
    request_payload_bytes: int = 0
    request_payload_missing_reason: str = ""
    response_payload_raw: str = ""
    response_payload_missing_reason: str = ""
    finish_reason: str = ""
    tool_calls_raw: str = ""
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
        self.round_index = non_negative_int("round_index", self.round_index)
        self.input_tokens = non_negative_int("input_tokens", self.input_tokens)
        self.output_tokens = non_negative_int("output_tokens", self.output_tokens)
        self.cache_read_tokens = non_negative_int("cache_read_tokens", self.cache_read_tokens)
        self.cache_write_tokens = non_negative_int("cache_write_tokens", self.cache_write_tokens)
        self.total_tokens = non_negative_int("total_tokens", self.total_tokens)
        self.request_payload_message_count = non_negative_int(
            "request_payload_message_count", self.request_payload_message_count,
        )
        self.request_payload_bytes = non_negative_int("request_payload_bytes", self.request_payload_bytes)
        self.tool_call_count = non_negative_int("tool_call_count", self.tool_call_count)
        self.failed_tool_count = non_negative_int("failed_tool_count", self.failed_tool_count)
        if self.tool_calls:
            actual_tool_count = len(self.tool_calls)
            actual_failed_count = sum(1 for tool in self.tool_calls if tool.is_failed)
            if self.tool_call_count not in (0, actual_tool_count):
                raise ValueError("tool_call_count must match len(tool_calls) when tool_calls are present")
            if self.failed_tool_count not in (0, actual_failed_count):
                raise ValueError("failed_tool_count must match failed tools when tool_calls are present")
            self.tool_call_count = actual_tool_count
            self.failed_tool_count = actual_failed_count
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.cache_read_tokens + self.cache_write_tokens + self.output_tokens

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
