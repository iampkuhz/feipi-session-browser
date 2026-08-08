"""独立 Gate health 入口的 fixed-full、归约与中断 contract。"""

import json
from pathlib import Path

from scripts.gates import cli, health
from scripts.gates.model import (
    ExecutionMode,
    GateSpec,
    GateTrigger,
    RunKind,
    RunSpec,
    RunStep,
    RunTargets,
    TriggerMode,
)
from scripts.gates.report import BLOCKED, FAIL, PASS, GateDetail


def _gate(*, target: int = 2) -> GateSpec:
    return GateSpec(
        name='sampleGate',
        description='sample gate for health contract',
        trigger=GateTrigger(TriggerMode.ALWAYS),
        targets=(),
        run=RunSpec(
            RunTargets(incremental=1, full=target),
            (RunStep('sampleLeaf', RunKind.COMMAND, argv=('true',)),),
        ),
    )


def _detail(*, status: str = PASS, duration: int | None = 100) -> GateDetail:
    return GateDetail(
        name='sampleGate',
        status=status,
        durationMs=duration,
        timingState='WITHIN_TARGET',
        leafResults=[
            {
                'name': 'sampleLeaf',
                'status': status,
                'durationMs': duration,
                'reason': '',
            }
        ],
    )


def _install_run(
    monkeypatch, gate: GateSpec, detail: GateDetail, *, doctor_status: str = PASS
) -> list[object]:
    plans: list[object] = []
    monkeypatch.setattr(health, 'GATES', (gate,))
    monkeypatch.setattr(health.executor, 'command_for_step', lambda *_args: ['true'])
    monkeypatch.setattr(
        health.executor,
        'run_cmd',
        lambda *_args, **_kwargs: GateDetail(
            name='healthDoctor', status=doctor_status, durationMs=10
        ),
    )

    def build(plan, *_args, **_kwargs):
        plans.append(plan)
        return object()

    monkeypatch.setattr(health.executor, 'build_execution_plan', build)
    monkeypatch.setattr(health.executor, 'execute_plan', lambda *_args, **_kwargs: (detail,))
    return plans


def test_health_is_fixed_full_and_doctor_blocked_still_runs_gate(
    tmp_path: Path, monkeypatch
) -> None:
    gate = _gate()
    plans = _install_run(monkeypatch, gate, _detail(), doctor_status=BLOCKED)

    result = health.run_health(repo_root=tmp_path, out_dir=tmp_path / 'health')

    assert result.status == BLOCKED
    assert len(plans) == 1
    assert plans[0].mode is ExecutionMode.FULL
    assert plans[0].changed_files == ()
    payload = json.loads(result.artifact_path.read_text(encoding='utf-8'))
    assert payload['kind'] == 'gate-health'
    assert payload['mode'] == 'full'
    assert result.artifact_path.name == 'gate-health-summary.full.json'


def test_health_over_full_target_is_blocked_without_changing_gate_status(
    tmp_path: Path, monkeypatch
) -> None:
    gate = _gate(target=1)
    detail = _detail(duration=1_001)
    _install_run(monkeypatch, gate, detail)

    result = health.run_health(repo_root=tmp_path, out_dir=tmp_path / 'health')
    payload = json.loads(result.artifact_path.read_text(encoding='utf-8'))

    assert result.status == BLOCKED
    assert result.gates[0].status == PASS
    assert payload['gateResults'][0]['overTarget'] is True


def test_health_unknown_duration_is_fail(tmp_path: Path, monkeypatch) -> None:
    gate = _gate()
    _install_run(monkeypatch, gate, _detail(duration=None))

    result = health.run_health(repo_root=tmp_path, out_dir=tmp_path / 'health')

    assert result.status == FAIL


def test_health_static_capability_failure_is_fail_but_recipe_still_runs(
    tmp_path: Path, monkeypatch
) -> None:
    gate = _gate()
    plans = _install_run(monkeypatch, gate, _detail())
    monkeypatch.setattr(health.executor, 'command_for_step', lambda *_args: [])

    result = health.run_health(repo_root=tmp_path, out_dir=tmp_path / 'health')

    assert result.status == FAIL
    assert len(plans) == 1


def test_health_cli_rejects_daily_gate_arguments_without_running(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        health,
        'run_health',
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError('must not run')),
    )

    assert cli.main(['health', '--mode', 'full']) == 2
    assert 'reason=input-unavailable' in capsys.readouterr().err


def test_health_interrupt_returns_130_without_success_artifact(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        health,
        'run_health',
        lambda **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert cli.main(['health']) == 130
    assert 'reason=interrupted' in capsys.readouterr().err
    assert not (tmp_path / 'tmp' / 'quality-health').exists()


def test_health_cli_preserves_blocked_and_fail_exit_codes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    doctor = GateDetail(name='healthDoctor', status=PASS, durationMs=1)
    for status, expected in ((BLOCKED, 1), (FAIL, 2)):
        result = health.HealthResult(status, tmp_path / 'health.json', doctor, ())
        monkeypatch.setattr(
            health,
            'run_health',
            lambda _result=result, **_kwargs: _result,
        )
        assert cli.main(['health']) == expected


def test_health_cli_unexpected_error_is_fail(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        health,
        'run_health',
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('broken health')),
    )

    assert cli.main(['health']) == 2
    assert 'reason=execution-unavailable' in capsys.readouterr().err


def test_daily_cli_interrupt_returns_130(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        'get_changed_files',
        lambda *_args: ['scripts/gates/cli.py'],
    )
    monkeypatch.setattr(
        cli,
        'run_service',
        lambda **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert cli.main([]) == 130
    assert 'reason=interrupted' in capsys.readouterr().err


def test_health_business_fail_is_fail(tmp_path: Path, monkeypatch) -> None:
    gate = _gate()
    _install_run(monkeypatch, gate, _detail(status=FAIL))

    assert health.run_health(repo_root=tmp_path, out_dir=tmp_path / 'health').status == FAIL
