"""测试统一的仓库文件政策 Check。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from scripts.checks._framework import CheckStatus
from scripts.checks.repository import check_repository_file_policy as policy


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git', *args], cwd=root, text=True, capture_output=True, check=True)


def _write_manifest(root: Path, paths: list[str] | object) -> None:
    manifest = root / policy.MANIFEST_RELATIVE_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        yaml.safe_dump({policy.MANIFEST_KEY: paths}, sort_keys=False), encoding='utf-8'
    )


def _write_required_paths(root: Path) -> None:
    for relative in policy.REQUIRED_PATHS:
        path = root / relative
        if Path(relative).suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('', encoding='utf-8')
        else:
            path.mkdir(parents=True, exist_ok=True)


def _init_repo(root: Path, forbidden: list[str] | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, 'init')
    _git(root, 'config', 'user.email', 'test@example.com')
    _git(root, 'config', 'user.name', 'Test User')
    _write_required_paths(root)
    _write_manifest(root, forbidden or ['output/'])


def test_clean_repository_passes(tmp_path: Path):
    root = tmp_path / 'repo'
    _init_repo(root)

    assert policy.check(['--root', str(root), '--all-tracked']).passed


def test_missing_required_path_fails(tmp_path: Path, monkeypatch):
    root = tmp_path / 'repo'
    _init_repo(root)
    monkeypatch.setattr(policy, 'REQUIRED_PATHS', ('missing-entry.py',))

    result = policy.check(['--root', str(root)])

    assert not result.passed
    assert '缺少必需路径: missing-entry.py' in result.diagnostics[0].message


def test_forbidden_path_on_disk_fails_even_when_ignored(tmp_path: Path):
    root = tmp_path / 'repo'
    _init_repo(root)
    (root / '.gitignore').write_text('/output/\n', encoding='utf-8')
    (root / 'output').mkdir()

    result = policy.check(['--root', str(root)])

    assert not result.passed
    assert any('禁止根路径不应出现在仓库磁盘: output' in d.message for d in result.diagnostics)


def test_invalid_manifest_fails_closed(tmp_path: Path):
    root = tmp_path / 'repo'
    _init_repo(root)
    _write_manifest(root, 'output/')

    result = policy.check(['--root', str(root)])

    assert not result.passed
    assert 'configuration' not in result.diagnostics[0].message.lower()
    assert 'must be a non-empty list' in result.diagnostics[0].message


def test_missing_required_manifest_is_blocked(tmp_path: Path):
    """必需政策文件缺失是明确仓库违规，而不是 Gate 执行失败。"""
    root = tmp_path / 'repo'
    _init_repo(root)
    (root / policy.MANIFEST_RELATIVE_PATH).unlink()

    result = policy.check(['--root', str(root)])

    assert result.status is CheckStatus.BLOCKED
    assert 'manifest is missing' in result.diagnostics[0].message


def test_staged_ignored_file_fails(tmp_path: Path):
    root = tmp_path / 'repo'
    _init_repo(root, ['generated/'])
    (root / '.gitignore').write_text('/cache/\n', encoding='utf-8')
    (root / 'cache').mkdir()
    (root / 'cache' / 'leak.txt').write_text('generated\n', encoding='utf-8')
    _git(root, 'add', '.gitignore')
    _git(root, 'add', '-f', 'cache/leak.txt')

    assert not policy.check(['--root', str(root), '--staged']).passed


def test_negated_gitignore_rule_is_allowed(tmp_path: Path):
    root = tmp_path / 'repo'
    _init_repo(root, ['generated/'])
    (root / '.gitignore').write_text('/tmp/*\n!/tmp/.gitkeep\n', encoding='utf-8')
    (root / 'tmp').mkdir()
    (root / 'tmp' / '.gitkeep').write_text('', encoding='utf-8')
    _git(root, 'add', '.gitignore', 'tmp/.gitkeep')

    assert policy.check(['--root', str(root), '--staged']).passed


def test_staged_deletion_is_allowed_for_cleanup(tmp_path: Path):
    root = tmp_path / 'repo'
    _init_repo(root, ['generated/'])
    (root / '.gitignore').write_text('/cache/\n', encoding='utf-8')
    (root / 'cache').mkdir()
    (root / 'cache' / 'legacy.txt').write_text('legacy\n', encoding='utf-8')
    _git(root, 'add', '.gitignore')
    _git(root, 'add', '-f', 'cache/legacy.txt')
    _git(root, 'commit', '-m', 'legacy ignored file')
    _git(root, 'rm', 'cache/legacy.txt')

    assert policy.check(['--root', str(root), '--staged']).passed


def test_forbidden_root_tracked_file_fails(tmp_path: Path):
    root = tmp_path / 'repo'
    _init_repo(root)
    (root / 'output').mkdir()
    (root / 'output' / 'result.txt').write_text('result\n', encoding='utf-8')
    _git(root, 'add', 'output/result.txt')

    result = policy.check(['--root', str(root), '--staged'])

    assert not result.passed
    assert any('禁止根路径不应进入 Git tracked' in d.message for d in result.diagnostics)


def test_tracked_database_fails(tmp_path: Path):
    root = tmp_path / 'repo'
    _init_repo(root, ['output/'])
    (root / 'fixture.sqlite3').write_bytes(b'database')
    _git(root, 'add', 'fixture.sqlite3')

    result = policy.check(['--root', str(root), '--staged'])

    assert not result.passed
    assert any(
        '数据库文件不应进入 Git tracked: fixture.sqlite3' in d.message for d in result.diagnostics
    )


def test_git_read_error_fails_closed(tmp_path: Path):
    root = tmp_path / 'not-a-repository'
    root.mkdir()
    _write_required_paths(root)
    _write_manifest(root, ['output/'])

    result = policy.check(['--root', str(root)])

    assert not result.passed
    assert 'git diff' in result.diagnostics[0].message
