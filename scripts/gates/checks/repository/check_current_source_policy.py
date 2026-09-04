"""检查源码是否始终只描述当前受支持状态。

本检查用于防止已清理内容回流，只保留跨仓库历史版本残留与 Harness 当前态两类规则。
Web 静态资源契约由 Java ``static-resource-contract`` 唯一拥有。唯一公开入口是
``check(arguments)``；返回诊断表示当前态政策违规或扫描失败。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from scripts.gates.checks.check_protocol import CheckResult, argument_parser

# 当前态文档和源码中禁止保留的历史版本标记。
HISTORICAL_VERSION_PATTERNS = [
    re.compile(r'HIFI\s+v\d+', re.IGNORECASE),
    re.compile(r'session_browser_hifi_v', re.IGNORECASE),
    re.compile(r'session-detail-payload-v', re.IGNORECASE),
    re.compile(r'DEPRECATED\s+T\d+', re.IGNORECASE),
    re.compile(r'migrated\s+Task\s+\d+', re.IGNORECASE),
    re.compile(r'gate-catalog:v\d+', re.IGNORECASE),
    re.compile(r'Catalog\s+v\d+', re.IGNORECASE),
]
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
EXCLUDED_FILE_NAMES = {'check_current_source_policy.py', 'test_current_source_policy.py'}


def _iter_current_text_files(repo_root: Path) -> list[Path]:
    """单次遍历仓库文本文件，并在进入本地缓存或历史 change 前剪枝。"""

    files: list[Path] = []
    for current, directories, names in os.walk(repo_root):
        current_path = Path(current)
        relative = current_path.relative_to(repo_root)

        # 直接剪掉大体积本地目录，避免先递归再逐文件过滤。
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
    """incremental 时读取 Planner 传入的路径；full 或无请求环境时返回全量标记。"""

    if os.environ.get('QUALITY_EXECUTION_MODE') != 'incremental':
        return None
    raw = os.environ.get('QUALITY_CHANGED_FILES')
    if raw is None:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError('QUALITY_CHANGED_FILES 必须是 JSON array')
    return [str(item) for item in parsed]


def _check_no_historical_version_comments(
    files: list[Path],
) -> tuple[list[str], list[str]]:
    """检查历史版本标记；仓库只描述当前状态，命中即阻断。"""
    errors: list[str] = []
    warnings: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except (OSError, UnicodeError) as exc:
            warnings.append(f'{path}: unreadable-source: {exc}')
            continue
        for pattern in HISTORICAL_VERSION_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                errors.append(
                    f'{path}: 发现历史版本注释模式 '
                    f"'{matches[0]}'（共 {len(matches)} 处），"
                    f'必须清理（rule: no-historical-version-comments）。'
                )
    return errors, warnings


# Harness 只描述当前可执行状态，不保留迁移或删除历史。
HARNESS_FORBIDDEN_PATTERNS = [
    (re.compile(r'deleted', re.IGNORECASE), 'deleted'),
    (re.compile(r'已删除', re.IGNORECASE), '已删除'),
    (re.compile(r'\bchangelog\b', re.IGNORECASE), 'changelog'),
    (re.compile(r'\.agent/quality', re.IGNORECASE), '.agent/quality'),
    # 固定日期日志路径会迅速失效，应使用当前或动态路径。
    (re.compile(r'tmp/agent_logs/MMDD', re.IGNORECASE), 'tmp/agent_logs/MMDD'),
]

# 否定或规则说明语境不代表维护历史状态，允许保留。
HARNESS_ALLOWED_CONTEXT = [
    re.compile(r'禁止.*deleted', re.IGNORECASE),
    re.compile(r'不存在.*deleted', re.IGNORECASE),
    re.compile(r'no.*deleted', re.IGNORECASE),
]


def _line_has_allowed_context(line: str) -> bool:
    """判断禁用词是否处于明确允许的否定或规则说明语境。"""
    for ctx in HARNESS_ALLOWED_CONTEXT:
        if ctx.search(line):
            return True
    return False


def _check_harness_current_state(
    harness_files: list[Path],
) -> tuple[list[str], list[str]]:
    """检查 Harness 是否只描述当前可执行状态；非豁免命中即阻断。"""
    errors: list[str] = []
    warnings: list[str] = []
    for path in harness_files:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except (OSError, UnicodeError) as exc:
            warnings.append(f'{path}: unreadable-source: {exc}')
            continue
        for pattern, label in HARNESS_FORBIDDEN_PATTERNS:
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    # 先识别否定语境，避免规则说明自身触发门禁。
                    if _line_has_allowed_context(line):
                        continue
                    errors.append(
                        f"{path}:{lineno}: harness 中出现 '{label}' "
                        f'（rule: harness-current-state-only），'
                        f'harness 应只描述当前状态。'
                    )
    return errors, warnings


def _check_current_source_policy(
    repo_root: Path, changed_files: list[str] | None = None
) -> tuple[list[str], list[str]]:
    """运行历史版本残留与 Harness 当前态检查并分别汇总错误与告警。"""
    errors: list[str] = []
    warnings: list[str] = []

    text_files = (
        _iter_current_text_files(repo_root)
        if changed_files is None
        else _changed_text_files(repo_root, changed_files)
    )
    e, w = _check_no_historical_version_comments(text_files)
    errors.extend(e)
    warnings.extend(w)

    harness_dir = repo_root / 'harness'
    if harness_dir.exists():
        harness_files = (
            list(harness_dir.rglob('*.md')) + list(harness_dir.rglob('*.yaml'))
            if changed_files is None
            else [path for path in text_files if path.is_relative_to(harness_dir)]
        )
        e, w = _check_harness_current_state(harness_files)
        errors.extend(e)
        warnings.extend(w)

    return errors, warnings


def check(arguments: list[str]) -> CheckResult:
    """解析仓库根目录并返回全部当前源码政策阻断项。"""
    parser = argument_parser(description='Check current source policy.')
    parser.add_argument('--root', default='.', help='Repository root to inspect')
    args = parser.parse_args(arguments)

    try:
        errors, scan_failures = _check_current_source_policy(
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
    if scan_failures:
        return CheckResult.execution_failure([*errors, *scan_failures], reason='input-unavailable')
    return CheckResult.from_errors(f'[BLOCK] {item}' for item in errors)
