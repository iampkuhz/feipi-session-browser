"""检查仓库内部标识是否保持稳定且不携带版本后缀。

稳定标识避免同一职责以数字后缀形成并行入口。唯一公开入口是 ``check(arguments)``；返回诊断表示
当前文本使用了版本化内部名称，返回执行失败表示输入路径无法可靠读取。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from scripts.gates.checks.check_protocol import CheckResult, argument_parser

INTERNAL_VERSION_SUFFIX = re.compile(
    r'\b[a-z][a-z0-9_-]*(?:catalog|payload|schema|profile)[._:-]?v\d+\b',
    re.IGNORECASE,
)
TEXT_SUFFIXES = frozenset({'.css', '.js', '.html', '.py', '.md', '.sh', '.yaml', '.json', '.txt'})
EXCLUDED_DIRECTORY_NAMES = {
    '.git',
    'node_modules',
    '__pycache__',
    '.pytest_cache',
    'tmp',
    '.mypy_cache',
    'dist',
    'venv',
    '.local',
}
CLIENT_CONFIG_ROOTS = {'.claude', '.codex', '.qoder'}
EXCLUDED_FILE_NAMES = {'check_current_version.py', 'test_current_version.py'}


def _iter_current_text_files(repo_root: Path) -> list[Path]:
    """单次遍历当前 checkout 文本，并在进入本地运行目录前剪枝。"""

    files: list[Path] = []
    for current, directories, names in os.walk(repo_root):
        current_path = Path(current)
        relative = current_path.relative_to(repo_root)
        directories[:] = [name for name in directories if name not in EXCLUDED_DIRECTORY_NAMES]
        if relative == Path('openspec'):
            directories[:] = [name for name in directories if name != 'changes']
        if relative.parts and relative.parts[0] in CLIENT_CONFIG_ROOTS:
            directories[:] = [name for name in directories if name != 'worktrees']
        files.extend(
            current_path / name
            for name in names
            if name not in EXCLUDED_FILE_NAMES
            and (current_path / name).suffix.lower() in TEXT_SUFFIXES
        )
    return files


def _changed_text_files(repo_root: Path, changed_files: list[str]) -> list[Path]:
    """把 incremental 路径收敛为当前 checkout 内实际存在的文本文件。"""

    root = repo_root.resolve()
    files: list[Path] = []
    for relative in changed_files:
        candidate = (root / relative).resolve()
        try:
            normalized = candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f'changed file 超出仓库: {relative}') from exc
        if (
            not candidate.is_file()
            or candidate.name in EXCLUDED_FILE_NAMES
            or candidate.suffix.lower() not in TEXT_SUFFIXES
            or any(part in EXCLUDED_DIRECTORY_NAMES for part in normalized.parts)
            or normalized.parts[:2] == ('openspec', 'changes')
            or (
                len(normalized.parts) >= 2
                and normalized.parts[0] in CLIENT_CONFIG_ROOTS
                and normalized.parts[1] == 'worktrees'
            )
        ):
            continue
        files.append(candidate)
    return sorted(set(files))


def _incremental_paths_from_environment() -> list[str] | None:
    """incremental 时读取 Planner 传入路径；full 请求返回全量标记。"""

    if os.environ.get('QUALITY_EXECUTION_MODE') != 'incremental':
        return None
    raw = os.environ.get('QUALITY_CHANGED_FILES')
    if raw is None:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError('QUALITY_CHANGED_FILES 必须是 JSON array')
    return [str(item) for item in parsed]


def _check_stable_internal_names(files: list[Path]) -> tuple[list[str], list[str]]:
    """报告版本化内部标识，并把无法读取的输入单独归类。"""

    errors: list[str] = []
    read_failures: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except (OSError, UnicodeError) as exc:
            read_failures.append(f'{path}: unreadable-source: {exc}')
            continue
        matches = INTERNAL_VERSION_SUFFIX.findall(text)
        if matches:
            errors.append(
                f'{path}: 内部标识必须使用稳定名称，发现“{matches[0]}”'
                f'（共 {len(matches)} 处；rule: stable-internal-name）。'
            )
    return errors, read_failures


def _check_current_version(
    repo_root: Path, changed_files: list[str] | None = None
) -> tuple[list[str], list[str]]:
    """按 full 或 incremental 范围检查稳定内部名称。"""

    text_files = (
        _iter_current_text_files(repo_root)
        if changed_files is None
        else _changed_text_files(repo_root, changed_files)
    )
    return _check_stable_internal_names(text_files)


def check(arguments: list[str]) -> CheckResult:
    """解析仓库根目录并返回全部当前版本政策诊断。"""

    parser = argument_parser(description='Check stable internal version names.')
    parser.add_argument('--root', default='.', help='Repository root to inspect')
    args = parser.parse_args(arguments)

    try:
        errors, read_failures = _check_current_version(
            Path(args.root).resolve(), _incremental_paths_from_environment()
        )
    except (json.JSONDecodeError, ValueError) as exc:
        return CheckResult.execution_failure(
            [f'incremental 路径输入无效: {exc}'], reason='input-unavailable'
        )
    except (OSError, UnicodeError) as exc:
        return CheckResult.execution_failure(
            [f'无法枚举待检查源码: {exc}'], reason='input-unavailable'
        )
    if read_failures:
        return CheckResult.execution_failure([*errors, *read_failures], reason='input-unavailable')
    return CheckResult.from_errors(f'[BLOCK] {item}' for item in errors)
