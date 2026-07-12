#!/usr/bin/env python3
"""统一 Stop 入口：agent 退出前验证本次运行是否合规，不合规则 BLOCK。

Stop hook 校验流程：
  1. identity   身份校验     验证 run_id/session_id/checkout 合法
  2. file_lock  并发互斥     同一 run 只允许一个 Stop 检查并行
  3. evidence   变更收集     git diff 收集本次 run 改了什么，减去启动前已有的脏文件
  4. reentry    重入检测     对比失败指纹，相同则复用旧结果；连续相同超限则熔断
  5. quality    质量门禁     openspec 规格验证 + 直接调用原子 check 脚本 + checkout 一致性复核
  6. report     报告产出     写 runtime-report + stop-check-summary
  7. finalize   结果闭环     写回 sessionctl + 释放文件锁

步骤 1/3-5 为验证类（决定 PASS/BLOCK），步骤 2/6/7 为输出类（记录结果、释放资源）。
子校验实现见 stop_entry_checks/ 子包。

质量门禁（步骤 5）直接调用原子 check 脚本，不再经过 run_required_quality_gates.py
管道。每个 check 脚本通过 --changed-files 参数自感知是否需要运行。
target → gate 映射来自 quality_targets.py，gate → 命令映射来自 run_quality_gate.py。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.harness import stop_helpers  # noqa: E402
from scripts.harness.primary_session import ensure_private_directory, resolve_runtime_root  # noqa: E402

from scripts.harness.stop_entry_checks.file_lock import FileLock  # noqa: E402
from scripts.harness.stop_entry_checks.git_evidence import (  # noqa: E402
    GitEvidenceError,
    collect_git_evidence,
    filter_baseline_dirty,
)
from scripts.harness.stop_entry_checks.identity import _repo_root, validate_run_identity  # noqa: E402
from scripts.harness.stop_entry_checks.quality import (  # noqa: E402
    run_openspec_validation,
    run_quality_checks,
    validate_runtime_report,
    write_runtime_report,
)
from scripts.harness.stop_entry_checks.reentry import (  # noqa: E402
    load_reentry,
    matching_reentry_failure,
    recovery_scope,
    resource_names,
    update_reentry,
    write_recovery_audit,
)
from scripts.harness.stop_entry_checks.report import (  # noqa: E402
    build_summary,
    runtime_report_path,
    stop_summary_path,
    write_summary,
)


# ── 共享状态 ──────────────────────────────────────────────────────


@dataclass
class StopContext:
    """Stop 流程各阶段共享的可变状态。"""

    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    git_evidence: dict[str, Any] = field(default_factory=lambda: {'changedFiles': []})
    changed_files: list[str] = field(default_factory=list)
    baseline_dirty_files: set[str] = field(default_factory=set)
    evidence_mode: str = 'git-run-record'
    change_id: str = 'unknown'
    targets: list[str] = field(default_factory=list)
    read_only: bool = True
    resource_lock_names: list[str] = field(default_factory=list)
    gates_ok: bool = True
    runtime_ok: bool = True
    lock_status: str = 'blocked'
    continuation_count: int = 0
    outcome_record: dict[str, Any] = field(default_factory=dict)
    gate_results: list[dict[str, str]] = field(default_factory=list)


# ── 入口 ──────────────────────────────────────────────────────────


# 读取一次标准输入并解析上下文字典。
def read_stdin_once() -> tuple[str, dict[str, Any]]:
    """返回：
        原始输入和解析后的上下文字典。
    """
    raw = sys.stdin.read()
    if not raw.strip():
        return raw, {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, {}
    return raw, data if isinstance(data, dict) else {}


# 仅在运行身份可信时收集变更文件。
def collect_run_changed_files(
    repo_root: Path,
    identity: Any,
    record: dict[str, Any] | None,
) -> tuple[list[str], str, list[str]]:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前运行身份。
        record: 当前会话记录。

    返回：
        变更文件、证据模式和失败列表。
    """
    if identity.has_run and identity.has_session and record:
        return collect_git_evidence(repo_root, record)['changedFiles'], 'git-run-record', []
    return [], 'run-identity-required', ['Stop requires an authoritative run record']


