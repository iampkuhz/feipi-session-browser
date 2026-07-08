#!/usr/bin/env python3
"""Quality gate 运行ner 带有 tier support (quick / 必需 / full)。"""

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
effective_targets = importlib.import_module('scripts.claude_hooks.classify').effective_targets
QUALITY_TARGETS = importlib.import_module('scripts.quality.quality_targets').QUALITY_TARGETS
target_parallel_meta = importlib.import_module(
    'scripts.quality.quality_targets'
).target_parallel_meta
changed_file_utils = importlib.import_module('scripts.quality.changed_files')
runtime_paths = importlib.import_module('scripts.claude_hooks.paths')

IDENTITY = runtime_paths.identity_from_values()
AGENT_LOG_DIR = runtime_paths.agent_log_dir(REPO_ROOT, IDENTITY)
CHANGED_FILES = AGENT_LOG_DIR / 'changed-files.jsonl'
SESSION_ID_FILE = AGENT_LOG_DIR / 'session-id.txt'
BASE_COMMIT_FILE = AGENT_LOG_DIR / 'base-commit.txt'
QUALITY_DIR = (
    runtime_paths.quality_dir(REPO_ROOT, IDENTITY)
    if IDENTITY.has_session
    else REPO_ROOT / 'tmp' / 'quality'
)

# session-detail 较重，普通 required target runner 默认排除；shared stop runner 显式纳入。
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
QUICK_GATES: frozenset[str] = frozenset(
    {
        'pythonCompile',
        'bashSyntax',
        'noTestSkips',
        'noJavaTestSkips',
        'noJavaSuppressWarnings',
        'languagePolicy',
        'doctor',
        'repoStructure',
        'harnessStructure',
    }
)

# target 路由前必须执行的全局轻量门禁；用于防止 unknown/ignored 路径绕过分类。
GLOBAL_PREFLIGHT_GATES: tuple[str, ...] = ('ignoredTrackedFiles',)
GLOBAL_PREFLIGHT_TIMEOUT_SECONDS = 60

# full 档在全部 target 之外额外执行的验证命令。
FULL_EXTRA_COMMANDS: list[list[str]] = [
    ['python3', 'scripts/quality/check_java_api_snapshot.py', '--verify'],
]


