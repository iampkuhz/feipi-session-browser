"""Required quality runner semantics for not-triggered/excluded/not-run states."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / 'scripts' / 'quality' / 'run_required_quality_gates.py'
)
_spec = importlib.util.spec_from_file_location('required_runner_semantics', SCRIPT_PATH)
_runner = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_runner)


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    """Run the runner entrypoint with stable no-op preflight."""
    monkeypatch.setattr(_runner, '_run_global_preflight', lambda repo_root, dry_run: True)
    monkeypatch.setattr(_runner, 'resolve_change_id', lambda explicit: explicit or 'test-change')
    monkeypatch.setattr(_runner.sys, 'argv', ['run_required_quality_gates.py', *argv])
    return _runner.main()


def test_no_changed_files_and_git_clean_is_not_triggered_not_skipped(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(_runner, 'get_changed_files', lambda explicit_json=None: [])
    monkeypatch.setattr(_runner, '_git_dirty_files', lambda: [])

    rc = _run_main(monkeypatch, ['--tier', 'required'])

    captured = capsys.readouterr()
    assert rc == 0
    assert 'no changed files; quality targets not triggered' in captured.err
    assert 'excluded target handled elsewhere' not in captured.err


def test_empty_changed_files_but_git_dirty_blocks_without_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(_runner, '_git_dirty_files', lambda: ['scripts/quality/run_quality_gate.py'])

    rc = _run_main(monkeypatch, ['--tier', 'required', '--changed-files', '[]'])

    captured = capsys.readouterr()
    assert rc == 1
    assert 'explicit --changed-files [] while git workspace is dirty' in captured.err
    assert '--allow-empty-changed-files-because' in captured.err


def test_session_detail_target_is_not_silently_excluded(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    rc = _run_main(
        monkeypatch,
        [
            '--tier',
            'required',
            '--dry-run',
            '--changed-files',
            '["java/web/src/main/resources/templates/session-detail.html"]',
        ],
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert 'would run target: session-detail' in captured.err
    assert 'excluded target handled elsewhere: session-detail' not in captured.err


def test_session_detail_exclusion_requires_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    changed = '["java/web/src/main/resources/templates/session-detail.html"]'

    blocked = _run_main(
        monkeypatch,
        [
            '--tier',
            'required',
            '--dry-run',
            '--changed-files',
            changed,
            '--exclude-session-detail-with-reason',
            '',
        ],
    )
    blocked_output = capsys.readouterr()
    assert blocked == 1
    assert 'requires a reason' in blocked_output.err

    allowed = _run_main(
        monkeypatch,
        [
            '--tier',
            'required',
            '--dry-run',
            '--changed-files',
            changed,
            '--exclude-session-detail-with-reason',
            'stop-runner',
        ],
    )
    allowed_output = capsys.readouterr()
    assert allowed == 0
    assert (
        'excluded target handled elsewhere: session-detail reason=stop-runner'
        in allowed_output.err
    )


def test_skipped_gate_status_fails_required_tier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    artifact = tmp_path / 'quality' / 'change' / 'quality-gate-summary.hook-runtime.json'

    def fake_run(cmd: list[str], **kwargs: object) -> object:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            json.dumps(
                {
                    'status': 'PASS',
                    'requiredGates': {'pythonCompile': 'PASS', 'pytest': 'SKIPPED'},
                    'gateDetails': [
                        {'name': 'pythonCompile', 'status': 'PASS'},
                        {'name': 'pytest', 'status': 'SKIPPED'},
                    ],
                }
            ),
            encoding='utf-8',
        )
        return _runner.subprocess.CompletedProcess(cmd, 0, stdout='ok')

    monkeypatch.setattr(_runner.subprocess, 'run', fake_run)
    passed, artifact_path = _runner.run_gate('hook-runtime', 'change', tmp_path / 'quality')

    assert passed is False
    assert Path(artifact_path) == artifact


def test_not_triggered_output_does_not_increment_skipped_count(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(_runner, 'get_changed_files', lambda explicit_json=None: [])
    monkeypatch.setattr(_runner, '_git_dirty_files', lambda: [])

    rc = _run_main(monkeypatch, ['--tier', 'quick'])

    captured = capsys.readouterr()
    assert rc == 0
    assert 'no changed files; quality targets not triggered' in captured.err
    assert 'skipped_count' not in captured.err
