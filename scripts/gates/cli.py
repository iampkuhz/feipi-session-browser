#!/usr/bin/env python3
"""提供 manual、preflight、Stop 共用的唯一 Gate service 与命令行入口。

不负责产品业务处理；由 Gate CLI 或 Stop pipeline 调用。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.gates import (  # noqa: E402
    executor,
    report,
    support,  # noqa: E402
)
from scripts.gates.catalog import CATALOG_VERSION, TARGETS, gate_by_name, tier_by_name  # noqa: E402
from scripts.gates.model import ExecutionPlan, GatePlan, TargetGatePlan  # noqa: E402
from scripts.gates.planner import plan as build_plan  # noqa: E402


@dataclass(frozen=True, slots=True)
class GateServiceResult:
    """保存一次统一 Gate service 的 typed 状态、计划、明细与产物路径。"""

    status: str
    plan: GatePlan
    details: tuple[report.GateDetail, ...]
    artifact_path: Path | None

    @property
    def passed(self) -> bool:
        """仅当总体状态严格为 PASS 时返回 True。"""
        return self.status == report.PASS


def resolve_change_id(explicit: str | None, repo_root: Path = REPO_ROOT) -> str:
    """优先采用显式 change id，否则读取 active change evidence。"""
    if explicit:
        return explicit
    active = repo_root / 'tmp' / 'active_change.json'
    try:
        data = json.loads(active.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return 'manual-run'
    value = data.get('change_id') if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else 'manual-run'


def get_changed_files(explicit: str | None, repo_root: Path = REPO_ROOT) -> list[str]:
    """从显式 JSON 或当前 identity 的 evidence/Git 基线收集 changed files。"""
    if explicit is not None:
        return support.parse_changed_files_json(explicit)
    identity = support.identity_from_values()
    log_dirs = support.session_log_dirs(
        repo_root,
        identity,
        include_agents=identity.has_session and not identity.is_agent,
    )
    recorded = support.read_recorded_changed_files_from_paths(
        [path / 'changed-files.jsonl' for path in log_dirs],
        identity.raw_session_id or None,
        agent_id=identity.raw_agent_id or None,
    )
    base_commit = support.agent_log_dir(repo_root, identity) / 'base-commit.txt'
    return support.dedupe_paths(
        recorded + support.read_files_since_base_commit(repo_root, base_commit)
    )


def _with_preflight(gate_plan: GatePlan) -> GatePlan:
    """把不可绕过的全局 preflight Gate 注入同一不可变计划。"""
    preflight_target = TargetGatePlan(
        target='python-standard',
        gates=(
            gate_by_name('ignoredTrackedFiles'),
            gate_by_name('misplacedGeneratedPaths'),
        ),
    )
    return GatePlan(
        changed_files=gate_plan.changed_files,
        classifications=gate_plan.classifications,
        raw_targets=gate_plan.raw_targets,
        effective_targets=gate_plan.effective_targets,
        targets=(preflight_target, *gate_plan.targets),
    )


def create_plan(
    changed_files: list[str],
    *,
    tier: str,
    target: str | None,
    explicit_changed_files: bool,
) -> GatePlan:
    """为显式 target 或 tier 构造唯一 catalog 驱动的不可变计划。"""
    tier_by_name(tier)
    if target:
        return build_plan(
            changed_files,
            [target],
            tier=tier,
            incremental=explicit_changed_files,
        )
    targets = [item.name for item in TARGETS] if tier == 'full' else None
    return build_plan(
        changed_files,
        targets,
        tier=tier,
        incremental=tier != 'full',
    )


def _overall_status(details: tuple[report.GateDetail, ...]) -> str:
    """归约总体状态，绝不把 skipped、warning 或空结果当作 PASS。"""
    statuses = {detail.status.upper() for detail in details}
    if report.FAIL in statuses or report.SKIPPED in statuses:
        return report.FAIL
    if report.BLOCKED in statuses or not details:
        return report.BLOCKED
    return report.PASS


def _build_execution_metadata(execution_plan: ExecutionPlan) -> dict[str, object]:
    """从冻结执行计划派生报告所需的 group 与进程计数元数据。"""
    return {
        'planId': execution_plan.plan_id,
        'planFingerprint': execution_plan.fingerprint,
        'catalogVersion': CATALOG_VERSION,
        'commandGroups': [
            {
                'groupId': group.group_id,
                'kind': group.kind,
                'gates': list(group.gate_names),
                'command': list(group.command),
                'resources': list(group.resources),
                'dependsOn': list(group.depends_on),
                'aggregationReason': group.aggregation_reason,
            }
            for group in execution_plan.groups
        ],
        'processCounts': {
            'gradle': sum(group.kind == 'gradle' for group in execution_plan.groups),
            'python': sum(
                bool(group.command) and Path(group.command[0]).name.startswith('python')
                for group in execution_plan.groups
            ),
            'bash': sum(
                bool(group.command) and Path(group.command[0]).name == 'bash'
                for group in execution_plan.groups
            ),
            'total': sum(bool(group.command) for group in execution_plan.groups),
        },
    }


def run_service(
    *,
    repo_root: Path,
    changed_files: list[str],
    tier: str = 'required',
    target: str | None = None,
    change_id: str = 'manual-run',
    out_dir: Path | None = None,
    explicit_changed_files: bool = True,
    base_url: str | None = None,
    include_preflight: bool = True,
    environment_overrides: dict[str, str] | None = None,
) -> GateServiceResult:
    """按“规划 → 冻结执行计划 → 执行 → 状态归约 → 报告”运行 Gate service。"""
    # 先由 planner 选择 Gate，再一次性冻结命令、资源依赖和 fingerprint。
    gate_plan = create_plan(
        changed_files,
        tier=tier,
        target=target,
        explicit_changed_files=explicit_changed_files,
    )
    execution_plan = _with_preflight(gate_plan) if include_preflight else gate_plan
    resolved_plan = executor.build_execution_plan(execution_plan, repo_root, base_url=base_url)
    # executor 只消费冻结计划；严格状态归约和报告在执行结束后分别完成。
    output = out_dir or repo_root / 'tmp' / 'quality'
    details = executor.execute_plan(
        resolved_plan,
        repo_root,
        environment_overrides={
            'QUALITY_GATE_TIER': tier,
            **(environment_overrides or {}),
        },
    )
    status = _overall_status(details)
    label = target or tier
    started_at = report.utc_now()
    summary = report.build_summary(
        label,
        change_id,
        started_at,
        list(details),
        repo_root=repo_root,
        execution_metadata=_build_execution_metadata(resolved_plan),
    )
    summary.status = status
    artifact = report.write_quality_summary(output, summary, target_specific=True)
    return GateServiceResult(status, gate_plan, details, artifact)


def _dry_run_payload(gate_plan: GatePlan, repo_root: Path) -> dict[str, object]:
    """返回稳定、可机器读取且不执行子进程的 dry-run 摘要。"""
    resolved = executor.build_execution_plan(_with_preflight(gate_plan), repo_root)
    groups = {group.group_id: group for group in resolved.groups}
    commands = [
        {
            'target': gate.target,
            'gate': gate.name,
            'groupId': gate.group_id,
            'statusSource': gate.status_source,
            'command': list(groups[gate.group_id].command),
        }
        for gate in resolved.gates
    ]
    return {
        'planId': resolved.plan_id,
        'planFingerprint': resolved.fingerprint,
        'changedFiles': list(gate_plan.changed_files),
        'rawTargets': list(gate_plan.raw_targets),
        'effectiveTargets': list(gate_plan.effective_targets),
        'commands': commands,
        'groups': [
            {
                'groupId': group.group_id,
                'kind': group.kind,
                'gates': list(group.gate_names),
                'command': list(group.command),
                'resources': list(group.resources),
                'dependsOn': list(group.depends_on),
                'aggregationReason': group.aggregation_reason,
            }
            for group in resolved.groups
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """解析统一 CLI，并按 fail-closed 语义返回进程退出码。"""
    parser = argparse.ArgumentParser(description='Unified typed Gate service')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--target', choices=sorted(target.name for target in TARGETS))
    mode.add_argument('--tier', choices=('quick', 'required', 'full'), default='required')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--changed-files', default=None, help='JSON array of repository paths')
    parser.add_argument('--out', default='tmp/quality')
    parser.add_argument('--change-id', default=None)
    parser.add_argument('--base-url', default=None, help='Explicit BASE_URL for browser Gates')
    parser.add_argument('--allow-empty-changed-files-because', default=None)
    args = parser.parse_args(argv)

    repo_root = Path.cwd()
    changed_files = get_changed_files(args.changed_files, repo_root)
    if args.changed_files is not None and not changed_files:
        dirty = support.read_git_dirty_files(repo_root)
        if dirty and not (args.allow_empty_changed_files_because or '').strip():
            print(
                'GATE_SERVICE_RESULT status=BLOCKED reason=explicit-empty-changed-files',
                file=sys.stderr,
            )
            return 1

    tier = args.tier or 'required'
    gate_plan = create_plan(
        changed_files,
        tier=tier,
        target=args.target,
        explicit_changed_files=args.changed_files is not None,
    )
    if args.dry_run:
        print(
            json.dumps(_dry_run_payload(gate_plan, repo_root), ensure_ascii=False, sort_keys=True)
        )
        return 0

    out = Path(args.out)
    if not out.is_absolute():
        out = repo_root / out
    result = run_service(
        repo_root=repo_root,
        changed_files=changed_files,
        tier=tier,
        target=args.target,
        change_id=resolve_change_id(args.change_id, repo_root),
        out_dir=out,
        explicit_changed_files=args.changed_files is not None,
        base_url=args.base_url or os.environ.get('BASE_URL'),
    )
    print(
        report.format_quality_report(
            json.loads(result.artifact_path.read_text(encoding='utf-8')),
            result.artifact_path,
        )
    )
    return 0 if result.passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
