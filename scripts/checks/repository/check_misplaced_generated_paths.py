#!/usr/bin/env python3
"""检查 manifest 禁止的生成路径是否直接出现在仓库磁盘上。

该检查阻止运行产物污染仓库工作区，同时不读取其内容。唯一入口 ``check(arguments)`` 返回配置
错误或按 manifest 顺序排列的路径诊断；任一诊断都表示仓库边界不可信。
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from scripts.checks._framework import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()
MANIFEST_RELATIVE_PATH = Path('harness/manifest.yaml')
MANIFEST_KEY = 'forbidden_generated_paths'


def _load_forbidden_paths(manifest_path: Path) -> tuple[str, ...]:
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


def _path_exists(path: Path) -> bool:
    """检查普通路径及悬空 symlink，避免 Git ignore 状态影响结果。"""
    return path.exists() or os.path.lexists(path)


def _find_misplaced_paths(root: Path, forbidden_paths: tuple[str, ...]) -> tuple[str, ...]:
    """返回磁盘上实际存在的禁止路径。"""
    return tuple(path for path in forbidden_paths if _path_exists(root / path))


def check(arguments: list[str]) -> CheckResult:
    """解析仓库与 manifest 参数并返回所有误放生成路径。"""
    parser = argument_parser(
        description='Fail when generated paths are misplaced in the repository'
    )
    parser.add_argument('--root', default=str(REPO_ROOT), help='Repository root to inspect')
    parser.add_argument(
        '--manifest',
        help='Manifest path; relative paths are resolved from --root',
    )
    args = parser.parse_args(arguments)

    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else MANIFEST_RELATIVE_PATH
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    try:
        forbidden_paths = _load_forbidden_paths(manifest_path)
    except ValueError as exc:
        return CheckResult.from_errors([f'misplaced-generated-paths configuration error: {exc}'])

    findings = _find_misplaced_paths(root, forbidden_paths)
    return CheckResult.from_errors(f'misplaced generated path exists: {path}' for path in findings)
