from __future__ import annotations

from ..hook_io import HookContext
from ..paths import RepoPaths, ensure_runtime_dirs
from ..evidence import record_hook_event


# 01. SessionStart/SubagentStart 处理
def handle_session_start(paths: RepoPaths, ctx: HookContext, event_label: str) -> None:
    """记录会话启动；不注入重型上下文，避免污染主 agent。"""

    ensure_runtime_dirs(paths)
    record_hook_event(paths, ctx, status="SESSION", extra={"sessionEvent": event_label})
