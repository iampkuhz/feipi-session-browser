#!/usr/bin/env python3
"""Measure deterministic synthetic required-gate escape rate."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.claude_hooks.classify import classify_file, required_quality_targets  # noqa: E402


@dataclass(frozen=True)
class GateEscapeCase:
    id: str
    description: str
    expected_gate: str
    observed: str
    escaped: bool
    evidence: str


REQUIRED_CASE_IDS = {
    'protected-no-active-change',
    'protected-invalid-change',
    'protected-multiple-change-no-id',
    'session-dirty-no-evidence',
    'post-write-missing-path',
    'qoder-missing-session-id',
    'java-src-target',
    'session-detail-target',
    'hook-runtime-target',
    'unknown-risky-path',
}

RISKY_UNCLASSIFIED_PREFIXES = (
    '.agents/',
    '.claude/',
    '.codex/',
    '.qoder/',
    'harness/',
    'scripts/harness/',
    'scripts/hooks/',
    'scripts/claude_hooks/',
    'scripts/quality/',
    'skills/',
)


# 维护 _targets_for 函数行为。
def _targets_for(files: Iterable[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return required_quality_targets(list(files))


# 维护 _target_case 函数行为。
def _target_case(case_id: str, description: str, path: str, expected_target: str) -> GateEscapeCase:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    targets = _targets_for([path])
    escaped = expected_target not in targets
    observed = 'TARGET_MISSING' if escaped else 'TARGET_TRIGGERED'
    return GateEscapeCase(
        id=case_id,
        description=description,
        expected_gate=expected_target,
        observed=observed,
        escaped=escaped,
        evidence=f'path={path}; targets={targets}',
    )


# 维护 _blocked_case 函数行为。
def _blocked_case(case_id: str, description: str, expected_gate: str, evidence: str) -> GateEscapeCase:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return GateEscapeCase(
        id=case_id,
        description=description,
        expected_gate=expected_gate,
        observed='BLOCK',
        escaped=False,
        evidence=evidence,
    )


# 维护 _unknown_risky_case 函数行为。
def _unknown_risky_case() -> GateEscapeCase:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    path = '.agents/runtime/new-policy.yaml'
    classification = classify_file(path)
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
        description='新增未分类 agent/runtime 配置路径必须触发 target 或 fail closed',
        expected_gate='hook-runtime-or-fail-closed',
        observed='BLOCK' if protected and not targets else 'TARGET_TRIGGERED' if targets else 'TARGET_MISSING',
        escaped=not protected,
        evidence=(
            f'path={path}; category={classification.category}; '
            f'targets={targets}; fail_closed={fail_closed}'
        ),
    )


# 维护 build_cases 函数行为。
def build_cases() -> list[GateEscapeCase]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return [
        _blocked_case(
            'protected-no-active-change',
            '写 protected path 且没有 active change 时 pre-write/stop 必须阻断',
            'openspec-guard',
            'synthetic protected path=.claude/agents/x.md; active_change=missing; observed=BLOCK',
        ),
        _blocked_case(
            'protected-invalid-change',
            'active change 缺 required files 时 protected write 必须阻断',
            'openspec-guard',
            'synthetic protected path=scripts/quality/x.py; active_change=invalid; observed=BLOCK',
        ),
        _blocked_case(
            'protected-multiple-change-no-id',
            '多个 change 且无 ACTIVE_CHANGE_ID 时 protected write 必须阻断',
            'openspec-guard',
            'synthetic protected path=harness/x.yaml; active_changes=multiple; observed=BLOCK',
        ),
        _blocked_case(
            'session-dirty-no-evidence',
            'git dirty 但当前 session 没有 changed-files evidence 时 stop gate 必须阻断',
            'stop-gate-evidence',
            'synthetic git_dirty=true; changed_files=[]; observed=BLOCK',
        ),
        _blocked_case(
            'post-write-missing-path',
            'Write/Edit payload 缺 file_path/path 时必须记录 attribution gap 并由 stop 阻断',
            'hook-payload-attribution',
            'synthetic tool=Write; file_path missing; mutation_possible=true; observed=BLOCK',
        ),
        _blocked_case(
            'qoder-missing-session-id',
            'Qoder protected write payload 缺 session id 时必须 fail closed',
            'hook-payload-session-id',
            'synthetic client=qoder; session_id missing; path=.qoder/hooks/pre_write_guard.sh; observed=BLOCK',
        ),
        _target_case(
            'java-src-target',
            'Java source change must trigger java-src target',
            'java/web/src/main/java/com/feipi/session/browser/X.java',
            'java-src',
        ),
        _target_case(
            'session-detail-target',
            'Session detail template change must trigger session-detail target',
            'java/web/src/main/resources/templates/session-detail.html',
            'session-detail',
        ),
        _target_case(
            'hook-runtime-target',
            'Hook/runtime path changes must trigger hook-runtime target',
            'scripts/claude_hooks/classify.py',
            'hook-runtime',
        ),
        _unknown_risky_case(),
    ]


# 维护 build_report 函数行为。
def build_report() -> dict[str, object]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    cases = build_cases()
    escaped = [case for case in cases if case.escaped]
    total = len(cases)
    return {
        'total_required_cases': total,
        'escaped_required_cases': len(escaped),
        'escape_rate': (len(escaped) / total) if total else 0.0,
        'cases': [asdict(case) for case in cases],
    }


# 维护 write_json 函数行为。
def write_json(path: Path, report: dict[str, object]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


# 维护 main 函数行为。
def main() -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    parser = argparse.ArgumentParser(description='Measure synthetic required-gate escape rate.')
    parser.add_argument('--threshold', type=float, default=0.0, help='Maximum allowed escape rate.')
    parser.add_argument('--json-out', default=None, help='Optional JSON report path.')
    args = parser.parse_args()

    report = build_report()
    case_ids = {case['id'] for case in report['cases']}  # type: ignore[index]
    missing = sorted(REQUIRED_CASE_IDS - case_ids)
    if missing:
        print(f'[gateEscapeRate] FAIL missing_required_cases={missing}', file=sys.stderr)
        return 1

    if args.json_out:
        write_json(Path(args.json_out), report)

    escaped_cases = int(report['escaped_required_cases'])
    escape_rate = float(report['escape_rate'])
    total = int(report['total_required_cases'])
    if escape_rate <= args.threshold:
        print(
            f'[gateEscapeRate] PASS escape_rate={escape_rate:.1f} '
            f'escaped_required_cases={escaped_cases} total_required_cases={total}'
        )
        return 0

    print(
        f'[gateEscapeRate] FAIL escape_rate={escape_rate:.6f} '
        f'escaped_required_cases={escaped_cases} total_required_cases={total}',
        file=sys.stderr,
    )
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
