"""Single-recipe GatePlan 到 deterministic ExecutionPlan 的映射 contract。"""

from dataclasses import asdict
from pathlib import Path

import pytest
from scripts.gates import executor
from scripts.gates.catalog import gate_by_name
from scripts.gates.model import ExecutionMode, GatePlan

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _stable_project_python(monkeypatch) -> None:
    """执行计划单测不探测工作区 Python 环境。"""

    monkeypatch.setattr(executor, '_project_python', lambda _root, dev=False: '/tmp/python')


def _plan(mode: ExecutionMode, *names: str) -> GatePlan:
    changed = ('scripts/gates/executor.py',) if mode is ExecutionMode.INCREMENTAL else ()
    return GatePlan(mode, changed, tuple(gate_by_name(name) for name in names))


def test_plan_fingerprint_includes_mode_but_recipe_is_identical() -> None:
    inc = executor.build_execution_plan(
        _plan(ExecutionMode.INCREMENTAL, 'pythonHarnessTests'), ROOT
    )
    full = executor.build_execution_plan(_plan(ExecutionMode.FULL, 'pythonHarnessTests'), ROOT)
    assert inc.fingerprint != full.fingerprint
    assert inc.groups[0].command == full.groups[0].command
    assert inc.gates[0].target_seconds != full.gates[0].target_seconds


def test_single_and_composite_gate_group_mapping() -> None:
    execution = executor.build_execution_plan(
        _plan(ExecutionMode.INCREMENTAL, 'scriptSourceStandard', 'javaCheck'), ROOT
    )
    composite, single = execution.gates
    assert len(composite.group_ids) == 6
    assert [group.step_name for group in execution.groups[:6]] == [
        'pythonFormat',
        'pythonLint',
        'bashSyntax',
        'pythonDependencyDeclarations',
        'pythonSourceSecurity',
        'pythonDeadCode',
    ]
    assert len(single.group_ids) == 1
    assert execution.groups[6].gate_name == 'javaCheck'


def test_execution_plan_contains_no_timeout_field() -> None:
    execution = executor.build_execution_plan(
        _plan(ExecutionMode.INCREMENTAL, 'javaCheck', 'webResourceTests'), ROOT
    )
    assert all('timeout' not in key.lower() for gate in execution.gates for key in asdict(gate))
    assert all('timeout' not in key.lower() for group in execution.groups for key in asdict(group))


def test_incremental_request_reaches_every_group() -> None:
    execution = executor.build_execution_plan(
        _plan(ExecutionMode.INCREMENTAL, 'scriptSourceStandard', 'javaCheck'), ROOT
    )
    for group in execution.groups:
        environment = dict(group.environment)
        assert environment['QUALITY_EXECUTION_MODE'] == 'incremental'
        assert environment['QUALITY_CHANGED_FILES'] == '["scripts/gates/executor.py"]'


def test_full_request_omits_changed_files() -> None:
    execution = executor.build_execution_plan(_plan(ExecutionMode.FULL, 'pythonHarnessTests'), ROOT)
    assert 'QUALITY_CHANGED_FILES' not in dict(execution.groups[0].environment)


def test_scan_prerequisite_precedes_pytest_without_deadline() -> None:
    execution = executor.build_execution_plan(
        _plan(ExecutionMode.INCREMENTAL, 'scanScriptSmoke'), ROOT
    )
    assert [group.kind for group in execution.groups] == ['scan-prerequisite', 'scan-smoke']
    assert execution.gates[0].group_ids == tuple(group.group_id for group in execution.groups)


def test_execution_plan_is_stable() -> None:
    plan = _plan(ExecutionMode.INCREMENTAL, 'scriptSourceStandard', 'javaCheck')
    assert executor.build_execution_plan(plan, ROOT) == executor.build_execution_plan(plan, ROOT)
