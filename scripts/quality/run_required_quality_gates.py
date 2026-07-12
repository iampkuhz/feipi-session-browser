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
from typing import Any

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
resource_lock = importlib.import_module('scripts.harness.resource_lock')
quality_artifact = importlib.import_module('scripts.quality.quality_artifact')

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

# 历史 helper 默认排除 session-detail；main runner 会清空该默认值，除非调用方显式给 reason。
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
        'agentRuntimeIsolation',
        'agentRuntimeWorktree',
        'gateBypassResistance',
        'gateEscapeRate',
        'protectedRootsSync',
        'qoderRuntimeParity',
        'hookPayloadCompat',
        'subagentHandoffProtocol',
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
CHILD_OUTPUT_MAX_CHARS = 2000


class GateRunResult:
    """保存单个 target 结果，并兼容历史二元组解包。"""

    __slots__ = ('artifact_path', 'diagnostic', 'passed', 'target')

    # 初始化单个质量目标的运行结果。
    def __init__(self, target: str, passed: bool, artifact_path: str, diagnostic: str = '') -> None:
        """参数：
            target: 质量目标名称。
            passed: 质量目标是否通过。
            artifact_path: 质量产物路径。
            diagnostic: 失败诊断内容。

        返回：
            无返回值。
        """
        self.target = target
        self.passed = passed
        self.artifact_path = artifact_path
        self.diagnostic = diagnostic

    # 按兼容顺序迭代通过状态与产物路径。
    def __iter__(self):
        """返回：
            依次生成通过状态与产物路径的迭代器。
        """
        yield self.passed
        yield self.artifact_path


# 解析change id。
def resolve_change_id(explicit: str | None) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    explicit = changed_file_utils.parse_changed_files_json(explicit_json)
    if explicit_json is not None:
        return explicit
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
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    all_targets = required_quality_targets(changed_files)
    return [t for t in all_targets if t not in excluded]


# 读取 git dirty 路径。
def _git_dirty_files() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    dirty = changed_file_utils.read_git_dirty_files(REPO_ROOT)
    return dirty


# 验证显式空 changed-files 是否安全。
def _explicit_empty_changed_files_allowed(
    explicit_changed_files: bool,
    changed_files: list[str],
    reason: str | None,
) -> bool:
    """参数：
        explicit_changed_files: 调用方是否显式传入 changed files。
        changed_files: 调用方给出的 changed files。
        reason: 允许空列表的说明。

    返回：
        显式空 changed-files 是否可以继续。
    """
    if not explicit_changed_files or changed_files:
        return True
    dirty = _git_dirty_files()
    if not dirty:
        return True
    if reason and reason.strip():
        print(
            '[required-runner] explicit empty changed files allowed because '
            f'{reason.strip()}; git dirty count={len(dirty)}',
            file=sys.stderr,
        )
        return True
    print(
        '[required-runner] BLOCKED: explicit --changed-files [] while git workspace is dirty; '
        'pass --allow-empty-changed-files-because <reason> to acknowledge.',
        file=sys.stderr,
    )
    print(
        '[required-runner] dirty files: '
        f'{", ".join(dirty[:10])}{" ..." if len(dirty) > 10 else ""}',
        file=sys.stderr,
    )
    return False


