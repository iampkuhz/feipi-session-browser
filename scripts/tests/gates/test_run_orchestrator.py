"""冻结 GatePlan 的串行执行、聚合与事件 contract。"""

import importlib
import json
from dataclasses import replace
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
from scripts.gates.evidence.receipt_store import store_run_receipt
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


def _supervisor(codes: iter, observed: list[str], *, stalled_steps: tuple[str, ...] = ()):
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
            stalled=invocation.recipe_step_name in stalled_steps,
        )

    return run


def test_stall_exit_zero_fails_all_layers_despite_later_pass(tmp_path: Path) -> None:
    steps = tuple(
        RecipeStep(name, RecipeStepKind.COMMAND, argv=('tool',))
        for name in ('stalled', 'independent')
    )
    plan = _plan(_gate(*steps), tuple(_invocation(step.name) for step in steps))
    observed: list[str] = []
    events: list[ExecutionEvent] = []
    results = orchestrate_gate_run(
        plan,
        tmp_path,
        supervisor=_supervisor(iter((0, 0)), observed, stalled_steps=('stalled',)),
        event_sink=events.append,
    )
    gate = results[0]
    stalled, independent = gate.step_results
    invocation = stalled.invocation_results[0]
    assert observed == ['stalled', 'independent']
    assert invocation.return_code == 0
    for result in (invocation, stalled, gate):
        assert result.status is ExecutionStatus.FAIL
        assert result.reason == 'process-stalled'
    assert independent.status is ExecutionStatus.PASS
    assert [(event.status, event.reason) for event in events if event.kind == 'RESULT'] == [
        ('FAIL', 'process-stalled'),
        ('PASS', ''),
    ]
    assert (events[-1].kind, events[-1].status, events[-1].reason) == (
        'DONE',
        'FAIL',
        'process-stalled',
    )
    receipt = store_run_receipt(plan, results, repo_root=tmp_path)
    assert (receipt.status, receipt.reason) == ('FAIL', 'process-stalled')
    payload = json.loads(receipt.summary_path.read_text(encoding='utf-8'))
    gate_payload = payload['gateResults'][0]
    step_payload = gate_payload['recipeSteps'][0]
    invocation_payload = step_payload['invocationResults'][0]
    for layer in (payload, gate_payload, step_payload, invocation_payload):
        assert (layer['status'], layer['reason']) == ('FAIL', 'process-stalled')
    assert invocation_payload['returnCode'] == 0
    assert gate_payload['recipeSteps'][1]['status'] == 'PASS'


def test_stalled_prerequisite_preserves_reason_and_skips_dependent_command(tmp_path: Path) -> None:
    steps = tuple(
        RecipeStep(name, RecipeStepKind.COMMAND, argv=('tool',))
        for name in ('dependent', 'independent')
    )
    prerequisite = replace(
        _invocation('dependent'), invocation_id='prerequisite', kind='gradle-prerequisite'
    )
    invocations = (prerequisite, _invocation('dependent'), _invocation('independent'))
    observed: list[str] = []
    result = orchestrate_gate_run(
        _plan(_gate(*steps), invocations),
        tmp_path,
        supervisor=_supervisor(iter((0, 0)), observed, stalled_steps=('dependent',)),
    )[0]
    assert observed == ['dependent', 'independent']
    dependent, independent = result.step_results
    assert len(dependent.invocation_results) == 1
    assert dependent.invocation_results[0].invocation_id == 'prerequisite'
    assert dependent.invocation_results[0].return_code == 0
    for layer in (dependent.invocation_results[0], dependent, result):
        assert (layer.status, layer.reason) == (ExecutionStatus.FAIL, 'process-stalled')
    assert independent.status is ExecutionStatus.PASS


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
