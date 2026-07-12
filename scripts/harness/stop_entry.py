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
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.claude_hooks import paths as runtime_paths  # noqa: E402
from scripts.harness import stop_helpers  # noqa: E402
from scripts.harness.primary_session import ensure_private_directory, resolve_runtime_root  # noqa: E402

from scripts.harness.stop_entry_checks.file_lock import FileLock  # noqa: E402
from scripts.harness.stop_entry_checks.git_evidence import (  # noqa: E402
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
    runtime_report_path,
    stop_summary_path,
    write_summary,
)
from scripts.harness.stop_entry_checks._io import utc_now  # noqa: E402


# ── 入口 ──────────────────────────────────────────────────────────


def read_stdin_once() -> tuple[str, dict[str, Any]]:
    """读取 stdin 一次，解析为 JSON。"""
    raw = sys.stdin.read()
    if not raw.strip():
        return raw, {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, {}
    return raw, data if isinstance(data, dict) else {}


# ── 核心编排 ──────────────────────────────────────────────────────


def run_stop(
    agent: str,
    raw_ctx: dict[str, Any],
    *,
    handoff_on_failure: bool = False,
) -> int:
    """Stop 流程主入口：身份 → 锁 → 证据 → 重入 → 门禁 → 报告 → 闭环。"""
    repo_root = _repo_root(raw_ctx)
    stop_helpers._use_repo_root(repo_root)

    # ── 1. identity：身份校验 ──────────────────────────────────────
    result = validate_run_identity(agent, raw_ctx, repo_root)
    if result is None:
        return 2
    ctx, identity, record, checkout_facts = result

    failures: list[str] = []
    warnings: list[str] = list(identity.identity_warnings)
    git_evidence: dict[str, Any] = {'changedFiles': []}
    changed_files: list[str] = []
    baseline_dirty_files: set[str] = set()
    evidence_mode = 'git-run-record'
    change_id = identity.change_id or str(record.get('changeId') or '') or 'unknown'
    targets: list[str] = []
    read_only = True
    runtime_root = resolve_runtime_root(repo_root)
    runs_root = ensure_private_directory(runtime_root / 'runs', root=runtime_root)
    run_dir = ensure_private_directory(runs_root / identity.run_id, root=runs_root)
    audit_dir = ensure_private_directory(runtime_root / 'audit', root=runtime_root)
    scope = recovery_scope(record)
    reentry_path = run_dir / 'stop-reentry.json'
    summary_path = stop_summary_path(repo_root, identity, agent)
    report_path = runtime_report_path(repo_root, identity, change_id)
    resource_lock_names: list[str] = []
    gates_ok = True
    runtime_ok = True
    lock_status = 'blocked'
    continuation_count = 0
    outcome_record: dict[str, Any] = {}
    gate_results: list[dict[str, str]] = []

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
    lock_status = 'acquired'
    reentry_state: dict[str, Any] = {}

    try:
        if stop_lock.reclaimed_owner:
            write_recovery_audit(
                audit_dir,
                event='STOP_LOCK_RECLAIMED',
                scope=scope,
                state={'continuationCount': 0, 'circuitBreaker': {'state': 'CLOSED'}},
            )

        # ── 3. evidence：变更收集（git diff + 减去 baseline dirty）──
        try:
            git_evidence = collect_git_evidence(repo_root, record)
        except stop_helpers.GitEvidenceError as exc:
            git_evidence = {'queryErrors': [str(exc)], 'changedFiles': []}
            failures.append(f'Git evidence unavailable: {exc}')
        changed_files = list(git_evidence.get('changedFiles') or [])
        changed_files, baseline_dirty_files = filter_baseline_dirty(changed_files, git_evidence)

        # ── target 映射（变更文件 → 需要的质量目标）─────────────
        targets = stop_helpers.required_targets(changed_files)
        if changed_files and not targets:
            failures.append('changed files did not map to required quality targets')
        read_only = not changed_files
        resource_lock_names = resource_names(targets)

        # ── 4. reentry：重入检测（指纹对比 + circuit breaker 熔断）─
        same_failure, reentry_state, scope_ok = matching_reentry_failure(
            reentry_path, repo_root, scope,
        )
        if not scope_ok:
            failures.append('run-scoped Stop recovery identity mismatch')
        if ctx.stop_hook_active:
            warnings.append('stop_hook_active reentry observed; not blocking solely on reentry')
        if same_failure and scope_ok:
            previous = [str(item) for item in reentry_state.get('lastFailures', [])]
            failures.extend(previous)
            gates_ok = False
            warnings.append('reused persistent Stop failure; heavy gates were not rerun')

        # ── circuit breaker：连续相同失败超限则熔断，跳过后续门禁 ──
        circuit_broken = (
            same_failure
            and scope_ok
            and isinstance(reentry_state, dict)
            and str((reentry_state.get('circuitBreaker') or {}).get('state') or 'CLOSED') == 'OPEN'
        )
        if circuit_broken:
            failures.append('continuation limit reached for identical Stop failure fingerprint')

        # ── 5. quality：质量门禁 ──────────────────────────────────
        #   5a. openspec 规格验证（受保护路径需要合法 change 规格）──
        elif not failures and not read_only:
            failures.extend(run_openspec_validation(change_id, changed_files, repo_root))

            #   5b. 直接调用原子 check 脚本（无中间路由层）──────────
            if not failures:
                gates_ok, gate_failures, gate_results = run_quality_checks(
                    change_id, changed_files, repo_root, targets,
                )
                failures.extend(gate_failures)

        #   5c. checkout 一致性复核（门禁期间工作目录没有变）──────
        if not circuit_broken and git_evidence.get('checkoutFingerprint'):
            try:
                post_gate_evidence = collect_git_evidence(repo_root, record)
                if post_gate_evidence.get('checkoutFingerprint') != git_evidence.get(
                    'checkoutFingerprint'
                ):
                    gates_ok = False
                    failures.append('checkout Git snapshot changed during Stop validation')
            except stop_helpers.GitEvidenceError as exc:
                gates_ok = False
                failures.append(f'post-gate Git evidence unavailable: {exc}')

        # ── 6. report：写 runtime-report + stop-check-summary ─────
        write_runtime_report(
            report_path,
            identity=identity,
            change_id=change_id,
            changed_files=changed_files,
            targets=targets,
            gates_ok=gates_ok,
            failures=failures,
            git_evidence=git_evidence,
            gate_results=gate_results,
        )
        if not failures:
            errors = validate_runtime_report(
                identity=identity,
                change_id=change_id,
                repo_root=repo_root,
                changed_files=changed_files,
                report_path=report_path,
            )
            if errors:
                runtime_ok = False
                failures.extend(f'runtime report: {error}' for error in errors)

    except Exception as exc:
        failures.append(f'stop exception: {type(exc).__name__}: {exc}')

    finally:
        # ── 7. finalize：写回 sessionctl + 释放文件锁 ─────────────
        failures[:] = list(dict.fromkeys(failures))
        try:
            continuation_count, reentry_failures = update_reentry(
                reentry_path, repo_root, failures, scope=scope, audit_dir=audit_dir,
            )
            failures.extend(reentry_failures)
        except Exception as exc:
            failures.append(f'Stop recovery update failed: {exc}')
        failures[:] = list(dict.fromkeys(failures))
        try:
            from scripts.harness.sessionctl import record_stop_result  # noqa: PLC0415

            requested_exit = 2 if failures else 0
            outcome_record, _outcome_facts = record_stop_result(
                repo_root,
                identity.raw_run_id,
                stop_exit=requested_exit,
                summary_status='BLOCKED' if failures else 'PASS',
                validated_facts=git_evidence,
                handoff_on_failure=handoff_on_failure,
            )
            if requested_exit == 0 and outcome_record.get('status') != 'VALIDATED':
                validation = outcome_record.get('stopValidation')
                detail = (
                    str(validation.get('evidenceError') or '')
                    if isinstance(validation, dict)
                    else ''
                )
                failures.append(detail or 'Stop validation receipt did not match gated Git snapshot')
                continuation_count, reentry_failures = update_reentry(
                    reentry_path, repo_root, failures, scope=scope, audit_dir=audit_dir,
                )
                failures.extend(reentry_failures)
                write_runtime_report(
                    report_path,
                    identity=identity,
                    change_id=change_id,
                    changed_files=changed_files,
                    targets=targets,
                    gates_ok=False,
                    failures=failures,
                    git_evidence=git_evidence,
                    gate_results=gate_results,
                )
        except Exception as exc:
            failures.append(f'Stop Registry result update failed: {exc}')

        released = stop_lock.release()
        if not released:
            lock_status = 'release-fenced'
            warnings.append('run-scoped Stop lock release was fenced')
        else:
            try:
                write_recovery_audit(
                    audit_dir,
                    event='STOP_LOCK_RELEASED',
                    scope=scope,
                    state=load_reentry(reentry_path),
                )
            except Exception as exc:
                warnings.append(f'Stop lock release audit failed: {exc}')

        recovery_state = load_reentry(reentry_path)
        circuit_state = str((recovery_state.get('circuitBreaker') or {}).get('state') or 'CLOSED')
        run_status = str(outcome_record.get('status') or 'BLOCKED')
        status = (
            'PASS'
            if not failures and runtime_ok and run_status == 'VALIDATED'
            else 'BLOCKED'
        )
        summary = {
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
        write_summary(summary_path, summary)

    if failures:
        for failure in failures:
            print(f'[stop_entry] BLOCK {failure}', file=sys.stderr)
        return 2
    print('[stop_entry] PASS', file=sys.stderr)
    return 0


# ── CLI ───────────────────────────────────────────────────────────


def main() -> int:
    """解析命令行参数并执行 Stop 流程。"""
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
