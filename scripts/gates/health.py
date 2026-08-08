"""提供显式、全量且无自动 deadline 的 Gate 健康检查。

本模块负责静态能力检查、Harness doctor、全部 Gate 执行及 full 时效目标归约。本模块不负责日常 Gate
选择，也不设置运行期限；它只由 ``scripts/gates/cli.py health`` 显式调用。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.gates import executor, report
from scripts.gates.catalog import GATES
from scripts.gates.model import ExecutionMode, GatePlan, GateSpec, RunStep


@dataclass(frozen=True, slots=True)
class HealthResult:
    """保存一次独立 health 运行的状态和 artifact。"""

    status: str
    artifact_path: Path
    doctor: report.GateDetail
    gates: tuple[report.GateDetail, ...]


def _executable_available(command: list[str]) -> bool:
    if not command:
        return False
    executable = command[0]
    if '/' not in executable:
        return shutil.which(executable) is not None
    path = Path(executable)
    return path.is_file() and os.access(path, os.X_OK)


def _static_check(gate: GateSpec, step: RunStep, repo_root: Path) -> dict[str, Any]:
    """检查一个 leaf 的路径、runtime、adapter 与 executable，不运行 recipe。"""
    problems = [
        f'missing required path: {path}'
        for path in step.required_paths
        if not (repo_root / path).exists()
    ]
    command: list[str] = []
    try:
        command = executor.command_for_step(step, repo_root)
    except (Exception, SystemExit) as exc:
        problems.append(f'adapter unavailable: {type(exc).__name__}: {exc}')
    if not command:
        problems.append('adapter produced no command')
    elif not _executable_available(command):
        problems.append(f'executable unavailable: {command[0]}')
    return {
        'gate': gate.name,
        'leaf': step.name,
        'kind': step.kind.value,
        'runtime': step.runtime,
        'requiredPaths': list(step.required_paths),
        'command': command,
        'status': report.FAIL if problems else report.PASS,
        'problems': problems,
    }


def _failed_gate(gate: GateSpec, exc: BaseException) -> report.GateDetail:
    """把单个 Gate 无法完成的异常转换为稳定 FAIL 明细。"""

    return report.GateDetail(
        name=gate.name,
        status=report.FAIL,
        output=f'health could not complete gate: {type(exc).__name__}: {exc}',
        executionState='CAPABILITY_FAILED',
        reason='runtime-missing',
    )


def _execute_gate(gate: GateSpec, repo_root: Path) -> report.GateDetail:
    """通过正常 executor 以 full owner 范围运行一个逻辑 Gate。"""
    gate_plan = GatePlan(ExecutionMode.FULL, (), (gate,))
    try:
        execution_plan = executor.build_execution_plan(gate_plan, repo_root)
        details = executor.execute_plan(execution_plan, repo_root)
    except (Exception, SystemExit) as exc:
        return _failed_gate(gate, exc)
    if len(details) != 1 or details[0].name != gate.name:
        return report.GateDetail(
            name=gate.name,
            status=report.FAIL,
            output='health executor returned a missing or mismatched logical Gate result',
            executionState='FAILED',
            reason='outcome-unknown',
        )
    return details[0]


def _result_complete(gate: GateSpec, detail: report.GateDetail) -> bool:
    if detail.status not in {report.PASS, report.BLOCKED, report.FAIL}:
        return False
    if not isinstance(detail.durationMs, int) or detail.durationMs < 0:
        return False
    leaves = detail.leafResults
    expected = [step.name for step in gate.run.steps]
    if [leaf.get('name') for leaf in leaves] != expected:
        return False
    return all(
        leaf.get('status') in {report.PASS, report.BLOCKED, report.FAIL}
        and isinstance(leaf.get('durationMs'), int)
        and leaf['durationMs'] >= 0
        for leaf in leaves
    )


def _health_status(
    static_checks: list[dict[str, Any]],
    doctor: report.GateDetail,
    gates: tuple[report.GateDetail, ...],
) -> str:
    """FAIL 表示诊断未完成；完整诊断发现业务或性能问题则 BLOCKED。"""
    by_name = {detail.name: detail for detail in gates}
    incomplete = (
        any(item['status'] != report.PASS for item in static_checks)
        or not isinstance(doctor.durationMs, int)
        or doctor.durationMs < 0
        or doctor.status not in {report.PASS, report.BLOCKED}
        or set(by_name) != {gate.name for gate in GATES}
        or any(
            gate.name not in by_name or not _result_complete(gate, by_name[gate.name])
            for gate in GATES
        )
        or any(detail.status == report.FAIL for detail in gates)
    )
    if incomplete:
        return report.FAIL
    blocked = doctor.status == report.BLOCKED or any(
        detail.status == report.BLOCKED or detail.durationMs > gate.run.target_seconds.full * 1000
        for gate, detail in ((gate, by_name[gate.name]) for gate in GATES)
    )
    return report.BLOCKED if blocked else report.PASS


def _write_artifact(
    out_dir: Path,
    change_id: str,
    status: str,
    started_at: str,
    static_checks: list[dict[str, Any]],
    doctor: report.GateDetail,
    gates: tuple[report.GateDetail, ...],
) -> Path:
    selected = out_dir / change_id
    selected.mkdir(parents=True, exist_ok=True)
    path = selected / 'gate-health-summary.full.json'
    gate_by_name = {detail.name: detail for detail in gates}
    payload = {
        'schemaVersion': 1,
        'kind': 'gate-health',
        'status': status,
        'mode': ExecutionMode.FULL.value,
        'changeId': change_id,
        'startedAt': started_at,
        'finishedAt': report.utc_now(),
        'staticChecks': static_checks,
        'doctor': asdict(doctor),
        'gateResults': [
            {
                **asdict(gate_by_name[gate.name]),
                'fullTargetSeconds': gate.run.target_seconds.full,
                'overTarget': (
                    isinstance(gate_by_name[gate.name].durationMs, int)
                    and gate_by_name[gate.name].durationMs > gate.run.target_seconds.full * 1000
                ),
            }
            for gate in GATES
            if gate.name in gate_by_name
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def run_health(
    *, repo_root: Path, change_id: str = 'manual-run', out_dir: Path | None = None
) -> HealthResult:
    """运行 doctor 和全部逻辑 Gate；本函数从不设置或传递 timeout。"""
    started_at = report.utc_now()
    static_checks = [
        _static_check(gate, step, repo_root) for gate in GATES for step in gate.run.steps
    ]
    doctor = executor.run_cmd('healthDoctor', ['bash', 'scripts/harness/doctor.sh'], repo_root)
    gates = tuple(_execute_gate(gate, repo_root) for gate in GATES)
    status = _health_status(static_checks, doctor, gates)
    artifact = _write_artifact(
        out_dir or repo_root / 'tmp' / 'quality-health',
        change_id,
        status,
        started_at,
        static_checks,
        doctor,
        gates,
    )
    return HealthResult(status, artifact, doctor, gates)


def format_health_result(result: HealthResult) -> str:
    """生成供维护者阅读和脚本识别的单行 health 汇总。"""

    passed = sum(detail.status == report.PASS for detail in result.gates)
    targets = {gate.name: gate.run.target_seconds.full for gate in GATES}
    over_target = sum(
        isinstance(detail.durationMs, int)
        and detail.name in targets
        and detail.durationMs > targets[detail.name] * 1000
        for detail in result.gates
    )
    return (
        f'GATE_HEALTH_RESULT status={result.status} mode=full '
        f'gates={passed}/{len(result.gates)} over_target={over_target} '
        f'artifact={result.artifact_path}'
    )
