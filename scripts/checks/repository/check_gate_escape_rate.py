#!/usr/bin/env python3
"""测量显式 required Gate 路径路由的合成逃逸率。

该检查用固定高风险路径证明 planner 不会漏掉 required target。唯一入口 ``check(arguments)``
先验证用例集合，再按原顺序写可选 JSON artifact 并返回阈值诊断；诊断表示路由保护不足。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.checks._framework import CheckResult, argument_parser, repository_root
from scripts.gates.planner import classify_path, required_quality_targets

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
    'agent-policy-target',
    'shared-skill-target',
    'acceptance-contract-target',
    'python-standard-target',
    'java-src-target',
    'java-build-target',
    'session-detail-target',
    'platform-settings-target',
    'scan-script-target',
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


def _targets_for(files: Iterable[str]) -> list[str]:
    return required_quality_targets(list(files))


def _target_case(case_id: str, description: str, path: str, expected_target: str) -> GateEscapeCase:
    targets = _targets_for([path])
    escaped = expected_target not in targets
    return GateEscapeCase(
        id=case_id,
        description=description,
        expected_gate=expected_target,
        observed='TARGET_MISSING' if escaped else 'TARGET_TRIGGERED',
        escaped=escaped,
        evidence=f'path={path}; targets={targets}',
    )


def _unknown_risky_case() -> GateEscapeCase:
    path = '.agents/experimental/new-policy.yaml'
    classification = classify_path(path)
    targets = _targets_for([path])
    fail_closed = path.startswith(RISKY_UNCLASSIFIED_PREFIXES) and (
        classification.risk_level in {'high', 'medium'}
        or classification.requires_quality_gate
        or not classification.allowed_by_default
        or classification.category == 'unknown'
    )
    protected = bool(targets) or fail_closed
    return GateEscapeCase(
        id='unknown-risky-path',
        description='新增未分类 agent 配置必须触发 target 或保持高风险分类',
        expected_gate='harness-or-risk-policy',
        observed='BLOCK'
        if protected and not targets
        else 'TARGET_TRIGGERED'
        if targets
        else 'TARGET_MISSING',
        escaped=not protected,
        evidence=(
            f'path={path}; category={classification.category}; '
            f'targets={targets}; fail_closed={fail_closed}'
        ),
    )


def _build_cases() -> list[GateEscapeCase]:
    """构造覆盖 minimal harness、产品和工具链的确定性路径场景。"""
    return [
        _target_case(
            'agent-policy-target',
            'Agent policy change must trigger harness target',
            '.claude/agents/qwen-main-default.md',
            'harness',
        ),
        _target_case(
            'shared-skill-target',
            'Shared skill change must trigger harness target',
            'skills/authoring/feipi-java-feature-dev/SKILL.md',
            'harness',
        ),
        _target_case(
            'acceptance-contract-target',
            'Acceptance contract change must trigger acceptance target',
            'docs/acceptance-contracts/features/HOOK_HARNESS.md',
            'acceptance-contracts',
        ),
        _target_case(
            'python-standard-target',
            'Gate implementation change must trigger Python target',
            'scripts/gates/planner.py',
            'python-standard',
        ),
        _target_case(
            'java-src-target',
            'Java source change must trigger java-src target',
            'java/web/src/main/java/com/feipi/session/browser/X.java',
            'java-src',
        ),
        _target_case(
            'java-build-target',
            'Build configuration change must trigger java-build target',
            'build.gradle.kts',
            'java-build',
        ),
        _target_case(
            'session-detail-target',
            'Session detail template change must trigger UI target',
            'java/web/src/main/resources/templates/session-detail.html',
            'session-detail',
        ),
        _target_case(
            'platform-settings-target',
            'Platform settings change must trigger harness target',
            '.qoder/settings.json',
            'harness',
        ),
        _target_case(
            'scan-script-target',
            'Scan launcher change must trigger scan smoke target',
            'scripts/session-browser.sh',
            'scan-script-smoke',
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
        return CheckResult.from_errors([f'[gateEscapeRate] FAIL missing_required_cases={missing}'])
    if args.json_out:
        _write_json(Path(args.json_out), report)
    escaped_cases = int(report['escaped_required_cases'])
    escape_rate = float(report['escape_rate'])
    total = int(report['total_required_cases'])
    if escape_rate <= args.threshold:
        return CheckResult()
    return CheckResult.from_errors(
        [
            f'[gateEscapeRate] FAIL escape_rate={escape_rate:.6f} '
            f'escaped_required_cases={escaped_cases} total_required_cases={total}'
        ]
    )
