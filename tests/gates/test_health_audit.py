"""Maintenance 快速控制面体检的公开契约与状态归约。"""

import ast
from pathlib import Path

from scripts.gates.catalog.gate_contracts import (
    DurationExpectations,
    ExecutionMode,
    Gate,
    GateRecipe,
    GateTrigger,
    RecipeStep,
    RecipeStepKind,
    TriggerMode,
)
from scripts.gates.execution import ExecutionEvent, ExecutionStatus, InvocationResult
from scripts.gates.maintenance import health_audit
from scripts.gates.planning import ChangeSnapshot, CommandInvocation, GatePlan


def _doctor(status: ExecutionStatus, reason: str = '') -> InvocationResult:
    return InvocationResult(
        'gate-health:harnessDoctor:run',
        'gate-health',
        'harnessDoctor',
        status,
        reason,
        0 if status is ExecutionStatus.PASS else 1,
        0.05,
        '/tmp/doctor.log',
        '',
    )


def _plan(*, executable: str = 'true', include_invocation: bool = True) -> GatePlan:
    step = RecipeStep('catalogContract', RecipeStepKind.COMMAND, argv=(executable,))
    gate = Gate(
        'gateFrameworkTests',
        '校验 Gate 控制面契约。',
        GateTrigger(TriggerMode.ALWAYS),
        (),
        GateRecipe(DurationExpectations(1, 1), (step,)),
    )
    invocation = CommandInvocation(
        'gateFrameworkTests:catalogContract:run',
        'command',
        (executable,),
        (),
        gate.name,
        step.name,
    )
    return GatePlan(
        ExecutionMode.FULL,
        ChangeSnapshot('full', 'head', None, (), 'fingerprint'),
        (gate,),
        (),
        (),
        command_invocations=(invocation,) if include_invocation else (),
    )


def _install(
    monkeypatch,
    *,
    plan: GatePlan,
    doctor: InvocationResult,
) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(health_audit, 'validate_gate_catalog', lambda _catalog: None)
    monkeypatch.setattr(health_audit, '_full_plan', lambda _root: plan)

    def supervise(*_args, **kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(health_audit, 'supervise_process', supervise)
    monkeypatch.setattr(health_audit, 'classify_owner_outcome', lambda *_args: doctor)
    return calls


def test_health_checks_full_plan_and_runs_only_doctor(tmp_path: Path, monkeypatch) -> None:
    calls = _install(monkeypatch, plan=_plan(), doctor=_doctor(ExecutionStatus.PASS))
    ticks = iter((10.0, 10.25))
    events: list[ExecutionEvent] = []

    result = health_audit.audit_gate_health(
        repo_root=tmp_path,
        event_sink=events.append,
        clock=lambda: next(ticks),
    )

    assert result.status is ExecutionStatus.PASS
    assert (result.gate_count, result.recipe_step_count) == (1, 1)
    assert (result.planned_process_count, result.executed_process_count) == (1, 1)
    assert result.elapsed_seconds == 0.25
    assert len(calls) == 1
    assert calls[0]['log_path'].name == 'harness-doctor.log'
    assert [event.kind for event in events] == ['PLAN', 'RESULT', 'DONE']
    assert events[-1].elapsed_seconds == 0.25


def test_missing_recipe_mapping_is_health_fail(tmp_path: Path, monkeypatch) -> None:
    _install(
        monkeypatch,
        plan=_plan(include_invocation=False),
        doctor=_doctor(ExecutionStatus.PASS),
    )

    result = health_audit.audit_gate_health(repo_root=tmp_path)

    assert result.status is ExecutionStatus.FAIL
    assert result.reason == 'runtime-missing'
    assert result.missing_recipe_steps == ('gateFrameworkTests:catalogContract',)


def test_unavailable_executable_is_health_fail(tmp_path: Path, monkeypatch) -> None:
    missing = str(tmp_path / 'missing-command')
    _install(
        monkeypatch,
        plan=_plan(executable=missing),
        doctor=_doctor(ExecutionStatus.PASS),
    )

    result = health_audit.audit_gate_health(repo_root=tmp_path)

    assert result.status is ExecutionStatus.FAIL
    assert result.unavailable_executables == (missing,)


def test_doctor_blocked_is_preserved(tmp_path: Path, monkeypatch) -> None:
    _install(
        monkeypatch,
        plan=_plan(),
        doctor=_doctor(ExecutionStatus.BLOCKED, 'verification-failed'),
    )

    result = health_audit.audit_gate_health(repo_root=tmp_path)

    assert result.status is ExecutionStatus.BLOCKED
    assert result.reason == 'verification-failed'


def test_health_audit_has_no_gate_execution_or_receipt_dependency() -> None:
    source = Path(health_audit.__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert 'orchestrate_gate_run' not in imported_names
    assert 'store_run_receipt' not in imported_names
    assert 'RunReceipt' not in imported_names
