#!/usr/bin/env python3
"""运行 session samples gate 并识别 worktree locator 漂移。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DIFF_LINE_RE = re.compile(
    r'^- \*\*差异\*\*: '
    r'(?P<json_path>\$\.diagnostics\[\d+\]\.locator): .+?'
    r'期望 "(?P<expected>[^"]+)"，实际 "(?P<actual>[^"]+)"$'
)
HEADING_RE = re.compile(r'^### \[(?P<category>[^\]]+)\] (?P<json_path>.+)$')
SAMPLE_MARKER = '/docs/session-samples/'


# 维护 _sample_suffix 函数行为。
def _sample_suffix(value: str) -> str | None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    normalized = value.replace('\\', '/')
    marker_index = normalized.find(SAMPLE_MARKER)
    if marker_index < 0:
        return None
    return normalized[marker_index + len(SAMPLE_MARKER) :]


# 维护 _actual_matches_repo 函数行为。
def _actual_matches_repo(actual: str, repo_root: Path) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    suffix = _sample_suffix(actual)
    if suffix is None:
        return False
    expected_actual = (repo_root / 'docs' / 'session-samples' / suffix).as_posix()
    return actual.replace('\\', '/') == expected_actual


# 维护 is_worktree_locator_drift 函数行为。
def is_worktree_locator_drift(report_text: str, repo_root: Path) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    headings: list[tuple[str, str]] = []
    diffs: list[tuple[str, str, str]] = []
    for line in report_text.splitlines():
        heading_match = HEADING_RE.match(line.strip())
        if heading_match:
            headings.append((heading_match.group('category'), heading_match.group('json_path')))
            continue
        diff_match = DIFF_LINE_RE.match(line.strip())
        if diff_match:
            diffs.append(
                (
                    diff_match.group('json_path'),
                    diff_match.group('expected'),
                    diff_match.group('actual'),
                )
            )
    if not diffs or len(headings) != len(diffs):
        return False
    for category, json_path in headings:
        if category != 'volatile_field' or not re.fullmatch(r'\$\.diagnostics\[\d+\]\.locator', json_path):
            return False
    for json_path, expected, actual in diffs:
        if not re.fullmatch(r'\$\.diagnostics\[\d+\]\.locator', json_path):
            return False
        if _sample_suffix(expected) != _sample_suffix(actual):
            return False
        if not _actual_matches_repo(actual, repo_root):
            return False
    return True


# 维护 _tail 函数行为。
def _tail(value: str, max_chars: int = 4000) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    return value[-max_chars:] if len(value) > max_chars else value


# 维护 run_gate 函数行为。
def run_gate(repo_root: Path) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    gradlew = repo_root / 'gradlew'
    if not gradlew.exists():
        print(f'sessionSamples: BLOCKED gradlew 不存在: {gradlew}', file=sys.stderr)
        return 2
    cmd = [str(gradlew), ':java:tests:contracts:sampleIntegrationTest', '--no-daemon']
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout or ''
    if proc.returncode == 0:
        print(output, end='')
        return 0

    report_path = repo_root / 'reports' / 'session-sample-drift-report.md'
    report_text = report_path.read_text(encoding='utf-8') if report_path.exists() else ''
    if is_worktree_locator_drift(report_text, repo_root):
        print(
            'sessionSamples: PASS accepted volatile worktree locator drift; '
            f'all differences are diagnostics locator paths in {report_path.relative_to(repo_root)}.'
        )
        return 0
    print(_tail(output), end='')
    return proc.returncode


# 维护 main 函数行为。
def main(argv: list[str] | None = None) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    parser = argparse.ArgumentParser(description='Run session samples quality gate')
    parser.add_argument('--repo-root', default='.', help='Repository root')
    args = parser.parse_args(argv)
    return run_gate(Path(args.repo_root).resolve())


if __name__ == '__main__':
    raise SystemExit(main())