# 维护 artifact status 检查。
def _artifact_is_required_pass(artifact_path: str) -> tuple[bool, str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    path = Path(artifact_path)
    if not path.exists():
        return False, 'missing'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f'invalid: {exc}'
    status = str(data.get('status', '')).upper()
    if status == 'PASS':
        required_gates = data.get('requiredGates')
        if isinstance(required_gates, dict):
            for gate_name, gate_status in required_gates.items():
                normalized = str(gate_status).upper()
                if normalized in {'SKIPPED', 'NOT_RUN'}:
                    return False, f'{gate_name}={normalized}'
        gate_details = data.get('gateDetails')
        if isinstance(gate_details, list):
            for detail in gate_details:
                if not isinstance(detail, dict):
                    continue
                normalized = str(detail.get('status', '')).upper()
                if normalized in {'SKIPPED', 'NOT_RUN'}:
                    return False, f'{detail.get("name", "gate")}={normalized}'
        return True, status
    if status in {'SKIPPED', 'NOT_RUN'}:
        return False, status
    return False, status or 'missing-status'


# 计算质量目标级产物缓存键。
def _gate_cache_key(target: str, changed_files: list[str] | None) -> str:
    """参数：
        target: 质量目标名称。
        changed_files: 已变更文件上下文。

    返回：
        当前质量目标输入组合的缓存键。
    """
    import hashlib

    base = ''
    head = ''
    try:
        base = subprocess.check_output(
            ['git', '-C', str(REPO_ROOT), 'merge-base', 'HEAD', 'HEAD'], text=True
        ).strip()
        head = subprocess.check_output(
            ['git', '-C', str(REPO_ROOT), 'rev-parse', 'HEAD'], text=True
        ).strip()
    except Exception:
        pass
    raw = json.dumps(
        {
            'target': target,
            'changedFiles': changed_files or [],
            'base': base,
            'head': head,
            'dirty': changed_file_utils.read_git_dirty_state(REPO_ROOT),
            'gateVersion': 'quality_targets:v1',
            'env': {
                'python': sys.version.split()[0],
                'javaHome': os.environ.get('JAVA_HOME', ''),
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# 判断既有 artifact 是否可作为 PASS cache 复用。
def _cached_pass(artifact_path: str, cache_key: str) -> bool:
    """参数：
        artifact_path: 质量汇总产物路径。
        cache_key: 当前输入组合缓存键。

    返回：
        产物对应相同缓存键且状态为 PASS 时返回 True。
    """
    path = Path(artifact_path)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return False
    return data.get('status') == 'PASS' and data.get('artifacts', {}).get('cacheKey') == cache_key


# 维护compute tier 必需 targets。
def compute_tier_required_targets(tier: str, changed_files: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if tier == 'full':
        return list(QUALITY_TARGETS)
    return required_quality_targets(changed_files)


# 构建 lock owner。
def _lock_owner(target: str) -> dict[str, Any]:
    """参数：
        target: 当前要执行的 quality target。

    返回：
        可写入 resource lock 的 owner metadata。
    """
    return resource_lock.owner_metadata(
        run_id=IDENTITY.raw_run_id,
        client=IDENTITY.client,
        session_id=IDENTITY.raw_session_id,
        worktree_id=IDENTITY.raw_worktree_id,
        target=target,
    )


# 运行gate。
def run_gate(
    target: str,
    change_id: str,
    quality_dir: Path | None = None,
    changed_files: list[str] | None = None,
    full_baseline: bool = False,
) -> GateRunResult:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。
        change_id: 当前 OpenSpec change id。
        quality_dir: quality dir 参数。
        changed_files: 待检查的文件列表。
        full_baseline: 是否由 full tier 显式请求全量基线。

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
    cache_key = _gate_cache_key(target, changed_files)
    if _cached_pass(artifact_path, cache_key):
        print(f'[required-runner] cache PASS target={target}', file=sys.stderr)
        return GateRunResult(target, True, artifact_path)

    if changed_files is not None:
        cmd.extend(['--changed-files', json.dumps(changed_files, ensure_ascii=False)])
    cmd.extend(['--cache-key', cache_key])

    try:
        # 缓存未命中后删除旧 artifact，避免用历史 PASS 解释本轮失败。
        Path(artifact_path).unlink(missing_ok=True)
        env = os.environ.copy()
        env.pop('QUALITY_CHANGED_FILES', None)
        if full_baseline:
            env['QUALITY_GATE_TIER'] = 'full'
            env['QUALITY_REUSE_CPD_MODE'] = 'full'
        else:
            env.pop('QUALITY_GATE_TIER', None)
            env.pop('QUALITY_REUSE_CPD_MODE', None)
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
            return GateRunResult(
                target,
                False,
                artifact_path,
                quality_artifact.concise_diagnostic(proc.stdout or ''),
            )
        artifact_ok, artifact_status = _artifact_is_required_pass(artifact_path)
        if not artifact_ok:
            print(
                f'[required-runner] FAIL/BLOCKED target={target} artifact status={artifact_status}',
                file=sys.stderr,
            )
            return GateRunResult(
                target,
                False,
                artifact_path,
                f'child runner artifact status is {artifact_status}',
            )
        return GateRunResult(target, True, artifact_path)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or exc.stderr or ''
        if isinstance(output, bytes):
            output = output.decode(errors='replace')
        diagnostic = f'child runner timed out after {exc.timeout}s'
        if output:
            diagnostic += '\n' + quality_artifact.concise_diagnostic(
                str(output)[-CHILD_OUTPUT_MAX_CHARS:]
            )
        return GateRunResult(target, False, artifact_path, diagnostic)
    except Exception as exc:
        return GateRunResult(target, False, artifact_path, f'child runner failed: {exc}')


# 格式化失败目标并在产物缺失时保留降级诊断。
def format_failed_target(result: GateRunResult) -> str:
    """参数：
        result: 失败的质量目标运行结果。

    返回：
        优先从质量产物渲染的失败报告。
    """
    artifact = Path(result.artifact_path)
    if artifact.exists():
        try:
            summary = json.loads(artifact.read_text(encoding='utf-8'))
            return quality_artifact.format_quality_report(summary, result.artifact_path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            diagnostic = f'cannot read quality artifact: {exc}'
    else:
        diagnostic = result.diagnostic or 'quality artifact was not created'
    return (
        f'QUALITY_GATE_RESULT status=FAIL target={result.target} '
        f'artifact={result.artifact_path}\n'
        'FAILED_GATES:\n'
        '- gate=runner status=FAIL\n'
        f'  error_summary={quality_artifact.concise_diagnostic(diagnostic)}'
    )


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
        target_gates = qt.applicable_gates_for_target(target, changed_files)
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
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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
        help='Include session-detail in runner targets (default behavior; kept for stop runner compatibility)',
    )
    parser.add_argument(
        '--exclude-session-detail-with-reason',
        default=None,
        help='Explicitly exclude session-detail because another runner handles it; requires a non-empty reason.',
    )
    parser.add_argument(
        '--allow-empty-changed-files-because',
        default=None,
        help='Allow explicit --changed-files [] while git is dirty with an audited reason.',
    )
    parser.add_argument(
        '--changed-files',
        default=None,
        help=(
            'JSON array of changed file paths used to select quality targets and applicable required gates.'
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

    effective_excluded: set[str] = set()
    exclusion_reasons: dict[str, str] = {}
    if args.exclude_session_detail_with_reason is not None:
        reason = args.exclude_session_detail_with_reason.strip()
        if not reason:
            print(
                f'[{tier}-tier] BLOCKED: --exclude-session-detail-with-reason requires a reason',
                file=sys.stderr,
            )
            return 1
        effective_excluded.add('session-detail')
        exclusion_reasons['session-detail'] = reason
    if tier == 'full':
        effective_excluded.clear()
        exclusion_reasons.clear()
        print(
            f'[{tier}-tier] full baseline includes session-detail',
            file=sys.stderr,
        )
    elif args.include_session_detail:
        effective_excluded.discard('session-detail')
        exclusion_reasons.pop('session-detail', None)
        print(
            f'[{tier}-tier] --include-session-detail: '
            'session-detail will be executed by this runner',
            file=sys.stderr,
        )
    else:
        print(
            f'[{tier}-tier] session-detail included when triggered; '
            'use --exclude-session-detail-with-reason <reason> only if handled elsewhere',
            file=sys.stderr,
        )

    change_id = resolve_change_id(args.change_id)
    quality_dir = Path(args.out)
    if not quality_dir.is_absolute():
        quality_dir = REPO_ROOT / quality_dir
    changed_files = get_changed_files(args.changed_files)
    explicit_changed_files = args.changed_files is not None

    if not _explicit_empty_changed_files_allowed(
        explicit_changed_files,
        changed_files,
        args.allow_empty_changed_files_because,
    ):
        return 1

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
                f'[{tier}-tier] no changed files; quality targets not triggered',
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
        for t in sorted(effective_excluded & set(effective_required)):
            reason_suffix = f' reason={exclusion_reasons[t]}' if t in exclusion_reasons else ''
            print(
                f'[{tier}-tier] excluded target handled elsewhere: {t}{reason_suffix}',
                file=sys.stderr,
            )
        print(
            f'[{tier}-tier] no required targets after exclusions; selected targets not triggered',
            file=sys.stderr,
        )
        return 0

    if args.dry_run:
        for t in sorted(all_required):
            print(f'[{tier}-tier] would run target: {t}', file=sys.stderr)
        for t in sorted(effective_excluded & set(effective_required)):
            reason_suffix = f' reason={exclusion_reasons[t]}' if t in exclusion_reasons else ''
            print(
                f'[{tier}-tier] excluded target handled elsewhere: {t}{reason_suffix}',
                file=sys.stderr,
            )
        if tier == 'full':
            for cmd_parts in FULL_EXTRA_COMMANDS:
                print(f'[{tier}-tier] would run extra: {" ".join(cmd_parts)}', file=sys.stderr)
        return 0

    blocked = False
    results: list[GateRunResult] = []
    for target in sorted(all_required):
        meta = target_parallel_meta(target)
        resources = [
            str(item) for item in meta.get('exclusive_resources', []) if isinstance(item, str)
        ]
        lock_timeout = float(meta.get('lock_timeout', min(120, int(meta.get('timeout', 300)))))
        print(f'[{tier}-tier] running target: {target}', file=sys.stderr)
        try:
            with resource_lock.ResourceLockSet(
                REPO_ROOT, resources, _lock_owner(target), timeout_seconds=lock_timeout
            ) as locks:
                for result in locks.results:
                    print(
                        f'[{tier}-tier] resource lock acquired target={target} '
                        f'resource={result.resource} waited={result.waitedSeconds:.3f}s',
                        file=sys.stderr,
                    )
                gate_changed_files = None if tier == 'full' else changed_files
                raw_result = run_gate(
                    target,
                    change_id,
                    quality_dir,
                    gate_changed_files,
                    full_baseline=tier == 'full',
                )
                if isinstance(raw_result, GateRunResult):
                    result = raw_result
                else:
                    passed, artifact_path = raw_result
                    result = GateRunResult(target, passed, artifact_path)
        except resource_lock.ResourceLockTimeout as exc:
            print(
                f'[{tier}-tier] BLOCKED target={target} resource={exc.resource} '
                f'waited={exc.waited_seconds:.3f}s owner={json.dumps(exc.owner, ensure_ascii=False, sort_keys=True)}',
                file=sys.stderr,
            )
            result = GateRunResult(
                target,
                False,
                str(quality_dir / change_id / f'quality-gate-summary.{target}.json'),
                f'resource lock timeout: resource={exc.resource} waited={exc.waited_seconds:.3f}s',
            )
            results.append(result)
            blocked = True
            continue
        results.append(result)
        passed = result.passed
        artifact_path = result.artifact_path
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
        reason_suffix = f' reason={exclusion_reasons[t]}' if t in exclusion_reasons else ''
        print(
            f'[{tier}-tier] excluded target handled elsewhere: {t}{reason_suffix}',
            file=sys.stderr,
        )

    failed_results = [result for result in results if not result.passed]
    final_status = 'FAIL' if blocked else 'PASS'
    print(
        f'REQUIRED_QUALITY_RESULT status={final_status} change_id={change_id} '
        f'passed={len(results) - len(failed_results)}/{len(results)} artifact_dir={quality_dir / change_id}'
    )
    for result in failed_results:
        print(format_failed_target(result))

    return 1 if blocked else 0


if __name__ == '__main__':
    raise SystemExit(main())
