#!/usr/bin/env python3
"""提供 检查 no test skips 脚本能力。"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class PatternRule:
    """表示 PatternRule。

    属性：
        name: 名称。
        regex: regex 参数。
        message: 用户可读消息。
    """

    name: str
    regex: re.Pattern[str]
    message: str


PYTHON_RULES = [
    PatternRule(
        'pytest-runtime-skip',
        re.compile(r'\bpytest\s*\.\s*skip\s*\('),
        'pytest runtime skip is forbidden; provide deterministic fixtures or fail explicitly.',
    ),
    PatternRule(
        'pytest-importorskip',
        re.compile(r'\bpytest\s*\.\s*importorskip\s*\('),
        'pytest importorskip is forbidden; add the dependency or avoid the optional path.',
    ),
    PatternRule(
        'pytest-skip-marker',
        re.compile(r'\bpytest\s*\.\s*mark\s*\.\s*skip(?:if)?\b'),
        'pytest skip markers are forbidden; remove the test from the target or make '
        'it deterministic.',
    ),
    PatternRule(
        'unittest-skip',
        re.compile(r'\bunittest\s*\.\s*skip(?:If|Unless)?\s*\('),
        'unittest skip decorators are forbidden in repository tests.',
    ),
    PatternRule(
        'unittest-skip-test',
        re.compile(r'\bskipTest\s*\('),
        'unittest runtime skipTest is forbidden in repository tests.',
    ),
]

PLAYWRIGHT_RULES = [
    PatternRule(
        'playwright-test-skip',
        re.compile(r'\btest\s*\.\s*skip\s*\('),
        'Playwright test.skip is forbidden; use fixture setup or explicit assertions.',
    ),
    PatternRule(
        'playwright-describe-skip',
        re.compile(r'\btest\s*\.\s*describe\s*\.\s*skip\b'),
        'Playwright describe-level skip is forbidden.',
    ),
    PatternRule(
        'playwright-fixme',
        re.compile(r'\btest\s*\.\s*fixme\s*\('),
        'Playwright fixme annotations are forbidden because they produce skipped outcomes.',
    ),
]

COMMENT_LINE_RE = re.compile(r'^\s*(#|//|/\*|\*)')


@dataclass(frozen=True)
class Finding:
    """表示一条 Finding 检查发现。

    属性：
        file: 待检查的文件。
        line: 待检查的源码行。
        rule: rule 参数。
        message: 用户可读消息。
        snippet: snippet 参数。
    """

    file: str
    line: int
    rule: str
    message: str
    snippet: str


# 维护遍历 文件。
def _iter_files(root: Path, relative_roots: list[str], suffixes: tuple[str, ...]) -> list[Path]:
    """参数：
        root: 扫描根目录。
        relative_roots: Relative 目录 或 文件以检查。
        suffixes: 文件 suffixes included in 结果。

    返回：
        结果列表。
    """
    files: list[Path] = []
    for rel in relative_roots:
        path = root / rel
        if path.is_file() and path.suffix in suffixes:
            files.append(path)
            continue
        if not path.is_dir():
            continue
        for suffix in suffixes:
            files.extend(path.rglob(f'*{suffix}'))
    return sorted(set(files))


# 判断是否注释 仅。
def _is_comment_only(line: str) -> bool:
    """参数：
        line: source 行到classify。

    返回：
        当scanning should ignore 行 as comment-仅.时返回 true。
    """
    return bool(COMMENT_LINE_RE.match(line.strip()))


# 维护扫描 文件。
def scan_file(path: Path, root: Path, rules: list[PatternRule]) -> list[Finding]:
    """参数：
        path: 文件以检查。
        root: 扫描根目录。
        rules: 用于匹配的规则集合。

    返回：
        结果列表。
    """
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return []

    try:
        rel_path = str(path.relative_to(root))
    except ValueError:
        rel_path = str(path)

    findings: list[Finding] = []
    for line_no, line in enumerate(lines, start=1):
        if _is_comment_only(line):
            continue
        for rule in rules:
            if rule.regex.search(line):
                findings.append(
                    Finding(
                        file=rel_path,
                        line=line_no,
                        rule=rule.name,
                        message=rule.message,
                        snippet=line.strip()[:160],
                    )
                )
    return findings


# 维护扫描 repo。
def scan_repo(root: Path = REPO_ROOT) -> list[Finding]:
    """参数：
        root: repo root containing `tests` 和 可选 Playwright config 文件。

    返回：
        结果列表。
    """
    python_files = _iter_files(root, ['tests'], ('.py',))
    playwright_files = _iter_files(root, ['tests', 'playwright.config.js'], ('.js', '.ts'))

    findings: list[Finding] = []
    for path in python_files:
        findings.extend(scan_file(path, root, PYTHON_RULES))
    for path in playwright_files:
        findings.extend(scan_file(path, root, PLAYWRIGHT_RULES))
    return findings


# 打印报告。
def print_report(findings: list[Finding]) -> None:
    """参数：
        findings: 已收集的检查发现列表。
    """
    print('=== no-test-skips quality gate ===')
    print(
        'Policy: selected/full/release pytest and Playwright runs must complete with '
        '0 skipped outcomes.'
    )
    print('Changed-file target mapping may be not triggered, but required tests must not skip.')
    print(f'Findings: {len(findings)}')
    if findings:
        print()
        print('Forbidden skip APIs:')
        for item in findings:
            print(f'  [FAIL] {item.file}:{item.line} {item.rule} | {item.snippet}')
            print(f'         {item.message}')


# 解析命令行参数并运行脚本入口。
def main(argv: list[str] | None = None) -> int:
    """参数：
        argv: 测试传入的可选命令行参数列表。

    返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(
        description='Fail when repository tests use pytest or Playwright skip APIs'
    )
    parser.add_argument('--root', default=str(REPO_ROOT), help='Repository root to scan')
    args = parser.parse_args(argv)

    findings = scan_repo(Path(args.root).resolve())
    print_report(findings)
    if findings:
        print()
        print(
            '结论: FAIL - 检测到测试 skip API. 请删除 skip, 改为确定性 fixture, '
            '明确断言或从触发映射中移除.'
        )
        return 1
    print('结论: PASS - 未发现 pytest/Playwright skip API.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
