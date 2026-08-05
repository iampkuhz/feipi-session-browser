"""测量 Gate-first Trigger 的合成逃逸率。

该检查用固定高风险路径证明 planner 不会漏掉应触发的 Gate。唯一入口 ``check(arguments)``
先验证用例集合，再按原顺序写可选 JSON artifact 并返回阈值诊断；诊断表示路由保护不足。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.checks._framework import CheckResult, argument_parser, repository_root
from scripts.gates.planner import classify_path, plan

if TYPE_CHECKING:
    from collections.abc import Iterable

REPO_ROOT = repository_root()


@dataclass(frozen=True)
class GateEscapeCase:
    """保存一个合成路径路由用例与可审计证据。"""

    id: str
    description: str
    expected_gate: str
    observed: str
    escaped: bool
    evidence: str


REQUIRED_CASE_IDS = {
    'agent-policy-gate',
    'shared-skill-gate',
    'acceptance-case-mapping-gate',
    'python-tooling-gate',
    'java-source-gate',
    'java-build-gate',
    'session-detail-gate',
    'platform-settings-gate',
    'scan-script-gate',
    'unknown-risky-path',
}

RISKY_UNCLASSIFIED_PREFIXES = (
    '.agents/',
    '.claude/',
    '.codex/',
    '.qoder/',
    'harness/',
    'scripts/harness/',
    'scripts/gates/',
    'scripts/checks/',
    'skills/',
)


def _gates_for(files: Iterable[str]) -> list[str]:
    """返回 changed files 直接匹配 Trigger 后选中的 Gate。"""
    return [gate.name for gate in plan(list(files)).gates]


def _gate_case(case_id: str, description: str, path: str, expected_gate: str) -> GateEscapeCase:
    """执行单个合成路径用例，并记录预期 Gate 是否被规划器选中。"""

    gates = _gates_for([path])
    escaped = expected_gate not in gates
    return GateEscapeCase(
        id=case_id,
        description=description,
        expected_gate=expected_gate,
        observed='GATE_MISSING' if escaped else 'GATE_TRIGGERED',
        escaped=escaped,
        evidence=f'path={path}; gates={gates}',
    )


def _unknown_risky_case() -> GateEscapeCase:
    path = '.agents/experimental/new-policy.yaml'
    classification = classify_path(path)
    gates = _gates_for([path])
    fail_closed = path.startswith(RISKY_UNCLASSIFIED_PREFIXES) and (
        classification.risk_level in {'high', 'medium'}
        or not classification.allowed
        or classification.category == 'unknown'
    )
    protected = bool(gates) or fail_closed
    return GateEscapeCase(
        id='unknown-risky-path',
        description='新增未分类 agent 配置必须触发治理 Gate 或保持高风险分类',
        expected_gate='protectedRootsSync-or-risk-policy',
        observed='BLOCK'
        if protected and not gates
        else 'GATE_TRIGGERED'
        if gates
        else 'GATE_MISSING',
        escaped=not protected,
        evidence=(
            f'path={path}; category={classification.category}; '
            f'gates={gates}; fail_closed={fail_closed}'
        ),
    )


def _build_cases() -> list[GateEscapeCase]:
    """构造覆盖 minimal harness、产品和工具链的确定性路径场景。"""
    return [
        _gate_case(
            'agent-policy-gate',
            'Agent policy change must trigger language policy Gate',
            '.claude/agents/qwen-main-default.md',
            'languagePolicy',
        ),
        _gate_case(
            'shared-skill-gate',
            'Shared skill change must trigger skill registry Gate',
            'skills/authoring/feipi-java-feature-dev/SKILL.md',
            'skillRegistry',
        ),
        _gate_case(
            'acceptance-case-mapping-gate',
            '验收用例表变更必须直接触发映射 Gate',
            'docs/acceptance-cases/features/HOOK_HARNESS.md',
            'acceptanceCaseMapping',
        ),
        _gate_case(
            'python-tooling-gate',
            'Gate implementation change must trigger Python test Gate',
            'scripts/gates/planner.py',
            'pythonHarnessTests',
        ),
        _gate_case(
            'java-source-gate',
            'Java source change must trigger Java check Gate',
            'java/web/src/main/java/com/feipi/session/browser/X.java',
            'javaCheck',
        ),
        _gate_case(
            'java-build-gate',
            'Build configuration change must trigger Java check Gate',
            'build.gradle.kts',
            'javaCheck',
        ),
        _gate_case(
            'session-detail-gate',
            'Session detail template change must trigger browser Gate',
            'java/web/src/main/resources/templates/session-detail.html',
            'browserInteraction',
        ),
        _gate_case(
            'platform-settings-gate',
            'Platform settings change must trigger protected roots Gate',
            '.qoder/settings.json',
            'protectedRootsSync',
        ),
        _gate_case(
            'scan-script-gate',
            'Scan launcher change must trigger scan smoke Gate',
            'scripts/session-browser.sh',
            'scanScriptSmoke',
        ),
        _unknown_risky_case(),
    ]


def _build_report() -> dict[str, object]:
    """构造稳定 JSON 报告，不执行外部命令。"""
    cases = _build_cases()
    escaped = [case for case in cases if case.escaped]
    total = len(cases)
    return {
        'total_required_cases': total,
        'escaped_required_cases': len(escaped),
        'escape_rate': (len(escaped) / total) if total else 0.0,
        'cases': [asdict(case) for case in cases],
    }


def _write_json(path: Path, report: dict[str, object]) -> None:
    """写入可选报告路径。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def check(arguments: list[str]) -> CheckResult:
    """解析阈值与 artifact 参数，返回缺失用例或逃逸率诊断。"""
    parser = argument_parser(description='Measure synthetic required-gate escape rate.')
    parser.add_argument('--threshold', type=float, default=0.0, help='Maximum allowed escape rate.')
    parser.add_argument('--json-out', default=None, help='Optional JSON report path.')
    args = parser.parse_args(arguments)

    report = _build_report()
    case_ids = {case['id'] for case in report['cases']}  # type: ignore[index]
    missing = sorted(REQUIRED_CASE_IDS - case_ids)
    if missing:
        return CheckResult.from_errors(
            [f'[gateEscapeRate] BLOCKED missing_required_cases={missing}']
        )
    if args.json_out:
        _write_json(Path(args.json_out), report)
    escaped_cases = int(report['escaped_required_cases'])
    escape_rate = float(report['escape_rate'])
    total = int(report['total_required_cases'])
    if escape_rate <= args.threshold:
        return CheckResult()
    return CheckResult.from_errors(
        [
            f'[gateEscapeRate] BLOCKED escape_rate={escape_rate:.6f} '
            f'escaped_required_cases={escaped_cases} total_required_cases={total}'
        ]
    )
