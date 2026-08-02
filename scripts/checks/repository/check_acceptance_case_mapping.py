"""检查验收用例表、测试绑定与代码位置是否一致。

该检查用于确保“验收用例 ID 到自动化测试”的映射可追踪，不执行测试。唯一公开入口
``check(arguments)`` 返回全部有序诊断；任一诊断都表示验收用例表与测试代码不一致。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from scripts.checks._framework import CheckResult, argument_parser

EXPECTED_FEATURE_TABLES = {
    'DATA_INDEX.md',
    'DATA_PRESENTERS.md',
    'DATA_SOURCES.md',
    'HOOK_HARNESS.md',
    'ROUTES_AND_API.md',
    'UI_DASHBOARD.md',
    'UI_GLOBAL_VISUAL.md',
    'UI_GLOSSARY.md',
    'UI_INTERACTIONS.md',
    'UI_PROJECTS.md',
    'UI_SESSIONS_LIST.md',
    'UI_SESSION_DETAIL.md',
}

ID_RE = re.compile(r'\b(?:DATA|UI|ROUTE|HOOK)-[A-Z0-9-]+-\d{3}\b')
MIN_CASE_COLUMNS = 9

PATH_RE = re.compile(
    r'((?:tests|src|scripts|java)/[\w./-]+\.(?:py|js|ts|html|css|json|yaml|yml|sh|java))'
)


@dataclass(frozen=True)
class AcceptanceCase:
    """保存一条验收用例及其声明的自动化代码位置。"""

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
    """汇总解析后的验收用例、代码绑定与阻断性错误。"""

    cases: dict[str, AcceptanceCase]
    code_bindings: dict[str, set[Path]]
    errors: list[str]


def _parse_cases(feature_dir: Path) -> tuple[dict[str, AcceptanceCase], list[str]]:
    """解析验收用例表；缺表、列不足或 ID 重复均作为阻断性错误返回。"""
    cases: dict[str, AcceptanceCase] = {}
    errors: list[str] = []

    actual_tables = {path.name for path in feature_dir.glob('*.md')}
    missing_tables = EXPECTED_FEATURE_TABLES - actual_tables
    if missing_tables:
        errors.append('缺少验收用例表文件: ' + ', '.join(sorted(missing_tables)))

    for md_file in sorted(feature_dir.glob('*.md')):
        for line_number, line in enumerate(md_file.read_text(encoding='utf-8').splitlines(), 1):
            if not line.startswith('|'):
                continue
            cols = [col.strip() for col in line.strip().strip('|').split('|')]
            if not cols or not ID_RE.fullmatch(cols[0]):
                continue
            if len(cols) < MIN_CASE_COLUMNS:
                errors.append(f'{md_file}:{line_number}: 验收用例行列数不足 9 列')
                continue
            case_id = cols[0]
            if case_id in cases:
                first = cases[case_id]
                errors.append(
                    f'{md_file}:{line_number}: {case_id} 重复定义, 首次定义在 '
                    f'{first.source_file}:{first.line_number}'
                )
                continue
            cases[case_id] = AcceptanceCase(
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


def _parse_code_bindings(tests_dir: Path, repo_root: Path) -> dict[str, set[Path]]:
    """扫描测试源码中的验收用例 ID，并建立 ID 到引用文件的映射。"""
    bindings: dict[str, set[Path]] = {}
    scan_dirs = [tests_dir]
    java_test_dir = repo_root / 'java'
    if java_test_dir.is_dir():
        scan_dirs.append(java_test_dir)
    for scan_dir in scan_dirs:
        for path in sorted(scan_dir.rglob('*')):
            if path.suffix not in {'.py', '.js', '.ts', '.java'}:
                continue
            if '__pycache__' in path.parts:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            for match in ID_RE.finditer(text):
                bindings.setdefault(match.group(0), set()).add(path)
    return bindings


def _is_pending_or_manual(case: AcceptanceCase) -> bool:
    """识别无需代码绑定的人工或待补用例，避免把人工验收误报为缺失。"""
    lowered = f'{case.test_type} {case.code_location} {case.scenario}'.lower()
    return 'manual' in lowered or '待补充' in lowered or case.code_location.strip() == '—'


def _validate_code_locations(repo_root: Path, cases: dict[str, AcceptanceCase]) -> list[str]:
    """验证自动化验收用例声明的代码路径真实存在。"""
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
                    f'{case.source_file}:{case.line_number}: '
                    f'{case.case_id} 代码位置不存在: {path_text}'
                )
    return errors


def _validate_acceptance_case_mapping(repo_root: Path) -> ValidationResult:
    """校验验收用例、测试绑定与代码位置；目录缺失或不一致均失败。"""
    feature_dir = repo_root / 'docs' / 'acceptance-cases' / 'features'
    tests_dir = repo_root / 'tests'

    errors: list[str] = []
    if not feature_dir.is_dir():
        errors.append(f'验收用例表目录不存在: {feature_dir}')
        return ValidationResult(cases={}, code_bindings={}, errors=errors)
    if not tests_dir.is_dir():
        errors.append(f'测试目录不存在: {tests_dir}')
        return ValidationResult(cases={}, code_bindings={}, errors=errors)

    cases, parse_errors = _parse_cases(feature_dir)
    errors.extend(parse_errors)
    for md_file in sorted(feature_dir.glob('*.md')):
        text = md_file.read_text(encoding='utf-8', errors='ignore')
        if '废弃' in text or 'Deprecated' in text or 'deprecated' in text:
            errors.append(f'{md_file}: 验收用例表不允许维护废弃信息')

    code_bindings = _parse_code_bindings(tests_dir, repo_root)
    for case_id, paths in sorted(code_bindings.items()):
        if case_id not in cases:
            rel_paths = ', '.join(str(path.relative_to(repo_root)) for path in sorted(paths))
            errors.append(f'{case_id} 在测试代码中绑定, 但验收用例表未定义: {rel_paths}')

    for case_id, case in sorted(cases.items()):
        if _is_pending_or_manual(case):
            continue
        if case_id not in code_bindings:
            errors.append(
                f'{case.source_file}:{case.line_number}: '
                f'{case_id} 是活跃自动化验收用例, 但未在测试代码中绑定'
            )

    errors.extend(_validate_code_locations(repo_root, cases))
    return ValidationResult(cases=cases, code_bindings=code_bindings, errors=errors)


def check(arguments: list[str]) -> CheckResult:
    """解析参数并返回验收用例映射的全部阻断性诊断。"""
    parser = argument_parser(description='Validate acceptance case mapping.')
    parser.add_argument('--repo-root', default='.', help='Repository root')
    args = parser.parse_args(arguments)

    repo_root = Path(args.repo_root).resolve()
    result = _validate_acceptance_case_mapping(repo_root)
    return CheckResult.from_errors(result.errors)
