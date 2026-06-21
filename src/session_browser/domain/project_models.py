"""Project aggregate domain models."""

from __future__ import annotations

from dataclasses import dataclass

from session_browser.domain._validation import non_negative_int


@dataclass
class ProjectStats:
    """Aggregated statistics for one project key."""

    project_key: str
    project_name: str
    total_sessions: int = 0
    claude_sessions: int = 0
    codex_sessions: int = 0
    qoder_sessions: int = 0
    first_seen: str = ""
    last_seen: str = ""
    total_fresh_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_tool_calls: int = 0
    total_user_messages: int = 0
    total_assistant_messages: int = 0
    total_failed_tools: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "total_sessions",
            "claude_sessions",
            "codex_sessions",
            "qoder_sessions",
            "total_fresh_input_tokens",
            "total_output_tokens",
            "total_cache_read_tokens",
            "total_cache_write_tokens",
            "total_tool_calls",
            "total_user_messages",
            "total_assistant_messages",
            "total_failed_tools",
        ):
            setattr(self, field_name, non_negative_int(field_name, getattr(self, field_name)))
