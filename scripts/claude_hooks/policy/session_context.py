"""Handle Claude session lifecycle hook events.

SessionStart and SubagentStart hooks use this module to create lightweight runtime
evidence. The handler deliberately avoids injecting large context into the agent; failure
semantics are non-blocking and only record the event.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..evidence import record_hook_event
from ..paths import ensure_runtime_dirs

if TYPE_CHECKING:
    from ..hook_io import HookContext
    from ..paths import RepoPaths


# 01. SessionStart/SubagentStart 处理
def handle_session_start(paths: RepoPaths, ctx: HookContext, event_label: str) -> None:
    """Record a session lifecycle event without blocking execution.

    Args:
        paths: Repository runtime paths for hook evidence output.
        ctx: Parsed Claude hook context.
        event_label: Session lifecycle label, such as ``session-start``.
    """
    ensure_runtime_dirs(paths)
    record_hook_event(paths, ctx, status='SESSION', extra={'sessionEvent': event_label})
