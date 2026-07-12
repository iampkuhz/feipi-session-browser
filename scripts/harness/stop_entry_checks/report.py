"""Stop summary 写入与路径计算。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.claude_hooks import paths as runtime_paths

from ._io import utc_now


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
    status = (
        'PASS'
        if not failures and run_status == 'VALIDATED'
        else 'BLOCKED'
    )
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
        'checkoutCreator': str(checkout_facts.get('checkoutCreator') or record.get('checkoutCreator') or 'unknown'),
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
