"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from session_browser.domain._validation import non_negative_float, non_negative_int

if TYPE_CHECKING:
    from session_browser.domain.subagent_models import SubagentSummary


@dataclass
class ToolCall:
    """ToolCall contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        name: Public contract field or enum value.
        parameters: Public contract field or enum value.
        result: Public contract field or enum value.
        status: Public contract field or enum value.
        duration_ms: Public contract field or enum value.
        timestamp: Public contract field or enum value.
        exit_code: Public contract field or enum value.
        error_message: Public contract field or enum value.
        files_touched: Public contract field or enum value.
        round_index: Public contract field or enum value.
        tool_use_id: Public contract field or enum value.
        scope: Public contract field or enum value.
        parent_tool_use_id: Public contract field or enum value.
        parent_tool_name: Public contract field or enum value.
        subagent_id: Public contract field or enum value.
        subagent_summary: Public contract field or enum value.
        llm_call_count: Public contract field or enum value.
        llm_error_count: Public contract field or enum value.
        subagent_tool_call_count: Public contract field or enum value.
        subagent_failed_tool_count: Public contract field or enum value.
    """

    name: str
    parameters: dict = field(default_factory=dict)
    result: str = ''
    status: str = 'completed'
    duration_ms: float = 0
    timestamp: str = ''
    exit_code: int | None = None
    error_message: str = ''
    files_touched: list[str] = field(default_factory=list)
    round_index: int = 0
    tool_use_id: str = ''
    scope: str = 'main'
    parent_tool_use_id: str = ''
    parent_tool_name: str = ''
    subagent_id: str = ''
    subagent_summary: SubagentSummary | dict[str, Any] = field(default_factory=dict)
    llm_call_count: int = 0
    llm_error_count: int = 0
    subagent_tool_call_count: int = 0
    subagent_failed_tool_count: int = 0

    def __post_init__(self) -> None:
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        self.duration_ms = non_negative_float('duration_ms', self.duration_ms)
        for field_name in (
            'round_index',
            'llm_call_count',
            'llm_error_count',
            'subagent_tool_call_count',
            'subagent_failed_tool_count',
        ):
            setattr(self, field_name, non_negative_int(field_name, getattr(self, field_name)))
        if self.exit_code is not None:
            self.exit_code = int(self.exit_code)

    @property
    def is_failed(self) -> bool:
        """is_failed method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.status == 'error'

    @property
    def has_nonzero_exit(self) -> bool:
        """has_nonzero_exit method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.exit_code is not None and self.exit_code != 0
