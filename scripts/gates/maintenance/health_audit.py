"""负责通过公开契约执行显式、全量且无 deadline 的 Gate 健康审计；不负责修复。

由 CLI 的 ``health`` 子命令调用。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.gates.catalog import CATALOG, ExecutionMode, validate_gate_catalog
from scripts.gates.evidence import RunReceipt, store_run_receipt
from scripts.gates.execution import (
    ExecutionStatus,
    InvocationResult,
    adapt_recipe_step,
    classify_owner_outcome,
    orchestrate_gate_run,
    supervise_process,
)
from scripts.gates.planning import (
    CommandInvocation,
    GatePlan,
    capture_change_snapshot,
    compile_gate_plan,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from scripts.gates.execution import ExecutionEvent, GateResult


@dataclass(frozen=True, slots=True)
class GateHealthAudit:
    """一次 health 审计的 doctor、Gate、时效和 receipt 结果。"""

    status: ExecutionStatus
    reason: str
    doctor_result: InvocationResult
    gate_results: tuple[GateResult, ...]
    over_target_gates: tuple[str, ...]
    receipt: RunReceipt


def _doctor_invocation() -> CommandInvocation:
    return CommandInvocation(
        'gate-health:harnessDoctor:run',
        'command',
        ('bash', 'scripts/harness/doctor.sh'),
        (),
        'gate-health',
        'harnessDoctor',
    )


def _full_plan(repo_root: Path) -> GatePlan:
    snapshot = capture_change_snapshot(repo_root, mode=ExecutionMode.FULL)

    def invocation_factory(gate, step):
        """为健康审计把全量模式绑定到一个 RecipeStep 的命令适配过程。"""
        return adapt_recipe_step(
            gate,
            step,
            repo_root,
            mode=ExecutionMode.FULL,
            changed_files=(),
        )

    return compile_gate_plan(
        snapshot,
        mode=ExecutionMode.FULL,
        invocation_factory=invocation_factory,
    )


def _health_status(
    doctor: InvocationResult, gate_results: tuple[GateResult, ...]
) -> tuple[ExecutionStatus, str, tuple[str, ...]]:
    over_target = tuple(
        result.gate_name for result in gate_results if result.timing_state == 'OVER_TARGET'
    )
    if doctor.status is ExecutionStatus.FAIL:
        return ExecutionStatus.FAIL, doctor.reason or 'outcome-unknown', over_target
    failed = next(
        (result for result in gate_results if result.status is ExecutionStatus.FAIL), None
    )
    if failed is not None:
        return ExecutionStatus.FAIL, failed.reason or 'outcome-unknown', over_target
    if (
        doctor.status is ExecutionStatus.BLOCKED
        or any(result.status is ExecutionStatus.BLOCKED for result in gate_results)
        or over_target
    ):
        return ExecutionStatus.BLOCKED, 'verification-failed', over_target
    if gate_results and all(result.status is ExecutionStatus.PASS for result in gate_results):
        return ExecutionStatus.PASS, '', over_target
    return ExecutionStatus.FAIL, 'outcome-unknown', over_target


def audit_gate_health(
    *,
    repo_root: Path,
    runs_root: Path | None = None,
    event_sink: Callable[[ExecutionEvent], None] | None = None,
) -> GateHealthAudit:
    """运行 Harness doctor 与 full GatePlan，不设置 retry、并行或 hard timeout。"""

    root = repo_root.resolve()
    validate_gate_catalog(CATALOG)
    plan = _full_plan(root)
    runtime_logs = root / 'tmp' / 'quality' / 'health-runtime' / str(time.monotonic_ns())
    runtime_logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    doctor_invocation = _doctor_invocation()
    doctor_observation = supervise_process(
        doctor_invocation,
        cwd=root,
        log_path=runtime_logs / 'harness-doctor.log',
        event_sink=event_sink,
    )
    doctor_result = classify_owner_outcome(doctor_invocation, doctor_observation)
    gate_results = orchestrate_gate_run(
        plan,
        root,
        log_dir=runtime_logs / 'gates',
        event_sink=event_sink,
    )
    status, reason, over_target = _health_status(doctor_result, gate_results)
    receipt = store_run_receipt(
        plan,
        gate_results,
        repo_root=root,
        runs_root=runs_root,
        reason=reason if status is ExecutionStatus.FAIL else '',
        additional_logs={'maintenance-harness-doctor.log': runtime_logs / 'harness-doctor.log'},
    )
    return GateHealthAudit(status, reason, doctor_result, gate_results, over_target, receipt)
