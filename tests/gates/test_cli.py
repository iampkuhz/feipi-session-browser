"""Gate CLI/service 的解析、当次 artifact 与 warning 边界 contract。"""

import json
import subprocess
from pathlib import Path

import pytest
from scripts.gates import cli, executor, report
from scripts.gates.report import FAIL, PASS, GateDetail


def test_service_modules_expose_stable_entrypoints() -> None:
    assert callable(cli.run_service)
    assert callable(executor.execute_plan)
    assert callable(report.format_quality_report)


def test_dry_run_has_stable_typed_plan(capsys) -> None:
    rc = cli.main(['--tier', 'required', '--dry-run', '--changed-files', '["build.gradle.kts"]'])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload['effectiveTargets'] == ['java-build']
    assert payload['commands'][0]['gate'] == 'ignoredTrackedFiles'
    assert all('resources' not in group and 'dependsOn' not in group for group in payload['groups'])


def test_misplaced_paths_preflight_runs_for_docs_only_change(capsys) -> None:
    rc = cli.main(['--tier', 'required', '--dry-run', '--changed-files', '["README.md"]'])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload['effectiveTargets'] == []
    assert [item['gate'] for item in payload['commands']] == [
        'ignoredTrackedFiles',
        'misplacedGeneratedPaths',
    ]


def test_target_and_tier_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        cli.main(['--target', 'harness', '--tier', 'quick'])


@pytest.mark.contract_case('HOOK-HARNESS-009')
def test_service_writes_current_run_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        executor,
        'execute_plan',
        lambda *_args, **_kwargs: (
            GateDetail(name='ignoredTrackedFiles', status=PASS),
            GateDetail(name='harnessStructure', status=PASS),
        ),
    )
    result = cli.run_service(
        repo_root=tmp_path,
        changed_files=['harness/manifest.yaml'],
        tier='required',
        change_id='change',
        out_dir=tmp_path / 'out',
    )
    assert result.passed
    assert result.artifact_path and result.artifact_path.exists()


def test_service_executes_plan_on_every_run(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    def fake_execute(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return (GateDetail(name='harnessStructure', status=PASS),)

    monkeypatch.setattr(executor, 'execute_plan', fake_execute)
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
    assert calls == 2
    assert all(detail.status == PASS for detail in second.details)
    assert all(detail.executionState == 'EXECUTED' for detail in second.details)
    assert second.artifact_path and second.artifact_path.exists()


def test_service_injects_tier_and_keeps_explicit_environment_override(
    tmp_path: Path, monkeypatch
) -> None:
    captured: list[dict[str, str]] = []

    def fake_execute(*_args, **kwargs):
        captured.append(kwargs['environment_overrides'])
        return (GateDetail(name='harnessStructure', status=PASS),)

    monkeypatch.setattr(executor, 'execute_plan', fake_execute)
    cli.run_service(
        repo_root=tmp_path,
        changed_files=['harness/manifest.yaml'],
        tier='full',
        out_dir=tmp_path / 'out',
    )
    cli.run_service(
        repo_root=tmp_path,
        changed_files=['harness/manifest.yaml'],
        tier='full',
        out_dir=tmp_path / 'out-override',
        environment_overrides={'QUALITY_GATE_TIER': 'required', 'CUSTOM': 'value'},
    )

    assert captured == [
        {'QUALITY_GATE_TIER': 'full'},
        {'QUALITY_GATE_TIER': 'required', 'CUSTOM': 'value'},
    ]


def test_explicit_empty_dirty_is_blocked(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.support, 'read_git_dirty_files', lambda _root: ['dirty.py'])
    assert cli.main(['--changed-files', '[]', '--dry-run']) == 1
    assert 'status=BLOCKED' in capsys.readouterr().err


@pytest.mark.contract_case('HOOK-HARNESS-012')
def test_required_gate_failure_writes_failure_artifact(tmp_path: Path, monkeypatch) -> None:
    failed = GateDetail(name='required-check', status=FAIL, output='failed')
    monkeypatch.setattr(executor, 'execute_plan', lambda *_args, **_kwargs: (failed,))
    result = cli.run_service(
        repo_root=tmp_path,
        changed_files=['build.gradle.kts'],
        change_id='required-failure',
        out_dir=tmp_path / 'out',
        include_preflight=False,
    )
    assert result.status == FAIL
    assert result.passed is False
    assert result.artifact_path and result.artifact_path.exists()
    payload = json.loads(result.artifact_path.read_text(encoding='utf-8'))
    assert payload['status'] == FAIL


def test_session_browser_test_rejects_pytest_arguments() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ['./scripts/session-browser.sh', 'test', 'tests/example.py'],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 2
    assert 'test 不接受额外参数' in proc.stdout


def test_changed_files_merge_recorded_evidence_and_git_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    subprocess.run(
        ['git', 'config', 'user.email', 'gate@example.invalid'], cwd=tmp_path, check=True
    )
    subprocess.run(['git', 'config', 'user.name', 'Gate Test'], cwd=tmp_path, check=True)
    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('base\n', encoding='utf-8')
    (tmp_path / '.gitignore').write_text('tmp/\n', encoding='utf-8')
    subprocess.run(['git', 'add', 'tracked.txt', '.gitignore'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'commit', '-qm', 'base'], cwd=tmp_path, check=True)
    base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=tmp_path, text=True).strip()

    monkeypatch.setenv('FEIPI_AGENT_CLIENT', 'codex')
    monkeypatch.setenv('FEIPI_SESSION_ID', 'session-a')
    monkeypatch.setenv('FEIPI_RUN_ID', 'run-a')
    identity = cli.support.identity_from_values()
    log_dir = cli.support.agent_log_dir(tmp_path, identity)
    log_dir.mkdir(parents=True)
    (log_dir / 'base-commit.txt').write_text(base + '\n', encoding='utf-8')
    (log_dir / 'changed-files.jsonl').write_text(
        json.dumps({'sessionId': 'session-a', 'file': './recorded.py'}) + '\n',
        encoding='utf-8',
    )
    tracked.write_text('changed\n', encoding='utf-8')
    (tmp_path / 'untracked.txt').write_text('new\n', encoding='utf-8')

    assert cli.get_changed_files(None, tmp_path) == [
        'recorded.py',
        'tracked.txt',
        'untracked.txt',
    ]
