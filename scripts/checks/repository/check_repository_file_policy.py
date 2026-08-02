"""统一检查仓库文件边界。

本文件只负责四件事：必需的工程入口必须存在；``harness/manifest.yaml`` 声明的禁止
根路径不得落在仓库磁盘；被 ``.gitignore`` 忽略的文件不得进入 Git；禁止根路径和
数据库文件不得进入 Git。Git 或配置无法可靠读取时直接失败，避免检查异常被误当成通过。
唯一公开入口是 ``check(arguments)``，返回诊断表示仓库文件边界不符合政策。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml
from scripts.checks._framework import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()
MANIFEST_RELATIVE_PATH = Path('harness/manifest.yaml')
MANIFEST_KEY = 'forbidden_root_paths'
GIT_TIMEOUT_SECONDS = 30

# 仓库运行与维护依赖的稳定入口。重命名入口时必须同步更新这里和对应测试。
REQUIRED_PATHS = (
    'scripts/gates/catalog.py',
    'scripts/gates/model.py',
    'scripts/gates/planner.py',
    'scripts/gates/cli.py',
    'scripts/gates/executor.py',
    'scripts/gates/report.py',
    'scripts/checks/repository/check_acceptance_case_mapping.py',
    'harness/agent-policy.manifest.yaml',
    'harness/skill-registry.yaml',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'harness/README.md',
    'docs/acceptance-cases/README.md',
)
DATABASE_SUFFIXES = ('.sqlite', '.sqlite3', '.db')


@dataclass(frozen=True)
class _IgnoredTrackedFinding:
    """保存一条被 ignore 规则命中却仍受 Git 追踪的路径。"""

    path: str
    source: str
    line: str
    pattern: str


def _run_git(
    root: Path,
    args: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """执行 Git 命令；启动失败和超时由调用方统一转换为阻断诊断。"""
    return subprocess.run(
        ['git', *args],
        cwd=root,
        input=input_bytes,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )


def _git_output(root: Path, args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    """读取必须成功的 Git 输出，任何错误都采用 fail-closed。"""
    try:
        result = _run_git(root, args, input_bytes=input_bytes)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git {' '.join(args)} failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail or result.returncode}")
    return result.stdout


def _split_nul_paths(raw: bytes) -> list[str]:
    """解析 NUL 分隔路径，确保空格和特殊字符不会破坏路径边界。"""
    return [item.decode('utf-8', errors='replace') for item in raw.split(b'\0') if item]


def _load_forbidden_paths(manifest_path: Path) -> tuple[str, ...]:
    """只从 manifest 的 ``forbidden_root_paths`` 读取禁止路径真源。"""
    try:
        document = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
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
        if relative.is_absolute() or '..' in relative.parts or relative == Path('.'):
            raise ValueError(f'{MANIFEST_KEY} entry must be repository-relative: {value}')
        normalized.append(relative.as_posix().rstrip('/'))
    if len(normalized) != len(set(normalized)):
        raise ValueError(f'{MANIFEST_KEY} entries must be unique')
    return tuple(normalized)


def _path_exists(path: Path) -> bool:
    """同时识别正常路径和悬空符号链接。"""
    return path.exists() or os.path.lexists(path)


def _candidate_paths(root: Path, all_tracked: bool) -> list[str]:
    """读取本次新增/修改路径或全部追踪路径，并排除正在删除的清理项。"""
    args = (
        ['ls-files', '-z']
        if all_tracked
        else ['diff', '--cached', '--name-only', '-z', '--diff-filter=ACMR']
    )
    paths = _split_nul_paths(_git_output(root, args))
    return [path for path in paths if _path_exists(root / path)]


def _ignored_findings(root: Path, paths: list[str]) -> tuple[_IgnoredTrackedFinding, ...]:
    """找出最终被 ignore 规则命中的路径；否定规则恢复的路径不报错。"""
    if not paths:
        return ()
    payload = ''.join(f'{path}\0' for path in paths).encode()
    try:
        result = _run_git(
            root,
            [
                '-c',
                'core.excludesFile=/dev/null',
                'check-ignore',
                '--no-index',
                '-v',
                '-z',
                '--stdin',
            ],
            input_bytes=payload,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'git check-ignore failed: {exc}') from exc
    if result.returncode == 1:
        return ()
    if result.returncode != 0:
        detail = result.stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'git check-ignore failed: {detail or result.returncode}')

    parts = result.stdout.split(b'\0')
    findings: list[_IgnoredTrackedFinding] = []
    for index in range(0, len(parts) - 1, 4):
        if index + 3 >= len(parts):
            break
        source, line, pattern, path = (
            value.decode('utf-8', errors='replace') for value in parts[index : index + 4]
        )
        if not pattern.startswith('!'):
            findings.append(_IgnoredTrackedFinding(path, source, line, pattern))
    return tuple(findings)


def _is_below(path: str, root_path: str) -> bool:
    """判断 Git 路径是否等于或位于某个禁止根路径下。"""
    return path == root_path or path.startswith(f'{root_path}/')


def _validate(root: Path, manifest_path: Path, all_tracked: bool) -> list[str]:
    """一次完成磁盘入口、禁止路径和 Git 追踪边界检查。"""
    forbidden_paths = _load_forbidden_paths(manifest_path)
    errors = [f'缺少必需路径: {path}' for path in REQUIRED_PATHS if not _path_exists(root / path)]
    errors.extend(
        f'禁止根路径不应出现在仓库磁盘: {path}'
        for path in forbidden_paths
        if _path_exists(root / path)
    )

    candidates = _candidate_paths(root, all_tracked)
    errors.extend(
        f'{item.path}: 被 ignore 规则追踪 ({item.source}:{item.line}:{item.pattern})'
        for item in _ignored_findings(root, candidates)
    )
    for path in candidates:
        if any(_is_below(path, forbidden) for forbidden in forbidden_paths):
            errors.append(f'禁止根路径不应进入 Git tracked: {path}')
        if path.lower().endswith(DATABASE_SUFFIXES):
            errors.append(f'数据库文件不应进入 Git tracked: {path}')
    return errors


def check(arguments: list[str]) -> CheckResult:
    """解析检查范围并返回全部仓库文件政策违规。"""
    parser = argument_parser(description='Validate repository file policy')
    parser.add_argument('--root', default=str(REPO_ROOT), help='Repository root to inspect')
    parser.add_argument('--manifest', help='Manifest path, relative to --root by default')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--staged', action='store_true', help='Check staged changed paths')
    mode.add_argument('--all-tracked', action='store_true', help='Check every tracked path')
    args = parser.parse_args(arguments)

    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else MANIFEST_RELATIVE_PATH
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    try:
        errors = _validate(root, manifest_path, args.all_tracked)
    except (RuntimeError, ValueError) as exc:
        return CheckResult.from_errors([f'repository file policy cannot inspect repository: {exc}'])
    return CheckResult.from_errors(errors)
