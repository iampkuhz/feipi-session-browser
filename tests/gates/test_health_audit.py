"""Maintenance health audit 的公开契约与状态归约。"""

import ast
from pathlib import Path
from types import SimpleNamespace

from scripts.gates.execution import ExecutionStatus, GateResult, InvocationResult
from scripts.gates.maintenance import health_audit


def _invocation(status: ExecutionStatus, reason: str = '') -> InvocationResult:
    return InvocationResult(
        'gate-health:harnessDoctor:run',
        'gate-health',
        'harnessDoctor',
        status,
        reason,
        0 if status is ExecutionStatus.PASS else 1,
        0.01,
        '/tmp/doctor.log',
        '',
    )


def _gate(
    status: ExecutionStatus = ExecutionStatus.PASS,
    *,
    timing: str = 'WITHIN_TARGET',
    reason: str = '',
) -> GateResult:
    return GateResult(
        'gateFrameworkTests',
        status,
        reason,
        0.1,
        10,
        timing,
        (),
        'python3 scripts/gates/cli.py run --mode full --gate gateFrameworkTests',
    )


def _install(
    monkeypatch,
    tmp_path: Path,
    *,
    doctor: InvocationResult,
    gates: tuple[GateResult, ...],
) -> tuple[list[dict], object]:
    plan = object()
    receipt = SimpleNamespace(summary_path=tmp_path / 'summary.json')
    calls: list[dict] = []
    monkeypatch.setattr(health_audit, 'validate_gate_catalog', lambda _catalog: None)
    monkeypatch.setattr(health_audit, '_full_plan', lambda _root: plan)
    monkeypatch.setattr(health_audit, 'supervise_process', lambda *_args, **kwargs: kwargs)
    monkeypatch.setattr(health_audit, 'classify_owner_outcome', lambda *_args: doctor)

    def run(selected_plan, root, **kwargs):
        calls.append({'plan': selected_plan, 'root': root, **kwargs})
        return gates

    monkeypatch.setattr(health_audit, 'orchestrate_gate_run', run)
    monkeypatch.setattr(
        health_audit,
        'store_run_receipt',
        lambda selected_plan, _selected_gates, **_kwargs: receipt,
    )
    return calls, receipt


def test_doctor_blocked_still_runs_full_gate_plan(tmp_path: Path, monkeypatch) -> None:
    calls, receipt = _install(
        monkeypatch,
        tmp_path,
        doctor=_invocation(ExecutionStatus.BLOCKED, 'verification-failed'),
        gates=(_gate(),),
    )

    result = health_audit.audit_gate_health(repo_root=tmp_path)

    assert result.status is ExecutionStatus.BLOCKED
    assert result.reason == 'verification-failed'
    assert len(calls) == 1
    assert calls[0]['log_dir'].name == 'gates'
    assert 'timeout' not in calls[0]
    assert result.receipt is receipt


def test_over_target_is_health_blocked_without_reclassifying_gate(
    tmp_path: Path, monkeypatch
) -> None:
    _install(
        monkeypatch,
        tmp_path,
        doctor=_invocation(ExecutionStatus.PASS),
        gates=(_gate(timing='OVER_TARGET'),),
    )

    result = health_audit.audit_gate_health(repo_root=tmp_path)

    assert result.status is ExecutionStatus.BLOCKED
    assert result.gate_results[0].status is ExecutionStatus.PASS
    assert result.over_target_gates == ('gateFrameworkTests',)


def test_incomplete_gate_execution_is_health_fail(tmp_path: Path, monkeypatch) -> None:
    _install(
        monkeypatch,
        tmp_path,
        doctor=_invocation(ExecutionStatus.PASS),
        gates=(_gate(ExecutionStatus.FAIL, reason='runtime-missing'),),
    )

    result = health_audit.audit_gate_health(repo_root=tmp_path)

    assert result.status is ExecutionStatus.FAIL
    assert result.reason == 'runtime-missing'


def test_health_audit_imports_only_public_stage_contracts() -> None:
    source = Path(health_audit.__file__).read_text(encoding='utf-8')
    imports = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert not any(module.startswith('scripts.gates.catalog.') for module in imports)
    assert not any(module.startswith('scripts.gates.planning.') for module in imports)
    assert not any(module.startswith('scripts.gates.execution.') for module in imports)
    assert not any(module.startswith('scripts.gates.evidence.') for module in imports)