# ── 各阶段实现 ────────────────────────────────────────────────────


# 收集变更证据并映射质量目标。
def _phase_evidence(
    ctx: StopContext,
    repo_root: Path,
    record: dict[str, Any],
) -> None:
    """参数：
        ctx: 停止流程共享上下文。
        repo_root: 仓库根目录。
        record: 当前会话记录。

    返回：
        无返回值。
    """
    try:
        ctx.git_evidence = collect_git_evidence(repo_root, record)
    except GitEvidenceError as exc:
        ctx.git_evidence = {'queryErrors': [str(exc)], 'changedFiles': []}
        ctx.failures.append(f'Git evidence unavailable: {exc}')
    ctx.changed_files = list(ctx.git_evidence.get('changedFiles') or [])
    ctx.changed_files, ctx.baseline_dirty_files = filter_baseline_dirty(
        ctx.changed_files, ctx.git_evidence,
    )

    ctx.targets = stop_helpers.required_targets(ctx.changed_files)
    if ctx.changed_files and not ctx.targets:
        ctx.failures.append('changed files did not map to required quality targets')
    ctx.read_only = not ctx.changed_files
    ctx.resource_lock_names = resource_names(ctx.targets)


# 检测停止流程重入状态与熔断条件。
def _phase_reentry(
    ctx: StopContext,
    reentry_path: Path,
    repo_root: Path,
    scope: dict[str, str],
    change_id: str,
    stop_hook_active: bool,
) -> bool:
    """参数：
        ctx: 停止流程共享上下文。
        reentry_path: 重入状态路径。
        repo_root: 仓库根目录。
        scope: 当前恢复状态身份范围。
        change_id: 变更标识。
        stop_hook_active: 停止钩子是否处于活动状态。

    返回：
        命中熔断条件时返回 true，否则返回 false。
    """
    same_failure, reentry_state, scope_ok = matching_reentry_failure(
        reentry_path, repo_root, scope, change_id=change_id,
    )
    if not scope_ok:
        ctx.failures.append('run-scoped Stop recovery identity mismatch')
    if stop_hook_active:
        ctx.warnings.append('stop_hook_active reentry observed; not blocking solely on reentry')
    if same_failure and scope_ok:
        previous = [str(item) for item in reentry_state.get('lastFailures', [])]
        ctx.failures.extend(previous)
        ctx.gates_ok = False
        ctx.warnings.append('reused persistent Stop failure; heavy gates were not rerun')

    circuit_broken = (
        same_failure
        and scope_ok
        and isinstance(reentry_state, dict)
        and str((reentry_state.get('circuitBreaker') or {}).get('state') or 'CLOSED') == 'OPEN'
    )
    if circuit_broken:
        ctx.failures.append('continuation limit reached for identical Stop failure fingerprint')
    return circuit_broken


# 执行质量门禁并复核检出状态一致性。
def _phase_quality(
    ctx: StopContext,
    circuit_broken: bool,
    change_id: str,
    repo_root: Path,
    record: dict[str, Any],
) -> None:
    """参数：
        ctx: 停止流程共享上下文。
        circuit_broken: 是否已触发熔断。
        change_id: 变更标识。
        repo_root: 仓库根目录。
        record: 当前会话记录。

    返回：
        无返回值。
    """
    if not circuit_broken and not ctx.failures and not ctx.read_only:
        ctx.failures.extend(run_openspec_validation(change_id, ctx.changed_files, repo_root))
        if not ctx.failures:
            ctx.gates_ok, gate_failures, ctx.gate_results = run_quality_checks(
                change_id, ctx.changed_files, repo_root, ctx.targets,
            )
            ctx.failures.extend(gate_failures)

    if not circuit_broken and ctx.git_evidence.get('checkoutFingerprint'):
        try:
            post_gate_evidence = collect_git_evidence(repo_root, record)
            if post_gate_evidence.get('checkoutFingerprint') != ctx.git_evidence.get(
                'checkoutFingerprint'
            ):
                ctx.gates_ok = False
                ctx.failures.append('checkout Git snapshot changed during Stop validation')
        except GitEvidenceError as exc:
            ctx.gates_ok = False
            ctx.failures.append(f'post-gate Git evidence unavailable: {exc}')


