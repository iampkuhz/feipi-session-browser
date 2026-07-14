"""统一定义 lifecycle 错误分类与紧凑协议；不负责执行恢复，由 controller 与 CLI 调用。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

from scripts.agent_runtime.storage import write_json_atomic

PASS = 'PASS'
REPAIR_REQUIRED = 'REPAIR_REQUIRED'
BUSY_RETRYABLE = 'BUSY_RETRYABLE'
CAPABILITY_RETRYABLE = 'CAPABILITY_RETRYABLE'
COMMITTED_HANDOFF = 'COMMITTED_HANDOFF'
TERMINAL_BLOCKED = 'TERMINAL_BLOCKED'
INTERNAL_ERROR = 'INTERNAL_ERROR'

EXIT_CODES = {
    PASS: 0,
    REPAIR_REQUIRED: 2,
    BUSY_RETRYABLE: 3,
    CAPABILITY_RETRYABLE: 4,
    COMMITTED_HANDOFF: 5,
    TERMINAL_BLOCKED: 6,
    INTERNAL_ERROR: 70,
}


class LifecycleError(RuntimeError):
    """携带稳定状态、错误码和唯一可执行下一动作的 controller 异常。"""

    def __init__(
        self,
        status: str,
        code: str,
        message: str,
        *,
        repair_argv: Iterable[str] = (),
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if status not in EXIT_CODES or status == PASS:
            raise ValueError(f'unsupported lifecycle error status: {status}')
        super().__init__(message)
        self.status = status
        self.code = code
        self.repair_argv = tuple(repair_argv)
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class RootFailure:
    """默认协议只暴露首个独立根因，依赖阻断只保留计数。"""

    code: str
    message: str
    path: str = ''
    line: int = 0
    repair_paths: tuple[str, ...] = ()
    rerun_argv: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """生成紧凑协议字段；不附加完整 Gate 输出。"""
        return {
            'code': self.code,
            'message': self.message,
            'path': self.path or None,
            'line': self.line or None,
            'repairPaths': list(self.repair_paths),
            'rerunArgv': list(self.rerun_argv),
        }


def classify_gate_failures(
    details: Iterable[Any],
) -> tuple[RootFailure | None, int, list[dict[str, Any]]]:
    """按 executionState/dependsOn 区分独立根因与 dependent BLOCKED。"""
    independent: list[dict[str, Any]] = []
    dependent = 0
    for detail in details:
        status = str(getattr(detail, 'status', '') or '').upper()
        if status not in {'FAIL', 'BLOCKED', 'SKIPPED'}:
            continue
        state = str(getattr(detail, 'executionState', '') or '').upper()
        output = str(getattr(detail, 'output', '') or '').strip()
        if state in {'DEPENDENCY_BLOCKED', 'DEPENDENT_BLOCKED'} or 'dependency' in state.lower():
            dependent += 1
            continue
        command = tuple(str(part) for part in (getattr(detail, 'command', None) or ()))
        independent.append(
            {
                'name': str(getattr(detail, 'name', '') or 'required-gate'),
                'status': status,
                'message': output[-1000:] or f'required gate {status.lower()}',
                'rerunArgv': list(command),
            }
        )
    if not independent:
        return None, dependent, independent
    first = independent[0]
    return (
        RootFailure(
            code=f'GATE_{first["status"]}',
            message=first['message'],
            rerun_argv=tuple(first['rerunArgv']),
        ),
        dependent,
        independent,
    )


def compact_payload(
    *,
    status: str,
    state: str,
    code: str,
    session_id: str = '',
    change_id: str = '',
    attempt_id: str = '',
    candidate_tree: str = '',
    commit_sha: str = '',
    result_ref: str = '',
    integration_status: str = '',
    next_action: str = '',
    root_failure: RootFailure | Mapping[str, Any] | None = None,
    dependent_blocked_count: int = 0,
    artifact_path: str = '',
    metrics: Mapping[str, int] | None = None,
    repair_argv: Iterable[str] = (),
    idempotent: bool = False,
) -> dict[str, Any]:
    """构造稳定单对象协议；完整 Git/Gate 事实只能写入 artifact。"""
    failure = root_failure.as_dict() if isinstance(root_failure, RootFailure) else root_failure
    return {
        'status': status,
        'state': state,
        'code': code,
        'sessionId': session_id or None,
        'changeId': change_id or None,
        'attemptId': attempt_id or None,
        'candidateTree': candidate_tree or None,
        'commitSha': commit_sha or None,
        'resultRef': result_ref or None,
        'integrationStatus': integration_status or None,
        'nextAction': next_action or None,
        'rootFailure': failure,
        'dependentBlockedCount': dependent_blocked_count,
        'artifactPath': artifact_path or None,
        'metrics': dict(metrics or {}),
        'repairArgv': list(repair_argv),
        'idempotent': idempotent,
    }


def encode_compact(payload: Mapping[str, Any], *, limit: int = 4096) -> str:
    """序列化协议并硬限制 4 KiB；超限是 controller bug，不能静默截断字段。"""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > limit:
        raise LifecycleError(INTERNAL_ERROR, 'OUTPUT_TOO_LARGE', 'compact protocol exceeds 4 KiB')
    return encoded


def write_artifact(path: Path, facts: Mapping[str, Any]) -> Path:
    """完整事实原子落入 run-scoped ignored runtime，stdout 只引用路径。"""
    write_json_atomic(path, dict(facts))
    return path
