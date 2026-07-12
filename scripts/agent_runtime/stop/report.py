"""Stop 报告域：直接消费 GateServiceResult 并持久化运行摘要。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime import paths as runtime_paths
from scripts.checks import check_agent_runtime_report

from .recovery import utc_now

if TYPE_CHECKING:
    from pathlib import Path


# 计算运行报告的输出路径。
def runtime_report_path(
    repo_root: Path,
    identity: Any,
    change_id: str,
) -> Path:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前运行身份。
        change_id: 变更标识。

    返回：
        运行报告的输出路径。
    """
    if not identity.has_run or not identity.has_session:
        raise ValueError('runtime report requires an authoritative run identity')
    return runtime_paths.quality_dir(repo_root, identity) / change_id / 'runtime-report.json'


# 计算停止检查摘要的输出路径。
def stop_summary_path(
    repo_root: Path,
    identity: Any,
    agent: str,
) -> Path:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前运行身份。
        agent: 代理名称。

    返回：
        停止检查摘要的输出路径。
    """
    del agent
    if not identity.has_run or not identity.has_session:
        raise ValueError('Stop summary requires an authoritative run identity')
    return runtime_paths.agent_log_dir(repo_root, identity) / 'stop-check-summary.json'


# 写入停止检查摘要文档。
def write_summary(path: Path, payload: dict[str, Any]) -> None:
    """参数：
        path: 摘要输出路径。
        payload: 待写入的摘要内容。

    返回：
        无返回值。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


# 组装停止检查摘要字典。
def build_summary(
    *,
    identity: Any,
    record: dict[str, Any],
    checkout_facts: dict[str, Any],
    git_evidence: dict[str, Any],
    change_id: str,
    changed_files: list[str],
    targets: list[str],
    resource_lock_names: list[str],
    read_only: bool,
    evidence_mode: str,
    failures: list[str],
    warnings: list[str],
    continuation_count: int,
    circuit_state: str,
    run_status: str,
    lock_status: str,
    summary_path: Path,
    report_path: Path,
    reentry_path: Path,
) -> dict[str, Any]:
    """参数：
        identity: 当前运行身份。
        record: 当前会话记录。
        checkout_facts: 检出状态事实。
        git_evidence: 版本库证据。
        change_id: 变更标识。
        changed_files: 变更文件列表。
        targets: 必需质量目标列表。
        resource_lock_names: 资源锁名称列表。
        read_only: 是否为只读运行。
        evidence_mode: 证据收集模式。
        failures: 阻断失败列表。
        warnings: 警告列表。
        continuation_count: 连续执行次数。
        circuit_state: 熔断状态。
        run_status: 运行状态。
        lock_status: 资源锁状态。
        summary_path: 摘要输出路径。
        report_path: 运行报告路径。
        reentry_path: 重入状态路径。

    返回：
        停止检查摘要字典。
    """
    status = 'PASS' if not failures and run_status == 'VALIDATED' else 'BLOCKED'
    return {
        'schemaVersion': 5,
        'ts': utc_now(),
        'runId': identity.raw_run_id,
        'client': identity.client,
        'sessionId': identity.raw_session_id,
        'taskId': identity.raw_task_id,
        'worktreeId': identity.raw_worktree_id,
        'branch': identity.branch or str(record.get('branch') or ''),
        'observedBranch': str(checkout_facts.get('branch') or ''),
        'detached': bool(checkout_facts.get('detached', record.get('detached', False))),
        'checkoutKind': str(checkout_facts.get('checkoutKind') or record.get('checkoutKind') or ''),
        'checkoutCreator': str(
            checkout_facts.get('checkoutCreator') or record.get('checkoutCreator') or 'unknown'
        ),
        'gitCommonDir': str(checkout_facts.get('gitCommonDir') or record.get('gitCommonDir') or ''),
        'baseCommit': str(record.get('baseCommit') or ''),
        'baseCommitExists': checkout_facts.get('baseCommitExists'),
        'baseIsAncestorOfHead': checkout_facts.get('baseIsAncestorOfHead'),
        'headCommit': git_evidence.get('headCommit', ''),
        'commits': git_evidence.get('commits', []),
        'committedFiles': git_evidence.get('committedFiles', []),
        'uncommittedFiles': git_evidence.get('uncommittedFiles', []),
        'untrackedFiles': git_evidence.get('untrackedFiles', []),
        'ahead': git_evidence.get('ahead', 0),
        'behind': git_evidence.get('behind', 0),
        'aheadBehind': git_evidence.get('aheadBehind', {'ahead': 0, 'behind': 0}),
        'mergeBase': git_evidence.get('mergeBase', ''),
        'initialDirtySnapshot': git_evidence.get('initialDirtySnapshot', {}),
        'initialDirtyBaseline': git_evidence.get('initialDirtyBaseline', {}),
        'changeAttribution': git_evidence.get('changeAttribution', {}),
        'checkoutStatus': git_evidence.get('checkoutStatus', {}),
        'targetBranch': git_evidence.get('targetBranch', str(record.get('targetBranch') or '')),
        'targetHead': git_evidence.get('targetHead', ''),
        'targetState': git_evidence.get('targetState', 'UNKNOWN'),
        'targetStatus': git_evidence.get('targetStatus', {}),
        'primaryStatus': git_evidence.get('primaryStatus', {}),
        'changeId': change_id,
        'readOnly': read_only,
        'status': status,
        'runStatus': run_status,
        'evidenceMode': evidence_mode,
        'changedFiles': changed_files,
        'requiredTargets': targets,
        'resourceLocks': resource_lock_names,
        'lockStatus': lock_status,
        'blockingFailures': failures,
        'warnings': warnings,
        'continuationCount': continuation_count,
        'circuitState': circuit_state,
        'artifacts': {
            'summary': str(summary_path),
            'runtimeReport': str(report_path),
            'reentry': str(reentry_path),
        },
    }


