"""构造 Change 的 exact manifest 与稳定 Git candidate。

本模块只负责 scope 校验、精确暂存和最多两轮 formatter 稳定化；不运行完整
required Gate、不提交，也不修改 lifecycle snapshot。controller 是唯一调用方。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from scripts.agent_runtime.git_state import run as git
from scripts.agent_runtime.session.contract import resolve_runtime_root
from scripts.harness.python_env import project_venv_dir


class CandidateError(RuntimeError):
    """candidate 不能安全稳定时的结构化错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class GitManifest:
    """保存 index、working tree 和 untracked 的 NUL-safe 精确并集。"""

    paths: tuple[str, ...]
    staged: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]
    manifest_hash: str


@dataclass(frozen=True, slots=True)
class PreparedCandidate:
    """formatter 稳定后、可绑定 Attempt 的 candidate 事实。"""

    manifest: GitManifest
    candidate_tree: str
    formatter_runs: int


def _nul_paths(output: str) -> set[str]:
    return {item for item in output.split('\0') if item}


def _normalize_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or value.startswith('/') or path.is_absolute() or '..' in path.parts:
        raise CandidateError('INVALID_MANIFEST_PATH', f'invalid repository path: {value!r}')
    normalized = path.as_posix()
    if normalized in {'', '.'}:
        raise CandidateError('INVALID_MANIFEST_PATH', f'invalid repository path: {value!r}')
    return normalized


def _stable_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def collect_manifest(repo: Path) -> GitManifest:
    """分别读取 staged/unstaged/untracked，避免 porcelain rename 解析歧义。"""
    staged = _nul_paths(
        git(repo, 'diff', '--cached', '--name-only', '--no-renames', '-z', 'HEAD', '--').stdout
    )
    unstaged = _nul_paths(git(repo, 'diff', '--name-only', '--no-renames', '-z', '--').stdout)
    untracked = _nul_paths(
        git(repo, 'ls-files', '--others', '--exclude-standard', '-z', '--').stdout
    )
    paths = {_normalize_path(item) for item in staged | unstaged | untracked}
    ordered = tuple(sorted(paths))
    return GitManifest(
        paths=ordered,
        staged=tuple(sorted(staged)),
        unstaged=tuple(sorted(unstaged)),
        untracked=tuple(sorted(untracked)),
        manifest_hash=_stable_hash(ordered),
    )


def _matches_scope(path: str, scopes: Sequence[object]) -> bool:
    for raw in scopes:
        scope = str(raw).strip().rstrip('/')
        if scope in {'', '.'} or path == scope or path.startswith(f'{scope}/'):
            return True
    return False


def validate_scope(manifest: GitManifest, record: Mapping[str, Any]) -> None:
    """在任何 index mutation 前校验 allowed/forbidden 与显式归因边界。"""
    forbidden = tuple(record.get('forbiddenPaths') or ())
    blocked = [path for path in manifest.paths if _matches_scope(path, forbidden)]
    if blocked:
        raise CandidateError('FORBIDDEN_PATH', f'forbidden candidate paths: {blocked}')
    allowed = tuple(record.get('allowedPaths') or ('.',))
    outside = [path for path in manifest.paths if not _matches_scope(path, allowed)]
    if outside:
        raise CandidateError('SCOPE_MISMATCH', f'candidate paths outside allowed scope: {outside}')


def _stage_paths(repo: Path, paths: Sequence[str]) -> None:
    if not paths:
        return
    payload = b''.join(os.fsencode(path) + b'\0' for path in sorted(set(paths)))
    # git_state 的统一 bounded wrapper 不接收 stdin；临时 pathspec 文件避免 shell
    # 拼接，也完整保留空格、换行和 deletion 路径。
    descriptor, raw_path = tempfile.mkstemp(prefix='feipi-pathspec-', suffix='.nul')
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        result = git(
            repo,
            'add',
            '-A',
            f'--pathspec-from-file={raw_path}',
            '--pathspec-file-nul',
            text=False,
            timeout=30,
            check=False,
        )
    finally:
        Path(raw_path).unlink(missing_ok=True)
    if result.returncode != 0:
        message = result.stderr.decode(errors='replace').strip()
        raise CandidateError('EXACT_STAGE_FAILED', message or 'git add failed')


