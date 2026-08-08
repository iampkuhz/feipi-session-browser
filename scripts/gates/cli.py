#!/usr/bin/env python3
"""提供 Gate 规划、执行与报告的唯一命令行入口。

本模块只负责校验命令行输入并编排既有服务，不负责定义 Catalog、选择规则或具体检查逻辑；
维护者通过 ``main`` 调用完整流程，也可通过 ``run_service`` 嵌入同一执行协议。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.gates import executor, report, support  # noqa: E402
from scripts.gates.catalog import GATES, TARGETS  # noqa: E402
from scripts.gates.model import ExecutionMode, ExecutionPlan, GatePlan  # noqa: E402
from scripts.gates.planner import plan as build_plan  # noqa: E402


@dataclass(frozen=True, slots=True)
class GateServiceResult:
    """保存一次 Gate service 的对外状态、计划、明细与报告路径。"""

    status: str
    plan: GatePlan
    details: tuple[report.GateDetail, ...]
    artifact_path: Path | None

    @property
    def passed(self) -> bool:
        """仅当对外汇总严格为 PASS 时返回 True。"""
        return self.status == report.PASS


class GateArgumentParser(argparse.ArgumentParser):
    """把 argparse 输入错误交给 Gate service 的统一 NOT_PASS 输出。"""

    def error(self, message: str) -> None:
        """拒绝默认 usage/SystemExit(2)，保留稳定外部状态与 reason。"""
        raise ValueError(f'argument error: {message}')


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
    """从显式 JSON 或当前执行身份的 evidence/Git 基线收集 changed files。"""
    if explicit is not None:
        parsed = json.loads(explicit)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError('--changed-files must be a JSON string array')
        for item in parsed:
            path = PurePosixPath(item)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('--changed-files only accepts repository-relative paths')
        return support.dedupe_paths(parsed)
    identity = support.identity_from_values()
    log_dirs = support.session_log_dirs(
        repo_root, identity, include_agents=identity.has_session and not identity.is_agent
    )
    recorded = support.read_recorded_changed_files_from_paths(
        [path / 'changed-files.jsonl' for path in log_dirs],
        identity.raw_session_id or None,
        agent_id=identity.raw_agent_id or None,
    )
    base_commit = support.agent_log_dir(repo_root, identity) / 'base-commit.txt'
    return support.dedupe_paths(
        recorded
        + support.read_files_since_base_commit(repo_root, base_commit)
        + support.read_git_dirty_files(repo_root)
    )


def create_plan(
    changed_files: list[str],
    *,
    mode: ExecutionMode | str = ExecutionMode.INCREMENTAL,
    target: str | None = None,
    gate: str | None = None,
) -> GatePlan:
    """把唯一 mode 和可选 selector 交给 Gate-first planner。"""
    return build_plan(changed_files, mode=mode, target=target, gate=gate)


def _overall_status(details: tuple[report.GateDetail, ...]) -> str:
    """对外仅输出 PASS/NOT_PASS；明细保留 BLOCKED/FAIL。"""
    return (
        report.PASS
        if details and all(item.status == report.PASS for item in details)
        else report.NOT_PASS
    )


def _not_triggered_gates(gate_plan: GatePlan) -> list[str]:
    """列出自动 incremental 未选中的 Gate；人工 selector 与 full 不使用该状态。"""

    if gate_plan.mode is not ExecutionMode.INCREMENTAL or gate_plan.selector is not None:
        return []
    selected = {gate.name for gate in gate_plan.gates}
    return [gate.name for gate in GATES if gate.name not in selected]


def _build_execution_metadata(
    execution_plan: ExecutionPlan, *, input_audit_reason: str = ''
) -> dict[str, object]:
    """从冻结执行计划派生稳定 group 与进程计数。"""
    return {
        'planId': execution_plan.plan_id,
        'planFingerprint': execution_plan.fingerprint,
        'commandGroups': [
            {
                'groupId': group.group_id,
                'kind': group.kind,
                'gates': [group.gate_name],
                'command': list(group.command),
            }
            for group in execution_plan.groups
        ],
        'processCounts': {
            'gradle': sum(
                group.kind in {'gradle', 'scan-prerequisite'} for group in execution_plan.groups
            ),
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
        'inputAuditReason': input_audit_reason,
    }


def run_service(
    *,
    repo_root: Path,
    changed_files: list[str],
    mode: ExecutionMode | str = ExecutionMode.INCREMENTAL,
    target: str | None = None,
    gate: str | None = None,
    change_id: str = 'manual-run',
    out_dir: Path | None = None,
    base_url: str | None = None,
    environment_overrides: dict[str, str] | None = None,
    input_audit_reason: str = '',
) -> GateServiceResult:
    """按“规划、冻结、执行、归约、报告”运行 Gate service。"""
    overrides = environment_overrides or {}
    reserved = {'QUALITY_EXECUTION_MODE', 'QUALITY_CHANGED_FILES'} & overrides.keys()
    if reserved:
        names = ', '.join(sorted(reserved))
        raise ValueError(f'GateRequest environment cannot be overridden: {names}')
    started_at = report.utc_now()
    gate_plan = create_plan(changed_files, mode=mode, target=target, gate=gate)
    execution_plan = executor.build_execution_plan(gate_plan, repo_root, base_url=base_url)
    details = executor.execute_plan(
        execution_plan,
        repo_root,
        environment_overrides=overrides,
    )
    status = _overall_status(details)
    summary = report.build_summary(
        gate_plan.mode.value,
        change_id,
        started_at,
        list(details),
        selector=gate_plan.selector,
        selector_value=gate_plan.selector_value,
        not_triggered_gates=_not_triggered_gates(gate_plan),
        repo_root=repo_root,
        execution_metadata=_build_execution_metadata(
            execution_plan, input_audit_reason=input_audit_reason
        ),
    )
    summary.status = status
    output = out_dir or repo_root / 'tmp' / 'quality'
    artifact = report.write_quality_summary(output, summary, selection_specific=True)
    return GateServiceResult(status, gate_plan, details, artifact)


def _dry_run_payload(
    gate_plan: GatePlan, repo_root: Path, *, input_audit_reason: str = ''
) -> dict[str, object]:
    """返回稳定、可机器读取且不产生 PASS 证据的计划摘要。"""
    resolved = executor.build_execution_plan(gate_plan, repo_root)
    return {
        'planId': resolved.plan_id,
        'planFingerprint': resolved.fingerprint,
        'mode': gate_plan.mode.value,
        'selector': gate_plan.selector,
        'selectorValue': gate_plan.selector_value,
        'changedFiles': list(gate_plan.changed_files),
        'inputAuditReason': input_audit_reason,
        'gates': [item.name for item in gate_plan.gates],
        'commands': [
            {
                'gate': group.gate_name,
                'leaf': group.step_name,
                'groupId': group.group_id,
                'command': list(group.command),
            }
            for group in resolved.groups
        ],
        'groups': [
            {
                'groupId': group.group_id,
                'kind': group.kind,
                'gates': [group.gate_name],
                'command': list(group.command),
            }
            for group in resolved.groups
        ],
    }


def _health_main(argv: list[str]) -> int:
    """解析独立 health 参数；不接受日常 mode、selector 或 changed-files。"""
    from scripts.gates import health

    parser = GateArgumentParser(
        prog='python3 scripts/gates/cli.py health',
        description='Explicit full Gate health maintenance (no automatic timeout)',
    )
    parser.add_argument('--out', default='tmp/quality-health')
    parser.add_argument('--change-id', default=None)
    repo_root = Path.cwd()
    try:
        args = parser.parse_args(argv)
    except ValueError as exc:
        print(
            f'GATE_HEALTH_RESULT status=FAIL reason=input-unavailable detail={exc}',
            file=sys.stderr,
        )
        return 2
    out = Path(args.out)
    if not out.is_absolute():
        out = repo_root / out
    try:
        result = health.run_health(
            repo_root=repo_root,
            change_id=resolve_change_id(args.change_id, repo_root),
            out_dir=out,
        )
    except KeyboardInterrupt:
        print('GATE_HEALTH_RESULT status=FAIL reason=interrupted', file=sys.stderr)
        return 130
    except (Exception, SystemExit) as exc:
        print(
            f'GATE_HEALTH_RESULT status=FAIL reason=execution-unavailable '
            f'detail={type(exc).__name__}: {exc}',
            file=sys.stderr,
        )
        return 2
    print(health.format_health_result(result))
    if result.status == report.PASS:
        return 0
    return 1 if result.status == report.BLOCKED else 2


def main(argv: list[str] | None = None) -> int:
    """解析统一 CLI；参数或执行条件不完整时以 FAIL 的退出码 2 结束。"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == 'health':
        return _health_main(arguments[1:])
    parser = GateArgumentParser(
        description='Unified typed Gate service',
        epilog='Maintenance: python3 scripts/gates/cli.py health',
    )
    parser.add_argument('--mode', choices=tuple(ExecutionMode), default=ExecutionMode.INCREMENTAL)
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument('--target', choices=sorted(item.name for item in TARGETS))
    selector.add_argument('--gate', choices=sorted(item.name for item in GATES))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--changed-files', default=None, help='JSON array of repository paths')
    parser.add_argument('--out', default='tmp/quality')
    parser.add_argument('--change-id', default=None)
    parser.add_argument('--base-url', default=None, help='Explicit BASE_URL for browser Gates')
    parser.add_argument('--allow-empty-changed-files-because', default=None)
    repo_root = Path.cwd()
    try:
        args = parser.parse_args(arguments)
        input_audit_reason = (args.allow_empty_changed_files_because or '').strip()
        if args.mode == ExecutionMode.FULL and args.changed_files is not None:
            raise ValueError('full mode does not accept --changed-files')
        if args.mode == ExecutionMode.FULL and args.allow_empty_changed_files_because is not None:
            raise ValueError('full mode does not accept --allow-empty-changed-files-because')
        changed_files = (
            []
            if args.mode == ExecutionMode.FULL
            else get_changed_files(args.changed_files, repo_root)
        )
        if args.mode == ExecutionMode.INCREMENTAL and not changed_files:
            dirty = support.read_git_dirty_files(repo_root)
            if dirty:
                if args.changed_files is None or not input_audit_reason:
                    raise ValueError(
                        'incremental mode has no trustworthy changed files; an audit exception '
                        'requires explicit [] and a non-empty reason'
                    )
            elif args.allow_empty_changed_files_because is not None:
                raise ValueError('empty changed-files audit exception is not needed')
        elif args.allow_empty_changed_files_because is not None:
            raise ValueError('empty changed-files audit exception requires an empty file list')
        gate_plan = create_plan(changed_files, mode=args.mode, target=args.target, gate=args.gate)
        if args.base_url and not any(
            step.kind.value == 'playwright' for item in gate_plan.gates for step in item.run.steps
        ):
            raise ValueError('--base-url requires a selected Playwright Gate')
    except (ValueError, json.JSONDecodeError) as exc:
        print(
            f'GATE_SERVICE_RESULT status=NOT_PASS detailStatus=FAIL '
            f'reason=input-unavailable detail={exc}',
            file=sys.stderr,
        )
        return 2

    if args.dry_run:
        print(
            json.dumps(
                _dry_run_payload(gate_plan, repo_root, input_audit_reason=input_audit_reason),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    out = Path(args.out)
    if not out.is_absolute():
        out = repo_root / out
    try:
        result = run_service(
            repo_root=repo_root,
            changed_files=changed_files,
            mode=args.mode,
            target=args.target,
            gate=args.gate,
            change_id=resolve_change_id(args.change_id, repo_root),
            out_dir=out,
            base_url=args.base_url or os.environ.get('BASE_URL'),
            input_audit_reason=input_audit_reason,
        )
    except KeyboardInterrupt:
        print(
            'GATE_SERVICE_RESULT status=NOT_PASS detailStatus=FAIL reason=interrupted',
            file=sys.stderr,
        )
        return 130
    print(
        report.format_quality_report(
            json.loads(result.artifact_path.read_text(encoding='utf-8')), result.artifact_path
        )
    )
    return 0 if result.passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
