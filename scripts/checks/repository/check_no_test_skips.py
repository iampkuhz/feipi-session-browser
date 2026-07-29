#!/usr/bin/env python3
"""检查仓库测试是否使用会产生 skipped 结果的 API。

该检查保证测试通过来自确定性 fixture 和断言，而不是测试框架的跳过标记。唯一入口
``check(arguments)`` 返回按文件、行号和规则排列的诊断；任一诊断都表示测试结果可能被跳过。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from scripts.checks._framework import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()


@dataclass(frozen=True)
class PatternRule:
    """保存 `PatternRule` 的结构化契约数据；字段由所属运行阶段构造并由后续报告读取。"""

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
    """记录一处禁用 skip API 的位置与诊断信息。"""

    file: str
    line: int
    rule: str
    message: str
    snippet: str


def _iter_files(root: Path, relative_roots: list[str], suffixes: tuple[str, ...]) -> list[Path]:
    """在指定相对路径中收集目标后缀文件，并排除依赖目录。"""
    files: list[Path] = []
    for rel in relative_roots:
        path = root / rel
        if path.is_file() and path.suffix in suffixes:
            files.append(path)
            continue
        if not path.is_dir():
            continue
        for suffix in suffixes:
            files.extend(
                candidate
                for candidate in path.rglob(f'*{suffix}')
                if 'node_modules' not in candidate.relative_to(root).parts
            )
    return sorted(set(files))


def _is_comment_only(line: str) -> bool:
    """判断一行是否只有注释，避免把示例文本误判为 skip 调用。"""
    return bool(COMMENT_LINE_RE.match(line.strip()))


def _scan_file(path: Path, root: Path, rules: list[PatternRule]) -> list[Finding]:
    """按规则扫描单个测试文件；文件不可读时不产生伪造发现。"""
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


def _scan_repo(root: Path = REPO_ROOT) -> list[Finding]:
    """扫描仓库 Python 与 Playwright 测试中的禁用 skip API。"""
    python_files = _iter_files(root, ['tests'], ('.py',))
    playwright_files = _iter_files(root, ['tests'], ('.js', '.ts'))

    findings: list[Finding] = []
    for path in python_files:
        findings.extend(_scan_file(path, root, PYTHON_RULES))
    for path in playwright_files:
        findings.extend(_scan_file(path, root, PLAYWRIGHT_RULES))
    return findings


def check(arguments: list[str]) -> CheckResult:
    """解析扫描根目录并返回所有禁用 skip API 的位置。"""
    parser = argument_parser(
        description='Fail when repository tests use pytest or Playwright skip APIs'
    )
    parser.add_argument('--root', default=str(REPO_ROOT), help='Repository root to scan')
    args = parser.parse_args(arguments)

    findings = _scan_repo(Path(args.root).resolve())
    return CheckResult.from_errors(
        f'{item.file}:{item.line} {item.rule} | {item.snippet} | {item.message}'
        for item in findings
    )
