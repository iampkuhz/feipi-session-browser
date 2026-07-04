"""提供 session context 脚本能力。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..evidence import record_hook_event
from ..paths import ensure_runtime_dirs
from scripts.quality import changed_files as changed_file_utils

if TYPE_CHECKING:
    from ..hook_io import HookContext
    from ..paths import RepoPaths


# 分发 session 启动事件。
def handle_session_start(paths: RepoPaths, ctx: HookContext, event_label: str) -> None:
    """参数：
        paths: Repository 运行time 路径用于hook evidence 输出。
        ctx: 已解析的Claude hook context。
        event_label: event label 参数。
    """
    ensure_runtime_dirs(paths)
    if ctx.session_id:
        paths.session_id_file.write_text(ctx.session_id + '\n', encoding='utf-8')
    changed_file_utils.write_base_commit_if_missing(
        paths.repo_root,
        paths.base_commit,
        overwrite=event_label == 'session-start',
    )
    record_hook_event(paths, ctx, status='SESSION', extra={'sessionEvent': event_label})
