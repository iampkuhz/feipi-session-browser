#!/usr/bin/env python3
"""Quality gate runner with tier support (quick / required / full).

Reads tmp/agent_logs/current/changed-files.jsonl, computes required targets
via classify.required_quality_targets(), and runs quality gates based on the
selected tier:

- quick: lightweight gate subset for fast local feedback.
- required: full required gate baseline (default, backward compatible).
- full: all targets plus extra validation commands for release gating.

By default excludes session-detail (handled by stop_quality_gate.py).
Pass --include-session-detail to include it in the runner (used by stop.sh).

Usage:
    python3 scripts/quality/run_required_quality_gates.py
    python3 scripts/quality/run_required_quality_gates.py --tier required
    python3 scripts/quality/run_required_quality_gates.py --tier quick
    python3 scripts/quality/run_required_quality_gates.py --tier full
    python3 scripts/quality/run_required_quality_gates.py --change-id fix-xyz
    python3 scripts/quality/run_required_quality_gates.py --change-id fix-xyz --dry-run

Exit codes:
    0 -- all targets PASS or no targets to run
    1 -- at least one target gate failed or produced skipped outcome
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

required_quality_targets = importlib.import_module(
    'scripts.claude_hooks.classify'
).required_quality_targets
# 导入 dominance 去重函数，避免重复运行被包含的 target。
effective_targets = importlib.import_module(
    'scripts.claude_hooks.classify'
).effective_targets

AGENT_LOG_DIR = REPO_ROOT / 'tmp' / 'agent_logs' / 'current'
CHANGED_FILES = AGENT_LOG_DIR / 'changed-files.jsonl'
SESSION_ID_FILE = AGENT_LOG_DIR / 'session-id.txt'
QUALITY_DIR = REPO_ROOT / 'tmp' / 'quality'

# session-detail 由 stop_quality_gate.py 单独处理, 默认排除
EXCLUDED_TARGETS = {'session-detail'}

# 01. 三档定义
VALID_TIERS = ('quick', 'required', 'full')

TIER_META: dict[str, dict[str, str]] = {
    'quick': {
        'description': '本地开发默认快速反馈，只运行轻量级 gate 子集。',
        'failure_policy': 'triggered gate 必须 PASS；not triggered 不算 skipped。',
    },
    'required': {
        'description': 'PR 合入和 Stop/handoff 前必须通过。',
        'failure_policy': '0 skipped outcome；skipped 即 FAIL/BLOCKED。',
    },
    'full': {
        'description': '发布或大迁移收口前运行，包含全部 target 和额外验证。',
        'failure_policy': '0 skipped outcome；skipped 即 FAIL/BLOCKED。',
    },
}

# quick 档运行的轻量级 gate 子集。
# 这些 gate 执行速度快、不需要 fixture 或外部依赖。
QUICK_GATES: frozenset[str] = frozenset({
    'pythonCompile',
    'bashSyntax',
    'noTestSkips',
    'noJavaTestSkips',
    'noJavaSuppressWarnings',
    'languagePolicy',
    'doctor',
    'repoStructure',
    'harnessStructure',
})

# full 档在全部 target 之外额外执行的验证命令。
FULL_EXTRA_COMMANDS: list[list[str]] = [
    ['python3', 'scripts/quality/check_java_api_snapshot.py', '--verify'],
]


def resolve_change_id(explicit: str | None) -> str:
    """Resolve change-id from args, env, or tmp/active_change.json.

    Args:
        explicit: Input value for explicit.

    Returns:
        Computed result.
    """
    if explicit:
        return explicit
    env = os.environ.get('ACTIVE_CHANGE_ID', '')
    if env:
        return env
    active_change = REPO_ROOT / 'tmp' / 'active_change.json'
    if active_change.exists():
        try:
            data = json.loads(active_change.read_text(encoding='utf-8'))
            cid = data.get('change_id', '')
            if cid:
                return cid
        except (json.JSONDecodeError, OSError):
            pass
    return 'unknown'


def get_changed_files() -> list[str]:
    """Read changed files from tmp/agent_logs/current/changed-files.jsonl.

    Returns:
        Computed result.
    """
    session_id = None
    if SESSION_ID_FILE.exists():
        session_id = SESSION_ID_FILE.read_text().strip() or None

    if not CHANGED_FILES.exists():
        return []

    files: list[str] = []
    for raw_line in CHANGED_FILES.read_text(encoding='utf-8').splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue
        try:
            record = json.loads(stripped_line)
            if session_id and record.get('sessionId') != session_id:
                continue
            f = record.get('file') or record.get('file_path')
            if f:
                files.append(f)
        except (json.JSONDecodeError, Exception):
            continue
    return files


def compute_required_targets(changed_files: list[str], excluded: set[str]) -> list[str]:
    """Compute required quality targets from changed files, applying exclusions.

    Args:
        changed_files: Input value for changed_files.
        excluded: Input value for excluded.

    Returns:
        Computed result.
    """
    all_targets = required_quality_targets(changed_files)
    return [t for t in all_targets if t not in excluded]


def run_gate(
    target: str,
    change_id: str,
    changed_files: list[str] | None = None,
) -> tuple[bool, str]:
    """Run run_quality_gate.py for a single target. Returns (passed, artifact_path).

    Args:
        target: Input value for target.
        change_id: Input value for change_id.
        changed_files: Input value for changed_files.

    Returns:
        Computed result.
    """
    cmd = [
        sys.executable,
        str(REPO_ROOT / 'scripts' / 'quality' / 'run_quality_gate.py'),
        '--target',
        target,
        '--change-id',
        change_id,
    ]
    artifact_path = str(QUALITY_DIR / change_id / f'quality-gate-summary.{target}.json')

    try:
        env = os.environ.copy()
        # changed_files selects required targets in this runner. Do not forward
        # it into target execution; each selected target must run its full
        # baseline instead of per-file pruning.
        env.pop('QUALITY_CHANGED_FILES', None)
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            timeout=300,
        )
        if proc.returncode != 0:
            return False, artifact_path
        # Verify artifact exists
        if not Path(artifact_path).exists():
            return False, artifact_path
        return True, artifact_path
    except subprocess.TimeoutExpired:
        return False, artifact_path
    except Exception:
        return False, artifact_path


def _run_quick_gate(
    gate: str,
    repo_root: Path,
) -> tuple[str, bool, str]:
    """Run a single quick-tier gate directly via run_quality_gate.run_cmd.

    Args:
        gate: Gate name from QUICK_GATES.
        repo_root: Repository root for command execution.

    Returns:
        Tuple of (gate_name, passed, status_label).
        status_label is one of PASS, FAIL, BLOCKED, NOT_TRIGGERED.
    """
    qt = importlib.import_module('scripts.quality.quality_targets')
    rqg = importlib.import_module('scripts.quality.run_quality_gate')

    cmd = rqg.gate_command(gate, repo_root, 'hook-runtime')
    if not cmd:
        return gate, False, 'BLOCKED'

    detail = rqg.run_cmd(gate, cmd, repo_root, required=True)
    return gate, detail.status == 'pass', detail.status.upper()


def _run_quick_tier(
    changed_files: list[str],
    excluded_targets: set[str],
    dry_run: bool,
) -> int:
    """Execute the quick tier: lightweight gate subset across triggered targets.

    Args:
        changed_files: Changed file paths for target selection.
        excluded_targets: Target names to exclude from execution.
        dry_run: If True, print what would run without executing.

    Returns:
        Exit code: 0 if all triggered gates PASS, 1 otherwise.
    """
    qt = importlib.import_module('scripts.quality.quality_targets')

    all_targets = required_quality_targets(changed_files)
    effective = effective_targets(all_targets)
    targets = [t for t in effective if t not in excluded_targets]

    # 收集所有需要运行的 quick gate（去重、保持顺序）。
    gates_to_run: list[str] = []
    seen_gates: set[str] = set()
    not_triggered_gates: set[str] = set(QUICK_GATES)

    for target in targets:
        target_gates = qt.required_gates_for_target(target)
        for gate in target_gates:
            if gate not in QUICK_GATES:
                continue
            not_triggered_gates.discard(gate)
            if gate not in seen_gates:
                seen_gates.add(gate)
                gates_to_run.append(gate)

    print(
        f'[quick-tier] triggered gates: {", ".join(gates_to_run) if gates_to_run else "(none)"}',
        file=sys.stderr,
    )
    if not_triggered_gates:
        print(
            f'[quick-tier] not triggered gates (not skipped): '
            f'{", ".join(sorted(not_triggered_gates))}',
            file=sys.stderr,
        )

    if dry_run:
        for gate in gates_to_run:
            print(f'[quick-tier] would run gate: {gate}', file=sys.stderr)
        return 0

    if not gates_to_run:
        print('[quick-tier] no gates triggered; nothing to run', file=sys.stderr)
        return 0

    failed = False
    for gate in gates_to_run:
        gate_name, passed, status = _run_quick_gate(gate, REPO_ROOT)
        print(f'[quick-tier] {status} gate={gate_name}', file=sys.stderr)
        if not passed:
            failed = True

    return 1 if failed else 0


def _run_full_extra_commands(change_id: str) -> list[tuple[str, bool]]:
    """Run full-tier extra validation commands beyond the required targets.

    Args:
        change_id: Change identifier for logging.

    Returns:
        List of (command_label, passed) tuples.
    """
    results: list[tuple[str, bool]] = []
    for cmd_parts in FULL_EXTRA_COMMANDS:
        label = ' '.join(cmd_parts)
        cmd_path = Path(cmd_parts[0])
        # 尝试解析为仓库内路径。
        resolved = cmd_parts.copy()
        if not cmd_path.is_absolute():
            candidate = REPO_ROOT / cmd_parts[0]
            if candidate.exists():
                resolved[0] = str(candidate)
            elif cmd_parts[0] == 'python3':
                resolved[0] = sys.executable

        try:
            proc = subprocess.run(
                resolved,
                cwd=REPO_ROOT,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
            passed = proc.returncode == 0
            results.append((label, passed))
            status_str = 'PASS' if passed else 'FAIL'
            print(f'[full-tier] {status_str} extra: {label}', file=sys.stderr)
        except subprocess.TimeoutExpired:
            results.append((label, False))
            print(f'[full-tier] FAIL extra (timeout): {label}', file=sys.stderr)
        except Exception as exc:
            results.append((label, False))
            print(f'[full-tier] FAIL extra ({exc}): {label}', file=sys.stderr)
    return results


def main() -> int:
    """Parse CLI options and run quality gates for the selected tier.

    Returns:
        Computed result.
    """
    parser = argparse.ArgumentParser(
        description='Run quality gates with tier support (quick/required/full)'
    )
    parser.add_argument('--change-id', default=None, help='Override change-id')
    parser.add_argument(
        '--tier',
        default='required',
        choices=list(VALID_TIERS),
        help='Quality tier to run. Default: required (backward compatible).',
    )
    parser.add_argument(
        '--dry-run', action='store_true', help='Print what would run without executing'
    )
    parser.add_argument(
        '--include-session-detail',
        action='store_true',
        help='Include session-detail in runner targets (default: excluded)',
    )
    parser.add_argument(
        '--changed-files',
        default=None,
        help=(
            'JSON array of changed file paths used only to select quality targets. '
            'Target gates always run the full baseline.'
        ),
    )
    args = parser.parse_args()

    tier = args.tier
    tier_desc = TIER_META[tier]['description']
    tier_policy = TIER_META[tier]['failure_policy']

    # Determine effective exclusions
    effective_excluded = set(EXCLUDED_TARGETS)
    if args.include_session_detail:
        effective_excluded.discard('session-detail')
        print(
            f'[{tier}-tier] --include-session-detail: '
            'session-detail will be executed by this runner',
            file=sys.stderr,
        )
    else:
        print(
            f'[{tier}-tier] session-detail excluded '
            '(handled by stop_quality_gate.py)',
            file=sys.stderr,
        )

    change_id = resolve_change_id(args.change_id)
    changed_files = json.loads(args.changed_files) if args.changed_files else get_changed_files()

    print(f'[{tier}-tier] change-id={change_id}', file=sys.stderr)
    print(f'[{tier}-tier] tier={tier}: {tier_desc}', file=sys.stderr)
    print(f'[{tier}-tier] failure policy: {tier_policy}', file=sys.stderr)
    print(
        f'[{tier}-tier] changed-files={CHANGED_FILES.relative_to(REPO_ROOT)}',
        file=sys.stderr,
    )

    # quick 档走独立的轻量级 gate 执行路径。
    if tier == 'quick':
        if not changed_files:
            print(
                f'[{tier}-tier] no changed files; quick gates not triggered',
                file=sys.stderr,
            )
            return 0
        return _run_quick_tier(changed_files, effective_excluded, args.dry_run)

    # required / full 档走 target-based 执行路径。
    full_required = required_quality_targets(changed_files)

    # 应用 dominance 规则：当 java-src 存在时自动移除被包含的 java-build，
    # 避免重复运行 Gradle baseline。
    effective_required = effective_targets(full_required)
    dominated = [t for t in full_required if t not in effective_required]

    # Targets actually executed after exclusions
    all_required = [t for t in effective_required if t not in effective_excluded]
    excluded = [t for t in effective_required if t in effective_excluded]

    print(
        f'[{tier}-tier] required targets: '
        f'{", ".join(sorted(full_required)) if full_required else "(none)"}',
        file=sys.stderr,
    )
    if dominated:
        print(
            f'[{tier}-tier] dominated targets (not triggered, not skipped): '
            f'{", ".join(sorted(dominated))}',
            file=sys.stderr,
        )
    if excluded:
        print(
            f'[{tier}-tier] excluded targets (handled elsewhere): '
            f'{", ".join(sorted(excluded))}',
            file=sys.stderr,
        )

    if not changed_files:
        print(
            f'[{tier}-tier] no changed files; quality targets not triggered',
            file=sys.stderr,
        )
        return 0

    if not all_required:
        print(
            f'[{tier}-tier] no required targets after exclusions; '
            'selected targets not triggered',
            file=sys.stderr,
        )
        return 0

    if args.dry_run:
        for t in sorted(all_required):
            print(f'[{tier}-tier] would run target: {t}', file=sys.stderr)
        for t in sorted(effective_excluded & set(effective_required)):
            print(
                f'[{tier}-tier] excluded target handled elsewhere: {t}',
                file=sys.stderr,
            )
        if tier == 'full':
            for cmd_parts in FULL_EXTRA_COMMANDS:
                print(f'[{tier}-tier] would run extra: {" ".join(cmd_parts)}', file=sys.stderr)
        return 0

    blocked = False
    for target in sorted(all_required):
        print(f'[{tier}-tier] running target: {target}', file=sys.stderr)
        passed, artifact_path = run_gate(target, change_id)
        status_str = 'PASS' if passed else 'FAIL/BLOCKED'
        print(
            f'[{tier}-tier] {status_str} target={target} artifact={artifact_path}',
            file=sys.stderr,
        )
        if not passed:
            blocked = True

    # full 档额外运行发布级验证命令。
    if tier == 'full' and not blocked:
        extra_results = _run_full_extra_commands(change_id)
        for label, passed in extra_results:
            if not passed:
                blocked = True

    # 输出被排除的 target，这些由其他 runner 处理，不是测试跳过。
    for t in sorted(effective_excluded & set(effective_required)):
        print(
            f'[{tier}-tier] excluded target handled elsewhere: {t}', file=sys.stderr
        )

    return 1 if blocked else 0


if __name__ == '__main__':
    raise SystemExit(main())
