"""Tests for ignored tracked files quality gate."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from scripts.checks.repository import check_ignored_tracked_files

if TYPE_CHECKING:
    from pathlib import Path


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, 'init')
    _git(root, 'config', 'user.email', 'test@example.com')
    _git(root, 'config', 'user.name', 'Test User')


def test_staged_ignored_file_fails(tmp_path: Path):
    repo = tmp_path / 'repo'
    _init_repo(repo)
    (repo / '.gitignore').write_text('output/\n', encoding='utf-8')
    (repo / 'output').mkdir()
    (repo / 'output' / 'leak.txt').write_text('secret\n', encoding='utf-8')

    _git(repo, 'add', '.gitignore')
    _git(repo, 'add', '-f', 'output/leak.txt')

    findings = check_ignored_tracked_files.ignored_paths(
        repo,
        check_ignored_tracked_files.staged_candidate_paths(repo),
    )

    assert [finding.path for finding in findings] == ['output/leak.txt']
    assert check_ignored_tracked_files.main(['--root', str(repo), '--staged']) == 1


def test_staged_deleted_ignored_file_is_allowed_for_cleanup(tmp_path: Path):
    repo = tmp_path / 'repo'
    _init_repo(repo)
    (repo / '.gitignore').write_text('output/\n', encoding='utf-8')
    (repo / 'output').mkdir()
    (repo / 'output' / 'legacy.txt').write_text('legacy\n', encoding='utf-8')
    _git(repo, 'add', '.gitignore')
    _git(repo, 'add', '-f', 'output/legacy.txt')
    _git(repo, 'commit', '-m', 'legacy ignored tracked file')

    _git(repo, 'rm', 'output/legacy.txt')

    assert check_ignored_tracked_files.staged_candidate_paths(repo) == []
    assert check_ignored_tracked_files.main(['--root', str(repo), '--staged']) == 0


def test_negated_gitignore_rule_is_not_reported(tmp_path: Path):
    repo = tmp_path / 'repo'
    _init_repo(repo)
    (repo / '.gitignore').write_text('/tmp/*\n!/tmp/.gitkeep\n', encoding='utf-8')
    (repo / 'tmp').mkdir()
    (repo / 'tmp' / '.gitkeep').write_text('', encoding='utf-8')

    _git(repo, 'add', '.gitignore', 'tmp/.gitkeep')

    assert check_ignored_tracked_files.main(['--root', str(repo), '--staged']) == 0


def test_all_tracked_mode_reports_legacy_ignored_tracking(tmp_path: Path):
    repo = tmp_path / 'repo'
    _init_repo(repo)
    (repo / '.gitignore').write_text('output/\n', encoding='utf-8')
    (repo / 'output').mkdir()
    (repo / 'output' / 'legacy.txt').write_text('legacy\n', encoding='utf-8')
    _git(repo, 'add', '.gitignore')
    _git(repo, 'add', '-f', 'output/legacy.txt')
    _git(repo, 'commit', '-m', 'legacy ignored tracked file')

    assert check_ignored_tracked_files.main(['--root', str(repo), '--all-tracked']) == 1
