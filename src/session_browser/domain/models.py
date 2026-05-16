"""Domain models for session-browser."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone


# ─── Token types ───────────────────────────────────────────────────────────


class TokenPrecision:
    EXACT = "exact"
    PROVIDER_REPORTED = "provider-reported"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class TokenProvider:
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    CODEX = "codex"
    QWEN_ANTHROPIC_COMPATIBLE = "qwen-anthropic-compatible"
    QODER = "qoder"
    UNKNOWN = "unknown"


@dataclass
class TokenBreakdown:
    """Per-round or per-session token usage breakdown.

    All fields are in tokens. Missing fields are None, not 0.
    """

    # Input-side
    input_fresh: Optional[int] = None
    input_cache_read: Optional[int] = None
    input_cache_write: Optional[int] = None

    # Output-side
    output_visible: Optional[int] = None
    output_reasoning: Optional[int] = None
    output_thinking: Optional[int] = None

    # Tool-related
    tool_definition_input: Optional[int] = None
    tool_call_output: Optional[int] = None
    tool_result_input: Optional[int] = None

    # Computed totals
    total_input: Optional[int] = None
    total_output: Optional[int] = None

    precision: str = TokenPrecision.UNKNOWN
    provider: Optional[str] = None
    raw_fields: dict = field(default_factory=dict)

    def compute_totals(self) -> None:
        """Compute total_input and total_output from breakdown fields."""
        # total_input = input_fresh + input_cache_read + input_cache_write
        input_parts = [
            self.input_fresh or 0,
            self.input_cache_read or 0,
            self.input_cache_write or 0,
        ]
        if any(p is not None for p in [self.input_fresh, self.input_cache_read, self.input_cache_write]):
            self.total_input = sum(input_parts)

        # total_output = output_visible + output_reasoning + output_thinking
        output_parts = [
            self.output_visible or 0,
            self.output_reasoning or 0,
            self.output_thinking or 0,
        ]
        if any(p is not None for p in [self.output_visible, self.output_reasoning, self.output_thinking]):
            self.total_output = sum(output_parts)


# ─── Session / Message / Tool models ──────────────────────────────────────


@dataclass
class SessionSummary:
    """Unified session index model for Claude Code, Codex, and Qoder."""

    agent: str  # "claude_code" | "codex" | "qoder"
    session_id: str
    title: str
    project_key: str  # full normalized path
    project_name: str  # last path segment
    cwd: str
    started_at: str  # ISO8601
    ended_at: str  # ISO8601
    duration_seconds: float = 0  # wall-clock: first event to last event
    model_execution_seconds: float = 0  # merged LLM response intervals (user msg → assistant msg)
    tool_execution_seconds: float = 0   # merged tool + subagent intervals (tool_use → tool_result)
    model: str = ""
    git_branch: str = ""
    source: str = ""  # "cli" | "vscode" | ...
    user_message_count: int = 0
    assistant_message_count: int = 0
    tool_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0  # cache_read_input_tokens
    cached_output_tokens: int = 0  # cache_creation_input_tokens (write cache)
    has_sensitive_data: bool = True

    # New fields for token breakdown
    token_breakdown: Optional[TokenBreakdown] = None
    failed_tool_count: int = 0

    @property
    def session_key(self) -> str:
        return f"{self.agent}:{self.session_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["session_key"] = self.session_key
        return d


@dataclass
class ChatMessage:
    """A single chat message (user or assistant) in a session."""

    role: str  # "user" | "assistant"
    content: str
    timestamp: str  # ISO8601
    model: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # for assistant messages
    usage: Optional[dict] = None  # token usage for assistant messages
    content_html: str = ""  # pre-rendered markdown HTML
    token_ratio: float = 0  # proportion of session tokens used in this message
    token_breakdown: Optional[TokenBreakdown] = None  # per-message token breakdown
    llm_call_id: str = ""  # provider/Claude message id, one logical LLM call
    llm_status: str = "ok"  # "ok" | "error"
    request_full: str = ""  # logged request context preceding this assistant response
    content_parts: list["ContentPart"] = field(default_factory=list)  # typed content parts


@dataclass
class ToolCall:
    """A tool invocation record."""

    name: str
    parameters: dict = field(default_factory=dict)
    result: str = ""
    status: str = "completed"  # "completed" | "error"
    duration_ms: float = 0
    timestamp: str = ""
    exit_code: Optional[int] = None
    error_message: str = ""
    files_touched: list[str] = field(default_factory=list)
    round_index: int = 0
    tool_use_id: str = ""
    scope: str = "main"  # "main" | "subagent"
    parent_tool_use_id: str = ""
    parent_tool_name: str = ""
    subagent_id: str = ""
    subagent_summary: dict = field(default_factory=dict)
    llm_call_count: int = 0
    llm_error_count: int = 0
    subagent_tool_call_count: int = 0
    subagent_failed_tool_count: int = 0

    @property
    def is_failed(self) -> bool:
        """Tool call itself failed (runtime error, API error, user rejection, etc.).

        A nonzero exit_code from Bash does NOT mean the tool call failed —
        it just records the command's return code, which may be business
        logic (e.g. rg found no matches, grep returned 1, test failed).
        """
        return self.status == "error"

    @property
    def has_nonzero_exit(self) -> bool:
        """Command returned a nonzero exit code, regardless of tool status."""
        return self.exit_code is not None and self.exit_code != 0


@dataclass
class LLMCall:
    """One logical LLM API call (main agent or subagent)."""

    id: str                          # msg["id"] — the llm_call_id
    model: str                       # e.g. "qwen3.6-plus", "claude-sonnet-4-6"
    scope: str                       # "main" | "subagent"
    subagent_id: str                 # "" for main; agent_id for subagent
    round_index: int                 # 0-based round index
    parent_id: str                   # "" for main; parent Agent tool_use_id for subagent
    parent_tool_name: str            # "" for main; "Agent" for subagent
    timestamp: str                   # ISO8601
    status: str                      # "ok" | "error"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    prompt_preview: str = ""         # first ~200 chars of prompt context
    request_preview: str = ""        # first ~200 chars of logged request
    request_full: str = ""           # full logged request context (rendered, NOT raw HTTP payload)
    response_preview: str = ""       # first ~200 chars of response
    response_full: str = ""          # full response text (for expand)
    # Raw HTTP request payload fields (distinct from request_full)
    request_payload_raw: str = ""    # raw HTTP request JSON sent to the model (if persisted)
    request_payload_message_count: int = 0  # message count in raw payload
    request_payload_bytes: int = 0   # byte size of raw payload
    request_payload_missing_reason: str = ""  # why raw payload is unavailable
    # Raw HTTP response payload fields (distinct from response_full)
    response_payload_raw: str = ""   # raw HTTP response JSON from the model (if persisted)
    response_payload_missing_reason: str = ""  # why raw response is unavailable
    finish_reason: str = ""          # e.g. "end_turn", "tool_use", "max_tokens", "stop_sequence"
    tool_calls_raw: str = ""         # raw tool calls JSON structure (if available)
    tool_calls: list["ToolCall"] = field(default_factory=list)
    tool_call_count: int = 0
    failed_tool_count: int = 0


@dataclass
class ConversationRound:
    """One exchange: user message + assistant response + tool calls."""

    user_msg: ChatMessage
    assistant_msg: ChatMessage
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_tokens: int = 0
    token_ratio: float = 0  # proportion of total session tokens
    round_index: int = 0
    llm_call_count: int = 0
    llm_error_count: int = 0
    interactions: list[LLMCall] = field(default_factory=list)
    preview_text: str = ""  # concise human-readable summary for timeline table

    @staticmethod
    def _compact_preview_text(text: str, limit: int = 120) -> str:
        """Compress whitespace and truncate text for preview display."""
        import re
        if not text:
            return ""
        compacted = re.sub(r'\s+', ' ', text).strip()
        if len(compacted) > limit:
            return compacted[:limit].rstrip() + '…'
        return compacted

    @staticmethod
    def _format_tool_counts(tools: list[ToolCall]) -> str:
        """Return tool count fragments as HTML-safe <span> tags for each tool.
        Format: <span class=\"preview-tool\">Bash</span>×1 · <span class=\"preview-tool\">Read</span>×2
        """
        if not tools:
            return ""
        tool_counts: dict[str, int] = {}
        for tc in tools:
            tool_counts[tc.name] = tool_counts.get(tc.name, 0) + 1
        parts = [
            f'<span class="preview-tool">{name}</span>×{count}'
            for name, count in tool_counts.items()
        ]
        return ' · '.join(parts)

    def compute_preview(self) -> None:
        """Derive a short preview from interactions/tool_calls after they are assigned.

        Priority:
        1. LLM response text (+ tool counts if present)
        2. User input text (+ tool counts if present)
        3. Tool counts only
        """
        all_tools: list[ToolCall] = []
        has_subagent = False
        subagent_response = ""
        for ix in self.interactions:
            if ix.scope == "main":
                all_tools.extend(ix.tool_calls)
            elif ix.scope == "subagent":
                has_subagent = True
                all_tools.extend(ix.tool_calls)
                if not subagent_response and ix.response_preview:
                    subagent_response = ix.response_preview

        # No tools, no user input — only assistant response
        has_user_input = bool(self.user_msg.content)
        if not all_tools and not has_user_input:
            content = self.assistant_msg.content
            if content:
                self.preview_text = self._compact_preview_text(content, 120)
            return

        tool_summary = self._format_tool_counts(all_tools) if all_tools else ""

        # Subagent: prefer response text over generic subagent label
        if has_subagent:
            if subagent_response:
                preview = self._compact_preview_text(subagent_response, 100)
                if tool_summary:
                    preview = f"{preview} · {tool_summary}"
            else:
                # Fallback: show subagent label + tools
                sub_desc = ""
                for ix in self.interactions:
                    if ix.scope == "subagent" and ix.parent_tool_name:
                        sub_desc = ix.parent_tool_name
                        break
                if tool_summary:
                    preview = f"Subagent({sub_desc}) · {tool_summary}"
                else:
                    preview = f"Subagent({sub_desc})"
            self.preview_text = preview
            return

        # Main agent with tool calls
        if all_tools:
            content = self.assistant_msg.content
            if content:
                # Response + tools
                preview = self._compact_preview_text(content, 100)
                self.preview_text = f"{preview} · {tool_summary}"
            else:
                # Tools only
                self.preview_text = tool_summary
            return

        # No tool calls but has user input — show truncated user message
        content = self.user_msg.content
        if content:
            self.preview_text = self._compact_preview_text(content, 120)

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
            return self.assistant_msg.usage.get("cache_read_input_tokens", 0)
        return 0

    @property
    def cache_write_tokens(self) -> int:
        """cache_creation_input_tokens: tokens being written to cache this turn."""
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get("cache_creation_input_tokens", 0)
        return 0

    def token_breakdown(self) -> dict:
        """Return a dict of token categories for this round."""
        if not self.assistant_msg.usage:
            return {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
        return {
            "input": self.assistant_msg.usage.get("input_tokens", 0),
            "cache_read": self.assistant_msg.usage.get("cache_read_input_tokens", 0),
            "cache_write": self.assistant_msg.usage.get("cache_creation_input_tokens", 0),
            "output": self.assistant_msg.usage.get("output_tokens", 0),
        }


@dataclass
class ProjectStats:
    """Aggregated statistics for a project."""

    project_key: str
    project_name: str
    total_sessions: int = 0
    claude_sessions: int = 0
    codex_sessions: int = 0
    qoder_sessions: int = 0
    first_seen: str = ""
    last_seen: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0  # cache read
    total_cache_write_tokens: int = 0  # cache write
    total_tool_calls: int = 0
    total_user_messages: int = 0
    total_assistant_messages: int = 0
    total_failed_tools: int = 0
