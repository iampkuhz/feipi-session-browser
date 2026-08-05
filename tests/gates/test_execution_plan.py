"""双模式 GatePlan 到不可变 ExecutionPlan 的映射 contract。"""

from pathlib import Path

from scripts.gates import executor
from scripts.gates.catalog import gate_by_name
from scripts.gates.model import ExecutionMode, GatePlan

ROOT = Path(__file__).resolve().parents[2]


def _plan(mode: ExecutionMode, *names: str) -> GatePlan:
    changed = ('scripts/gates/executor.py',) if mode is ExecutionMode.INCREMENTAL else ()
    return GatePlan(mode, changed, tuple(gate_by_name(name) for name in names))


def test_plan_fingerprint_includes_mode() -> None:
    inc = executor.build_execution_plan(_plan(ExecutionMode.INCREMENTAL, 'pythonLint'), ROOT)
    full = executor.build_execution_plan(_plan(ExecutionMode.FULL, 'pythonLint'), ROOT)
    assert inc.fingerprint != full.fingerprint


def test_profiles_choose_independent_timing() -> None:
    inc = executor.build_execution_plan(_plan(ExecutionMode.INCREMENTAL, 'pythonLint'), ROOT)
    full = executor.build_execution_plan(_plan(ExecutionMode.FULL, 'pythonLint'), ROOT)
    assert inc.groups[0].timeout_seconds == 60
    assert full.groups[0].timeout_seconds == 120


def test_gradle_gates_keep_independent_profile_timeouts() -> None:
    execution = executor.build_execution_plan(
        _plan(ExecutionMode.INCREMENTAL, 'javaCheck', 'webResourceTests'), ROOT
    )
    gradle = [group for group in execution.groups if group.kind == 'gradle']
    assert [group.gate_names for group in gradle] == [('javaCheck',), ('webResourceTests',)]
    assert [group.timeout_seconds for group in gradle] == [900, 300]


def test_incremental_request_reaches_every_group() -> None:
    execution = executor.build_execution_plan(
        _plan(ExecutionMode.INCREMENTAL, 'pythonLint', 'javaCheck'), ROOT
    )
    for group in execution.groups:
        environment = dict(group.environment)
        assert environment['QUALITY_EXECUTION_MODE'] == 'incremental'
        assert environment['QUALITY_CHANGED_FILES'] == '["scripts/gates/executor.py"]'


def test_full_request_omits_changed_files() -> None:
    execution = executor.build_execution_plan(_plan(ExecutionMode.FULL, 'pythonLint'), ROOT)
    assert 'QUALITY_CHANGED_FILES' not in dict(execution.groups[0].environment)


def test_scan_prerequisite_precedes_pytest_group() -> None:
    execution = executor.build_execution_plan(
        _plan(ExecutionMode.INCREMENTAL, 'scanScriptSmoke'), ROOT
    )
    assert [group.kind for group in execution.groups] == ['scan-prerequisite', 'scan-smoke']
    assert [group.timeout_seconds for group in execution.groups] == [300, 300]

    full = executor.build_execution_plan(_plan(ExecutionMode.FULL, 'scanScriptSmoke'), ROOT)
    assert [group.timeout_seconds for group in full.groups] == [600, 600]


def test_execution_plan_is_stable() -> None:
    plan = _plan(ExecutionMode.INCREMENTAL, 'pythonLint', 'javaCheck')
    assert executor.build_execution_plan(plan, ROOT) == executor.build_execution_plan(plan, ROOT)
