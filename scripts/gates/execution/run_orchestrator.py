"""负责串行执行冻结 GatePlan 并归约 StepResult 与 GateResult；不负责选择 Gate。

由 CLI 和 Maintenance 健康审计调用。"""

from __future__ import annotations

import os
import re
import shlex
import time
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.gates.execution.outcome_classifier import (
    ExecutionStatus,
    GateResult,
    InvocationResult,
    StepResult,
    classify_owner_outcome,
)
from scripts.gates.execution.process_supervisor import (
    ExecutionEvent,
    supervise_process,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from scripts.gates.catalog.gate_contracts import Gate, RecipeStep
    from scripts.gates.planning.plan_compiler import CommandInvocation, GatePlan

RESERVED_ENVIRONMENT_KEYS = frozenset({'QUALITY_EXECUTION_MODE', 'QUALITY_CHANGED_FILES'})


def _emit(
    sink: Callable[[ExecutionEvent], None] | None,
    kind: str,
    *,
    gate_name: str = '',
    step_name: str = '',
    status: ExecutionStatus | None = None,
    reason: str = '',
    elapsed: float = 0.0,
    process_count: int = 0,
) -> None:
    if sink is not None:
        sink(
            ExecutionEvent(
                kind,
                gate_name=gate_name,
                recipe_step_name=step_name,
                elapsed_seconds=round(elapsed, 3),
                status=status.value if status else '',
                reason=reason,
                process_count=process_count,
            )
        )


def _aggregate_status(results: tuple[InvocationResult, ...]) -> tuple[ExecutionStatus, str]:
    """按 FAIL、BLOCKED、PASS 优先级归约步骤内的命令结果。"""
    failed = next((result for result in results if result.status is ExecutionStatus.FAIL), None)
    if failed is not None:
        return ExecutionStatus.FAIL, failed.reason or 'outcome-unknown'
    if any(result.status is ExecutionStatus.BLOCKED for result in results):
        return ExecutionStatus.BLOCKED, 'verification-failed'
    if results and all(result.status is ExecutionStatus.PASS for result in results):
        return ExecutionStatus.PASS, ''
    return ExecutionStatus.FAIL, 'outcome-unknown'


def _step_result(
    gate: Gate,
    step: RecipeStep,
    results: tuple[InvocationResult, ...],
    invocations: tuple[CommandInvocation, ...],
    *,
    forced_reason: str = '',
) -> StepResult:
    status, reason = _aggregate_status(results)
    if forced_reason:
        status, reason = ExecutionStatus.FAIL, forced_reason
    rerun = ' && '.join(
        shlex.join(invocation.argv) for invocation in invocations if invocation.argv
    )
    return StepResult(
        gate.name,
        step.name,
        status,
        reason,
        round(sum(result.duration_seconds for result in results), 6),
        results,
        rerun,
    )


def _missing_step_result(gate: Gate, step: RecipeStep, reason: str) -> StepResult:
    return StepResult(gate.name, step.name, ExecutionStatus.FAIL, reason, 0.0, (), '')


def _gate_result(gate: Gate, mode: object, steps: tuple[StepResult, ...]) -> GateResult:
    """归约一个 Gate 的步骤结果并计算时间目标状态与重跑命令。"""
    failed = next((step for step in steps if step.status is ExecutionStatus.FAIL), None)
    if failed is not None:
        status, reason = ExecutionStatus.FAIL, failed.reason or 'outcome-unknown'
    elif any(step.status is ExecutionStatus.BLOCKED for step in steps):
        status, reason = ExecutionStatus.BLOCKED, 'verification-failed'
    elif steps and all(step.status is ExecutionStatus.PASS for step in steps):
        status, reason = ExecutionStatus.PASS, ''
    else:
        status, reason = ExecutionStatus.FAIL, 'outcome-unknown'
    duration = round(sum(step.duration_seconds for step in steps), 6)
    target = gate.recipe.duration_for(str(mode))
    timing = 'OVER_TARGET' if duration > target else 'WITHIN_TARGET'
    rerun = f'python3 scripts/gates/cli.py run --mode {mode} --gate {shlex.quote(gate.name)}'
    return GateResult(gate.name, status, reason, duration, target, timing, steps, rerun)


def _log_file(log_dir: Path, invocation: CommandInvocation, index: int) -> Path:
    safe = re.sub(r'[^A-Za-z0-9_.-]+', '-', invocation.invocation_id).strip('-') or 'command'
    return log_dir / f'{index:03d}-{safe[:96]}.log'


def _run_step_invocations(
    gate: Gate,
    step: RecipeStep,
    invocations: tuple[CommandInvocation, ...],
    *,
    repo_root: Path,
    log_dir: Path,
    invocation_offset: int,
    environment_overrides: Mapping[str, str | None] | None,
    event_sink: Callable[[ExecutionEvent], None] | None,
    supervisor: Callable[..., object],
) -> tuple[StepResult, bool]:
    if not invocations:
        return _missing_step_result(gate, step, 'runtime-missing'), False
    results: list[InvocationResult] = []
    interrupted = False
    forced_reason = ''
    for index, invocation in enumerate(invocations, start=invocation_offset):
        if results and invocations[0].kind == 'gradle-prerequisite':
            prerequisite = results[0]
            if prerequisite.status is not ExecutionStatus.PASS:
                forced_reason = (
                    'process-stalled'
                    if prerequisite.reason == 'process-stalled'
                    else 'dependency-unavailable'
                )
                break
        observation = supervisor(
            invocation,
            cwd=repo_root,
            log_path=_log_file(log_dir, invocation, index),
            environment_overrides=environment_overrides,
            event_sink=event_sink,
        )
        result = classify_owner_outcome(invocation, observation)
        results.append(result)
        if result.reason == 'interrupted':
            interrupted = True
            break
    return (
        _step_result(gate, step, tuple(results), invocations, forced_reason=forced_reason),
        interrupted,
    )


def orchestrate_gate_run(
    gate_plan: GatePlan,
    repo_root: Path | str,
    *,
    log_dir: Path | str | None = None,
    environment_overrides: Mapping[str, str | None] | None = None,
    event_sink: Callable[[ExecutionEvent], None] | None = None,
    supervisor: Callable[..., object] = supervise_process,
) -> tuple[GateResult, ...]:
    """串行执行全部 RecipeStep；业务 BLOCKED/FAIL 不阻断后续步骤。"""

    started = time.monotonic()
    overrides = environment_overrides or {}
    reserved = RESERVED_ENVIRONMENT_KEYS & overrides.keys()
    if reserved:
        raise ValueError(
            f'cannot override frozen GatePlan environment: {", ".join(sorted(reserved))}'
        )
    root = Path(repo_root).resolve()
    selected_log_dir = (
        Path(log_dir).resolve()
        if log_dir is not None
        else root / 'tmp' / 'quality' / 'runtime-logs' / f'{os.getpid()}-{time.monotonic_ns()}'
    )
    selected_log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    _emit(event_sink, 'PLAN', process_count=gate_plan.process_count)
    results: list[GateResult] = []
    interrupted = False
    invocation_index = 1
    invocations = tuple(gate_plan.command_invocations)
    for gate in gate_plan.gates:
        step_results: list[StepResult] = []
        for step in gate.recipe.steps:
            owned = tuple(
                invocation
                for invocation in invocations
                if invocation.gate_name == gate.name and invocation.recipe_step_name == step.name
            )
            if interrupted:
                step_result = _missing_step_result(gate, step, 'interrupted')
            else:
                step_result, interrupted = _run_step_invocations(
                    gate,
                    step,
                    owned,
                    repo_root=root,
                    log_dir=selected_log_dir,
                    invocation_offset=invocation_index,
                    environment_overrides=overrides,
                    event_sink=event_sink,
                    supervisor=supervisor,
                )
                invocation_index += len(step_result.invocation_results)
            step_results.append(step_result)
            _emit(
                event_sink,
                'RESULT',
                gate_name=gate.name,
                step_name=step.name,
                status=step_result.status,
                reason=step_result.reason,
                elapsed=step_result.duration_seconds,
            )
        gate_result = _gate_result(gate, gate_plan.mode, tuple(step_results))
        results.append(gate_result)
    aggregate, reason = _aggregate_gate_status(tuple(results))
    _emit(
        event_sink,
        'DONE',
        status=aggregate,
        reason=reason,
        elapsed=time.monotonic() - started,
        process_count=gate_plan.process_count,
    )
    return tuple(results)


def _aggregate_gate_status(results: tuple[GateResult, ...]) -> tuple[ExecutionStatus, str]:
    """归约整次运行的 Gate 状态，空结果明确归为输入失败。"""
    failed = next((result for result in results if result.status is ExecutionStatus.FAIL), None)
    if failed is not None:
        return ExecutionStatus.FAIL, failed.reason or 'outcome-unknown'
    if any(result.status is ExecutionStatus.BLOCKED for result in results):
        return ExecutionStatus.BLOCKED, 'verification-failed'
    if results and all(result.status is ExecutionStatus.PASS for result in results):
        return ExecutionStatus.PASS, ''
    return ExecutionStatus.FAIL, 'input-empty'