def stage_exact(repo: Path, manifest: GitManifest) -> GitManifest:
    """只暂存 manifest 内尚未 staged 的路径，并保留 staged deletion 语义。"""
    current = collect_manifest(repo)
    if current.paths != manifest.paths:
        raise CandidateError(
            'MANIFEST_CHANGED',
            f'manifest changed before stage: expected={manifest.paths}, actual={current.paths}',
        )
    to_stage = sorted((set(current.unstaged) | set(current.untracked)) & set(manifest.paths))
    _stage_paths(repo, to_stage)
    stable = collect_manifest(repo)
    if stable.paths != manifest.paths or stable.staged != manifest.paths:
        raise CandidateError(
            'EXACT_STAGE_MISMATCH',
            f'exact stage mismatch: expected={manifest.paths}, staged={stable.staged}',
        )
    if stable.unstaged or stable.untracked:
        raise CandidateError('EXACT_STAGE_MISMATCH', 'working tree remains dirty after exact stage')
    return stable


def default_formatter_argv(repo: Path) -> tuple[str, ...]:
    """只探测 pre-commit executable；具体只运行两个可修改源码的 Ruff hook。"""
    local = project_venv_dir(repo) / 'bin' / 'pre-commit'
    executable = (
        str(local) if local.is_file() and os.access(local, os.X_OK) else shutil.which('pre-commit')
    )
    return (str(executable),) if executable else ()


def _default_log_dir(repo: Path) -> Path:
    """为非 controller 调用提供 run-scoped runtime 日志目录。"""
    run_id = os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID')
    identity = run_id or f'pid-{os.getpid()}'
    return resolve_runtime_root(repo) / 'runs' / identity / 'change-candidate'


def _run_changed_file_cheap_checks(
    repo: Path,
    manifest: GitManifest,
    log_dir: Path,
) -> None:
    """稳定化后运行适用的 Spotless/中文注释检查，不允许它们修改 candidate。"""
    from scripts.agent_runtime.change.runtime import run_bounded

    existing = [path for path in manifest.paths if (repo / path).is_file()]
    java_files = [path for path in existing if path.endswith(('.java', '.kt', '.kts'))]
    script_files = [
        path for path in existing if path.startswith('scripts/') and path.endswith(('.py', '.sh'))
    ]
    commands: list[tuple[str, list[str], int]] = []
    if java_files:
        commands.append(
            (
                'spotless',
                [str(repo / 'gradlew'), 'spotlessCheck', '--console=plain'],
                180,
            )
        )
        commands.append(
            (
                'java-comments',
                [
                    sys.executable,
                    '-m',
                    'scripts.checks',
                    'source.comment-language',
                    *java_files,
                    '--policy',
                    str(repo / 'config/technical-terms.json'),
                ],
                30,
            )
        )
    if script_files:
        commands.append(
            (
                'script-comments',
                [
                    sys.executable,
                    '-m',
                    'scripts.checks',
                    'source.comment-language',
                    '--script-comments',
                    *script_files,
                    '--policy',
                    str(repo / 'config/technical-terms.json'),
                ],
                30,
            )
        )
    for name, command, timeout in commands:
        result = run_bounded(
            command,
            cwd=repo,
            timeout=timeout,
            env=None,
            log_path=log_dir / f'cheap-{name}.log',
        )
        if not result.passed:
            raise CandidateError(
                'CHEAP_CHECK_FAILED',
                f'{name} failed: {result.output_tail or result.exit_reason}',
            )
        after = collect_manifest(repo)
        if after.paths != manifest.paths or after.unstaged or after.untracked:
            raise CandidateError(
                'CHEAP_CHECK_MUTATED_CANDIDATE',
                f'{name} modified the stable candidate',
            )


