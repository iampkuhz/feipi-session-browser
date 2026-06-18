#!/usr/bin/env python3
"""Fail when pytest or Playwright tests use skip APIs.

This gate protects the repository policy that required, selected, full, and
release test runs must execute with 0 skipped outcomes. Changed-file mapping can
still leave gates not triggered; it must not be represented as a test skip.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class PatternRule:
    name: str
    regex: re.Pattern[str]
    message: str


PYTHON_RULES = [
    PatternRule(
        "pytest-runtime-skip",
        re.compile(r"\bpytest\s*\.\s*skip\s*\("),
        "pytest runtime skip is forbidden; provide deterministic fixtures or fail explicitly.",
    ),
    PatternRule(
        "pytest-importorskip",
        re.compile(r"\bpytest\s*\.\s*importorskip\s*\("),
        "pytest importorskip is forbidden; add the dependency or avoid the optional path.",
    ),
    PatternRule(
        "pytest-skip-marker",
        re.compile(r"\bpytest\s*\.\s*mark\s*\.\s*skip(?:if)?\b"),
        "pytest skip markers are forbidden; remove the test from the target or make it deterministic.",
    ),
    PatternRule(
        "unittest-skip",
        re.compile(r"\bunittest\s*\.\s*skip(?:If|Unless)?\s*\("),
        "unittest skip decorators are forbidden in repository tests.",
    ),
    PatternRule(
        "unittest-skip-test",
        re.compile(r"\bskipTest\s*\("),
        "unittest runtime skipTest is forbidden in repository tests.",
    ),
]

PLAYWRIGHT_RULES = [
    PatternRule(
        "playwright-test-skip",
        re.compile(r"\btest\s*\.\s*skip\s*\("),
        "Playwright test.skip is forbidden; use fixture setup or explicit assertions.",
    ),
    PatternRule(
        "playwright-describe-skip",
        re.compile(r"\btest\s*\.\s*describe\s*\.\s*skip\b"),
        "Playwright describe-level skip is forbidden.",
    ),
    PatternRule(
        "playwright-fixme",
        re.compile(r"\btest\s*\.\s*fixme\s*\("),
        "Playwright fixme annotations are forbidden because they produce skipped outcomes.",
    ),
]

COMMENT_LINE_RE = re.compile(r"^\s*(#|//|/\*|\*)")


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    message: str
    snippet: str


def _iter_files(root: Path, relative_roots: list[str], suffixes: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for rel in relative_roots:
        path = root / rel
        if path.is_file() and path.suffix in suffixes:
            files.append(path)
            continue
        if not path.is_dir():
            continue
        for suffix in suffixes:
            files.extend(path.rglob(f"*{suffix}"))
    return sorted(set(files))


def _is_comment_only(line: str) -> bool:
    return bool(COMMENT_LINE_RE.match(line.strip()))


def scan_file(path: Path, root: Path, rules: list[PatternRule]) -> list[Finding]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
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


def scan_repo(root: Path = REPO_ROOT) -> list[Finding]:
    python_files = _iter_files(root, ["tests"], (".py",))
    playwright_files = _iter_files(root, ["tests", "playwright.config.js"], (".js", ".ts"))

    findings: list[Finding] = []
    for path in python_files:
        findings.extend(scan_file(path, root, PYTHON_RULES))
    for path in playwright_files:
        findings.extend(scan_file(path, root, PLAYWRIGHT_RULES))
    return findings


def print_report(findings: list[Finding]) -> None:
    print("=== no-test-skips quality gate ===")
    print("Policy: selected/full/release pytest and Playwright runs must complete with 0 skipped outcomes.")
    print("Changed-file target mapping may be not triggered, but required tests must not skip.")
    print(f"Findings: {len(findings)}")
    if findings:
        print()
        print("Forbidden skip APIs:")
        for item in findings:
            print(f"  [FAIL] {item.file}:{item.line} {item.rule} | {item.snippet}")
            print(f"         {item.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail when repository tests use pytest or Playwright skip APIs")
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root to scan")
    args = parser.parse_args(argv)

    findings = scan_repo(Path(args.root).resolve())
    print_report(findings)
    if findings:
        print()
        print("结论：FAIL — 检测到测试 skip API。请删除 skip，改为确定性 fixture、明确断言或从触发映射中移除。")
        return 1
    print("结论：PASS — 未发现 pytest/Playwright skip API。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
