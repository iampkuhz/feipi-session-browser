"""验证统一 Gate CLI 的 not-triggered 与 fail-closed 状态语义。"""

from scripts.gates import cli
from scripts.gates.report import NOT_PASS, GateDetail


def test_not_triggered_is_empty_plan_not_skipped() -> None:
    plan = cli.create_plan([], mode='incremental')
    assert plan.logical_gates == ()


def test_skipped_status_is_external_not_pass() -> None:
    assert cli._overall_status((GateDetail(name='x', status='SKIPPED'),)) == NOT_PASS


def test_empty_execution_is_external_not_pass() -> None:
    assert cli._overall_status(()) == NOT_PASS


def test_session_detail_is_not_silently_excluded() -> None:
    plan = cli.create_plan(
        ['java/web/src/main/resources/templates/session-detail.html'],
        mode='incremental',
    )
    names = {gate.name for gate in plan.gates}
    assert {'webResourceTests', 'browserLayout', 'browserInteraction'} <= names