# 写入并校验当前运行报告。
def _phase_report(
    ctx: StopContext,
    identity: Any,
    change_id: str,
    repo_root: Path,
    report_path: Path,
) -> None:
    """参数：
        ctx: 停止流程共享上下文。
        identity: 当前运行身份。
        change_id: 变更标识。
        repo_root: 仓库根目录。
        report_path: 运行报告路径。

    返回：
        无返回值。
    """
    write_runtime_report(
        report_path,
        identity=identity,
        change_id=change_id,
        changed_files=ctx.changed_files,
        targets=ctx.targets,
        gates_ok=ctx.gates_ok,
        failures=ctx.failures,
        git_evidence=ctx.git_evidence,
        gate_results=ctx.gate_results,
    )
    if not ctx.failures:
        errors = validate_runtime_report(
            identity=identity,
            change_id=change_id,
            repo_root=repo_root,
            changed_files=ctx.changed_files,
            report_path=report_path,
        )
        if errors:
            ctx.runtime_ok = False
            ctx.failures.extend(f'runtime report: {error}' for error in errors)


# 更新重入状态并写回会话登记结果。
def _finalize_reentry_and_registry(
    ctx: StopContext,
    *,
    repo_root: Path,
    identity: Any,
    scope: dict[str, str],
    reentry_path: Path,
    audit_dir: Path,
    report_path: Path,
    change_id: str,
    handoff_on_failure: bool,
    adapter_mode: str,
) -> None:
    """参数：
        ctx: 停止流程共享上下文。
        repo_root: 仓库根目录。
        identity: 当前运行身份。
        scope: 当前恢复状态身份范围。
        reentry_path: 重入状态路径。
        audit_dir: 恢复审计目录。
        report_path: 运行报告路径。
        change_id: 变更标识。
        handoff_on_failure: 失败时是否移交。
        adapter_mode: 调用适配模式。

    返回：
        无返回值。
    """
    ctx.failures[:] = list(dict.fromkeys(ctx.failures))
    try:
        ctx.continuation_count, reentry_failures = update_reentry(
            reentry_path,
            repo_root,
            ctx.failures,
            scope=scope,
            audit_dir=audit_dir,
            change_id=change_id,
        )
        ctx.failures.extend(reentry_failures)
    except Exception as exc:
        ctx.failures.append(f'Stop recovery update failed: {exc}')
    ctx.failures[:] = list(dict.fromkeys(ctx.failures))

    try:
        from scripts.harness.sessionctl import record_stop_result  # noqa: PLC0415

        requested_exit = 2 if ctx.failures else 0
        ctx.outcome_record, _outcome_facts = record_stop_result(
            repo_root,
            identity.raw_run_id,
            stop_exit=requested_exit,
            summary_status='BLOCKED' if ctx.failures else 'PASS',
            validated_facts=ctx.git_evidence,
            handoff_on_failure=handoff_on_failure,
            retryable_failure=(adapter_mode == 'hook' and not handoff_on_failure),
        )
        if requested_exit == 0 and ctx.outcome_record.get('status') != 'VALIDATED':
            validation = ctx.outcome_record.get('stopValidation')
            detail = (
                str(validation.get('evidenceError') or '')
                if isinstance(validation, dict)
                else ''
            )
            ctx.failures.append(detail or 'Stop validation receipt did not match gated Git snapshot')
            ctx.continuation_count, reentry_failures = update_reentry(
                reentry_path,
                repo_root,
                ctx.failures,
                scope=scope,
                audit_dir=audit_dir,
                change_id=change_id,
            )
            ctx.failures.extend(reentry_failures)
            write_runtime_report(
                report_path,
                identity=identity,
                change_id=change_id,
                changed_files=ctx.changed_files,
                targets=ctx.targets,
                gates_ok=False,
                failures=ctx.failures,
                git_evidence=ctx.git_evidence,
                gate_results=ctx.gate_results,
            )
    except Exception as exc:
        ctx.failures.append(f'Stop Registry result update failed: {exc}')


