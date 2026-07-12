"""Stop 唯一七阶段 dispatcher；Gate 阶段只调用统一 ``run_service``。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from scripts.agent_runtime import paths as runtime_paths
from scripts.agent_runtime.context import HookContext
from scripts.agent_runtime.identity import identity_from_hook_context
from scripts.gates.cli import run_service
from scripts.harness.primary_session import (
    ensure_private_directory,
    load_run_record,
    resolve_runtime_root,
    validate_checkout_record,
    validate_run_record,
)

from . import evidence, report
from .model import StopContext, StopPhase, StopTerminalState
from .recovery import (
    FileLock,
    load_reentry,
    matching_reentry_failure,
    recovery_scope,
    resource_names,
    update_reentry,
    write_recovery_audit,
)

PHASES = tuple(StopPhase)


def _repo_root(raw_context: dict[str, Any]) -> Path:
    """从 Hook payload 的 cwd 解析可信仓库根。"""
    raw = raw_context.get('cwd') or raw_context.get('workingDirectory') or ''
    return runtime_paths.find_repo_root(raw or Path.cwd())


def _identity(ctx: StopContext) -> bool:
    """阶段一：校验 run/session/checkout 身份并初始化运行路径。"""
    ctx.phase = StopPhase.IDENTITY
    ctx.repo_root = _repo_root(ctx.raw_context)
    hook_context = HookContext('Stop', ctx.raw_context)
    identity = identity_from_hook_context(hook_context, agent_client=ctx.agent)
    if not identity.has_run or not identity.has_session:
        ctx.failures.append('authoritative run/session identity is required')
        return False
    record = load_run_record(ctx.repo_root, identity.raw_run_id)
    if not record:
        ctx.failures.append('run record not found for run_id')
        return False
    try:
        validate_run_record(record)
        checkout_facts, checkout_errors = validate_checkout_record(ctx.repo_root, record)
    except Exception as exc:
        ctx.failures.append(f'run identity cannot be proven: {exc}')
        return False
    if checkout_errors:
        ctx.failures.append('checkout identity: ' + '; '.join(checkout_errors))
        return False
    ctx.hook_context, ctx.identity = hook_context, identity
    ctx.record, ctx.checkout_facts = record, checkout_facts
    ctx.warnings.extend(identity.identity_warnings)
    ctx.change_id = identity.change_id or str(record.get('changeId') or '') or 'unknown'
    ctx.runtime_root = resolve_runtime_root(ctx.repo_root)
    runs_root = ensure_private_directory(ctx.runtime_root / 'runs', root=ctx.runtime_root)
    ctx.run_dir = ensure_private_directory(runs_root / identity.run_id, root=runs_root)
    ctx.audit_dir = ensure_private_directory(ctx.runtime_root / 'audit', root=ctx.runtime_root)
    ctx.recovery_scope = recovery_scope(record)
    ctx.reentry_path = ctx.run_dir / 'stop-reentry.json'
    ctx.summary_path = report.stop_summary_path(ctx.repo_root, identity, ctx.agent)
    ctx.report_path = report.runtime_report_path(ctx.repo_root, identity, ctx.change_id)
    return True


def _lock(ctx: StopContext) -> bool:
    """阶段二：获取 run-scoped FileLock 并记录 stale-owner reclaim。"""
    ctx.phase = StopPhase.LOCK
    assert ctx.run_dir and ctx.audit_dir
    scope = ctx.recovery_scope
    ctx.stop_lock = FileLock(
        ctx.run_dir / 'stop-check.lock',
        {
            'kind': 'stop',
            'runId': scope['runId'],
            'sessionId': scope['sessionId'],
            'worktreeId': scope['worktreeId'],
            'checkoutRoot': scope['checkoutRoot'],
            'repoKey': scope['repoKey'],
            'client': ctx.identity.client,
        },
    )
    if not ctx.stop_lock.acquire():
        ctx.failures.append('stop check already running for this run')
        return False
    ctx.lock_status = 'acquired'
    if ctx.stop_lock.reclaimed_owner:
        write_recovery_audit(
            ctx.audit_dir,
            event='STOP_LOCK_RECLAIMED',
            scope=scope,
            state={'continuationCount': 0, 'circuitBreaker': {'state': 'CLOSED'}},
        )
    return True


def _collect_evidence(ctx: StopContext) -> None:
    """阶段三：收集 Git/changed-files/OpenSpec direct validation 证据。"""
    ctx.phase = StopPhase.EVIDENCE
    assert ctx.repo_root
    try:
        ctx.git_evidence = evidence.collect_git_evidence(ctx.repo_root, ctx.record)
    except evidence.GitEvidenceError as exc:
        ctx.git_evidence = {'queryErrors': [str(exc)], 'changedFiles': []}
        ctx.failures.append(f'Git evidence unavailable: {exc}')
    ctx.changed_files = list(ctx.git_evidence.get('changedFiles') or [])
    ctx.changed_files, ctx.baseline_dirty_files = evidence.filter_baseline_dirty(
        ctx.changed_files,
        ctx.git_evidence,
    )
    ctx.targets = evidence.required_targets(ctx.changed_files)
    if ctx.changed_files and not ctx.targets:
        ctx.failures.append('changed files did not map to required quality targets')
    ctx.read_only = not ctx.changed_files
    ctx.resource_lock_names = resource_names(ctx.targets)
    if not ctx.failures and not ctx.read_only:
        ctx.failures.extend(
            evidence.validate_openspec_evidence(
                ctx.change_id,
                ctx.changed_files,
                ctx.repo_root,
            )
        )


def _reentry_recovery(ctx: StopContext) -> None:
    """阶段四：匹配持久失败并保持 Phase 1 circuit OPEN 语义。"""
    ctx.phase = StopPhase.REENTRY_RECOVERY
    assert ctx.repo_root and ctx.reentry_path
    same, state, scope_ok = matching_reentry_failure(
        ctx.reentry_path,
        ctx.repo_root,
        ctx.recovery_scope,
        change_id=ctx.change_id,
    )
    if not scope_ok:
        ctx.failures.append('run-scoped Stop recovery identity mismatch')
    if ctx.hook_context.stop_hook_active:
        ctx.warnings.append('stop_hook_active reentry observed; not blocking solely on reentry')
    if same and scope_ok:
        ctx.failures.extend(str(item) for item in state.get('lastFailures', []))
        ctx.gates_ok = False
        ctx.warnings.append('reused persistent Stop failure; heavy gates were not rerun')
    ctx.circuit_broken = bool(
        same
        and scope_ok
        and str((state.get('circuitBreaker') or {}).get('state') or 'CLOSED') == 'OPEN'
    )
    if ctx.circuit_broken:
        ctx.failures.append('continuation limit reached for identical Stop failure fingerprint')


def _gate(ctx: StopContext) -> None:
    """阶段五：唯一调用 Gate service，不选择 Gate、不解释命令、不循环执行。"""
    ctx.phase = StopPhase.GATE
    assert ctx.repo_root and ctx.report_path
    if not ctx.circuit_broken and not ctx.failures and not ctx.read_only:
        ctx.gate_result = run_service(
            repo_root=ctx.repo_root,
            changed_files=ctx.changed_files,
            tier='required',
            change_id=ctx.change_id,
            out_dir=ctx.report_path.parent,
            explicit_changed_files=True,
            base_url=os.environ.get('BASE_URL'),
        )
        ctx.gates_ok = ctx.gate_result.passed
        ctx.gate_results = report.gate_result_records(ctx.gate_result, read_only=False)
        if not ctx.gates_ok:
            ctx.failures.extend(
                f'{item["name"]}={item["status"]}'
                for item in ctx.gate_results
                if item['status'] not in {report.EXECUTED, report.REUSED}
            )
    if not ctx.circuit_broken and ctx.git_evidence.get('checkoutFingerprint'):
        try:
            after = evidence.collect_git_evidence(ctx.repo_root, ctx.record)
            if after.get('checkoutFingerprint') != ctx.git_evidence.get('checkoutFingerprint'):
                ctx.gates_ok = False
                ctx.failures.append('checkout Git snapshot changed during Stop validation')
        except evidence.GitEvidenceError as exc:
            ctx.gates_ok = False
            ctx.failures.append(f'post-gate Git evidence unavailable: {exc}')


def _write_report(ctx: StopContext) -> None:
    """阶段六：直接消费 GateServiceResult 写入并校验 runtime report。"""
    ctx.phase = StopPhase.REPORT
    assert ctx.repo_root and ctx.report_path
    report.write_runtime_report(
        ctx.report_path,
        identity=ctx.identity,
        change_id=ctx.change_id,
        changed_files=ctx.changed_files,
        targets=ctx.targets,
        gates_ok=ctx.gates_ok,
        failures=ctx.failures,
        git_evidence=ctx.git_evidence,
        service_result=ctx.gate_result,
        read_only=ctx.read_only,
    )
    if not ctx.failures:
        errors = report.validate_runtime_report(
            identity=ctx.identity,
            change_id=ctx.change_id,
            repo_root=ctx.repo_root,
            changed_files=ctx.changed_files,
            report_path=ctx.report_path,
        )
        if errors:
            ctx.runtime_ok = False
            ctx.failures.extend(f'runtime report: {error}' for error in errors)


def _finalize_registry(ctx: StopContext) -> None:
    """在 finally 中更新 reentry 与 registry；失败也必须形成可审计闭环。"""
    assert ctx.repo_root and ctx.reentry_path and ctx.audit_dir and ctx.report_path
    ctx.failures[:] = list(dict.fromkeys(ctx.failures))
    try:
        ctx.continuation_count, extra = update_reentry(
            ctx.reentry_path,
            ctx.repo_root,
            ctx.failures,
            scope=ctx.recovery_scope,
            audit_dir=ctx.audit_dir,
            change_id=ctx.change_id,
        )
        ctx.failures.extend(extra)
        state = load_reentry(ctx.reentry_path)
        ctx.circuit_state = str((state.get('circuitBreaker') or {}).get('state') or 'CLOSED')
    except Exception as exc:
        ctx.failures.append(f'Stop recovery update failed: {exc}')
    try:
        from scripts.harness.sessionctl import record_stop_result

        requested_exit = 2 if ctx.failures else 0
        ctx.outcome_record, _ = record_stop_result(
            ctx.repo_root,
            ctx.identity.raw_run_id,
            stop_exit=requested_exit,
            summary_status='BLOCKED' if ctx.failures else 'PASS',
            validated_facts=ctx.git_evidence,
            handoff_on_failure=ctx.handoff_on_failure,
            retryable_failure=(
                ctx.adapter_mode == 'hook'
                and not ctx.handoff_on_failure
                and ctx.circuit_state != 'OPEN'
            ),
        )
        if requested_exit == 0 and ctx.outcome_record.get('status') != 'VALIDATED':
            validation = ctx.outcome_record.get('stopValidation')
            detail = (
                str(validation.get('evidenceError') or '') if isinstance(validation, dict) else ''
            )
            ctx.failures.append(
                detail or 'Stop validation receipt did not match gated Git snapshot'
            )
            ctx.continuation_count, extra = update_reentry(
                ctx.reentry_path,
                ctx.repo_root,
                ctx.failures,
                scope=ctx.recovery_scope,
                audit_dir=ctx.audit_dir,
                change_id=ctx.change_id,
            )
            ctx.failures.extend(extra)
            report.write_runtime_report(
                ctx.report_path,
                identity=ctx.identity,
                change_id=ctx.change_id,
                changed_files=ctx.changed_files,
                targets=ctx.targets,
                gates_ok=False,
                failures=ctx.failures,
                git_evidence=ctx.git_evidence,
                service_result=ctx.gate_result,
                read_only=ctx.read_only,
            )
    except Exception as exc:
        ctx.failures.append(f'Stop Registry result update failed: {exc}')


def _finalize(ctx: StopContext) -> None:
    """阶段七：无条件关闭 registry/lock 并落 stop summary。"""
    ctx.phase = StopPhase.FINALIZE
    if ctx.identity is None or ctx.stop_lock is None or not ctx.stop_lock.acquired:
        return
    _finalize_registry(ctx)
    assert ctx.audit_dir and ctx.reentry_path and ctx.summary_path and ctx.report_path
    if not ctx.stop_lock.release():
        ctx.lock_status = 'release-fenced'
        ctx.warnings.append('run-scoped Stop lock release was fenced')
    else:
        try:
            write_recovery_audit(
                ctx.audit_dir,
                event='STOP_LOCK_RELEASED',
                scope=ctx.recovery_scope,
                state=load_reentry(ctx.reentry_path),
            )
        except Exception as exc:
            ctx.warnings.append(f'Stop lock release audit failed: {exc}')
    state = load_reentry(ctx.reentry_path)
    ctx.circuit_state = str((state.get('circuitBreaker') or {}).get('state') or 'CLOSED')
    summary = report.build_summary(
        identity=ctx.identity,
        record=ctx.record,
        checkout_facts=ctx.checkout_facts,
        git_evidence=ctx.git_evidence,
        change_id=ctx.change_id,
        changed_files=ctx.changed_files,
        targets=ctx.targets,
        resource_lock_names=ctx.resource_lock_names,
        read_only=ctx.read_only,
        evidence_mode=ctx.evidence_mode,
        failures=list(dict.fromkeys(ctx.failures)),
        warnings=ctx.warnings,
        continuation_count=ctx.continuation_count,
        circuit_state=ctx.circuit_state,
        run_status=str(ctx.outcome_record.get('status') or 'BLOCKED'),
        lock_status=ctx.lock_status,
        summary_path=ctx.summary_path,
        report_path=ctx.report_path,
        reentry_path=ctx.reentry_path,
    )
    report.write_summary(ctx.summary_path, summary)


def run_stop(
    agent: str,
    raw_context: dict[str, Any],
    *,
    handoff_on_failure: bool = False,
    adapter_mode: str = 'hook',
) -> int:
    """按唯一七阶段顺序执行 Stop；circuit OPEN 仍以 BLOCKED 非零结束。"""
    if adapter_mode not in {'hook', 'cli'}:
        raise ValueError(f'unsupported Stop adapter mode: {adapter_mode}')
    ctx = StopContext(agent, raw_context, handoff_on_failure, adapter_mode)
    try:
        if not _identity(ctx) or not _lock(ctx):
            return 2
        _collect_evidence(ctx)
        _reentry_recovery(ctx)
        _gate(ctx)
        _write_report(ctx)
    except Exception as exc:
        ctx.failures.append(f'stop exception: {type(exc).__name__}: {exc}')
    finally:
        _finalize(ctx)
    ctx.failures[:] = list(dict.fromkeys(ctx.failures))
    if ctx.failures:
        ctx.terminal_state = StopTerminalState.BLOCKED
        for failure in ctx.failures:
            print(f'[stop_entry] BLOCK {failure}', file=sys.stderr)
        if ctx.circuit_state == 'OPEN':
            print('[stop_entry] HANDOFF_BLOCKED circuit OPEN', file=sys.stderr)
        return 2
    ctx.terminal_state = StopTerminalState.PASS
    print('[stop_entry] PASS', file=sys.stderr)
    return 0
