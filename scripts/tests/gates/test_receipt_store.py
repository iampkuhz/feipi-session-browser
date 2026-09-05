"""schema v5 immutable RunReceipt 的证据与复现契约。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
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
from scripts.gates.execution.outcome_classifier import (
    ExecutionStatus,
    GateResult,
    InvocationResult,
    StepResult,
)
from scripts.gates.planning.change_snapshot import ChangeSnapshot
from scripts.gates.planning.plan_compiler import CommandInvocation, GatePlan
from scripts.gates.planning.trigger_matcher import NotTriggeredGate, TriggerMatch


def _plan(*, source: str = 'git-base', base: str | None = 'base-sha') -> GatePlan:
    gate = Gate(
        'javaBuildVerification',
        'Verify the Java build.',
        GateTrigger(TriggerMode.CHANGED, ('java/**',)),
        ('java-build',),
        GateRecipe(
            DurationExpectations(60, 120),
            (RecipeStep('gradleCheck', RecipeStepKind.GRADLE_TASK, tasks=('check',)),),
        ),
    )
    snapshot = ChangeSnapshot(source, 'head-sha', base, ('java/App.java',), 'content-sha')
    invocation = CommandInvocation(
        'javaBuildVerification:gradleCheck:run',
        'gradle-task',
        ('./java/gradlew', '-p', 'java', 'check'),
        (('QUALITY_EXECUTION_MODE', 'incremental'), ('API_TOKEN', 'do-not-store')),
        gate.name,
        'gradleCheck',
    )
    return GatePlan(
        ExecutionMode.INCREMENTAL,
        snapshot,
        (gate,),
        (TriggerMatch('java/App.java', 'java/**', gate.name),),
        (NotTriggeredGate('webStaticRules', 'no-trigger-pattern-matched'),),
        command_invocations=(invocation,),
    )


def _blocked_result(log_path: Path) -> GateResult:
    invocation = InvocationResult(
        'javaBuildVerification:gradleCheck:run',
        'javaBuildVerification',
        'gradleCheck',
        ExecutionStatus.BLOCKED,
        'verification-failed',
        1,
        0.125,
        str(log_path),
        'Spotless found a violation',
        ((':check', 'FAILED'),),
        (),
    )
    step = StepResult(
        'javaBuildVerification',
        'gradleCheck',
        ExecutionStatus.BLOCKED,
        'verification-failed',
        0.125,
        (invocation,),
        './java/gradlew -p java check',
    )
    return GateResult(
        'javaBuildVerification',
        ExecutionStatus.BLOCKED,
        'verification-failed',
        0.125,
        60,
        'WITHIN_TARGET',
        (step,),
        'python3 scripts/gates/cli.py run --mode full --gate javaBuildVerification',
    )


@pytest.mark.contract_case('HOOK-HARNESS-007', 'HOOK-HARNESS-012')
def test_receipt_v5_preserves_plan_results_logs_and_gate_rerun(tmp_path: Path) -> None:
    source_log = tmp_path / 'owner.log'
    source_log.write_text('Spotless found a violation\n', encoding='utf-8')
    doctor_log = tmp_path / 'doctor.log'
    doctor_log.write_text('doctor ok\n', encoding='utf-8')

    receipt = store_run_receipt(
        _plan(),
        (_blocked_result(source_log),),
        repo_root=tmp_path,
        run_id='run-001',
        started_at='2026-09-04T01:00:00+00:00',
        finished_at='2026-09-04T01:00:01+00:00',
        additional_logs={'maintenance-harness-doctor': doctor_log},
    )
    plan = json.loads(receipt.plan_path.read_text(encoding='utf-8'))
    summary = json.loads(receipt.summary_path.read_text(encoding='utf-8'))

    assert receipt.status == 'BLOCKED'
    assert summary['schemaVersion'] == 5
    assert summary['snapshot'] == {
        'base': 'base-sha',
        'contentFingerprint': 'content-sha',
        'files': ['java/App.java'],
        'head': 'head-sha',
        'source': 'git-base',
    }
    assert summary['matches'] == [
        {'file': 'java/App.java', 'gate': 'javaBuildVerification', 'pattern': 'java/**'}
    ]
    assert summary['notTriggered'][0]['gate'] == 'webStaticRules'
    assert plan['processCount'] == summary['processCount'] == 1
    assert plan['commandInvocations'][0]['environment']['API_TOKEN'] == '<redacted>'
    assert summary['gateResults'][0]['canonicalRerun'].endswith('--gate javaBuildVerification')
    assert summary['gateResults'][0]['recipeSteps'][0]['durationMs'] == 125
    copied_log = receipt.run_directory / summary['artifacts']['logs'][0]
    assert copied_log.read_text(encoding='utf-8') == 'Spotless found a violation\n'
    assert (receipt.run_directory / 'logs' / 'maintenance-harness-doctor.log').read_text(
        encoding='utf-8'
    ) == 'doctor ok\n'
    assert '--base base-sha' in summary['canonicalRerun']


def test_same_run_id_never_overwrites_history(tmp_path: Path) -> None:
    source_log = tmp_path / 'owner.log'
    source_log.write_text('first\n', encoding='utf-8')
    first = store_run_receipt(
        _plan(), (_blocked_result(source_log),), repo_root=tmp_path, run_id='fixed-run'
    )
    original = first.summary_path.read_bytes()

    with pytest.raises(FileExistsError):
        store_run_receipt(
            _plan(), (_blocked_result(source_log),), repo_root=tmp_path, run_id='fixed-run'
        )

    assert first.summary_path.read_bytes() == original


def test_consecutive_auto_runs_are_unique_and_latest_is_only_pointer(tmp_path: Path) -> None:
    source_log = tmp_path / 'owner.log'
    source_log.write_text('owner evidence\n', encoding='utf-8')
    first = store_run_receipt(_plan(), (_blocked_result(source_log),), repo_root=tmp_path)
    second = store_run_receipt(_plan(), (_blocked_result(source_log),), repo_root=tmp_path)
    latest = json.loads(
        (tmp_path / 'tmp' / 'quality' / 'runs' / 'latest.json').read_text(encoding='utf-8')
    )

    assert first.run_id != second.run_id
    assert first.summary_path.is_file() and second.summary_path.is_file()
    assert latest == {'runId': second.run_id, 'summary': f'{second.run_id}/summary.json'}


def test_empty_run_is_fail_receipt_with_explicit_input_reason(tmp_path: Path) -> None:
    plan = _plan(source='explicit-changed-files', base=None)
    plan = GatePlan(
        plan.mode,
        ChangeSnapshot('git-working-tree', 'head-sha', None, (), 'empty-sha'),
        (),
        (),
        plan.not_triggered,
    )

    receipt = store_run_receipt(
        plan, (), repo_root=tmp_path, run_id='empty-run', reason='input-empty'
    )
    summary = json.loads(receipt.summary_path.read_text(encoding='utf-8'))

    assert receipt.status == 'FAIL'
    assert receipt.reason == 'input-empty'
    assert summary['gateResults'] == []
    assert summary['artifacts']['logs'] == []
    assert (receipt.run_directory / 'logs').is_dir()


def test_incremental_selector_rerun_keeps_frozen_input(tmp_path: Path) -> None:
    plan = replace(_plan(), selector_kind='gate', selector_value='javaBuildVerification')

    receipt = store_run_receipt(
        plan, (), repo_root=tmp_path, run_id='selector-run', reason='input-empty'
    )

    assert '--gate javaBuildVerification' in receipt.canonical_rerun
    assert '--base base-sha' in receipt.canonical_rerun
