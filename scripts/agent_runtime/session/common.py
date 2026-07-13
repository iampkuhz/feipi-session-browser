"""负责统一 Session 状态迁移、审计身份与 JSON 输出；不负责读写 Git 或选择 Gate；由 lifecycle、lease 与 finalize 调用。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime.storage import utc_now

from .contract import validate_status_transition
from .errors import SessionctlError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .registry import Registry

LEASE_RECORD_FIELDS = (
    "leaseId",
    "holderRunId",
    "holderSessionId",
    "runId",
    "sessionId",
    "client",
    "repoKey",
    "worktreeId",
    "checkoutRoot",
    "checkoutKind",
    "epoch",
    "fencingToken",
    "state",
    "heartbeatAt",
    "acquiredAt",
    "updatedAt",
    "owner",
    "ownerUid",
    "pid",
    "processStartTime",
)


def emit_json(payload: Any) -> None:
    """用稳定缩进与键顺序输出 CLI JSON，避免各 Session 子命令形成不同格式。"""
    print(json.dumps(payload, indent=2, sort_keys=True))


def _lease_record_view(lease: Mapping[str, Any]) -> dict[str, Any]:
    """只投影写入运行记录所需的 lease fencing 字段，排除非契约元数据。"""
    return {field: lease[field] for field in LEASE_RECORD_FIELDS if field in lease}


def _append_run_audit(registry: Registry, record: dict[str, Any], event: dict[str, Any]) -> None:
    events = record.setdefault('auditEvents', [])
    if not isinstance(events, list):
        raise SessionctlError('run auditEvents must be a list')
    events.append(event)
    registry.write_audit(event)


def audit_run(
    registry: Registry,
    record: dict[str, Any],
    event: str,
    *,
    at: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    """追加带权威运行身份的审计事件，并返回实际持久化的数据。"""
    payload = {
        "event": event,
        "runId": record["runId"],
        "sessionId": record["sessionId"],
        "worktreeId": record["worktreeId"],
        **details,
        "at": at or utc_now(),
    }
    _append_run_audit(registry, record, payload)
    return payload


def _set_run_status(record: dict[str, Any], status: str) -> None:
    previous = str(record.get('status') or '')
    if previous != status:
        validate_status_transition(previous, status)
        record['status'] = status


def _writer_status(record: Mapping[str, Any]) -> str:
    return 'LOCAL_WRITER' if record.get('checkoutKind') == 'primary-checkout' else 'ISOLATED_WRITER'


def _parse_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
