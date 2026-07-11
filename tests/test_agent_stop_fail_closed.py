import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.claude_hooks import paths as runtime_paths
from scripts.harness import agent_stop_check as stop_check
from scripts.quality import changed_files as changed_file_utils


PROTECTED_FILE = '.claude/agents/qwen-main-default.md'


def _write_runtime_manifest(repo_root: Path) -> None:
    manifest = repo_root / 'harness' / 'agent-runtime.manifest.yaml'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        'protected_roots:\n'
        '  - .claude/\n'
        '  - .codex/\n'
        '  - .qoder/\n'
        '  - .agents/\n'
        '  - skills/\n'
        '  - harness/\n'
        '  - scripts/\n'
        '  - openspec/\n'
        '  - src/session_browser/\n'
        '  - tests/\n'
        '  - AGENTS.md\n'
        '  - CLAUDE.md\n',
        encoding='utf-8',
    )


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _init_git_repo(tmp_path: Path) -> Path:
    _run(['git', 'init'], tmp_path)
    _run(['git', 'config', 'user.email', 'test@example.com'], tmp_path)
    _run(['git', 'config', 'user.name', 'Test User'], tmp_path)
    (tmp_path / 'README.md').write_text('base\n', encoding='utf-8')
    (tmp_path / '.gitignore').write_text('tmp/\n', encoding='utf-8')
    protected = tmp_path / PROTECTED_FILE
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected.write_text('base\n', encoding='utf-8')
    _write_runtime_manifest(tmp_path)
    _run(['git', 'add', '.gitignore', 'README.md', PROTECTED_FILE, 'harness/agent-runtime.manifest.yaml'], tmp_path)
    _run(['git', 'commit', '-m', 'base'], tmp_path)
    return tmp_path


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    return _init_git_repo(tmp_path)


@pytest.fixture
def isolated_stop(monkeypatch: pytest.MonkeyPatch, temp_repo: Path):
    monkeypatch.setattr(stop_check, 'REPO_ROOT', temp_repo)
    monkeypatch.setattr(stop_check, 'AGENT_LOG_BASE', temp_repo / 'tmp' / 'agent_logs')
    monkeypatch.setattr(
        stop_check, 'LEGACY_SESSION_ID_FILE', temp_repo / 'tmp' / 'agent_logs' / 'legacy' / 'session-id.txt'
    )
    monkeypatch.setattr(
        stop_check,
        'LEGACY_CHANGED_FILES',
        temp_repo / 'tmp' / 'agent_logs' / 'legacy' / 'changed-files.jsonl',
    )
    monkeypatch.setattr(stop_check, 'CHANGED_FILES', stop_check.LEGACY_CHANGED_FILES)
    monkeypatch.setattr(stop_check, 'STOP_LOCK', temp_repo / 'tmp' / 'agent_logs' / 'stop-check' / 'legacy.lock')
    monkeypatch.setattr(stop_check, 'required_targets', lambda files: ['hook-runtime'] if files else [])
    return stop_check


def _invoke_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    agent: str = 'claude',
    session_id: str = 'session-a',
) -> tuple[int, str]:
    monkeypatch.setenv('FEIPI_SESSION_ID', session_id)
    monkeypatch.setenv('ACTIVE_CHANGE_ID', 'harden-agent-runtime-full-v3')
    monkeypatch.setattr(sys, 'argv', ['stop_entry.py', '--agent', agent])
    monkeypatch.setattr(sys, 'stdin', io.StringIO(''))
    code = stop_check.main()
    captured = capsys.readouterr()
    return code, captured.err


def _summary(repo_root: Path, session_id: str = 'session-a') -> dict:
    path = repo_root / 'tmp' / 'agent_logs' / 'claude' / session_id / 'main' / 'stop-check-summary.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _dirty_protected(repo_root: Path) -> None:
    (repo_root / PROTECTED_FILE).write_text('dirty\n', encoding='utf-8')


def _write_evidence(repo_root: Path, session_id: str = 'session-a', file_path: str = PROTECTED_FILE) -> Path:
    identity = runtime_paths.identity_from_values('claude', session_id, '')
    log_dir = runtime_paths.agent_log_dir(repo_root, identity)
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {'schemaVersion': 1, 'sessionId': session_id, 'file': file_path}
    evidence_path = log_dir / 'changed-files.jsonl'
    evidence_path.write_text(json.dumps(record) + '\n', encoding='utf-8')
    return evidence_path