# 释放停止流程文件锁并写入审计事件。
def _finalize_lock(
    ctx: StopContext,
    stop_lock: FileLock,
    *,
    scope: dict[str, str],
    audit_dir: Path,
    reentry_path: Path,
) -> None:
    """参数：
        ctx: 停止流程共享上下文。
        stop_lock: 待释放的停止流程文件锁。
        scope: 当前恢复状态身份范围。
        audit_dir: 恢复审计目录。
        reentry_path: 重入状态路径。

    返回：
        无返回值。
    """
    released = stop_lock.release()
    if not released:
        ctx.lock_status = 'release-fenced'
        ctx.warnings.append('run-scoped Stop lock release was fenced')
    else:
        try:
            write_recovery_audit(
                audit_dir,
                event='STOP_LOCK_RELEASED',
                scope=scope,
                state=load_reentry(reentry_path),
            )
        except Exception as exc:
            ctx.warnings.append(f'Stop lock release audit failed: {exc}')


# ── 核心编排 ──────────────────────────────────────────────────────


# 编排身份、锁、证据、门禁与报告的停止流程。
def run_stop(
    agent: str,
    raw_ctx: dict[str, Any],
    *,
    handoff_on_failure: bool = False,
    adapter_mode: str = 'hook',
) -> int:
    """参数：
        agent: 调用方代理名称。
        raw_ctx: 原始钩子上下文。
        handoff_on_failure: 失败时是否移交。
        adapter_mode: 区分客户端钩子与人工命令行的熔断退出语义。

    返回：
        停止流程退出码。
    """
    if adapter_mode not in {'hook', 'cli'}:
        raise ValueError(f'unsupported Stop adapter mode: {adapter_mode}')
    repo_root = _repo_root(raw_ctx)
    stop_helpers._use_repo_root(repo_root)

    # ── 1. identity：身份校验 ──────────────────────────────────────
    result = validate_run_identity(agent, raw_ctx, repo_root)
    if result is None:
        return 2
    hook_ctx, identity, record, checkout_facts = result

    # ── 初始化共享状态 ──────────────────────────────────────────────
    ctx = StopContext(
        warnings=list(identity.identity_warnings),
        change_id=identity.change_id or str(record.get('changeId') or '') or 'unknown',
    )
    runtime_root = resolve_runtime_root(repo_root)
    runs_root = ensure_private_directory(runtime_root / 'runs', root=runtime_root)
    run_dir = ensure_private_directory(runs_root / identity.run_id, root=runs_root)
    audit_dir = ensure_private_directory(runtime_root / 'audit', root=runtime_root)
    scope = recovery_scope(record)
    reentry_path = run_dir / 'stop-reentry.json'
    summary_path = stop_summary_path(repo_root, identity, agent)
    report_path = runtime_report_path(repo_root, identity, ctx.change_id)

    # ── 2. file_lock：并发互斥 ─────────────────────────────────────
    stop_lock = FileLock(
        run_dir / 'stop-check.lock',
        {
            'kind': 'stop',
            'runId': scope['runId'],
            'sessionId': scope['sessionId'],
            'worktreeId': scope['worktreeId'],
            'checkoutRoot': scope['checkoutRoot'],
            'repoKey': scope['repoKey'],
            'client': identity.client,
        },
    )
    if not stop_lock.acquire():
        print('[stop_entry] BLOCK stop check already running for this run', file=sys.stderr)
        return 2
    ctx.lock_status = 'acquired'

    try:
        if stop_lock.reclaimed_owner:
            write_recovery_audit(
                audit_dir,
                event='STOP_LOCK_RECLAIMED',
                scope=scope,
                state={'continuationCount': 0, 'circuitBreaker': {'state': 'CLOSED'}},
            )

        # ── 3. evidence：变更收集 ──────────────────────────────────
        _phase_evidence(ctx, repo_root, record)

        # ── 4. reentry：重入检测 ──────────────────────────────────
        circuit_broken = _phase_reentry(
            ctx, reentry_path, repo_root, scope,
            change_id=ctx.change_id,
            stop_hook_active=hook_ctx.stop_hook_active,
        )

        # ── 5. quality：质量门禁 ──────────────────────────────────
        _phase_quality(ctx, circuit_broken, ctx.change_id, repo_root, record)

        # ── 6. 报告：写入运行报告 ────────────────────────────────
        _phase_report(ctx, identity, ctx.change_id, repo_root, report_path)

    except Exception as exc:
        ctx.failures.append(f'stop exception: {type(exc).__name__}: {exc}')

    finally:
        # ── 7. finalize：闭环 ─────────────────────────────────────
        _finalize_reentry_and_registry(
            ctx,
            repo_root=repo_root,
            identity=identity,
            scope=scope,
            reentry_path=reentry_path,
            audit_dir=audit_dir,
            report_path=report_path,
            change_id=ctx.change_id,
            handoff_on_failure=handoff_on_failure,
            adapter_mode=adapter_mode,
        )
        _finalize_lock(
            ctx, stop_lock,
            scope=scope,
            audit_dir=audit_dir,
            reentry_path=reentry_path,
        )

        recovery_state = load_reentry(reentry_path)
        circuit_state = str((recovery_state.get('circuitBreaker') or {}).get('state') or 'CLOSED')
        run_status = str(ctx.outcome_record.get('status') or 'BLOCKED')

        summary = build_summary(
            identity=identity,
            record=record,
            checkout_facts=checkout_facts,
            git_evidence=ctx.git_evidence,
            change_id=ctx.change_id,
            changed_files=ctx.changed_files,
            targets=ctx.targets,
            resource_lock_names=ctx.resource_lock_names,
            read_only=ctx.read_only,
            evidence_mode=ctx.evidence_mode,
            failures=ctx.failures,
            warnings=ctx.warnings,
            continuation_count=ctx.continuation_count,
            circuit_state=circuit_state,
            run_status=run_status,
            lock_status=ctx.lock_status,
            summary_path=summary_path,
            report_path=report_path,
            reentry_path=reentry_path,
        )
        write_summary(summary_path, summary)

    if ctx.failures:
        for failure in ctx.failures:
            print(f'[stop_entry] BLOCK {failure}', file=sys.stderr)
        if adapter_mode == 'hook' and circuit_state == 'OPEN':
            print(
                '[stop_entry] circuit OPEN; stop hook continuation terminated',
                file=sys.stderr,
            )
            return 0
        return 2
    print('[stop_entry] PASS', file=sys.stderr)
    return 0


# ── CLI ───────────────────────────────────────────────────────────


# 解析命令行参数并执行停止流程。
def main() -> int:
    """返回：
        停止流程退出码。
    """
    parser = argparse.ArgumentParser(description='Run unified Stop entry.')
    parser.add_argument('--agent', default='unknown')
    parser.add_argument('--agent-id', default=None)
    args = parser.parse_args()
    _raw, ctx = read_stdin_once()
    if args.agent_id and 'agent_id' not in ctx and 'agentId' not in ctx:
        ctx['agent_id'] = args.agent_id
    try:
        return run_stop(args.agent, ctx)
    except BaseException as exc:
        print(f'[stop_entry] FAIL unhandled stop exception: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
