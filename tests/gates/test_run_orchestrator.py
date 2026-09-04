"""冻结 GatePlan 的串行执行、聚合与事件 contract。"""

import importlib
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
from scripts.gates.execution.outcome_classifier import ExecutionStatus
from scripts.gates.execution.process_supervisor import ExecutionEvent, ProcessObservation
from scripts.gates.execution.run_orchestrator import orchestrate_gate_run
from scripts.gates.planning.change_snapshot import ChangeSnapshot
from scripts.gates.planning.plan_compiler import CommandInvocation, GatePlan


def _gate(*steps: RecipeStep) -> Gate:
    return Gate(
        'sampleGate',
        'sample',
        GateTrigger(TriggerMode.CHANGED, ('**',)),
        (),
        GateRecipe(DurationExpectations(1, 1), steps),
    )


def _plan(gate: Gate, invocations: tuple[CommandInvocation, ...]) -> GatePlan:
    snapshot = ChangeSnapshot('changed-files', 'head', None, ('file.py',), 'fingerprint')
    return GatePlan(
        ExecutionMode.INCREMENTAL, snapshot, (gate,), (), (), command_invocations=invocations
    )


def _invocation(step: str) -> CommandInvocation:
    return CommandInvocation(
        f'sampleGate:{step}:run', 'command', ('tool', step), (), 'sampleGate', step
    )


def _supervisor(codes: iter, observed: list[str]):
    def run(invocation, **kwargs):
        observed.append(invocation.recipe_step_name)
        code = next(codes)
        log = Path(kwargs['log_path'])
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('finding' if code else 'ok', encoding='utf-8')
        return ProcessObservation(
            code,
            'EXITED',
            'c',
            'e',
            's',
            'f',
            0.6,
            1,
            str(log),
            '',
        )

    return run


def test_composite_runs_every_step_and_fail_dominates(tmp_path: Path) -> None:
    steps = (
        RecipeStep('first', RecipeStepKind.COMMAND, argv=('tool',)),
        RecipeStep('second', RecipeStepKind.COMMAND, argv=('tool',)),
    )
    gate = _gate(*steps)
    invocations = tuple(_invocation(step.name) for step in steps)
    observed: list[str] = []
    result = orchestrate_gate_run(
        _plan(gate, invocations),
        tmp_path,
        log_dir=tmp_path / 'logs',
        supervisor=_supervisor(iter((2, 0)), observed),
    )[0]
    assert observed == ['first', 'second']
    assert [step.status for step in result.step_results] == [
        ExecutionStatus.FAIL,
        ExecutionStatus.PASS,
    ]
    assert result.status is ExecutionStatus.FAIL


def test_blocked_does_not_fail_fast_or_exceed_target_status(tmp_path: Path) -> None:
    steps = (
        RecipeStep('first', RecipeStepKind.COMMAND, argv=('tool',)),
        RecipeStep('second', RecipeStepKind.COMMAND, argv=('tool',)),
    )
    gate = _gate(*steps)
    observed: list[str] = []
    result = orchestrate_gate_run(
        _plan(gate, tuple(_invocation(step.name) for step in steps)),
        tmp_path,
        log_dir=tmp_path / 'logs',
        supervisor=_supervisor(iter((1, 0)), observed),
    )[0]
    assert observed == ['first', 'second']
    assert result.status is ExecutionStatus.BLOCKED
    assert result.reason == 'verification-failed'
    assert result.timing_state == 'OVER_TARGET'


def test_plan_result_done_events_are_stable(tmp_path: Path, monkeypatch) -> None:
    module = importlib.import_module('scripts.gates.execution.run_orchestrator')
    ticks = iter((10.0, 12.5))
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(ticks))
    step = RecipeStep('only', RecipeStepKind.COMMAND, argv=('tool',))
    gate = _gate(step)
    events: list[ExecutionEvent] = []
    result = orchestrate_gate_run(
        _plan(gate, (_invocation('only'),)),
        tmp_path,
        log_dir=tmp_path / 'logs',
        supervisor=_supervisor(iter((0,)), []),
        event_sink=events.append,
    )[0]
    assert [event.kind for event in events] == ['PLAN', 'RESULT', 'DONE']
    assert events[0].process_count == 1
    assert events[-1].status == 'PASS'
    assert events[-1].elapsed_seconds == 2.5
    assert events[-1].process_count == 1
    assert '--gate sampleGate' in result.canonical_rerun


def test_reserved_frozen_environment_cannot_be_overridden(tmp_path: Path) -> None:
    step = RecipeStep('only', RecipeStepKind.COMMAND, argv=('tool',))
    gate = _gate(step)
    try:
        orchestrate_gate_run(
            _plan(gate, (_invocation('only'),)),
            tmp_path,
            environment_overrides={'QUALITY_EXECUTION_MODE': 'full'},
        )
    except ValueError as exc:
        assert 'cannot override frozen GatePlan' in str(exc)
    else:
        raise AssertionError('reserved environment override should fail')
