"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from session_browser.domain._validation import non_negative_float, non_negative_int

if TYPE_CHECKING:
    from pathlib import Path

    from session_browser.domain.message_models import ChatMessage
    from session_browser.domain.tool_models import ToolCall

_SUMMARY_FIELDS = {
    'agent_id',
    'agent_type',
    'agent_nickname',
    'nickname',
    'description',
    'parent_thread_id',
    'depth',
    'status',
    'llm_call_count',
    'llm_error_count',
    'assistant_event_count',
    'tool_call_count',
    'failed_tool_count',
    'tool_counts',
    'input_tokens',
    'output_tokens',
    'cache_read_input_tokens',
    'cache_creation_input_tokens',
    'started_at',
    'ended_at',
    'duration_ms',
    'path',
}


@dataclass
class SubagentSummary:
    """SubagentSummary contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        agent_id: Public contract field or enum value.
        agent_type: Public contract field or enum value.
        agent_nickname: Public contract field or enum value.
        nickname: Public contract field or enum value.
        description: Public contract field or enum value.
        parent_thread_id: Public contract field or enum value.
        depth: Public contract field or enum value.
        status: Public contract field or enum value.
        llm_call_count: Public contract field or enum value.
        llm_error_count: Public contract field or enum value.
        assistant_event_count: Public contract field or enum value.
        tool_call_count: Public contract field or enum value.
        failed_tool_count: Public contract field or enum value.
        tool_counts: Public contract field or enum value.
        input_tokens: Public contract field or enum value.
        output_tokens: Public contract field or enum value.
        cache_read_input_tokens: Public contract field or enum value.
        cache_creation_input_tokens: Public contract field or enum value.
        started_at: Public contract field or enum value.
        ended_at: Public contract field or enum value.
        duration_ms: Public contract field or enum value.
        path: Public contract field or enum value.
        extras: Public contract field or enum value.
    """

    agent_id: str
    agent_type: str = ''  # Runtime role label such as implementer/explore/code.
    agent_nickname: str = ''  # Optional Codex UI nickname for the child agent.
    nickname: str = ''  # Backward-compatible alias used by spawn_agent payloads.
    description: str = ''  # Parent prompt/description used to match Agent tools.
    parent_thread_id: str = ''  # Parent Codex thread/session id when available.
    depth: int = 0  # Subagent nesting depth reported by the runtime.
    status: str = ''  # Adapter status string: ok/error/success/failed/empty.

    llm_call_count: int = 0
    llm_error_count: int = 0
    assistant_event_count: int = 0
    tool_call_count: int = 0
    failed_tool_count: int = 0
    tool_counts: dict[str, int] = field(default_factory=dict)

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    started_at: str = ''
    ended_at: str = ''
    duration_ms: float = 0
    path: str = ''
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """__post_init__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        for field_name in (
            'depth',
            'llm_call_count',
            'llm_error_count',
            'assistant_event_count',
            'tool_call_count',
            'failed_tool_count',
            'input_tokens',
            'output_tokens',
            'cache_read_input_tokens',
            'cache_creation_input_tokens',
        ):
            setattr(
                self,
                field_name,
                non_negative_int(f'subagent_summary.{field_name}', getattr(self, field_name)),
            )
        self.duration_ms = non_negative_float('subagent_summary.duration_ms', self.duration_ms)
        self.tool_counts = {
            str(name): non_negative_int(f'subagent_summary.tool_counts.{name}', count)
            for name, count in dict(self.tool_counts or {}).items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | SubagentSummary) -> SubagentSummary:
        """from_dict method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            data: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        if isinstance(data, cls):
            return data
        data = data if isinstance(data, dict) else {}
        known = {key: data.get(key) for key in _SUMMARY_FIELDS if key in data}
        extras = {str(key): value for key, value in data.items() if key not in _SUMMARY_FIELDS}
        return cls(
            agent_id=str(known.get('agent_id') or ''),
            agent_type=str(known.get('agent_type') or ''),
            agent_nickname=str(known.get('agent_nickname') or ''),
            nickname=str(known.get('nickname') or ''),
            description=str(known.get('description') or ''),
            parent_thread_id=str(known.get('parent_thread_id') or ''),
            depth=known.get('depth') or 0,
            status=str(known.get('status') or ''),
            llm_call_count=known.get('llm_call_count') or 0,
            llm_error_count=known.get('llm_error_count') or 0,
            assistant_event_count=known.get('assistant_event_count') or 0,
            tool_call_count=known.get('tool_call_count') or 0,
            failed_tool_count=known.get('failed_tool_count') or 0,
            tool_counts=dict(known.get('tool_counts') or {}),
            input_tokens=known.get('input_tokens') or 0,
            output_tokens=known.get('output_tokens') or 0,
            cache_read_input_tokens=known.get('cache_read_input_tokens') or 0,
            cache_creation_input_tokens=known.get('cache_creation_input_tokens') or 0,
            started_at=str(known.get('started_at') or ''),
            ended_at=str(known.get('ended_at') or ''),
            duration_ms=known.get('duration_ms') or 0,
            path=str(known.get('path') or ''),
            extras=extras,
        )

    def _as_legacy_dict(self) -> dict[str, Any]:
        """_as_legacy_dict method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        data: dict[str, Any] = {
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
            'agent_nickname': self.agent_nickname,
            'nickname': self.nickname,
            'description': self.description,
            'parent_thread_id': self.parent_thread_id,
            'depth': self.depth,
            'status': self.status,
            'llm_call_count': self.llm_call_count,
            'llm_error_count': self.llm_error_count,
            'assistant_event_count': self.assistant_event_count,
            'tool_call_count': self.tool_call_count,
            'failed_tool_count': self.failed_tool_count,
            'tool_counts': dict(self.tool_counts),
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'cache_read_input_tokens': self.cache_read_input_tokens,
            'cache_creation_input_tokens': self.cache_creation_input_tokens,
            'started_at': self.started_at,
            'ended_at': self.ended_at,
            'duration_ms': self.duration_ms,
            'path': self.path,
        }
        data.update(self.extras)
        return data

    def get(self, key: str, default: Any = None) -> Any:
        """Get method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            key: Input value supplied by the caller for this pipeline step.
            default: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self._as_legacy_dict().get(key, default)

    def __getitem__(self, key: str) -> Any:
        """__getitem__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            key: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self._as_legacy_dict()[key]

    def __contains__(self, key: object) -> bool:
        """__contains__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            key: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return isinstance(key, str) and key in self._as_legacy_dict()


