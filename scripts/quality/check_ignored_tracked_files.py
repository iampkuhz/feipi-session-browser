#!/usr/bin/env python3
"""检查被 ignore 规则命中的路径是否被加入 Git 追踪。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
GIT_TIMEOUT_SECONDS = 30

from scripts.quality._trigger import add_changed_files_arg, parse_changed_files, skip_if_not_triggered

TRIGGER_PATTERNS = [
    '.gitignore',
    'scripts/quality/check_ignored_tracked_files.py',
    'scripts/quality/run_required_quality_gates.py',
    'scripts/quality/run_quality_gate.py',
]


@dataclass(frozen=True)
class IgnoredTrackedFinding:
    """表示一条 ignored tracked 路径发现。"""

    path: str
    source: str
    line: str
    pattern: str


# 运行git 命令。
def _run_git(
    root: Path,
    args: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """参数：
        root: Git worktree 根目录。
        args: git 子命令参数。
        input_bytes: 可选 stdin bytes。

    返回：
        CompletedProcess 结果。
    """
    return subprocess.run(
        ['git', *args],
        cwd=root,
        input=input_bytes,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )


# 判断是否Git worktree。
def is_git_worktree(root: Path) -> bool:
    """参数：
        root: 待检查目录。

    返回：
        目录是否位于 Git worktree 内。
    """
    proc = _run_git(root, ['rev-parse', '--is-inside-work-tree'])
    return proc.returncode == 0 and proc.stdout.strip() == b'true'


# 解析NUL 分隔路径。
def _split_nul_paths(raw: bytes) -> list[str]:
    """参数：
        raw: NUL 分隔路径 bytes。

    返回：
        解码后的路径列表。
    """
    return [item.decode('utf-8', errors='replace') for item in raw.split(b'\0') if item]


# 读取staged 候选路径。
def staged_candidate_paths(root: Path) -> list[str]:
    """参数：
        root: Git worktree 根目录。

    返回：
        staged 新增、复制、修改、重命名路径列表；删除用于清理，不阻断。
    """
    proc = _run_git(root, ['diff', '--cached', '--name-only', '-z', '--diff-filter=ACMR'])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode('utf-8', errors='replace').strip())
    return _split_nul_paths(proc.stdout)


# 读取所有追踪路径。
def tracked_paths(root: Path) -> list[str]:
    """参数：
        root: Git worktree 根目录。

    返回：
        Git index 中的所有追踪路径。
    """
    proc = _run_git(root, ['ls-files', '-z'])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode('utf-8', errors='replace').strip())
    return _split_nul_paths(proc.stdout)


# 解析 check-ignore 输出。
def _parse_check_ignore_output(raw: bytes) -> list[IgnoredTrackedFinding]:
    """参数：
        raw: `git check-ignore -v -z` 输出。

    返回：
        被最终 ignore 规则命中的路径列表。
    """
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
        findings.append(
            IgnoredTrackedFinding(path=path, source=source, line=line, pattern=pattern)
        )
    return findings


# 找出ignored paths。
def ignored_paths(root: Path, paths: list[str]) -> list[IgnoredTrackedFinding]:
    """参数：
        root: Git worktree 根目录。
        paths: 需要按 ignore 规则检查的路径列表。

    返回：
        被 ignore 规则命中且未被否定规则恢复的路径发现。
    """
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


# 打印报告。
def print_report(mode: str, candidates: list[str], findings: list[IgnoredTrackedFinding]) -> None:
    """参数：
        mode: 检查模式。
        candidates: 候选路径。
        findings: 检查发现。
    """
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


# 解析候选路径。
def collect_candidates(root: Path, mode: str) -> list[str]:
    """参数：
        root: Git worktree 根目录。
        mode: 检查模式，表示暂存区或全量追踪。

    返回：
        候选路径列表。
    """
    if mode == 'staged':
        return staged_candidate_paths(root)
    return tracked_paths(root)


# 解析命令行并执行。
def main(argv: list[str] | None = None) -> int:
    """参数：
        argv: 可选命令行参数。

    返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(
        description='Fail when ignored paths are staged or tracked by Git'
    )
    parser.add_argument('--root', default=str(REPO_ROOT), help='Repository root to inspect')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--staged',
        action='store_true',
        help='Check staged added/copied/modified/renamed paths (default)',
    )
    mode.add_argument('--all-tracked', action='store_true', help='Audit all tracked paths')
    add_changed_files_arg(parser)
    args = parser.parse_args(argv)

    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    skip_if_not_triggered(parse_changed_files(args.changed_files), TRIGGER_PATTERNS)

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


if __name__ == '__main__':
    raise SystemExit(main())