# Gate runtime report 使用的稳定执行状态。
EXECUTED = 'EXECUTED'
REUSED = 'REUSED'
NOT_TRIGGERED = 'NOT_TRIGGERED'
FAILED = 'FAILED'
BLOCKED = 'BLOCKED'


def gate_result_records(service_result: Any | None, *, read_only: bool) -> list[dict[str, str]]:
    """把 GateServiceResult 转换成 Stop 报告状态，绝不把 NOT_TRIGGERED 改写成 PASS。"""
    if read_only or service_result is None:
        return [{'name': 'required', 'status': NOT_TRIGGERED}]
    reused = bool(getattr(service_result, 'reused', False))
    records: list[dict[str, str]] = []
    for detail in service_result.details:
        raw = str(detail.status).upper()
        if raw == 'PASS':
            status = REUSED if reused else EXECUTED
        elif raw == 'FAIL' or raw == 'SKIPPED':
            status = FAILED
        else:
            status = BLOCKED
        records.append({'name': detail.name, 'status': status})
    if not records:
        records.append({'name': 'required', 'status': BLOCKED})
    return records


def write_runtime_report(
    path: Path,
    *,
    identity: Any,
    change_id: str,
    changed_files: list[str],
    targets: list[str],
    gates_ok: bool,
    failures: list[str],
    git_evidence: dict[str, Any],
    service_result: Any | None = None,
    read_only: bool = False,
) -> None:
    """直接依据 typed Gate service 结果写运行报告，不回读或猜测 Gate artifact。"""
    gates = gate_result_records(service_result, read_only=read_only)
    blocked = list(failures)
    if targets and not gates_ok and 'quality checks failed' not in blocked:
        blocked.append('quality checks failed')
    if not targets and changed_files:
        blocked.append('changed files did not map to required quality targets')
    final_status = (
        'PASS'
        if not blocked
        and all(gate['status'] in {EXECUTED, REUSED, NOT_TRIGGERED} for gate in gates)
        else 'BLOCKED'
    )
    payload = {
        'schemaVersion': 1,
        'run_id': identity.raw_run_id,
        'client': identity.client,
        'session_id': identity.raw_session_id,
        'change_id': change_id,
        'created_at': utc_now(),
        'agent_platform': identity.client,
        'subagents': [],
        'changed_files': changed_files,
        'gitEvidence': git_evidence,
        'commits': git_evidence.get('commits', []),
        'committedFiles': git_evidence.get('committedFiles', []),
        'uncommittedFiles': git_evidence.get('uncommittedFiles', []),
        'untrackedFiles': git_evidence.get('untrackedFiles', []),
        'initialDirtySnapshot': git_evidence.get('initialDirtySnapshot', {}),
        'checkoutKind': git_evidence.get('checkoutKind', ''),
        'checkoutCreator': git_evidence.get('checkoutCreator', 'unknown'),
        'targetBranch': git_evidence.get('targetBranch', ''),
        'targetHead': git_evidence.get('targetHead', ''),
        'targetStatus': git_evidence.get('targetStatus', {}),
        'ahead': git_evidence.get('ahead', 0),
        'behind': git_evidence.get('behind', 0),
        'mergeBase': git_evidence.get('mergeBase', ''),
        'primary': git_evidence.get('primary', {}),
        'expected_outcomes': [
            {
                'id': chr(code),
                'required': False,
                'status': 'NOT_RUN',
                'evidence': 'not a runtime-report self-certified outcome',
            }
            for code in range(ord('A'), ord('L') + 1)
        ],
        'effect_checks': [
            {'id': 'git-changed-file-truth', 'status': 'PASS' if not failures else 'FAIL'}
        ],
        'gate_escape_rate': {'status': 'NOT_RUN', 'threshold': 0, 'escape_rate': None},
        'concurrency_matrix': [
            {'id': 'run-scoped-quality', 'status': 'PASS' if not failures else 'BLOCKED'}
        ],
        'gates': gates,
        'skipped_count': 0,
        'blocked_items': blocked,
        'risks': [],
        'notes': ['run-scoped runtime report generated by scripts/agent_runtime/stop/pipeline.py'],
        'status': final_status,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def validate_runtime_report(
    *,
    identity: Any,
    change_id: str,
    repo_root: Path,
    changed_files: list[str],
    report_path: Path,
) -> list[str]:
    """调用运行报告公共 validator 并返回所有结构错误。"""
    return check_agent_runtime_report.validate_runtime_report(
        run_id=identity.raw_run_id,
        client=identity.client,
        session_id=identity.raw_session_id,
        change_id=change_id,
        worktree_root=repo_root,
        changed_files=changed_files,
        report_path=report_path,
    )
