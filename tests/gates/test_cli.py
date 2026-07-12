"""Gate CLI/service 的解析、artifact、receipt 与 warning 边界 contract。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.gates import cli, executor, receipt, report
from scripts.gates.report import FAIL, PASS, GateDetail


def test_service_modules_expose_stable_entrypoints() -> None:
    assert callable(cli.run_service)
    assert callable(executor.execute_plan)
    assert callable(receipt.content_cache_key)
    assert callable(report.format_quality_report)


def test_dry_run_has_stable_typed_plan(capsys) -> None:
    rc = cli.main(['--tier', 'required', '--dry-run', '--changed-files', '["build.gradle.kts"]'])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload['effectiveTargets'] == ['java-build']
    assert payload['commands'][0]['gate'] == 'ignoredTrackedFiles'


def test_target_and_tier_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        cli.main(['--target', 'harness', '--tier', 'quick'])


@pytest.mark.contract_case('HOOK-HARNESS-009')
def test_service_writes_artifact_and_receipt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        executor,
        'execute_plan',
        lambda *_args, **_kwargs: (
            GateDetail(name='ignoredTrackedFiles', status=PASS),
            GateDetail(name='harnessStructure', status=PASS),
        ),
    )
    monkeypatch.setattr(cli.receipt, 'content_cache_key', lambda *_args: 'cache')
    result = cli.run_service(
        repo_root=tmp_path,
        changed_files=['harness/manifest.yaml'],
        tier='required',
        change_id='change',
        out_dir=tmp_path / 'out',
    )
    assert result.passed
    assert result.artifact_path and result.artifact_path.exists()
    assert result.receipt_paths and result.receipt_paths[0].exists()


def test_service_reuses_content_sensitive_pass_receipt(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    def fake_execute(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return (GateDetail(name='harnessStructure', status=PASS),)

    monkeypatch.setattr(executor, 'execute_plan', fake_execute)
    monkeypatch.setattr(cli.receipt, 'content_cache_key', lambda *_args, **_kwargs: 'stable')
    kwargs = {
        'repo_root': tmp_path,
        'changed_files': ['harness/manifest.yaml'],
        'tier': 'required',
        'change_id': 'change',
        'out_dir': tmp_path / 'out',
    }
    first = cli.run_service(**kwargs)
    second = cli.run_service(**kwargs)
    assert first.passed and second.passed
    assert calls == 1
    assert all(detail.status == PASS for detail in second.details)
    assert all(detail.executionState == 'REUSED' for detail in second.details)
    assert first.artifact_path != second.artifact_path
    assert second.artifact_path and second.artifact_path.name.endswith('.reuse.json')
    bound = receipt.read_receipt(second.receipt_paths[0]) or {}
    assert bound['artifact_path'] == str(first.artifact_path)


def test_explicit_empty_dirty_is_blocked(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.evidence, 'read_git_dirty_files', lambda _root: ['dirty.py'])
    assert cli.main(['--changed-files', '[]', '--dry-run']) == 1
    assert 'status=BLOCKED' in capsys.readouterr().err


@pytest.mark.contract_case('HOOK-HARNESS-012')
def test_required_gate_failure_never_writes_pass_receipt(tmp_path: Path, monkeypatch) -> None:
    failed = GateDetail(name='required-check', status=FAIL, output='failed')
    monkeypatch.setattr(executor, 'execute_plan', lambda *_args, **_kwargs: (failed,))
    monkeypatch.setattr(receipt, 'content_cache_key', lambda *_args, **_kwargs: 'cache-key')
    monkeypatch.setattr(
        report,
        'write_quality_summary',
        lambda *_args, **_kwargs: tmp_path / 'quality-gate-summary.required.json',
    )
    monkeypatch.setattr(
        receipt,
        'write_pass_receipt',
        lambda *_args, **_kwargs: pytest.fail('失败的 required Gate 不得写 PASS receipt'),
    )
    result = cli.run_service(
        repo_root=tmp_path,
        changed_files=['build.gradle.kts'],
        change_id='required-failure',
        include_preflight=False,
        reuse_receipts=False,
    )
    assert result.status == FAIL
    assert result.passed is False
    assert result.receipt_paths == ()


def test_session_browser_test_fails_on_pytest_warning(tmp_path: Path) -> None:
    test_file = tmp_path / 'test_warning_gate.py'
    test_file.write_text(
        'import warnings\n\n'
        'def test_warning_after_trigger():\n'
        "    warnings.warn('gate must reject this warning', UserWarning)\n",
        encoding='utf-8',
    )
    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ['./scripts/session-browser.sh', 'test', str(test_file)],
        cwd=repo_root,
        env={**os.environ, 'SESSION_BROWSER_PYTHON': sys.executable},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )
    assert proc.returncode != 0
    assert 'UserWarning: gate must reject this warning' in proc.stdout
