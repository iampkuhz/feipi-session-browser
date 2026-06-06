#!/usr/bin/env python3
"""Validate acceptance contract tables against test code bindings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import re
import sys


EXPECTED_FEATURE_TABLES = {
    "DATA_INDEX.md",
    "DATA_PRESENTERS.md",
    "DATA_SOURCES.md",
    "HOOK_HARNESS.md",
    "ROUTES_AND_API.md",
    "UI_DASHBOARD.md",
    "UI_GLOBAL_VISUAL.md",
    "UI_GLOSSARY.md",
    "UI_INTERACTIONS.md",
    "UI_PROJECTS.md",
    "UI_SESSIONS_LIST.md",
    "UI_SESSION_DETAIL.md",
}

ID_RE = re.compile(r"\b(?:DATA|UI|ROUTE|HOOK)-[A-Z0-9-]+-\d{3}\b")
PATH_RE = re.compile(r"((?:tests|src|scripts)/[\w./-]+\.(?:py|js|ts|html|css|json|yaml|yml|sh))")


@dataclass(frozen=True)
class ContractCase:
    case_id: str
    source_file: Path
    line_number: int
    priority: str
    layer: str
    scenario: str
    test_type: str
    code_location: str


@dataclass(frozen=True)
class ValidationResult:
    cases: dict[str, ContractCase]
    code_bindings: dict[str, set[Path]]
    errors: list[str]


def _parse_cases(feature_dir: Path) -> tuple[dict[str, ContractCase], list[str]]:
    cases: dict[str, ContractCase] = {}
    errors: list[str] = []

    actual_tables = {path.name for path in feature_dir.glob("*.md")}
    missing_tables = EXPECTED_FEATURE_TABLES - actual_tables
    if missing_tables:
        errors.append("缺少契约表文件: " + ", ".join(sorted(missing_tables)))

    for md_file in sorted(feature_dir.glob("*.md")):
        for line_number, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.startswith("|"):
                continue
            cols = [col.strip() for col in line.strip().strip("|").split("|")]
            if not cols or not ID_RE.fullmatch(cols[0]):
                continue
            if len(cols) < 9:
                errors.append(f"{md_file}:{line_number}: 契约行列数不足 9 列")
                continue
            case_id = cols[0]
            if case_id in cases:
                first = cases[case_id]
                errors.append(
                    f"{md_file}:{line_number}: {case_id} 重复定义，首次定义在 "
                    f"{first.source_file}:{first.line_number}"
                )
                continue
            cases[case_id] = ContractCase(
                case_id=case_id,
                source_file=md_file,
                line_number=line_number,
                priority=cols[1],
                layer=cols[2],
                scenario=cols[3],
                test_type=cols[6],
                code_location=cols[8],
            )

    return cases, errors


def _parse_code_bindings(tests_dir: Path) -> dict[str, set[Path]]:
    bindings: dict[str, set[Path]] = {}
    for path in sorted(tests_dir.rglob("*")):
        if path.suffix not in {".py", ".js", ".ts"}:
            continue
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in ID_RE.finditer(text):
            bindings.setdefault(match.group(0), set()).add(path)
    return bindings


def _is_pending_or_manual(case: ContractCase) -> bool:
    lowered = f"{case.test_type} {case.code_location} {case.scenario}".lower()
    return (
        "manual" in lowered
        or "待补充" in lowered
        or case.code_location.strip() == "—"
    )


def _validate_code_locations(repo_root: Path, cases: dict[str, ContractCase]) -> list[str]:
    errors: list[str] = []
    for case in cases.values():
        if _is_pending_or_manual(case):
            continue
        paths = PATH_RE.findall(case.code_location)
        if not paths:
            continue
        for path_text in paths:
            if not (repo_root / path_text).exists():
                errors.append(
                    f"{case.source_file}:{case.line_number}: "
                    f"{case.case_id} 代码位置不存在: {path_text}"
                )
    return errors


def validate_acceptance_contracts(repo_root: Path) -> ValidationResult:
    feature_dir = repo_root / "docs" / "acceptance-contracts" / "features"
    tests_dir = repo_root / "tests"

    errors: list[str] = []
    if not feature_dir.is_dir():
        errors.append(f"契约表目录不存在: {feature_dir}")
        return ValidationResult(cases={}, code_bindings={}, errors=errors)
    if not tests_dir.is_dir():
        errors.append(f"测试目录不存在: {tests_dir}")
        return ValidationResult(cases={}, code_bindings={}, errors=errors)

    cases, parse_errors = _parse_cases(feature_dir)
    errors.extend(parse_errors)
    for md_file in sorted(feature_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        if "废弃" in text or "Deprecated" in text or "deprecated" in text:
            errors.append(f"{md_file}: docs 契约表不允许维护废弃信息")

    code_bindings = _parse_code_bindings(tests_dir)
    for case_id, paths in sorted(code_bindings.items()):
        if case_id not in cases:
            rel_paths = ", ".join(str(path.relative_to(repo_root)) for path in sorted(paths))
            errors.append(f"{case_id} 在测试代码中绑定，但 docs 契约表未定义: {rel_paths}")

    for case_id, case in sorted(cases.items()):
        if _is_pending_or_manual(case):
            continue
        if case_id not in code_bindings:
            errors.append(
                f"{case.source_file}:{case.line_number}: "
                f"{case_id} 是活跃自动化用例，但未在测试代码中绑定"
            )

    errors.extend(_validate_code_locations(repo_root, cases))
    return ValidationResult(cases=cases, code_bindings=code_bindings, errors=errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate acceptance contract tables.")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    result = validate_acceptance_contracts(repo_root)

    print(f"契约用例数: {len(result.cases)}")
    print(f"测试绑定 ID 数: {len(result.code_bindings)}")
    if result.errors:
        print("校验失败:")
        for error in result.errors:
            print(f"- {error}")
        return 1
    print("校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