# 解析change id。
def resolve_change_id(explicit: str | None) -> str:
    """参数：
        explicit: explicit 参数。

    返回：
        resolve change id 字符串。
    """
    if explicit:
        return explicit
    env = os.environ.get('ACTIVE_CHANGE_ID', '')
    if env:
        return env
    if IDENTITY.has_session:
        candidates = runtime_paths.build_paths(REPO_ROOT, IDENTITY).active_change_candidates
    else:
        candidates = [runtime_paths.legacy_active_change_path(REPO_ROOT)]
    for active_change in candidates:
        if not active_change.exists():
            continue
        try:
            data = json.loads(active_change.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        cid = data.get('change_id') or data.get('changeId') or ''
        if isinstance(cid, str) and cid:
            return cid
    return 'unknown'


# 读取changed-files 文件。
def get_changed_files(explicit_json: str | None = None) -> list[str]:
    """参数：
        explicit_json: explicit JSON 参数。

    返回：
        结果列表。
    """
    explicit = changed_file_utils.parse_changed_files_json(explicit_json)
    if explicit:
        return explicit
    if explicit_json is not None:
        session_id = (
            IDENTITY.raw_session_id
            if IDENTITY.has_session
            else changed_file_utils.read_session_id(SESSION_ID_FILE)
        )
        return changed_file_utils.collect_changed_files(
            session_id,
            include_git=True,
            repo_root=REPO_ROOT,
            changed_files_path=CHANGED_FILES,
            base_commit_file=BASE_COMMIT_FILE,
            agent_id=IDENTITY.raw_agent_id or None,
        )
    if IDENTITY.has_session:
        log_dirs = runtime_paths.session_log_dirs(
            REPO_ROOT,
            IDENTITY,
            include_agents=not IDENTITY.is_agent,
        )
        return changed_file_utils.read_recorded_changed_files_from_paths(
            [path / 'changed-files.jsonl' for path in log_dirs],
            IDENTITY.raw_session_id,
            agent_id=IDENTITY.raw_agent_id or None,
        )
    session_id = changed_file_utils.read_session_id(SESSION_ID_FILE)
    return changed_file_utils.collect_changed_files(
        session_id,
        include_git=True,
        repo_root=REPO_ROOT,
        changed_files_path=CHANGED_FILES,
        base_commit_file=BASE_COMMIT_FILE,
    )


# 维护compute 必需 targets。
def compute_required_targets(changed_files: list[str], excluded: set[str]) -> list[str]:
    """参数：
        changed_files: 待检查的文件列表。
        excluded: excluded 参数。

    返回：
        Computed 结果。
    """
    all_targets = required_quality_targets(changed_files)
    return [t for t in all_targets if t not in excluded]


# 维护compute tier 必需 targets。
def compute_tier_required_targets(tier: str, changed_files: list[str]) -> list[str]:
    """参数：
        tier: tier 参数。
        changed_files: changed 文件 供 quick/必需 tiers。

    返回：
        结果列表。
    """
    if tier == 'full':
        return list(QUALITY_TARGETS)
    return required_quality_targets(changed_files)


# 运行gate。
def run_gate(
    target: str,
    change_id: str,
    quality_dir: Path | None = None,
    changed_files: list[str] | None = None,
) -> tuple[bool, str]:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。
        change_id: 当前 OpenSpec change id。
        quality_dir: quality dir 参数。
        changed_files: 待检查的文件列表。

    返回：
        Computed 结果。
    """
    cmd = [
        sys.executable,
        str(REPO_ROOT / 'scripts' / 'quality' / 'run_quality_gate.py'),
        '--target',
        target,
        '--change-id',
        change_id,
    ]
    out_dir = quality_dir or QUALITY_DIR
    try:
        out_arg = str(out_dir.relative_to(REPO_ROOT)) if out_dir.is_absolute() else str(out_dir)
    except ValueError:
        out_arg = str(out_dir)
    cmd.extend(['--out', out_arg])
    artifact_path = str(out_dir / change_id / f'quality-gate-summary.{target}.json')

    try:
        env = os.environ.copy()
        env.pop('QUALITY_CHANGED_FILES', None)
        # 使用 target 元数据里的 timeout，避免 Java baseline 被固定 300 秒上限误杀。
        timeout = int(target_parallel_meta(target).get('timeout', 300))
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return False, artifact_path
        # 验证artifact exists。
        if not Path(artifact_path).exists():
            return False, artifact_path
        return True, artifact_path
    except subprocess.TimeoutExpired:
        return False, artifact_path
    except Exception:
        return False, artifact_path


# 运行quick gate。
def _run_quick_gate(
    gate: str,
    repo_root: Path,
) -> tuple[str, bool, str]:
    """参数：
        gate: gate 参数。
        repo_root: repo root用于命令 execution。

    返回：
        结果 tuple。
    """
    rqg = importlib.import_module('scripts.quality.run_quality_gate')

    cmd = rqg.gate_command(gate, repo_root, 'hook-runtime')
    if not cmd:
        return gate, False, 'BLOCKED'

    detail = rqg.run_cmd(gate, cmd, repo_root, required=True)
    return gate, detail.status == 'pass', detail.status.upper()


# 运行quick tier。
def _run_quick_tier(
    changed_files: list[str],
    excluded_targets: set[str],
    dry_run: bool,
) -> int:
    """参数：
        changed_files: Changed 文件路径s用于target selection。
        excluded_targets: 已排除的 quality target 集合。
        dry_run: dry 运行 参数。

    返回：
        进程退出码。
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


# 构建全局preflight 命令。
def _global_preflight_commands(repo_root: Path) -> list[tuple[str, list[str]]]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        需要在 target 路由前执行的 gate 命令列表。
    """
    rqg = importlib.import_module('scripts.quality.run_quality_gate')
    commands: list[tuple[str, list[str]]] = []
    for gate in GLOBAL_PREFLIGHT_GATES:
        cmd = rqg.gate_command(gate, repo_root, 'hook-runtime')
        if cmd:
            commands.append((gate, cmd))
    return commands


# 运行全局preflight gates。
def _run_global_preflight(repo_root: Path, dry_run: bool) -> bool:
    """参数：
        repo_root: 仓库根目录。
        dry_run: 是否只打印命令。

    返回：
        全部 preflight gate 是否通过。
    """
    commands = _global_preflight_commands(repo_root)
    if not commands:
        print('[preflight] no global gates available; not applicable', file=sys.stderr)
        return True
    if dry_run:
        for gate, cmd in commands:
            print(f'[preflight] would run gate: {gate} -> {" ".join(cmd)}', file=sys.stderr)
        return True

    passed = True
    for gate, cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                cwd=repo_root,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=GLOBAL_PREFLIGHT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            print(f'[preflight] FAIL gate={gate} timeout: {exc}', file=sys.stderr)
            passed = False
            continue
        output = (proc.stdout or '').strip()
        if output:
            print(output, file=sys.stderr)
        status = 'PASS' if proc.returncode == 0 else 'FAIL/BLOCKED'
        print(f'[preflight] {status} gate={gate}', file=sys.stderr)
        if proc.returncode != 0:
            passed = False
    return passed


# 运行full extra 命令。
def _run_full_extra_commands(change_id: str) -> list[tuple[str, bool]]:
    """参数：
        change_id: 当前 OpenSpec change id。

    返回：
        结果列表。
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


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        Computed 结果。
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
    parser.add_argument(
        '--out',
        default=str(QUALITY_DIR),
        help='Quality artifact base directory. Default: tmp/quality',
    )
    args = parser.parse_args()

    tier = args.tier
    tier_desc = TIER_META[tier]['description']
    tier_policy = TIER_META[tier]['failure_policy']

    effective_excluded = set(EXCLUDED_TARGETS)
    if tier == 'full':
        effective_excluded.clear()
        print(
            f'[{tier}-tier] full baseline includes session-detail',
            file=sys.stderr,
        )
    elif args.include_session_detail:
        effective_excluded.discard('session-detail')
        print(
            f'[{tier}-tier] --include-session-detail: '
            'session-detail will be executed by this runner',
            file=sys.stderr,
        )
    else:
        print(
            f'[{tier}-tier] session-detail excluded (use --include-session-detail for stop gating)',
            file=sys.stderr,
        )

    change_id = resolve_change_id(args.change_id)
    quality_dir = Path(args.out)
    if not quality_dir.is_absolute():
        quality_dir = REPO_ROOT / quality_dir
    changed_files = get_changed_files(args.changed_files)

    print(f'[{tier}-tier] change-id={change_id}', file=sys.stderr)
    print(f'[{tier}-tier] tier={tier}: {tier_desc}', file=sys.stderr)
    print(f'[{tier}-tier] failure policy: {tier_policy}', file=sys.stderr)
    try:
        changed_display = CHANGED_FILES.relative_to(REPO_ROOT)
    except ValueError:
        changed_display = CHANGED_FILES
    print(f'[{tier}-tier] changed-files={changed_display}', file=sys.stderr)
    if changed_files:
        print(f'[{tier}-tier] changed-file count={len(changed_files)}', file=sys.stderr)

    if not _run_global_preflight(REPO_ROOT, args.dry_run):
        return 1

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
    full_required = compute_tier_required_targets(tier, changed_files)

    # 应用 dominance 规则：当 java-src 存在时自动移除被包含的 java-build，
    # 避免重复运行 Gradle baseline。
    effective_required = effective_targets(full_required)
    dominated = [t for t in full_required if t not in effective_required]

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
            f'[{tier}-tier] excluded targets (handled elsewhere): {", ".join(sorted(excluded))}',
            file=sys.stderr,
        )

    if tier != 'full' and not changed_files:
        print(
            f'[{tier}-tier] no changed files; quality targets not triggered',
            file=sys.stderr,
        )
        return 0

    if not all_required:
        print(
            f'[{tier}-tier] no required targets after exclusions; selected targets not triggered',
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
        passed, artifact_path = run_gate(target, change_id, quality_dir)
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
        print(f'[{tier}-tier] excluded target handled elsewhere: {t}', file=sys.stderr)

    return 1 if blocked else 0


if __name__ == '__main__':
    raise SystemExit(main())
