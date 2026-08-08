from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.gates.checks.privacy import check_secret_like_content as secrets

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_secret_guard_scans_qoder_and_reports_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, 'ROOT', tmp_path)

    qoder_secret = _write(
        tmp_path,
        '.qoder/agents/privacy-reviewer.md',
        'token=' + 'sk-' + 'ant-' + 'unitSecretValue123\n',
    )
    report_secret = _write(
        tmp_path,
        'harness/runtime.json',
        '{"token":"' + 'github' + '_pat_' + 'A' * 32 + '"}\n',
    )

    assert '.qoder' in set(secrets.SCAN_DIRS)
    assert secrets._scan_file(qoder_secret)
    assert secrets._scan_file(report_secret)
    assert secrets._check_sensitive_marker('name=' + 'AWS' + '_SECRET' + '_ACCESS_KEY')
    assert secrets._check_sensitive_marker('-----' + 'BEGIN ' + 'OPENSSH ' + 'PRIVATE KEY')
    assert secrets._check_github_token('token=' + 'gh' + 'p_' + 'A' * 32)


def test_secret_guard_ignores_local_claude_worktrees(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, 'ROOT', tmp_path)
    local_worktree_file = _write(
        tmp_path,
        '.claude/worktrees/local-run/runtime.json',
        '/Users/' + 'private/.claude/projects/private-session.jsonl\n',
    )

    assert secrets._is_excluded_path(local_worktree_file)