def _write_base_commit(repo_root: Path, session_id: str = 'session-a') -> None:
    identity = runtime_paths.identity_from_values('claude', session_id, '')
    log_dir = runtime_paths.agent_log_dir(repo_root, identity)
    changed_file_utils.write_base_commit_if_missing(repo_root, log_dir / 'base-commit.txt')


def test_session_identity_with_dirty_git_and_no_evidence_blocks(
    isolated_stop, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], temp_repo: Path
):
    _dirty_protected(temp_repo)
    monkeypatch.setattr(stop_check, 'run_step', lambda *args, **kwargs: True)

    code, stderr = _invoke_main(monkeypatch, capsys)
    summary = _summary(temp_repo)

    assert code != 0
    assert summary['status'] == 'BLOCKED'
    assert any('attribution evidence missing' in failure for failure in summary['blockingFailures'])
    assert 'base commit missing' in stderr
    assert 'PASS read-only session' not in stderr


def test_session_identity_with_unchanged_baseline_dirty_state_passes_read_only(
    isolated_stop, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], temp_repo: Path
):
    _dirty_protected(temp_repo)
    _write_base_commit(temp_repo)
    monkeypatch.setattr(stop_check, 'run_step', lambda *args, **kwargs: True)

    code, stderr = _invoke_main(monkeypatch, capsys)
    summary = _summary(temp_repo)

    assert code == 0
    assert summary['status'] == 'PASS'
    assert summary['readOnly'] is True
    assert summary['blockingFailures'] == []
    assert 'PASS read-only session' in stderr


def test_session_identity_with_changed_baseline_dirty_state_without_files_blocks(
    isolated_stop, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], temp_repo: Path
):
    _dirty_protected(temp_repo)
    _write_base_commit(temp_repo)
    (temp_repo / PROTECTED_FILE).write_text('dirty again\n', encoding='utf-8')
    monkeypatch.setattr(stop_check, 'run_step', lambda *args, **kwargs: True)

    code, stderr = _invoke_main(monkeypatch, capsys)
    summary = _summary(temp_repo)

    assert code != 0
    assert summary['status'] == 'BLOCKED'
    assert any('attribution evidence missing' in failure for failure in summary['blockingFailures'])
    assert 'PASS read-only session' not in stderr


def test_session_identity_with_clean_git_and_no_evidence_passes_read_only(
    isolated_stop, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], temp_repo: Path
):
    monkeypatch.setattr(stop_check, 'run_step', lambda *args, **kwargs: True)

    code, stderr = _invoke_main(monkeypatch, capsys)
    summary = _summary(temp_repo)

    assert code == 0
    assert summary['status'] == 'PASS'
    assert summary['readOnly'] is True
    assert summary['blockingFailures'] == []
    assert 'PASS read-only session' in stderr


def test_session_identity_with_evidence_runs_targets_not_read_only(
    isolated_stop, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], temp_repo: Path
):
    _write_evidence(temp_repo)
    _write_base_commit(temp_repo)
    _dirty_protected(temp_repo)
    calls: list[str] = []

    def fake_run_step(name, cmd, env_overrides=None):
        calls.append(name)
        return True

    monkeypatch.setattr(stop_check, 'run_step', fake_run_step)

    code, stderr = _invoke_main(monkeypatch, capsys)
    summary = _summary(temp_repo)

    assert code == 0
    assert summary['readOnly'] is False
    assert summary['status'] == 'PASS'
    assert 'required-quality-gates' in calls
    assert summary['changedFiles'] == [PROTECTED_FILE]
    assert 'PASS read-only session' not in stderr


def test_missing_base_commit_with_dirty_protected_file_blocks(
    isolated_stop, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], temp_repo: Path
):
    _dirty_protected(temp_repo)
    monkeypatch.setattr(stop_check, 'run_step', lambda *args, **kwargs: True)

    code, stderr = _invoke_main(monkeypatch, capsys)
    summary = _summary(temp_repo)

    assert code != 0
    assert summary['status'] == 'BLOCKED'
    assert any('base commit missing' in failure for failure in summary['blockingFailures'])
    assert 'base commit missing' in stderr
