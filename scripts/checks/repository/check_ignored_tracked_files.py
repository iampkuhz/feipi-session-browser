#!/usr/bin/env python3
"""检查被 ignore 规则命中的路径是否被加入 Git 追踪。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.checks._framework import argument_parser, repository_root

REPO_ROOT = repository_root()
GIT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class IgnoredTrackedFinding:
    """记录一条被 ignore 规则命中但已进入 Git 追踪的路径。"""

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
    """在指定 worktree 中运行有超时保护的 Git 子命令。"""
    return subprocess.run(
        ['git', *args],
        cwd=root,
        input=input_bytes,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )


def is_git_worktree(root: Path) -> bool:
    """判断目录是否位于 Git worktree 内。"""
    proc = _run_git(root, ['rev-parse', '--is-inside-work-tree'])
    return proc.returncode == 0 and proc.stdout.strip() == b'true'


def _split_nul_paths(raw: bytes) -> list[str]:
    """解析 Git 输出的 NUL 分隔路径，避免空格等字符破坏边界。"""
    return [item.decode('utf-8', errors='replace') for item in raw.split(b'\0') if item]


def staged_candidate_paths(root: Path) -> list[str]:
    """读取暂存区新增、复制、修改和重命名路径；删除操作不应被阻断。"""
    proc = _run_git(root, ['diff', '--cached', '--name-only', '-z', '--diff-filter=ACMR'])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode('utf-8', errors='replace').strip())
    return _split_nul_paths(proc.stdout)


def tracked_paths(root: Path) -> list[str]:
    """读取 Git index 中的全部追踪路径。"""
    proc = _run_git(root, ['ls-files', '-z'])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode('utf-8', errors='replace').strip())
    return _split_nul_paths(proc.stdout)


def _parse_check_ignore_output(raw: bytes) -> list[IgnoredTrackedFinding]:
    """解析 ``git check-ignore -v -z`` 输出并保留最终生效的 ignore 规则。"""
    parts = raw.split(b'\0')
    findings: list[IgnoredTrackedFinding] = []
    for index in range(0, len(parts) - 1, 4):
        if index + 3 >= len(parts):
            break
        source, line, pattern, path = (
            value.decode('utf-8', errors='replace') for value in parts[index : index + 4]
        )
        # `check-ignore --no-index -v` 会返回最终匹配的否定规则；这类路径并未被忽略。
        if pattern.startswith('!'):
            continue
        findings.append(IgnoredTrackedFinding(path=path, source=source, line=line, pattern=pattern))
    return findings


def ignored_paths(root: Path, paths: list[str]) -> list[IgnoredTrackedFinding]:
    """找出被 ignore 规则命中且未由否定规则恢复的候选路径。"""
    if not paths:
        return []
    input_bytes = ''.join(f'{path}\0' for path in paths).encode()
    proc = _run_git(
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
        input_bytes=input_bytes,
    )
    if proc.returncode == 1:
        return []
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode('utf-8', errors='replace').strip())
    return _parse_check_ignore_output(proc.stdout)


def print_report(mode: str, candidates: list[str], findings: list[IgnoredTrackedFinding]) -> None:
    """输出稳定的检查摘要与可操作发现。"""
    print('=== ignored-tracked quality gate ===')
    print('Policy: gitignore 命中的路径不得通过手工 force-add 加入 Git 追踪。')
    print(f'Mode: {mode}')
    print(f'Candidate paths: {len(candidates)}')
    print(f'Findings: {len(findings)}')
    if findings:
        print()
        for item in findings:
            print(f'  [FAIL] {item.path}')
            print(f'         matched {item.source}:{item.line}:{item.pattern}')
        print()
        print('Fix: unstage/remove the path from Git tracking, or change .gitignore explicitly.')


def collect_candidates(root: Path, mode: str) -> list[str]:
    """按检查模式读取暂存区或全量追踪路径。"""
    if mode == 'staged':
        return staged_candidate_paths(root)
    return tracked_paths(root)


def main(argv: list[str] | None = None) -> int:
    """执行 ignored-tracked 检查；Git 状态读取错误时返回阻断性退出码。"""
    parser = argument_parser(description='Fail when ignored paths are staged or tracked by Git')
    parser.add_argument('--root', default=str(REPO_ROOT), help='Repository root to inspect')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--staged',
        action='store_true',
        help='Check staged added/copied/modified/renamed paths (default)',
    )
    mode.add_argument('--all-tracked', action='store_true', help='Audit all tracked paths')
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    selected_mode = 'all-tracked' if args.all_tracked else 'staged'
    if not is_git_worktree(root):
        print('=== ignored-tracked quality gate ===')
        print(f'Root is not a Git worktree; not applicable: {root}')
        return 0

    try:
        candidates = collect_candidates(root, selected_mode)
        findings = ignored_paths(root, candidates)
    except RuntimeError as exc:
        print(f'ignored-tracked quality gate failed to inspect Git state: {exc}', file=sys.stderr)
        return 2

    print_report(selected_mode, candidates, findings)
    return 1 if findings else 0
