#!/usr/bin/env python3
"""本模块负责检查 manifest 禁止的生成路径是否直接出现在仓库磁盘上。

不负责删除或读取生成内容；由 Gate executor、doctor 或维护者命令行调用。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

from scripts.checks._framework import argument_parser, repository_root

REPO_ROOT = repository_root()
MANIFEST_RELATIVE_PATH = Path('harness/manifest.yaml')
MANIFEST_KEY = 'forbidden_generated_paths'


def load_forbidden_paths(manifest_path: Path) -> tuple[str, ...]:
    """从 harness manifest 读取唯一的禁止生成路径清单。"""
    try:
        document = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f'cannot read manifest {manifest_path}: {exc}') from exc
    if not isinstance(document, dict):
        raise ValueError(f'manifest must be a mapping: {manifest_path}')
    paths = document.get(MANIFEST_KEY)
    if not isinstance(paths, list) or not paths:
        raise ValueError(f'manifest key {MANIFEST_KEY!r} must be a non-empty list')

    normalized: list[str] = []
    for value in paths:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{MANIFEST_KEY} entries must be non-empty strings')
        relative = Path(value)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'{MANIFEST_KEY} entry must be repository-relative: {value}')
        normalized.append(relative.as_posix())
    if len(normalized) != len(set(normalized)):
        raise ValueError(f'{MANIFEST_KEY} entries must be unique')
    return tuple(normalized)


def path_exists(path: Path) -> bool:
    """检查普通路径及悬空 symlink，避免 Git ignore 状态影响结果。"""
    return path.exists() or os.path.lexists(path)


def find_misplaced_paths(root: Path, forbidden_paths: tuple[str, ...]) -> tuple[str, ...]:
    """返回磁盘上实际存在的禁止路径。"""
    return tuple(path for path in forbidden_paths if path_exists(root / path))


def main(argv: list[str] | None = None) -> int:
    """执行禁止生成路径检查。"""
    parser = argument_parser(description='Fail when generated paths are misplaced in the repository')
    parser.add_argument('--root', default=str(REPO_ROOT), help='Repository root to inspect')
    parser.add_argument(
        '--manifest',
        help='Manifest path; relative paths are resolved from --root',
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else MANIFEST_RELATIVE_PATH
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    try:
        forbidden_paths = load_forbidden_paths(manifest_path)
    except ValueError as exc:
        print(f'misplaced-generated-paths configuration error: {exc}', file=sys.stderr)
        return 2

    findings = find_misplaced_paths(root, forbidden_paths)
    if findings:
        for path in findings:
            print(f'misplaced generated path exists: {path}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
