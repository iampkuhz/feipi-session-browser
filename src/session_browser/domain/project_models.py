"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from session_browser.domain._validation import non_negative_int


@dataclass
class ProjectStats:
    """ProjectStats contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        project_key: Public contract field or enum value.
        project_name: Public contract field or enum value.
        total_sessions: Public contract field or enum value.
        claude_sessions: Public contract field or enum value.
        codex_sessions: Public contract field or enum value.
        qoder_sessions: Public contract field or enum value.
        first_seen: Public contract field or enum value.
        last_seen: Public contract field or enum value.
        total_fresh_input_tokens: Public contract field or enum value.
        total_output_tokens: Public contract field or enum value.
        total_cache_read_tokens: Public contract field or enum value.
        total_cache_write_tokens: Public contract field or enum value.
        total_tool_calls: Public contract field or enum value.
        total_user_messages: Public contract field or enum value.
        total_assistant_messages: Public contract field or enum value.
        total_failed_tools: Public contract field or enum value.
    """

    project_key: str
    project_name: str
    total_sessions: int = 0
    claude_sessions: int = 0
    codex_sessions: int = 0
    qoder_sessions: int = 0
    first_seen: str = ''
    last_seen: str = ''
    total_fresh_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_tool_calls: int = 0
    total_user_messages: int = 0
    total_assistant_messages: int = 0
    total_failed_tools: int = 0

    def __post_init__(self) -> None:
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        for field_name in (
            'total_sessions',
            'claude_sessions',
            'codex_sessions',
            'qoder_sessions',
            'total_fresh_input_tokens',
            'total_output_tokens',
            'total_cache_read_tokens',
            'total_cache_write_tokens',
            'total_tool_calls',
            'total_user_messages',
            'total_assistant_messages',
            'total_failed_tools',
        ):
            setattr(self, field_name, non_negative_int(field_name, getattr(self, field_name)))
