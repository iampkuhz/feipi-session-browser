from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.harness import stop_helpers


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_parse_git_status_paths_handles_hidden_paths():
    assert stop_helpers.parse_git_status_paths(' M .codex/hooks.json\n?? .qoder/settings.json\n') == [
        '.codex/hooks.json',
        '.qoder/settings.json',
    ]


@pytest.mark.contract_case('HOOK-HARNESS-006')
def test_git_changed_files_includes_committed_dirty_and_untracked(tmp_path: Path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    _run(['git', 'init', '-b', 'main_java'], repo)
    _run(['git', 'config', 'user.email', 'stop@example.invalid'], repo)
    _run(['git', 'config', 'user.name', 'Stop Test'], repo)
    (repo / 'README.md').write_text('base\n', encoding='utf-8')
    _run(['git', 'add', 'README.md'], repo)
    _run(['git', 'commit', '-m', 'init'], repo)
    base = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    (repo / 'committed.txt').write_text('committed\n', encoding='utf-8')
    _run(['git', 'add', 'committed.txt'], repo)
    _run(['git', 'commit', '-m', 'committed'], repo)
    (repo / 'README.md').write_text('dirty\n', encoding='utf-8')
    (repo / 'untracked.txt').write_text('new\n', encoding='utf-8')

    assert stop_helpers.git_changed_files(repo, base) == ['committed.txt', 'README.md', 'untracked.txt']
