"""Presentation 阶段的 catalog、plan 与事件稳定性契约。"""

import json
from types import SimpleNamespace

import pytest
from scripts.gates.catalog.gate_contracts import (
    DurationExpectations,
    ExecutionMode,
    Gate,
    GateCatalog,
    GateRecipe,
    GateTrigger,
    RecipeStep,
    RecipeStepKind,
    TargetPreset,
    TriggerMode,
)
from scripts.gates.planning.change_snapshot import ChangeSnapshot
from scripts.gates.planning.plan_compiler import CommandInvocation, GatePlan
from scripts.gates.planning.trigger_matcher import NotTriggeredGate, TriggerMatch
from scripts.gates.presentation.terminal_ui import (
    render_explanation,
    render_gate_catalog,
    render_gate_plan,
    render_run_receipt,
    render_terminal_event,
)


def _catalog_and_plan() -> tuple[GateCatalog, GatePlan]:
    target = TargetPreset('gate-infrastructure', 'Gate infrastructure owners')
    gate = Gate(
        'gateFrameworkTests',
        'Run Gate framework contracts.',
        GateTrigger(TriggerMode.CHANGED, ('scripts/gates/**',)),
        (target.name,),
        GateRecipe(
            DurationExpectations(10, 20),
            (RecipeStep('frameworkContracts', RecipeStepKind.COMMAND, argv=('true',)),),
        ),
    )
    snapshot = ChangeSnapshot(
        'explicit-changed-files',
        'head-sha',
        None,
        ('scripts/gates/cli.py',),
        'content-sha',
    )
    invocation = CommandInvocation(
        'gateFrameworkTests:frameworkContracts:run',
        'command',
        ('true',),
        (),
        gate.name,
        'frameworkContracts',
    )
    plan = GatePlan(
        ExecutionMode.INCREMENTAL,
        snapshot,
        (gate,),
        (TriggerMatch('scripts/gates/cli.py', 'scripts/gates/**', gate.name),),
        (NotTriggeredGate('javaBuildVerification', 'no-trigger-pattern-matched'),),
        command_invocations=(invocation,),
    )
    return GateCatalog((target,), (gate,)), plan


def test_catalog_and_explain_share_public_ids() -> None:
    catalog, _plan = _catalog_and_plan()

    payload = json.loads(render_gate_catalog(catalog, output_format='json'))
    explanation = json.loads(render_explanation(catalog.gates[0], catalog, output_format='json'))

    assert payload['gates'][0]['id'] == 'gateFrameworkTests'
    assert payload['targetPresets'][0]['id'] == 'gate-infrastructure'
    assert explanation['recipeSteps'] == [
        {'checkId': None, 'kind': 'command', 'name': 'frameworkContracts'}
    ]
    assert 'RecipeStep' in render_explanation(catalog.gates[0], catalog).replace(
        'recipeStep', 'RecipeStep'
    )


def test_human_plan_explains_snapshot_match_not_triggered_and_process_cost() -> None:
    _catalog, plan = _catalog_and_plan()

    rendered = render_gate_plan(plan)

    assert 'source=explicit-changed-files' in rendered
    assert 'MATCH file=scripts/gates/cli.py pattern=scripts/gates/**' in rendered
    assert 'NOT_TRIGGERED gate=javaBuildVerification' in rendered
    assert 'target_seconds=10' in rendered
    assert 'processes=1' in rendered
    assert 'RECIPE_STEP gate=gateFrameworkTests step=frameworkContracts' in rendered


def test_json_plan_keeps_exact_causal_chain() -> None:
    _catalog, plan = _catalog_and_plan()

    payload = json.loads(render_gate_plan(plan, output_format='json'))

    assert payload['snapshot']['files'] == ['scripts/gates/cli.py']
    assert payload['matches'] == [
        {
            'file': 'scripts/gates/cli.py',
            'gate': 'gateFrameworkTests',
            'pattern': 'scripts/gates/**',
        }
    ]
    assert payload['processCount'] == 1


def test_terminal_event_is_one_line_and_does_not_reclassify_status() -> None:
    assert render_terminal_event(
        'result',
        {'gate': 'javaBuildVerification', 'status': 'BLOCKED'},
        reason='verification-failed',
    ) == ('RESULT gate=javaBuildVerification status=BLOCKED reason=verification-failed')
    assert render_terminal_event('heartbeat', elapsed_seconds=30) == (
        'HEARTBEAT elapsed_seconds=30'
    )
    with pytest.raises(ValueError, match='unsupported terminal event'):
        render_terminal_event('WARNING', status='PASS')


def test_receipt_rendering_preserves_final_status(tmp_path) -> None:
    receipt = SimpleNamespace(
        schema_version=5,
        run_id='run-1',
        status='FAIL',
        reason='input-empty',
        duration_ms=0,
        plan_fingerprint='plan-sha',
        summary_path=tmp_path / 'summary.json',
        canonical_rerun='python3 scripts/gates/cli.py run --mode incremental',
    )

    human = render_run_receipt(receipt)
    payload = json.loads(render_run_receipt(receipt, output_format='json'))

    assert 'status=FAIL reason=input-empty' in human
    assert payload['status'] == 'FAIL'
    assert payload['schemaVersion'] == 5
