"""Gate Executor 的 typed adapter、请求环境和 0/1/2 状态 contract。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.gates import executor
from scripts.gates.catalog import gate_by_name
from scripts.gates.model import ExecutionMode, GatePlan
from scripts.gates.report import BLOCKED, FAIL, PASS, GateDetail


@pytest.fixture(autouse=True)
def _stable_project_python(monkeypatch) -> None:
    """Unit tests use synthetic repo roots and must not probe their Python environment."""

    monkeypatch.setattr(executor, '_project_python', lambda _root, dev=False: '/tmp/python')


def _single(gate: str, mode: ExecutionMode = ExecutionMode.INCREMENTAL) -> GatePlan:
    return GatePlan(
        mode,
        ('scripts/a.py',) if mode is ExecutionMode.INCREMENTAL else (),
        (gate_by_name(gate),),
        'gate',
        gate,
    )


def test_python_check_adapter_uses_declared_check_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor, '_project_python', lambda _root, dev=False: '/tmp/python')
    step = gate_by_name('noPythonPlaywrightSkips').run.steps[0]
    assert executor.command_for_step(step, tmp_path) == [
        '/tmp/python',
        '-m',
        'scripts.gates.checks',
        'repository.no-python-playwright-skips',
    ]


def test_gradle_and_java_rule_use_typed_step(tmp_path: Path) -> None:
    (tmp_path / 'gradlew').write_text('', encoding='utf-8')
    gradle_step = gate_by_name('webResourceTests').run.steps[0]
    assert executor.command_for_step(gradle_step, tmp_path)[1:] == [':java:web:test']
    java_step = gate_by_name('webSourcePolicy').run.steps[0]
    assert executor.command_for_step(java_step, tmp_path)[-1] == (
        '-PfeipiJavaQualityRules=raw-innerhtml'
    )


def test_playwright_adapter_uses_typed_tests_and_args(tmp_path: Path) -> None:
    command = executor.command_for_step(gate_by_name('browserLayout').run.steps[0], tmp_path)
    assert command[:5] == ['npm', '--prefix', 'tests/playwright', 'test', '--']
    assert 'ui-contract.spec.ts' in command


def test_gate_request_environment_has_mode_and_incremental_files() -> None:
    env = executor.gate_request_environment(_single('pythonHarnessTests'))
    assert env == {
        'QUALITY_EXECUTION_MODE': 'incremental',
        'QUALITY_CHANGED_FILES': '["scripts/a.py"]',
    }
    assert executor.gate_request_environment(_single('pythonHarnessTests', ExecutionMode.FULL)) == {
        'QUALITY_EXECUTION_MODE': 'full'
    }


@pytest.mark.parametrize(('code', 'status'), [(0, PASS), (1, BLOCKED), (2, FAIL), (7, FAIL)])
def test_owner_exit_code_maps_to_three_states(
    code: int, status: str, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def managed(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text('owner output', encoding='utf-8')
        return SimpleNamespace(return_code=code, duration_seconds=0.01, output_tail='')

    monkeypatch.setattr(executor, 'run_managed', managed)
    assert executor.run_cmd('owner', ['tool'], tmp_path).status == status


def test_vulture_findings_are_blocked_not_execution_failure(tmp_path: Path, monkeypatch) -> None:
    """Vulture 的退出码 3 表示发现死代码，不能误报为 Gate 执行失败。"""

    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/python')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def managed(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text('dead code finding', encoding='utf-8')
        return SimpleNamespace(return_code=3, duration_seconds=0.01, output_tail='')

    monkeypatch.setattr(executor, 'run_managed', managed)
    detail = executor.run_cmd('pythonDeadCode', ['python', '-m', 'vulture'], tmp_path)
    assert detail.status == BLOCKED
    assert detail.reason == ''


def test_fail_owner_reason_is_structured(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def managed(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text(
            'GATE_RESULT status=FAIL reason=runtime-missing check=owner', encoding='utf-8'
        )
        return SimpleNamespace(return_code=2, duration_seconds=0.01, output_tail='')

    monkeypatch.setattr(executor, 'run_managed', managed)
    detail = executor.run_cmd('owner', ['tool'], tmp_path)
    assert detail.status == FAIL
    assert detail.reason == 'runtime-missing'


def test_conflicting_owner_marker_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def managed(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text(
            'GATE_RESULT status=FAIL reason=runtime-missing check=owner', encoding='utf-8'
        )
        return SimpleNamespace(return_code=0, duration_seconds=0.01, output_tail='')

    monkeypatch.setattr(executor, 'run_managed', managed)
    detail = executor.run_cmd('owner', ['tool'], tmp_path)
    assert detail.status == FAIL
    assert detail.reason == 'outcome-unknown'


def test_missing_command_is_fail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: None)
    assert executor.run_cmd('missing', ['missing'], tmp_path).status == FAIL


@pytest.mark.contract_case('HOOK-HARNESS-008')
def test_pytest_skip_is_fail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def managed(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text('1 skipped', encoding='utf-8')
        return SimpleNamespace(return_code=0, duration_seconds=0.01, output_tail='')

    monkeypatch.setattr(executor, 'run_managed', managed)
    detail = executor.run_cmd('pytest', ['python3', '-m', 'pytest'], tmp_path)
    assert detail.status == FAIL
    assert detail.reason == 'execution-skipped'


def test_run_cmd_uses_managed_runner_without_timeout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/npm')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))
    captured: list[dict] = []

    def managed(_cmd, **kwargs):
        captured.append(kwargs)
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text('ok', encoding='utf-8')
        return SimpleNamespace(
            return_code=0, duration_seconds=0.01, output_tail='', exit_reason='EXITED'
        )

    monkeypatch.setattr(executor, 'run_managed', managed)
    executor.run_cmd('browser', ['npm', '--prefix', 'tests/playwright', 'test', '--'], tmp_path)
    assert 'timeout' not in captured[0]


def test_negative_return_code_is_process_signaled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def managed(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text('terminated', encoding='utf-8')
        return SimpleNamespace(
            return_code=-15, duration_seconds=0.01, output_tail='', exit_reason='SIGNAL'
        )

    monkeypatch.setattr(executor, 'run_managed', managed)
    detail = executor.run_cmd('owner', ['tool'], tmp_path)
    assert detail.status == FAIL
    assert detail.reason == 'process-signaled'


def test_gradle_no_source_is_not_complete() -> None:
    assert executor._gradle_gate_outcome({':check': 'NO-SOURCE'}, (':check',)) == 'NOT_EXECUTED'


def test_gradle_skip_dominates_blocked_for_multi_task_defense() -> None:
    """即使未来误配多 task，任何未执行项仍必须让 leaf 归为未完成。"""

    assert (
        executor._gradle_gate_outcome(
            {
                ':first': 'BLOCKED',
                ':second': 'SKIPPED',
            },
            ('first', 'second'),
        )
        == 'NOT_EXECUTED'
    )


def test_gradle_owner_reason_is_parsed_before_output_truncation() -> None:
    output = 'GATE_TASK_RESULT task=:reuseStandardCpd status=FAIL reason=input-unavailable\n' + (
        'detail\n' * 1000
    )
    assert executor._gradle_task_failure_reasons(output) == {
        ':reuseStandardCpd': 'input-unavailable'
    }


def test_execute_plan_propagates_mode_and_timing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor, 'command_for_step', lambda *_args: ['/bin/true'])
    monkeypatch.setattr(
        executor,
        'run_cmd',
        lambda *args, **_kwargs: GateDetail(name=args[0], status=PASS, durationMs=10),
    )
    execution = executor.build_execution_plan(_single('pythonHarnessTests'), tmp_path)
    detail = executor.execute_plan(execution, tmp_path)[0]
    assert detail.mode == 'incremental'
    assert detail.targetSeconds
    assert detail.timingState == 'WITHIN_TARGET'


def test_executor_rejects_reserved_gate_request_override(tmp_path: Path) -> None:
    execution = executor.build_execution_plan(_single('pythonHarnessTests'), tmp_path)

    with pytest.raises(ValueError, match='cannot be overridden'):
        executor.execute_plan(
            execution,
            tmp_path,
            environment_overrides={'QUALITY_EXECUTION_MODE': 'full'},
        )


def test_scan_prerequisite_and_pytest_sum_duration_without_budget(
    tmp_path: Path, monkeypatch
) -> None:
    execution = executor.build_execution_plan(_single('scanScriptSmoke'), tmp_path)
    observed: list[str] = []

    def fake_execute(group, _root):
        observed.append(group.kind)
        if group.kind == 'scan-prerequisite':
            return GateDetail(
                name=group.step_name,
                status=PASS,
                durationMs=1_000,
                taskOutcomes={':java:app-cli:installDist': 'EXECUTED'},
            )
        return GateDetail(name=group.step_name, status=PASS, durationMs=2_000)

    monkeypatch.setattr(executor, '_execute_group', fake_execute)
    detail = executor.execute_plan(execution, tmp_path)[0]
    assert observed == ['scan-prerequisite', 'scan-smoke']
    assert detail.durationMs == 3_000
    assert detail.leafResults[0]['durationMs'] == 3_000


def test_composite_executes_all_leaves_and_fail_dominates(tmp_path: Path, monkeypatch) -> None:
    execution = executor.build_execution_plan(_single('scriptSourceStandard'), tmp_path)
    statuses = iter((BLOCKED, FAIL, PASS, PASS, PASS, PASS))
    observed: list[str] = []

    def fake_execute(group, _root):
        observed.append(group.step_name)
        status = next(statuses)
        return GateDetail(
            name=group.step_name,
            status=status,
            durationMs=10,
            reason='runtime-missing' if status == FAIL else '',
            output=f'{group.step_name} diagnostic',
        )

    monkeypatch.setattr(executor, '_execute_group', fake_execute)
    detail = executor.execute_plan(execution, tmp_path)[0]
    assert observed == [
        'pythonFormat',
        'pythonLint',
        'bashSyntax',
        'pythonDependencyDeclarations',
        'pythonSourceSecurity',
        'pythonDeadCode',
    ]
    assert detail.status == FAIL
    assert [leaf['status'] for leaf in detail.leafResults] == [
        BLOCKED,
        FAIL,
        PASS,
        PASS,
        PASS,
        PASS,
    ]


def test_java_rule_composite_runs_later_leaf_and_skip_makes_gate_fail(
    tmp_path: Path, monkeypatch
) -> None:
    """Gradle leaf 必须独立执行；前项阻断后，后项未执行仍归为 FAIL。"""

    execution = executor.build_execution_plan(_single('webSourcePolicy'), tmp_path)
    observed: list[str] = []

    def fake_execute(group, _root):
        observed.append(group.step_name)
        if group.step_name == 'rawInnerhtml':
            return GateDetail(
                name=group.step_name,
                status=BLOCKED,
                durationMs=10,
                taskOutcomes={':java:tests:quality-gates:runJavaQualityGates': 'BLOCKED'},
            )
        if group.step_name == 'layoutInlineStyle':
            return GateDetail(
                name=group.step_name,
                status=PASS,
                durationMs=10,
                taskOutcomes={':java:tests:quality-gates:runJavaQualityGates': 'SKIPPED'},
            )
        return GateDetail(
            name=group.step_name,
            status=PASS,
            durationMs=10,
            taskOutcomes={':java:tests:quality-gates:runJavaQualityGates': 'EXECUTED'},
        )

    monkeypatch.setattr(executor, '_execute_group', fake_execute)

    detail = executor.execute_plan(execution, tmp_path)[0]

    assert observed == [
        'rawInnerhtml',
        'layoutInlineStyle',
        'templateContract',
        'staticCssContract',
        'cssOwnership',
    ]
    assert [leaf['status'] for leaf in detail.leafResults] == [
        BLOCKED,
        FAIL,
        PASS,
        PASS,
        PASS,
    ]
    assert detail.leafResults[1]['reason'] == 'execution-skipped'
    assert detail.status == FAIL


def test_java_rule_without_owner_marker_is_execution_fail(tmp_path: Path, monkeypatch) -> None:
    """Java rule 裸 Gradle FAILED 表示 owner 未完成，不能误报为业务 BLOCKED。"""

    execution = executor.build_execution_plan(_single('webSourcePolicy'), tmp_path)
    monkeypatch.setattr(
        executor,
        '_execute_group',
        lambda group, _root: GateDetail(
            name=group.step_name,
            status=BLOCKED,
            durationMs=10,
            output='Input file does not exist',
            taskOutcomes={':java:tests:quality-gates:runJavaQualityGates': 'FAILED'},
        ),
    )

    detail = executor.execute_plan(execution, tmp_path)[0]

    assert detail.status == FAIL
    assert detail.reason == 'outcome-unknown'
    assert all(leaf['status'] == FAIL for leaf in detail.leafResults)


def test_composite_blocked_dominates_pass_and_unknown_duration(tmp_path: Path, monkeypatch) -> None:
    execution = executor.build_execution_plan(_single('scriptSourceStandard'), tmp_path)
    outcomes = iter(((PASS, 10), (BLOCKED, None), (PASS, 20), (PASS, 10), (PASS, 10), (PASS, 10)))

    def fake_execute(group, _root):
        status, duration = next(outcomes)
        return GateDetail(name=group.step_name, status=status, durationMs=duration)

    monkeypatch.setattr(executor, '_execute_group', fake_execute)
    detail = executor.execute_plan(execution, tmp_path)[0]
    assert detail.status == BLOCKED
    assert detail.durationMs is None
    assert detail.timingState == 'UNKNOWN'


def test_over_target_does_not_change_pass(tmp_path: Path, monkeypatch) -> None:
    execution = executor.build_execution_plan(_single('pythonHarnessTests'), tmp_path)
    target_ms = execution.gates[0].target_seconds * 1000
    monkeypatch.setattr(
        executor,
        '_execute_group',
        lambda group, _root: GateDetail(
            name=group.step_name, status=PASS, durationMs=target_ms + 1
        ),
    )
    detail = executor.execute_plan(execution, tmp_path)[0]
    assert detail.status == PASS
    assert detail.timingState == 'OVER_TARGET'