def prepare_candidate(
    repo: Path,
    record: Mapping[str, Any],
    *,
    formatter_argv: Sequence[str] | None = None,
    run_formatter: Any | None = None,
    log_dir: Path | None = None,
) -> PreparedCandidate:
    """自动 manifest、exact-stage，并允许 formatter 修改归属路径后自动再暂存一次。

    formatter 第一次修改 candidate 是可恢复稳定化；第二次仍修改、失败或触及 scope 外
    路径时返回 ``REPAIR_REQUIRED``，绝不自动 stage 新增的越界路径。
    """
    manifest = collect_manifest(repo)
    if not manifest.paths:
        raise CandidateError('NO_CHANGES', 'no task-owned changes')
    validate_scope(manifest, record)
    stage_exact(repo, manifest)
    default_formatter = formatter_argv is None
    argv = tuple(formatter_argv) if formatter_argv is not None else default_formatter_argv(repo)
    candidate_log_dir = Path(log_dir or _default_log_dir(repo)).resolve()
    if not argv:
        candidate_tree = git(repo, 'write-tree').stdout.strip()
        _run_changed_file_cheap_checks(repo, manifest, candidate_log_dir)
        return PreparedCandidate(manifest, candidate_tree, 0)
    if run_formatter is None:
        from scripts.agent_runtime.change.runtime import run_bounded

        def run_formatter(command: Sequence[str]) -> Any:
            """通过有界 runner 执行可修改源码的 hook；不运行审计或完整 Gate。"""
            if not default_formatter:
                return run_bounded(
                    command,
                    cwd=repo,
                    timeout=600,
                    env=None,
                    log_path=candidate_log_dir / 'formatter.log',
                )
            executable, *paths = command
            outcomes = [
                run_bounded(
                    [executable, 'run', hook, '--files', *paths],
                    cwd=repo,
                    timeout=600,
                    env=None,
                    log_path=candidate_log_dir / f'formatter-{hook}.log',
                )
                for hook in ('ruff-format', 'ruff')
            ]
            return next((item for item in outcomes if not item.passed), outcomes[-1])

    previous_tree = git(repo, 'write-tree').stdout.strip()
    for pass_number in (1, 2):
        result = run_formatter([*argv, *manifest.paths])
        current = collect_manifest(repo)
        if set(current.paths) - set(manifest.paths):
            raise CandidateError(
                'FORMATTER_SCOPE_ESCAPE',
                f'formatter touched paths outside manifest: {sorted(set(current.paths) - set(manifest.paths))}',
            )
        changed = bool(current.unstaged or current.untracked)
        returncode = int(getattr(result, 'returncode', getattr(result, 'return_code', 0)) or 0)
        if changed and pass_number == 1:
            _stage_paths(repo, sorted(set(current.unstaged) | set(current.untracked)))
            restaged = collect_manifest(repo)
            if restaged.paths != manifest.paths or restaged.staged != manifest.paths:
                raise CandidateError('FORMATTER_STAGE_MISMATCH', 'formatter restage was not exact')
            previous_tree = git(repo, 'write-tree').stdout.strip()
            continue
        candidate_tree = git(repo, 'write-tree').stdout.strip()
        tree_changed = candidate_tree != previous_tree
        if returncode != 0 or changed or (pass_number == 2 and tree_changed):
            raise CandidateError(
                'FORMATTER_UNSTABLE',
                f'formatter did not stabilize on pass {pass_number}',
            )
        _run_changed_file_cheap_checks(repo, manifest, candidate_log_dir)
        return PreparedCandidate(collect_manifest(repo), candidate_tree, pass_number)
    raise CandidateError('FORMATTER_UNSTABLE', 'formatter did not stabilize')
