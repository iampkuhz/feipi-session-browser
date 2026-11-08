"""Deterministic ChangeSnapshot input contracts."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from scripts.gates.planning.change_snapshot import capture_change_snapshot
from scripts.gates.planning.plan_compiler import compile_gate_plan

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


def test_git_deleted_and_added_browser_contracts_select_native_discovery(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    browser = repo / 'java/tests/playwright'
    browser.mkdir(parents=True)
    removed = browser / 'removed-contract.spec.js'
    removed.write_text('synthetic old contract\n')
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-qm', 'synthetic browser contract')
    removed.unlink()
    (browser / 'new-critical.spec.ts').write_text('synthetic new contract\n')
    snapshot = capture_change_snapshot(repo)
    assert snapshot.files == (
        'java/tests/playwright/new-critical.spec.ts',
        'java/tests/playwright/removed-contract.spec.js',
    )
    gate = next(gate for gate in compile_gate_plan(snapshot).gates if gate.name == 'browserTests')
    assert gate.recipe.steps[0].tests == ()  # 原生发现，无旧清单掩盖新文件。


def test_full_input_records_head_without_changed_files(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    (repo / 'working.txt').write_text('ignored by full input\n', encoding='utf-8')

    snapshot = capture_change_snapshot(repo, mode='full')

    assert snapshot.source == 'full'
    assert snapshot.files == ()
    assert snapshot.base is None


def test_full_mode_rejects_git_base(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    with pytest.raises(ValueError, match='does not accept a base'):
        capture_change_snapshot(repo, mode='full', base='HEAD')


def test_staged_rename_out_of_browser_keeps_old_consumers(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    old = 'java/tests/playwright/old.spec.js'
    (repo / old).parent.mkdir(parents=True)
    (repo / old).write_text('synthetic contract\n')
    _git(repo, 'add', old)
    _git(repo, 'commit', '-qm', 'add browser test')
    _git(repo, 'mv', old, 'outside.txt')

    snapshot = capture_change_snapshot(repo)
    assert snapshot.files == (old, 'outside.txt')
    assert 'browserTests' in {gate.name for gate in compile_gate_plan(snapshot).gates}


def test_worktree_type_change_is_not_dropped(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    path = repo / 'stable.txt'
    path.unlink()
    path.symlink_to('working.txt')
    assert capture_change_snapshot(repo).files == ('stable.txt',)


def test_unmerged_index_cannot_produce_a_plan(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    digest = _git(repo, 'rev-parse', 'HEAD:staged.txt')
    subprocess.run(
        ('git', 'update-index', '--index-info'),
        cwd=repo,
        input=f'0 {"0" * len(digest)}\tstaged.txt\n100644 {digest} 2\tstaged.txt\n',
        text=True,
        check=True,
    )
    with pytest.raises(RuntimeError, match='unresolved Git conflicts'):
        capture_change_snapshot(repo)
