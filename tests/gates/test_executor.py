"""Gate Executor 的 typed adapter、请求环境和 0/1/2 状态 contract。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.gates import executor
from scripts.gates.catalog import gate_by_name
from scripts.gates.model import ExecutionMode, GatePlan
from scripts.gates.report import BLOCKED, FAIL, PASS, GateDetail


def _single(gate: str, mode: ExecutionMode = ExecutionMode.INCREMENTAL) -> GatePlan:
    return GatePlan(
        mode,
        ('scripts/a.py',) if mode is ExecutionMode.INCREMENTAL else (),
        (gate_by_name(gate),),
        'gate',
        gate,
    )


def test_python_check_adapter_uses_profile_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor, '_project_python', lambda _root, dev=False: '/tmp/python')
    assert executor.command_for_gate(gate_by_name('noPythonPlaywrightSkips'), tmp_path) == [
        '/tmp/python',
        '-m',
        'scripts.checks',
        'repository.no-python-playwright-skips',
    ]


def test_gradle_and_java_rule_use_profile(tmp_path: Path) -> None:
    (tmp_path / 'gradlew').write_text('', encoding='utf-8')
    assert executor.command_for_gate(gate_by_name('webResourceTests'), tmp_path)[1:] == [
        ':java:web:test'
    ]
    assert executor.command_for_gate(gate_by_name('javaChineseComments'), tmp_path)[-1] == (
        '-PfeipiJavaQualityRules=java-comment-language'
    )


def test_playwright_adapter_uses_typed_tests_and_args(tmp_path: Path) -> None:
    command = executor.command_for_gate(gate_by_name('browserLayout'), tmp_path)
    assert command[:5] == ['npm', '--prefix', 'tests/playwright', 'test', '--']
    assert 'ui-contract.spec.ts' in command


def test_gate_request_environment_has_mode_and_incremental_files() -> None:
    env = executor.gate_request_environment(_single('pythonLint'))
    assert env == {
        'QUALITY_EXECUTION_MODE': 'incremental',
        'QUALITY_CHANGED_FILES': '["scripts/a.py"]',
    }
    assert executor.gate_request_environment(_single('pythonLint', ExecutionMode.FULL)) == {
        'QUALITY_EXECUTION_MODE': 'full'
    }


@pytest.mark.parametrize(('code', 'status'), [(0, PASS), (1, BLOCKED), (2, FAIL), (7, FAIL)])
def test_owner_exit_code_maps_to_three_states(
    code: int, status: str, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def bounded(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text('owner output', encoding='utf-8')
        return SimpleNamespace(
            return_code=code, duration_seconds=0.01, timed_out=False, output_tail=''
        )

    monkeypatch.setattr(executor, 'run_bounded', bounded)
    assert executor.run_cmd('owner', ['tool'], tmp_path).status == status


def test_vulture_findings_are_blocked_not_execution_failure(tmp_path: Path, monkeypatch) -> None:
    """Vulture 的退出码 3 表示发现死代码，不能误报为 Gate 执行失败。"""

    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/python')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def bounded(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text('dead code finding', encoding='utf-8')
        return SimpleNamespace(
            return_code=3, duration_seconds=0.01, timed_out=False, output_tail=''
        )

    monkeypatch.setattr(executor, 'run_bounded', bounded)
    detail = executor.run_cmd('pythonDeadCode', ['python', '-m', 'vulture'], tmp_path)
    assert detail.status == BLOCKED
    assert detail.reason == ''


def test_fail_owner_reason_is_structured(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def bounded(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text(
            'GATE_RESULT status=FAIL reason=runtime-missing check=owner', encoding='utf-8'
        )
        return SimpleNamespace(
            return_code=2, duration_seconds=0.01, timed_out=False, output_tail=''
        )

    monkeypatch.setattr(executor, 'run_bounded', bounded)
    detail = executor.run_cmd('owner', ['tool'], tmp_path)
    assert detail.status == FAIL
    assert detail.reason == 'runtime-missing'


def test_conflicting_owner_marker_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def bounded(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text(
            'GATE_RESULT status=FAIL reason=runtime-missing check=owner', encoding='utf-8'
        )
        return SimpleNamespace(
            return_code=0, duration_seconds=0.01, timed_out=False, output_tail=''
        )

    monkeypatch.setattr(executor, 'run_bounded', bounded)
    detail = executor.run_cmd('owner', ['tool'], tmp_path)
    assert detail.status == FAIL
    assert detail.reason == 'outcome-unknown'


def test_timeout_and_missing_command_are_fail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: None)
    assert executor.run_cmd('missing', ['missing'], tmp_path).status == FAIL


@pytest.mark.contract_case('HOOK-HARNESS-008')
def test_pytest_skip_is_fail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def bounded(_cmd, **kwargs):
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text('1 skipped', encoding='utf-8')
        return SimpleNamespace(
            return_code=0, duration_seconds=0.01, timed_out=False, output_tail=''
        )

    monkeypatch.setattr(executor, 'run_bounded', bounded)
    detail = executor.run_cmd('pytest', ['python3', '-m', 'pytest'], tmp_path)
    assert detail.status == FAIL
    assert detail.reason == 'execution-skipped'


def test_playwright_uses_profile_timeout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/npm')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))
    captured: list[int] = []

    def bounded(_cmd, **kwargs):
        captured.append(kwargs['timeout'])
        kwargs['log_path'].parent.mkdir(parents=True, exist_ok=True)
        kwargs['log_path'].write_text('ok', encoding='utf-8')
        return SimpleNamespace(
            return_code=0, duration_seconds=0.01, timed_out=False, output_tail=''
        )

    monkeypatch.setattr(executor, 'run_bounded', bounded)
    executor.run_cmd(
        'browser',
        ['npm', '--prefix', 'tests/playwright', 'test', '--'],
        tmp_path,
        timeout_seconds=900,
    )
    assert captured == [900]


def test_gradle_no_source_is_not_complete() -> None:
    assert executor._gradle_gate_outcome({':check': 'NO-SOURCE'}, (':check',)) == 'NOT_EXECUTED'


def test_gradle_owner_reason_is_parsed_before_output_truncation() -> None:
    output = 'GATE_TASK_RESULT task=:reuseStandardCpd status=FAIL reason=input-unavailable\n' + (
        'detail\n' * 1000
    )
    assert executor._gradle_task_failure_reasons(output) == {
        ':reuseStandardCpd': 'input-unavailable'
    }


def test_execute_plan_propagates_mode_and_timing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor, 'command_for_gate', lambda *_args: ['/bin/true'])
    monkeypatch.setattr(
        executor,
        'run_cmd',
        lambda *args, **_kwargs: GateDetail(name=args[0], status=PASS, durationMs=10),
    )
    execution = executor.build_execution_plan(_single('pythonLint'), tmp_path)
    detail = executor.execute_plan(execution, tmp_path)[0]
    assert detail.mode == 'incremental'
    assert detail.targetSeconds
    assert detail.timingState == 'WITHIN_TARGET'


def test_executor_rejects_reserved_gate_request_override(tmp_path: Path) -> None:
    execution = executor.build_execution_plan(_single('pythonLint'), tmp_path)

    with pytest.raises(ValueError, match='cannot be overridden'):
        executor.execute_plan(
            execution,
            tmp_path,
            environment_overrides={'QUALITY_EXECUTION_MODE': 'full'},
        )


def test_scan_prerequisite_and_pytest_share_one_profile_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    """scan Gate 的报告耗时包含 prerequisite，第二段只能使用剩余预算。"""
    execution = executor.build_execution_plan(_single('scanScriptSmoke'), tmp_path)
    observed_timeouts: list[int] = []

    def fake_execute(group, _root):
        observed_timeouts.append(group.timeout_seconds)
        if group.kind == 'scan-prerequisite':
            return GateDetail(
                name=group.group_id,
                status=PASS,
                durationMs=1_000,
                taskOutcomes={':java:app-cli:installDist': 'EXECUTED'},
            )
        return GateDetail(name=group.group_id, status=PASS, durationMs=2_000)

    monkeypatch.setattr(executor, '_execute_group', fake_execute)

    detail = executor.execute_plan(execution, tmp_path)[0]

    assert observed_timeouts == [300, 299]
    assert detail.durationMs == 3_000
    assert detail.targetSeconds == 90
    assert detail.timingState == 'WITHIN_TARGET'
