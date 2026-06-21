"""Tool-call domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

from session_browser.domain._validation import non_negative_float, non_negative_int

if TYPE_CHECKING:
    from session_browser.domain.subagent_models import SubagentSummary


@dataclass
class ToolCall:
    """One visible tool invocation and its observed result.

    ``status`` describes the tool transport/runtime status. A non-zero
    ``exit_code`` is kept separate because shell commands can fail as business
    output without the tool invocation itself failing.
    """

    name: str
    parameters: dict = field(default_factory=dict)
    result: str = ""
    status: str = "completed"
    duration_ms: float = 0
    timestamp: str = ""
    exit_code: Optional[int] = None
    error_message: str = ""
    files_touched: list[str] = field(default_factory=list)
    round_index: int = 0
    tool_use_id: str = ""
    scope: str = "main"
    parent_tool_use_id: str = ""
    parent_tool_name: str = ""
    subagent_id: str = ""
    subagent_summary: "SubagentSummary | dict[str, Any]" = field(default_factory=dict)
    llm_call_count: int = 0
    llm_error_count: int = 0
    subagent_tool_call_count: int = 0
    subagent_failed_tool_count: int = 0

    def __post_init__(self) -> None:
        self.duration_ms = non_negative_float("duration_ms", self.duration_ms)
        for field_name in (
            "round_index",
            "llm_call_count",
            "llm_error_count",
            "subagent_tool_call_count",
            "subagent_failed_tool_count",
        ):
            setattr(self, field_name, non_negative_int(field_name, getattr(self, field_name)))
        if self.exit_code is not None:
            self.exit_code = int(self.exit_code)

    @property
    def is_failed(self) -> bool:
        """Whether the tool invocation itself failed."""
        return self.status == "error"

    @property
    def has_nonzero_exit(self) -> bool:
        """Whether a command returned a non-zero process exit code."""
        return self.exit_code is not None and self.exit_code != 0
