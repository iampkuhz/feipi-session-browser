"""验证统一 Gate CLI 的 not-triggered 与 fail-closed 状态语义。"""

from scripts.gates import cli
from scripts.gates.report import BLOCKED, FAIL, GateDetail


def test_not_triggered_is_empty_plan_not_skipped() -> None:
    plan = cli.create_plan([], tier='required', targets=None, explicit_changed_files=True)
    assert plan.logical_gates == ()


def test_skipped_status_fails_required_service() -> None:
    assert cli._overall_status((GateDetail(name='x', status='SKIPPED'),)) == FAIL


def test_empty_execution_is_blocked() -> None:
    assert cli._overall_status(()) == BLOCKED


def test_session_detail_is_not_silently_excluded() -> None:
    plan = cli.create_plan(
        ['java/web/src/main/resources/templates/session-detail.html'],
        tier='required',
        targets=None,
        explicit_changed_files=True,
    )
    assert 'session-detail' in plan.effective_targets