@dataclass
class SubagentRun:
    """SubagentRun contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        summary: Public contract field or enum value.
        messages: Public contract field or enum value.
        tool_calls: Public contract field or enum value.
        path: Public contract field or enum value.
        parent_tool_use_id: Public contract field or enum value.
        extras: Public contract field or enum value.
    """

    summary: SubagentSummary
    messages: list[ChatMessage] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    path: str | Path = ''  # Source sidechain file path for lazy loading/debugging.
    parent_tool_use_id: str = ''  # Parent Agent/spawn tool id once matched.
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | SubagentRun) -> SubagentRun:
        """from_dict method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            data: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        if isinstance(data, cls):
            return data
        data = data if isinstance(data, dict) else {}
        return cls(
            summary=SubagentSummary.from_dict(
                data.get('summary')
                if isinstance(data.get('summary'), dict | SubagentSummary)
                else {}
            ),
            messages=list(data.get('messages') or []),
            tool_calls=list(data.get('tool_calls') or []),
            path=data.get('path') or '',
            parent_tool_use_id=str(data.get('parent_tool_use_id') or ''),
            extras={
                str(key): value
                for key, value in data.items()
                if key not in {'summary', 'messages', 'tool_calls', 'path', 'parent_tool_use_id'}
            },
        )

    @property
    def agent_id(self) -> str:
        """agent_id method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.summary.agent_id

    @property
    def live_tool_call_count(self) -> int:
        """live_tool_call_count method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return len(self.tool_calls)

    @property
    def live_failed_tool_count(self) -> int:
        """live_failed_tool_count method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return sum(1 for tool in self.tool_calls if tool.is_failed)

    def _as_legacy_dict(self) -> dict[str, Any]:
        """_as_legacy_dict method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        data: dict[str, Any] = {
            'path': str(self.path) if self.path else '',
            'parent_tool_use_id': self.parent_tool_use_id,
            'summary': self.summary._as_legacy_dict(),
            'messages': self.messages,
            'tool_calls': self.tool_calls,
        }
        data.update(self.extras)
        return data

    def get(self, key: str, default: Any = None) -> Any:
        """Get method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            key: Input value supplied by the caller for this pipeline step.
            default: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self._as_legacy_dict().get(key, default)

    def __getitem__(self, key: str) -> Any:
        """__getitem__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            key: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self._as_legacy_dict()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """__setitem__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            key: Input value supplied by the caller for this pipeline step.
            value: Input value supplied by the caller for this pipeline step.
        """
        if key == 'summary':
            self.summary = SubagentSummary.from_dict(value)
        elif key == 'messages':
            self.messages = list(value or [])
        elif key == 'tool_calls':
            self.tool_calls = list(value or [])
        elif key == 'path':
            self.path = value or ''
        elif key == 'parent_tool_use_id':
            self.parent_tool_use_id = str(value or '')
        else:
            self.extras[str(key)] = value

    def __contains__(self, key: object) -> bool:
        """__contains__ method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            key: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return isinstance(key, str) and key in self._as_legacy_dict()
