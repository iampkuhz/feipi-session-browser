"""快速检查 Gate 控制面声明、命令适配与 Harness。

负责静态编译完整计划并运行 Harness doctor；不负责执行 Gate owner 或写 RunReceipt；由 CLI 的
``health`` 子命令调用。完整仓库验证由 ``run --mode full`` 承担。
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.gates.catalog import CATALOG, ExecutionMode, validate_gate_catalog
from scripts.gates.execution import (
    ExecutionEvent,
    ExecutionStatus,
    InvocationResult,
    adapt_recipe_step,
    classify_owner_outcome,
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


@dataclass(frozen=True, slots=True)
class GateHealthAudit:
    """保存一次快速控制面体检的结构化结果。"""

    status: ExecutionStatus
    reason: str
    doctor_result: InvocationResult
    gate_count: int
    recipe_step_count: int
    planned_process_count: int
    executed_process_count: int
    missing_recipe_steps: tuple[str, ...]
    unavailable_executables: tuple[str, ...]
    elapsed_seconds: float


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
        """把全部 RecipeStep 适配为声明，不启动对应命令。"""
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


def _missing_recipe_steps(plan: GatePlan) -> tuple[str, ...]:
    owned = {
        (invocation.gate_name, invocation.recipe_step_name)
        for invocation in plan.command_invocations
    }
    return tuple(
        f'{gate.name}:{step.name}'
        for gate in plan.gates
        for step in gate.recipe.steps
        if (gate.name, step.name) not in owned
    )


def _executable_available(executable: str) -> bool:
    if '/' not in executable:
        return shutil.which(executable) is not None
    path = Path(executable)
    return path.is_file() and os.access(path, os.X_OK)


def _unavailable_executables(plan: GatePlan) -> tuple[str, ...]:
    executables = tuple(
        dict.fromkeys(
            invocation.argv[0] for invocation in plan.command_invocations if invocation.argv
        )
    )
    return tuple(item for item in executables if not _executable_available(item))


def _health_status(
    doctor: InvocationResult,
    missing_steps: tuple[str, ...],
    unavailable_executables: tuple[str, ...],
) -> tuple[ExecutionStatus, str]:
    if missing_steps or unavailable_executables:
        return ExecutionStatus.FAIL, 'runtime-missing'
    if doctor.status is ExecutionStatus.FAIL:
        return ExecutionStatus.FAIL, doctor.reason or 'outcome-unknown'
    if doctor.status is ExecutionStatus.BLOCKED:
        return ExecutionStatus.BLOCKED, doctor.reason or 'verification-failed'
    return ExecutionStatus.PASS, ''


def _emit(
    sink: Callable[[ExecutionEvent], None] | None,
    kind: str,
    *,
    elapsed_seconds: float,
    status: ExecutionStatus | None = None,
    reason: str = '',
    process_count: int = 1,
) -> None:
    if sink is None:
        return
    sink(
        ExecutionEvent(
            kind,
            gate_name='gate-health',
            elapsed_seconds=round(elapsed_seconds, 3),
            status=status.value if status else '',
            reason=reason,
            process_count=process_count,
        )
    )


def audit_gate_health(
    *,
    repo_root: Path,
    event_sink: Callable[[ExecutionEvent], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> GateHealthAudit:
    """静态检查完整 GatePlan，并只运行一个 Harness doctor 进程。"""

    started = clock()
    root = repo_root.resolve()
    validate_gate_catalog(CATALOG)
    plan = _full_plan(root)
    missing_steps = _missing_recipe_steps(plan)
    unavailable = _unavailable_executables(plan)
    runtime_logs = root / 'tmp' / 'quality' / 'health' / str(time.monotonic_ns())
    runtime_logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    _emit(event_sink, 'PLAN', elapsed_seconds=0.0)

    doctor_invocation = _doctor_invocation()
    doctor_observation = supervise_process(
        doctor_invocation,
        cwd=root,
        log_path=runtime_logs / 'harness-doctor.log',
        event_sink=event_sink,
    )
    doctor_result = classify_owner_outcome(doctor_invocation, doctor_observation)
    status, reason = _health_status(doctor_result, missing_steps, unavailable)
    elapsed = round(clock() - started, 6)
    _emit(
        event_sink,
        'RESULT',
        elapsed_seconds=doctor_result.duration_seconds,
        status=doctor_result.status,
        reason=doctor_result.reason,
    )
    _emit(
        event_sink,
        'DONE',
        elapsed_seconds=elapsed,
        status=status,
        reason=reason,
    )
    return GateHealthAudit(
        status,
        reason,
        doctor_result,
        len(plan.gates),
        sum(len(gate.recipe.steps) for gate in plan.gates),
        plan.process_count,
        1,
        missing_steps,
        unavailable,
        elapsed,
    )
