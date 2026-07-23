from __future__ import annotations

from pathlib import Path

from scripts.checks import check_no_committed_local_paths as local_paths
from scripts.checks import check_no_real_session_fixtures as real_sessions
from scripts.checks import check_secret_like_content as secrets


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_secret_guard_scans_qoder_and_reports_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "ROOT", tmp_path)

    qoder_secret = _write(
        tmp_path,
        ".qoder/agents/privacy-reviewer.md",
        "token=" + "sk-" + "ant-" + "unitSecretValue123\n",
    )
    report_secret = _write(
        tmp_path,
        "harness/runtime.json",
        '{"token":"' + "github" + "_pat_" + "A" * 32 + '"}\n',
    )

    scan_dirs = set(secrets.SCAN_DIRS)
    assert ".qoder" in scan_dirs
    assert secrets._scan_file(qoder_secret)
    assert secrets._scan_file(report_secret)
    assert secrets._check_sensitive_marker("name=" + "AWS" + "_SECRET" + "_ACCESS_KEY")
    assert secrets._check_sensitive_marker("-----" + "BEGIN " + "OPENSSH " + "PRIVATE KEY")
    assert secrets._check_github_token("token=" + "gh" + "p_" + "A" * 32)


def test_real_session_guard_scans_agent_runtime_fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr(real_sessions, "ROOT", tmp_path)

    raw_fixture = _write(
        tmp_path,
        "tests/fixtures/raw_session.jsonl",
        (
            '{"parentUuid":null,"promptId":"unit","type":"user",'
            '"message":{"role":"user","content":"unit raw prompt"}}\n'
        ),
    )
    runtime_test = _write(
        tmp_path,
        "tests/test_agent_runtime_privacy.py",
        str(Path.home()) + "/.claude/projects/unit-session.jsonl\n",
    )

    scan_dirs = set(real_sessions.SCAN_DIRS)
    assert "tests/fixtures" in scan_dirs
    assert "tests/test_*agent*runtime*.py" in real_sessions.SCAN_GLOBS
    assert raw_fixture in real_sessions._iter_scan_files()
    assert runtime_test in real_sessions._iter_scan_files()
    assert real_sessions._scan_file(raw_fixture)
    assert real_sessions._scan_file(runtime_test)


def test_local_path_guard_rejects_committed_absolute_user_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(local_paths, "ROOT", tmp_path)

    runtime_test = _write(
        tmp_path,
        "tests/test_agent_runtime_privacy.py",
        str(Path.home()) + "/Downloads/feipi_agent_env_full_qoder_tasks/shared/PROMPT.md\n",
    )
    fixture = _write(
        tmp_path,
        "tests/fixtures/runtime_sample.jsonl",
        str(Path.home()) + "/.qoder/sessions/unit.jsonl\n",
    )

    assert "tests/fixtures" in set(local_paths.SCAN_DIRS)
    assert "tests/test_*agent*runtime*.py" in local_paths.SCAN_GLOBS
    assert runtime_test in local_paths._iter_scan_files()
    assert fixture in local_paths._iter_scan_files()
    assert local_paths._scan_file(runtime_test)
    assert local_paths._scan_file(fixture)


def test_privacy_guards_ignore_local_claude_worktrees(tmp_path, monkeypatch):
    monkeypatch.setattr(local_paths, "ROOT", tmp_path)
    monkeypatch.setattr(secrets, "ROOT", tmp_path)

    local_worktree_file = _write(
        tmp_path,
        ".claude/worktrees/local-run/runtime.json",
        str(Path.home()) + "/.claude/projects/private.jsonl\n",
    )

    assert local_worktree_file not in local_paths._iter_scan_files()
    assert secrets._is_excluded_path(local_worktree_file)


def test_qoder_docs_may_reference_tilde_qoder_but_not_raw_session_content(tmp_path, monkeypatch):
    monkeypatch.setattr(real_sessions, "ROOT", tmp_path)

    qoder_doc = _write(
        tmp_path,
        ".qoder/agents/privacy-reviewer.md",
        "Use `~/.qoder` only as a path placeholder; do not read session data.\n",
    )
    raw_doc = _write(
        tmp_path,
        ".qoder/agents/raw-session-example.md",
        (
            '{"parentUuid":null,"promptId":"unit","type":"user",'
            '"message":{"role":"user","content":"raw session content"}}\n'
        ),
    )

    assert real_sessions._scan_file(qoder_doc) == []
    assert real_sessions._scan_file(raw_doc)
