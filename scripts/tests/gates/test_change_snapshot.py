"""Deterministic ChangeSnapshot input contracts."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from scripts.gates.planning.change_snapshot import capture_change_snapshot

if TYPE_CHECKING:
    from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(('git', *args), cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repository(tmp_path: Path) -> Path:
    _git(tmp_path, 'init', '-q')
    _git(tmp_path, 'config', 'user.name', 'Gate Test')
    _git(tmp_path, 'config', 'user.email', 'gate-test@example.invalid')
    for name in ('staged.txt', 'working.txt', 'stable.txt'):
        (tmp_path / name).write_text(f'{name}\n', encoding='utf-8')
    _git(tmp_path, 'add', '.')
    _git(tmp_path, 'commit', '-qm', 'initial')
    return tmp_path


def test_default_input_freezes_staged_working_and_untracked_files(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    (repo / 'staged.txt').write_text('staged change\n', encoding='utf-8')
    _git(repo, 'add', 'staged.txt')
    (repo / 'working.txt').write_text('working change\n', encoding='utf-8')
    (repo / 'untracked.txt').write_text('new\n', encoding='utf-8')

    snapshot = capture_change_snapshot(repo)

    assert snapshot.source == 'git-working-tree'
    assert snapshot.base is None
    assert snapshot.head == _git(repo, 'rev-parse', 'HEAD')
    assert snapshot.files == ('staged.txt', 'untracked.txt', 'working.txt')
    assert len(snapshot.content_fingerprint) == 64


def test_base_input_only_compares_committed_head_and_records_resolved_base(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    base = _git(repo, 'rev-parse', 'HEAD')
    (repo / 'stable.txt').write_text('committed after base\n', encoding='utf-8')
    _git(repo, 'add', 'stable.txt')
    _git(repo, 'commit', '-qm', 'after base')
    (repo / 'untracked.txt').write_text('not part of base comparison\n', encoding='utf-8')

    snapshot = capture_change_snapshot(repo, base=base)

    assert snapshot.source == 'git-base'
    assert snapshot.base == base
    assert snapshot.head == _git(repo, 'rev-parse', 'HEAD')
    assert snapshot.files == ('stable.txt',)


def test_explicit_files_are_normalized_deduplicated_and_content_sensitive(
    tmp_path: Path,
) -> None:
    repo = _repository(tmp_path)
    first = capture_change_snapshot(
        repo, changed_files=(r'.\working.txt', 'staged.txt', 'working.txt')
    )
    (repo / 'working.txt').write_text('new content\n', encoding='utf-8')
    second = capture_change_snapshot(repo, changed_files=('staged.txt', 'working.txt'))

    assert first.source == 'explicit-changed-files'
    assert first.files == ('staged.txt', 'working.txt')
    assert first.content_fingerprint != second.content_fingerprint


def test_full_input_records_head_without_changed_files(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    (repo / 'working.txt').write_text('ignored by full input\n', encoding='utf-8')

    snapshot = capture_change_snapshot(repo, mode='full')

    assert snapshot.source == 'full'
    assert snapshot.files == ()
    assert snapshot.base is None


@pytest.mark.parametrize(
    'kwargs',
    [
        {'base': 'HEAD', 'changed_files': ('a.py',)},
        {'mode': 'full', 'base': 'HEAD'},
        {'mode': 'full', 'changed_files': ()},
    ],
)
def test_input_sources_are_mutually_exclusive(tmp_path: Path, kwargs: dict[str, object]) -> None:
    repo = _repository(tmp_path)
    with pytest.raises(ValueError):
        capture_change_snapshot(repo, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize('path', ('../outside.py', '/absolute.py', r'C:\absolute.py', '', './'))
def test_explicit_changed_files_reject_non_repository_paths(tmp_path: Path, path: str) -> None:
    repo = _repository(tmp_path)
    with pytest.raises(ValueError, match='repository-relative'):
        capture_change_snapshot(repo, changed_files=(path,))


def test_explicit_changed_files_rejects_scalar_string(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    with pytest.raises(TypeError, match='iterable of paths'):
        capture_change_snapshot(repo, changed_files='one.py')
