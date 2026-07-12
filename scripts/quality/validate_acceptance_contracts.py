#!/usr/bin/env python3
"""提供 validate acceptance contracts 脚本能力。"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.quality._trigger import add_changed_files_arg, parse_changed_files, skip_if_not_triggered

# 声明本脚本的触发模式：只有匹配的文件变更时才运行本检查。
TRIGGER_PATTERNS = [
    'docs/acceptance-contracts/**/*.md',
    'tests/**/*.py', 'tests/**/*.js', 'tests/**/*.ts',
    'scripts/quality/validate_acceptance_contracts.py',
    'tests/quality/test_contract_case_specs.py',
    'pyproject.toml',
]

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
MIN_CONTRACT_COLUMNS = 9

PATH_RE = re.compile(
    r'((?:tests|src|scripts|java)/[\w./-]+\.(?:py|js|ts|html|css|json|yaml|yml|sh|java))'
)


@dataclass(frozen=True)
class ContractCase:
    """表示 ContractCase。

    属性：
        case_id: case id 参数。
        source_file: source file 参数。
        line_number: 行 number 参数。
        priority: priority 参数。
        layer: layer 参数。
        scenario: scenario 参数。
        test_type: test type 参数。
        code_location: code location 参数。
    """

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
    """汇总 ValidationResult 的检查结果。

    属性：
        cases: cases 参数。
        code_bindings: code bindings 参数。
        errors: errors 参数。
    """

    cases: dict[str, ContractCase]
    code_bindings: dict[str, set[Path]]
    errors: list[str]


# 解析cases。
def _parse_cases(feature_dir: Path) -> tuple[dict[str, ContractCase], list[str]]:
    """参数：
        feature_dir: feature dir 参数。

    返回：
        已解析的cases keyed by contract id 和 阻断 解析 错误。
    """
    cases: dict[str, ContractCase] = {}
    errors: list[str] = []

    actual_tables = {path.name for path in feature_dir.glob('*.md')}
    missing_tables = EXPECTED_FEATURE_TABLES - actual_tables
    if missing_tables:
        errors.append('缺少契约表文件: ' + ', '.join(sorted(missing_tables)))

    for md_file in sorted(feature_dir.glob('*.md')):
        for line_number, line in enumerate(md_file.read_text(encoding='utf-8').splitlines(), 1):
            if not line.startswith('|'):
                continue
            cols = [col.strip() for col in line.strip().strip('|').split('|')]
            if not cols or not ID_RE.fullmatch(cols[0]):
                continue
            if len(cols) < MIN_CONTRACT_COLUMNS:
                errors.append(f'{md_file}:{line_number}: 契约行列数不足 9 列')
                continue
            case_id = cols[0]
            if case_id in cases:
                first = cases[case_id]
                errors.append(
                    f'{md_file}:{line_number}: {case_id} 重复定义, 首次定义在 '
                    f'{first.source_file}:{first.line_number}'
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


# 解析code bindings。
def _parse_code_bindings(tests_dir: Path, repo_root: Path) -> dict[str, set[Path]]:
    """参数：
        tests_dir: Test 目录到scan用于contract id markers。
        repo_root: repo root用于resolving additional 扫描 目录。

    返回：
        映射从contract id到source 文件 that reference it。
    """
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


# 判断是否pending manual。
def _is_pending_or_manual(case: ContractCase) -> bool:
    """参数：
        case: 已解析的contract 行到classify。

    返回：
        true用于manual, pending, 或 dash-仅 code-location 行。
    """
    lowered = f'{case.test_type} {case.code_location} {case.scenario}'.lower()
    return 'manual' in lowered or '待补充' in lowered or case.code_location.strip() == '—'


# 验证code locations。
def _validate_code_locations(repo_root: Path, cases: dict[str, ContractCase]) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        cases: 已解析的contract 行 keyed by id。

    返回：
        阻断 错误用于declared code 路径 that do 不 exist。
    """
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


# 验证acceptance contracts。
def validate_acceptance_contracts(repo_root: Path) -> ValidationResult:
    """参数：
        repo_root: 仓库根目录。

    返回：
        已解析的cases, discovered code bindings, 和 阻断 错误. CLI treats。 any 错误 as `FAIL`；缺失 必需 目录 fail closed。
    """
    feature_dir = repo_root / 'docs' / 'acceptance-contracts' / 'features'
    tests_dir = repo_root / 'tests'

    errors: list[str] = []
    if not feature_dir.is_dir():
        errors.append(f'契约表目录不存在: {feature_dir}')
        return ValidationResult(cases={}, code_bindings={}, errors=errors)
    if not tests_dir.is_dir():
        errors.append(f'测试目录不存在: {tests_dir}')
        return ValidationResult(cases={}, code_bindings={}, errors=errors)

    cases, parse_errors = _parse_cases(feature_dir)
    errors.extend(parse_errors)
    for md_file in sorted(feature_dir.glob('*.md')):
        text = md_file.read_text(encoding='utf-8', errors='ignore')
        if '废弃' in text or 'Deprecated' in text or 'deprecated' in text:
            errors.append(f'{md_file}: docs 契约表不允许维护废弃信息')

    code_bindings = _parse_code_bindings(tests_dir, repo_root)
    for case_id, paths in sorted(code_bindings.items()):
        if case_id not in cases:
            rel_paths = ', '.join(str(path.relative_to(repo_root)) for path in sorted(paths))
            errors.append(f'{case_id} 在测试代码中绑定, 但 docs 契约表未定义: {rel_paths}')

    for case_id, case in sorted(cases.items()):
        if _is_pending_or_manual(case):
            continue
        if case_id not in code_bindings:
            errors.append(
                f'{case.source_file}:{case.line_number}: '
                f'{case_id} 是活跃自动化用例, 但未在测试代码中绑定'
            )

    errors.extend(_validate_code_locations(repo_root, cases))
    return ValidationResult(cases=cases, code_bindings=code_bindings, errors=errors)


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description='Validate acceptance contract tables.')
    parser.add_argument('--repo-root', default='.', help='Repository root')
    add_changed_files_arg(parser)
    args = parser.parse_args()

    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = parse_changed_files(args.changed_files)
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    repo_root = Path(args.repo_root).resolve()
    result = validate_acceptance_contracts(repo_root)

    print(f'契约用例数: {len(result.cases)}')
    print(f'测试绑定 ID 数: {len(result.code_bindings)}')
    if result.errors:
        print('校验失败:')
        for error in result.errors:
            print(f'- {error}')
        return 1
    print('校验通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
