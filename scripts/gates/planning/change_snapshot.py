"""采集唯一受支持的确定性 Gate 输入快照。

本模块负责读取 Git 或显式 changed files 并冻结内容指纹；不负责读取 session、runtime 或
active change 证据，不匹配 Trigger。由 CLI 在调用 plan compiler 前调用。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from scripts.gates.catalog.gate_contracts import ExecutionMode

if TYPE_CHECKING:
    from collections.abc import Iterable

_SOURCE_WORKTREE = 'git-working-tree'
_SOURCE_BASE = 'git-base'
_SOURCE_EXPLICIT = 'explicit-changed-files'
_SOURCE_FULL = 'full'


class ChangeSnapshotError(RuntimeError):
    """表示 Git 或文件系统故障导致无法生成可复现快照。"""


@dataclass(frozen=True, slots=True)
class ChangeSnapshot:
    """冻结输入来源及其选中的仓库内容。"""

    source: str
    head: str | None
    base: str | None
    files: tuple[str, ...]
    content_fingerprint: str


def _run_git(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ('git', *args),
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ChangeSnapshotError(f'cannot run git {" ".join(args)}: {exc}') from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or 'unknown git error'
        raise ChangeSnapshotError(f'git {" ".join(args)} failed: {detail}')
    return completed.stdout


def _normalize_repo_path(raw_path: str) -> str:
    value = raw_path.replace('\\', '/').strip()
    while value.startswith('./'):
        value = value[2:]
    value = value.rstrip('/')
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith('/')
        or re.match(r'^[A-Za-z]:/', value)
        or '..' in path.parts
        or '\x00' in value
    ):
        raise ValueError(f'changed file must be a repository-relative path: {raw_path!r}')
    return path.as_posix()


def _normalize_files(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({_normalize_repo_path(path) for path in paths}))


def _nul_paths(output: str) -> tuple[str, ...]:
    return _normalize_files(path for path in output.split('\0') if path)


def _capture_worktree_files(repo_root: Path) -> tuple[str, ...]:
    outputs = (
        _run_git(repo_root, 'diff', '--name-only', '--diff-filter=ACMRD', '-z'),
        _run_git(repo_root, 'diff', '--cached', '--name-only', '--diff-filter=ACMRD', '-z'),
        _run_git(repo_root, 'ls-files', '--others', '--exclude-standard', '-z'),
    )
    return _normalize_files(path for output in outputs for path in output.split('\0') if path)


def _resolve_head(repo_root: Path) -> str:
    return _run_git(repo_root, 'rev-parse', '--verify', 'HEAD').strip()


def _resolve_base(repo_root: Path, base: str) -> str:
    value = base.strip()
    if not value:
        raise ValueError('base commit cannot be empty')
    return _run_git(repo_root, 'rev-parse', '--verify', f'{value}^{{commit}}').strip()


def _content_identity(repo_root: Path, repo_path: str) -> dict[str, object]:
    path = repo_root / repo_path
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {'path': repo_path, 'state': 'missing'}
    mode = stat.S_IMODE(metadata.st_mode)
    if stat.S_ISLNK(metadata.st_mode):
        payload = os.readlink(path).encode('utf-8', errors='surrogateescape')
        kind = 'symlink'
    elif stat.S_ISREG(metadata.st_mode):
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ChangeSnapshotError(f'cannot read changed file {repo_path}: {exc}') from exc
        kind = 'file'
    elif stat.S_ISDIR(metadata.st_mode):
        payload = b''
        kind = 'directory'
    else:
        payload = b''
        kind = 'other'
    return {
        'path': repo_path,
        'state': kind,
        'mode': mode,
        'sha256': hashlib.sha256(payload).hexdigest(),
    }


def _fingerprint(
    repo_root: Path,
    *,
    source: str,
    head: str | None,
    base: str | None,
    files: tuple[str, ...],
) -> str:
    payload = {
        'source': source,
        'head': head,
        'base': base,
        'files': [_content_identity(repo_root, path) for path in files],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def capture_change_snapshot(
    repo_root: Path,
    *,
    mode: ExecutionMode | str = ExecutionMode.INCREMENTAL,
    base: str | None = None,
    changed_files: Iterable[str] | None = None,
) -> ChangeSnapshot:
    """采集 full 或 incremental 输入，不读取 session/runtime 证据。

    Incremental 只允许一种显式来源（``base`` 或 ``changed_files``），否则使用
    当前 Git staged/working/untracked 快照。Full 记录 HEAD，但不携带 changed files。
    """

    root = repo_root.resolve()
    if base is not None and changed_files is not None:
        raise ValueError('base and changed-files inputs are mutually exclusive')
    if isinstance(changed_files, str):
        raise TypeError('changed-files input must be an iterable of paths, not a string')
    selected_mode = ExecutionMode(mode)
    head = _resolve_head(root)
    resolved_base: str | None = None

    if selected_mode is ExecutionMode.FULL:
        if base is not None or changed_files is not None:
            raise ValueError('full mode does not accept base or changed-files input')
        source, files = _SOURCE_FULL, ()
    elif base is not None:
        source = _SOURCE_BASE
        resolved_base = _resolve_base(root, base)
        files = _nul_paths(
            _run_git(
                root,
                'diff',
                '--name-only',
                '--diff-filter=ACMRD',
                '-z',
                f'{resolved_base}...HEAD',
            )
        )
    elif changed_files is not None:
        source, files = _SOURCE_EXPLICIT, _normalize_files(changed_files)
    else:
        source, files = _SOURCE_WORKTREE, _capture_worktree_files(root)

    return ChangeSnapshot(
        source=source,
        head=head,
        base=resolved_base,
        files=files,
        content_fingerprint=_fingerprint(
            root,
            source=source,
            head=head,
            base=resolved_base,
            files=files,
        ),
    )
