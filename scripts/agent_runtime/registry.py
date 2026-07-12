"""向 Hook 暴露统一的 Session Registry 服务边界。

本模块只适配 ``primary_session`` 与 ``sessionctl`` 的权威能力，不复制状态机、
writer lease 或 checkout 校验规则；Hook 事件不得绕过这里直接拼装 Registry 记录。"""

from __future__ import annotations

from scripts.harness.primary_session import (
    ACTIVE_WRITER_STATUSES,
    resolve_bound_run_record,
    validate_run_write_authorization,
)
from scripts.harness.sessionctl import (
    Registry,
    SessionctlError,
    WriterLeaseConflict,
    WriterLeaseFenced,
    acquire_writer_lease,
    bootstrap_session,
    classify_tool_call,
    heartbeat_writer_lease,
    mark_read_only_ready,
    release_writer_lease,
)

__all__ = [
    'ACTIVE_WRITER_STATUSES',
    'Registry',
    'SessionctlError',
    'WriterLeaseConflict',
    'WriterLeaseFenced',
    'acquire_writer_lease',
    'bootstrap_session',
    'classify_tool_call',
    'heartbeat_writer_lease',
    'mark_read_only_ready',
    'release_writer_lease',
    'resolve_bound_run_record',
    'validate_run_write_authorization',
]
