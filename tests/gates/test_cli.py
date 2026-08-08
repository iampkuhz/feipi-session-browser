"""Gate CLI 的双模式、selector、输入与 service contract。"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.gates import cli, executor, report
from scripts.gates.model import ExecutionMode
from scripts.gates.report import BLOCKED, FAIL, NOT_PASS, PASS, GateDetail


@pytest.fixture(autouse=True)
def _stable_project_python(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI 单元测试固定解释器，避免把环境探测时延混入编排契约。"""

    monkeypatch.setattr(executor, '_project_python', lambda *_args, **_kwargs: sys.executable)


def test_default_incremental_dry_run_uses_changed_trigger(capsys) -> None:
    rc = cli.main(['--dry-run', '--changed-files', '["scripts/gates/cli.py"]'])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload['mode'] == 'incremental'
    assert payload['selector'] is None
    assert 'pythonHarnessTests' in payload['gates']


def test_automatic_changed_files_include_current_git_dirty_paths(
    tmp_path: Path, monkeypatch
) -> None:
    """缺少客户端 evidence 时仍使用当前 checkout 的可信 Git dirty 路径。"""
    identity = SimpleNamespace(
        has_session=False,
        is_agent=False,
        raw_session_id='',
        raw_agent_id='',
    )
    monkeypatch.setattr(cli.support, 'identity_from_values', lambda: identity)
    monkeypatch.setattr(cli.support, 'session_log_dirs', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli.support, 'agent_log_dir', lambda *_args: tmp_path)
    monkeypatch.setattr(
        cli.support, 'read_recorded_changed_files_from_paths', lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(cli.support, 'read_files_since_base_commit', lambda *_args: [])
    monkeypatch.setattr(
        cli.support,
        'read_git_dirty_files',
        lambda _root: ['scripts/gates/cli.py', 'tests/gates/test_cli.py'],
    )

    assert cli.get_changed_files(None, tmp_path) == [
        'scripts/gates/cli.py',
        'tests/gates/test_cli.py',
    ]


@pytest.mark.parametrize('selector', ['--target', '--gate'])
def test_selector_combines_with_full_mode(selector: str, capsys) -> None:
    value = 'python-standard' if selector == '--target' else 'scriptSourceStandard'
    assert cli.main(['--mode', 'full', selector, value, '--dry-run']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['mode'] == 'full'
    assert payload['selector'] == selector.removeprefix('--')


def test_target_and_gate_are_mutually_exclusive(capsys) -> None:
    assert cli.main(['--target', 'harness', '--gate', 'scriptSourceStandard', '--dry-run']) == 2
    assert 'status=NOT_PASS detailStatus=FAIL' in capsys.readouterr().err


@pytest.mark.parametrize('arguments', [['--mode', 'quick'], ['--unknown-option']])
def test_argparse_errors_keep_external_not_pass(arguments: list[str], capsys) -> None:
    """choice 和未知参数错误也必须使用统一二态输出，而不是裸 argparse usage。"""
    assert cli.main(arguments) == 2
    error = capsys.readouterr().err
    assert 'status=NOT_PASS detailStatus=FAIL' in error
    assert 'reason=input-unavailable' in error


def test_full_rejects_changed_files(capsys) -> None:
    assert cli.main(['--mode', 'full', '--changed-files', '[]', '--dry-run']) == 2
    assert 'status=NOT_PASS detailStatus=FAIL' in capsys.readouterr().err


@pytest.mark.parametrize('raw', ['{}', '[1]', '["/tmp/x"]', '["../x"]', 'not-json'])
def test_invalid_changed_files_fail(raw: str, capsys) -> None:
    assert cli.main(['--changed-files', raw, '--dry-run']) == 2
    assert 'status=NOT_PASS detailStatus=FAIL' in capsys.readouterr().err


def test_explicit_empty_dirty_is_execution_fail(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.support, 'read_git_dirty_files', lambda _root: ['dirty.py'])
    assert cli.main(['--changed-files', '[]', '--dry-run']) == 2
    assert 'status=NOT_PASS detailStatus=FAIL' in capsys.readouterr().err


def test_explicit_empty_dirty_audit_exception_is_recorded(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """空输入例外必须显式说明，并在计划证据中保留理由。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.support, 'read_git_dirty_files', lambda _root: ['dirty.py'])

    assert (
        cli.main(
            [
                '--changed-files',
                '[]',
                '--allow-empty-changed-files-because',
                '只验证 always Gate',
                '--dry-run',
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload['inputAuditReason'] == '只验证 always Gate'


def test_empty_changed_files_audit_exception_cannot_hide_nonempty_input(
    capsys,
) -> None:
    """审计例外不能附着到普通增量输入上制造误导证据。"""
    assert (
        cli.main(
            [
                '--changed-files',
                '["scripts/a.py"]',
                '--allow-empty-changed-files-because',
                'irrelevant',
                '--dry-run',
            ]
        )
        == 2
    )
    assert 'status=NOT_PASS detailStatus=FAIL' in capsys.readouterr().err


def test_service_preserves_custom_environment_without_reinjecting_mode(
    tmp_path: Path, monkeypatch
) -> None:
    captured: list[dict[str, str]] = []

    def fake_execute(*_args, **kwargs):
        captured.append(kwargs['environment_overrides'])
        return (GateDetail(name='scriptSourceStandard', status=PASS),)

    monkeypatch.setattr(executor, 'execute_plan', fake_execute)
    result = cli.run_service(
        repo_root=tmp_path,
        changed_files=['scripts/a.py'],
        gate='scriptSourceStandard',
        out_dir=tmp_path / 'out',
        environment_overrides={'CUSTOM': 'value'},
    )
    assert result.status == PASS
    assert captured == [{'CUSTOM': 'value'}]


@pytest.mark.parametrize('reserved', ['QUALITY_EXECUTION_MODE', 'QUALITY_CHANGED_FILES'])
def test_service_rejects_gate_request_environment_override(tmp_path: Path, reserved: str) -> None:
    """调用者不能让实际 owner 输入与冻结 plan、报告中的 mode 分叉。"""
    with pytest.raises(ValueError, match='cannot be overridden'):
        cli.run_service(
            repo_root=tmp_path,
            changed_files=['scripts/a.py'],
            gate='scriptSourceStandard',
            out_dir=tmp_path / 'out',
            environment_overrides={reserved: 'full'},
        )


def test_service_writes_input_audit_reason_to_report(tmp_path: Path, monkeypatch) -> None:
    """执行型审计例外必须进入最终报告，而不只存在于 CLI 内存。"""
    monkeypatch.setattr(
        executor,
        'execute_plan',
        lambda *_args, **_kwargs: (GateDetail(name='scriptSourceStandard', status=PASS),),
    )

    result = cli.run_service(
        repo_root=tmp_path,
        changed_files=[],
        gate='scriptSourceStandard',
        out_dir=tmp_path / 'out',
        input_audit_reason='人工确认空增量输入',
    )

    payload = json.loads(result.artifact_path.read_text(encoding='utf-8'))
    assert payload['artifacts']['inputAuditReason'] == '人工确认空增量输入'
    assert payload['mode'] == 'incremental'
    assert payload['selector'] == 'gate'
    assert payload['selectorValue'] == 'scriptSourceStandard'
    assert 'target' not in payload


def test_service_timestamps_cover_gate_execution(tmp_path: Path, monkeypatch) -> None:
    """报告起始时间必须先于执行，不能在 Gate 已全部结束后才生成。"""

    events: list[str] = []
    timestamps = iter(['2026-08-03T01:00:00+00:00', '2026-08-03T01:00:03+00:00'])

    def now() -> str:
        value = next(timestamps)
        events.append(value)
        return value

    def execute(*_args, **_kwargs):
        assert events == ['2026-08-03T01:00:00+00:00']
        return (GateDetail(name='scriptSourceStandard', status=PASS, durationMs=3_000),)

    monkeypatch.setattr(report, 'utc_now', now)
    monkeypatch.setattr(executor, 'execute_plan', execute)

    result = cli.run_service(
        repo_root=tmp_path,
        changed_files=['scripts/a.py'],
        gate='scriptSourceStandard',
        out_dir=tmp_path / 'out',
    )

    payload = json.loads(result.artifact_path.read_text(encoding='utf-8'))
    assert payload['startedAt'] == '2026-08-03T01:00:00+00:00'
    assert payload['finishedAt'] == '2026-08-03T01:00:03+00:00'
    assert payload['generatedAt'] == payload['finishedAt']


def test_automatic_incremental_report_lists_not_triggered_gates(
    tmp_path: Path, monkeypatch
) -> None:
    """自动增量报告显式区分未选中 Gate，且不把它们伪装成 PASS 或 skipped。"""

    def execute(execution_plan, *_args, **_kwargs):
        return tuple(
            GateDetail(name=gate.name, status=PASS) for gate in execution_plan.gate_plan.gates
        )

    monkeypatch.setattr(executor, 'execute_plan', execute)
    result = cli.run_service(
        repo_root=tmp_path,
        changed_files=['scripts/gates/cli.py'],
        out_dir=tmp_path / 'out',
    )

    payload = json.loads(result.artifact_path.read_text(encoding='utf-8'))
    not_triggered = payload['artifacts']['notTriggeredGates']
    assert not_triggered
    assert set(not_triggered).isdisjoint(payload['gateResults'])
    assert all(payload['gateStates'][name] == 'NOT_TRIGGERED' for name in not_triggered)


@pytest.mark.parametrize('detail_status', [BLOCKED, FAIL])
@pytest.mark.contract_case('HOOK-HARNESS-012')
def test_service_exposes_not_pass_and_keeps_detail(
    detail_status: str, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        executor,
        'execute_plan',
        lambda *_args, **_kwargs: (GateDetail(name='scriptSourceStandard', status=detail_status),),
    )
    result = cli.run_service(
        repo_root=tmp_path,
        changed_files=['scripts/a.py'],
        gate='scriptSourceStandard',
        out_dir=tmp_path / 'out',
    )
    assert result.status == NOT_PASS
    payload = json.loads(result.artifact_path.read_text(encoding='utf-8'))
    assert payload['status'] == NOT_PASS
    assert payload['gateResults']['scriptSourceStandard'] == detail_status


def test_create_plan_uses_exact_gate_selector() -> None:
    plan = cli.create_plan(
        ['README.md'], mode=ExecutionMode.INCREMENTAL, gate='scriptSourceStandard'
    )
    assert [gate.name for gate in plan.gates] == ['scriptSourceStandard']
    assert plan.selector == 'gate'


def test_base_url_requires_playwright_gate(capsys) -> None:
    assert (
        cli.main(
            [
                '--gate',
                'scriptSourceStandard',
                '--base-url',
                'http://127.0.0.1:8080',
                '--changed-files',
                '["scripts/a.py"]',
                '--dry-run',
            ]
        )
        == 2
    )
    assert 'status=NOT_PASS detailStatus=FAIL' in capsys.readouterr().err


def test_change_id_falls_back_to_active_change_evidence(tmp_path: Path) -> None:
    active = tmp_path / 'tmp' / 'active_change.json'
    active.parent.mkdir()
    active.write_text('{"change_id":"change-a"}', encoding='utf-8')
    assert cli.resolve_change_id(None, tmp_path) == 'change-a'


def test_report_module_exposes_external_summary_status() -> None:
    assert report.NOT_PASS == 'NOT_PASS'
