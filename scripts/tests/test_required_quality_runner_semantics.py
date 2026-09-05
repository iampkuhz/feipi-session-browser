"""验证统一 GatePlan 的 NOT_TRIGGERED 与 fail-closed 状态语义。"""

from scripts.gates.execution import ExecutionStatus
from scripts.gates.planning import ChangeSnapshot, compile_gate_plan


def test_not_triggered_is_empty_plan_not_skipped() -> None:
    plan = compile_gate_plan(ChangeSnapshot('test', 'head', None, (), 'fingerprint'))
    assert plan.logical_gates == ()
    assert plan.not_triggered


def test_execution_status_has_no_skipped_member() -> None:
    assert {status.value for status in ExecutionStatus} == {'PASS', 'BLOCKED', 'FAIL'}


def test_session_detail_is_not_silently_excluded() -> None:
    path = 'java/web/src/main/resources/templates/session-detail.html'
    plan = compile_gate_plan(ChangeSnapshot('test', 'head', None, (path,), 'fingerprint'))
    names = {gate.name for gate in plan.gates}
    assert {'webResourceContracts', 'browserVisualTests', 'browserBehaviorTests'} <= names
