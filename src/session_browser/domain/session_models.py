"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from session_browser.domain._validation import non_negative_float, non_negative_int


@dataclass
class SessionSummary:
    """SessionSummary contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        agent: Public contract field or enum value.
        session_id: Public contract field or enum value.
        title: Public contract field or enum value.
        project_key: Public contract field or enum value.
        project_name: Public contract field or enum value.
        cwd: Public contract field or enum value.
        started_at: Public contract field or enum value.
        ended_at: Public contract field or enum value.
        duration_seconds: Public contract field or enum value.
        model_execution_seconds: Public contract field or enum value.
        tool_execution_seconds: Public contract field or enum value.
        model: Public contract field or enum value.
        git_branch: Public contract field or enum value.
        source: Public contract field or enum value.
        user_message_count: Public contract field or enum value.
        assistant_message_count: Public contract field or enum value.
        tool_call_count: Public contract field or enum value.
        output_tokens: Public contract field or enum value.
        has_sensitive_data: Public contract field or enum value.
        fresh_input_tokens: Public contract field or enum value.
        cache_read_tokens: Public contract field or enum value.
        cache_write_tokens: Public contract field or enum value.
        total_tokens: Public contract field or enum value.
        failed_tool_count: Public contract field or enum value.
        subagent_instance_count: Public contract field or enum value.
        parse_diagnostics: Public contract field or enum value.
        file_path: Public contract field or enum value.
    """

    agent: str  # Runtime identifier: claude_code, codex, qoder, or future adapter id.
    session_id: str
    title: str
    project_key: str  # Normalized full project path/key used for filtering.
    project_name: str  # Display name, usually basename of project_key.
    cwd: str
    started_at: str  # ISO8601 first visible event timestamp.
    ended_at: str  # ISO8601 last visible event timestamp.
    duration_seconds: float = 0  # Wall-clock span from first to last event.
    model_execution_seconds: float = 0  # Merged visible LLM response intervals.
    tool_execution_seconds: float = 0  # Merged visible tool/subagent intervals.
    model: str = ''
    git_branch: str = ''
    source: str = ''  # Runtime source such as cli, vscode, fixture, or empty.
    user_message_count: int = 0
    assistant_message_count: int = 0
    tool_call_count: int = 0  # Persisted snapshot; live traces should use len(tool_calls).
    output_tokens: int = 0
    has_sensitive_data: bool = True

    fresh_input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0

    failed_tool_count: int = (
        0  # Persisted snapshot; live traces should derive from ToolCall.is_failed.
    )
    subagent_instance_count: int = 0
    parse_diagnostics: dict | None = None
    file_path: str = ''

    def __post_init__(self) -> None:
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        self.duration_seconds = non_negative_float('duration_seconds', self.duration_seconds)
        self.model_execution_seconds = non_negative_float(
            'model_execution_seconds', self.model_execution_seconds
        )
        self.tool_execution_seconds = non_negative_float(
            'tool_execution_seconds', self.tool_execution_seconds
        )
        for field_name in (
            'user_message_count',
            'assistant_message_count',
            'tool_call_count',
            'output_tokens',
            'fresh_input_tokens',
            'cache_read_tokens',
            'cache_write_tokens',
            'total_tokens',
            'failed_tool_count',
            'subagent_instance_count',
        ):
            setattr(self, field_name, non_negative_int(field_name, getattr(self, field_name)))
        if self.total_tokens == 0 and self.token_component_total > 0:
            self.total_tokens = self.token_component_total

    @property
    def session_key(self) -> str:
        """session_key method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return f'{self.agent}:{self.session_id}'

    @property
    def token_component_total(self) -> int:
        """token_component_total method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return (
            self.fresh_input_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + self.output_tokens
        )
