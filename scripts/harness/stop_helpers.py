"""Pure helpers for unified Stop runtime.

This module intentionally has no CLI entrypoint.  `scripts/harness/stop_entry.py`
is the only production Stop entry.
"""

from __future__ import annotations

import importlib
import hashlib
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.agent_runtime import policy as runtime_policy  # noqa: E402
from scripts.claude_hooks import paths as runtime_paths  # noqa: E402
from scripts.claude_hooks.evidence import pre_bash_exempts_missing_snapshot  # noqa: E402
from scripts.quality import changed_files as changed_file_utils  # noqa: E402

LOCAL_ONLY_PATHS = [
    '.claude/settings.local.json',
    '.mcp.json',
    '.env',
    'data',
    'output',
    '.venv',
    '.pytest_cache',
]


# 维护 UTC 时间字符串。
def utc_now() -> str:
    """返回：
        当前 UTC ISO-8601 时间字符串。
    """
    return datetime.now(timezone.utc).isoformat()


# 切换 helper 使用的仓库根。
def _use_repo_root(repo_root: Path) -> None:
    """参数：
        repo_root: 新的仓库根目录。
    """
    global REPO_ROOT
    REPO_ROOT = repo_root.resolve()


# 规范化仓库相对路径。
def _normalize(path: str) -> str:
    """参数：
        path: 原始路径。

    返回：
        标准化后的仓库相对路径。
    """
    return changed_file_utils.normalize_path(path)


# 读取当前 Git dirty 文件。
def read_git_dirty_files(repo_root: Path | None = None) -> list[str]:
    """参数：
        repo_root: 可选仓库根目录。

    返回：
        dirty 文件路径列表。
    """
    return changed_file_utils.read_git_dirty_files(repo_root or REPO_ROOT)


class GitEvidenceError(RuntimeError):
    """Raised when a required Git fact cannot be collected without guessing."""


# 执行必需的 Git 查询，在事实无法证明时以关闭方式失败。
def _git_lines_required(repo_root: Path, *args: str) -> list[str]:
    """参数：
        repo_root: 当前仓库根目录。
        *args: 传给 Git 的查询参数。

    返回：
        去除空白行的 Git 输出列表。

    异常：
        GitEvidenceError: Git 查询无法启动或返回失败时抛出。
    """

    try:
        proc = subprocess.run(
            ['git', '-C', str(repo_root), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        raise GitEvidenceError(f'Git query could not start: {" ".join(args)}: {exc}') from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f'exit {proc.returncode}'
        raise GitEvidenceError(f'Git query failed: {" ".join(args)}: {detail}')
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


# 执行必需的 Git 查询并要求结果恰好包含一个值。
def _git_value_required(repo_root: Path, *args: str) -> str:
    """参数：
        repo_root: 当前仓库根目录。
        *args: 传给 Git 的查询参数。

    返回：
        Git 查询的唯一输出值。

    异常：
        GitEvidenceError: 查询失败或结果数量不是一个时抛出。
    """
    values = _git_lines_required(repo_root, *args)
    if len(values) != 1:
        raise GitEvidenceError(f'Git query did not return one value: {" ".join(args)}')
    return values[0]


# 执行内容敏感的 Git 查询，并保留原始字节而不进行文本规范化。
def _git_bytes_required(repo_root: Path, *args: str) -> bytes:
    """参数：
        repo_root: 当前仓库根目录。
        *args: 传给 Git 的查询参数。

    返回：
        Git 查询的原始输出字节。

    异常：
        GitEvidenceError: Git 查询无法启动或返回失败时抛出。
    """

    try:
        proc = subprocess.run(
            ['git', '-C', str(repo_root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        raise GitEvidenceError(f'Git query could not start: {" ".join(args)}: {exc}') from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors='replace').strip() or f'exit {proc.returncode}'
        raise GitEvidenceError(f'Git query failed: {" ".join(args)}: {detail}')
    return proc.stdout


# 在不跟随符号链接的前提下，对未跟踪路径名、类型、模式和内容字节计算哈希。
def _hash_untracked_contents(repo_root: Path, raw_paths: bytes) -> tuple[str, int]:
    """参数：
        repo_root: 当前仓库根目录。
        raw_paths: 以空字节分隔的未跟踪路径字节。

    返回：
        未跟踪内容哈希与文件数量。

    异常：
        GitEvidenceError: 路径不安全、文件类型不支持或采集期间内容变更时抛出。
    """

    digest = hashlib.sha256()
    digest.update(b'feipi-untracked-snapshot-v1\0')
    count = 0
    if not raw_paths:
        return digest.hexdigest(), count
    if not raw_paths.endswith(b'\0'):
        raise GitEvidenceError('Git returned an unterminated untracked path list')
    entries = raw_paths.split(b'\0')[:-1]
    repo_real = repo_root.resolve(strict=True)
    for raw_path in entries:
        components = raw_path.split(b'/')
        if (
            not raw_path
            or raw_path.startswith(b'/')
            or any(component in {b'', b'.', b'..'} for component in components)
        ):
            raise GitEvidenceError(
                f'unsafe untracked path in Git evidence: {os.fsdecode(raw_path)!r}'
            )
        names = [os.fsdecode(component) for component in components]
        relative_text = os.fsdecode(raw_path)
        candidate = repo_real.joinpath(*names)
        try:
            candidate.parent.resolve(strict=True).relative_to(repo_real)
        except (OSError, ValueError) as exc:
            raise GitEvidenceError(
                f'untracked path escapes checkout: {relative_text!r}'
            ) from exc

        directory_descriptors: list[int] = []
        directory_names: list[str] = []
        try:
            root_descriptor = os.open(
                repo_real,
                os.O_RDONLY
                | getattr(os, 'O_DIRECTORY', 0)
                | getattr(os, 'O_NOFOLLOW', 0),
            )
            directory_descriptors.append(root_descriptor)
            root_metadata = os.fstat(root_descriptor)
            for name in names[:-1]:
                descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, 'O_DIRECTORY', 0)
                    | getattr(os, 'O_NOFOLLOW', 0),
                    dir_fd=directory_descriptors[-1],
                )
                directory_names.append(name)
                directory_descriptors.append(descriptor)
            final_name = names[-1]
            metadata = os.stat(
                final_name,
                dir_fd=directory_descriptors[-1],
                follow_symlinks=False,
            )
            count += 1
            digest.update(len(raw_path).to_bytes(8, 'big'))
            digest.update(raw_path)
            digest.update(stat.S_IFMT(metadata.st_mode).to_bytes(8, 'big'))
            digest.update(stat.S_IMODE(metadata.st_mode).to_bytes(8, 'big'))
            if stat.S_ISLNK(metadata.st_mode):
                target = os.fsencode(
                    os.readlink(final_name, dir_fd=directory_descriptors[-1])
                )
                digest.update(len(target).to_bytes(8, 'big'))
                digest.update(target)
            elif stat.S_ISREG(metadata.st_mode):
                digest.update(metadata.st_size.to_bytes(8, 'big'))
                descriptor = os.open(
                    final_name,
                    os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0),
                    dir_fd=directory_descriptors[-1],
                )
                try:
                    opened = os.fstat(descriptor)
                    if opened.st_dev != metadata.st_dev or opened.st_ino != metadata.st_ino:
                        raise GitEvidenceError(
                            f'untracked file changed while collecting evidence: {relative_text!r}'
                        )
                    while True:
                        chunk = os.read(descriptor, 1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                    finished = os.fstat(descriptor)
                    if (
                        finished.st_size != opened.st_size
                        or finished.st_mtime_ns != opened.st_mtime_ns
                        or finished.st_ctime_ns != opened.st_ctime_ns
                    ):
                        raise GitEvidenceError(
                            f'untracked file changed while collecting evidence: {relative_text!r}'
                        )
                finally:
                    os.close(descriptor)
            else:
                raise GitEvidenceError(
                    f'unsupported untracked file type in Git evidence: {relative_text!r}'
                )

            final_metadata = os.stat(
                final_name,
                dir_fd=directory_descriptors[-1],
                follow_symlinks=False,
            )
            if (
                final_metadata.st_dev != metadata.st_dev
                or final_metadata.st_ino != metadata.st_ino
                or final_metadata.st_mode != metadata.st_mode
                or final_metadata.st_size != metadata.st_size
                or final_metadata.st_mtime_ns != metadata.st_mtime_ns
                or final_metadata.st_ctime_ns != metadata.st_ctime_ns
            ):
                raise GitEvidenceError(
                    f'untracked file changed while collecting evidence: {relative_text!r}'
                )
            for index, name in enumerate(directory_names):
                attached = os.stat(
                    name,
                    dir_fd=directory_descriptors[index],
                    follow_symlinks=False,
                )
                opened = os.fstat(directory_descriptors[index + 1])
                if (
                    not stat.S_ISDIR(attached.st_mode)
                    or attached.st_dev != opened.st_dev
                    or attached.st_ino != opened.st_ino
                ):
                    raise GitEvidenceError(
                        f'untracked parent changed while collecting evidence: {relative_text!r}'
                    )
            current_root = repo_real.stat()
            if (
                current_root.st_dev != root_metadata.st_dev
                or current_root.st_ino != root_metadata.st_ino
            ):
                raise GitEvidenceError('checkout root changed while collecting Git evidence')
            candidate.parent.resolve(strict=True).relative_to(repo_real)
        except GitEvidenceError:
            raise
        except (OSError, ValueError) as exc:
            raise GitEvidenceError(
                f'untracked file changed while collecting evidence: {relative_text!r}: {exc}'
            ) from exc
        finally:
            for descriptor in reversed(directory_descriptors):
                os.close(descriptor)
    return digest.hexdigest(), count


# 采集覆盖 HEAD、索引、worktree 与未跟踪文件的内容敏感快照。
def checkout_content_snapshot(repo_root: Path) -> dict[str, Any]:
    """参数：
        repo_root: 当前仓库根目录。

    返回：
        checkout 内容组件哈希与综合指纹。

    异常：
        GitEvidenceError: 任一必需 Git 事实无法安全采集时抛出。
    """

    head = _git_value_required(repo_root, 'rev-parse', 'HEAD')
    status = _git_bytes_required(
        repo_root,
        'status',
        '--porcelain=v1',
        '-z',
        '--untracked-files=all',
    )
    staged = _git_bytes_required(
        repo_root,
        'diff',
        '--cached',
        '--no-ext-diff',
        '--no-textconv',
        '--binary',
        '--full-index',
        '--',
    )
    working = _git_bytes_required(
        repo_root,
        'diff',
        '--no-ext-diff',
        '--no-textconv',
        '--binary',
        '--full-index',
        '--',
    )
    untracked_paths = _git_bytes_required(
        repo_root,
        'ls-files',
        '--others',
        '--exclude-standard',
        '-z',
    )
    untracked_sha, untracked_count = _hash_untracked_contents(repo_root, untracked_paths)
    components = {
        'schemaVersion': 1,
        'headCommit': head,
        'statusSha256': hashlib.sha256(status).hexdigest(),
        'stagedDiffSha256': hashlib.sha256(staged).hexdigest(),
        'workingDiffSha256': hashlib.sha256(working).hexdigest(),
        'untrackedContentSha256': untracked_sha,
        'untrackedCount': untracked_count,
    }
    encoded = json.dumps(components, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return {**components, 'fingerprint': hashlib.sha256(encoded).hexdigest()}


# 执行可选 Git 查询并取第一个输出值。
def _git_optional_value(repo_root: Path, *args: str) -> str:
    """参数：
        repo_root: 当前仓库根目录。
        *args: 传给 Git 的查询参数。

    返回：
        第一个输出值；查询无结果时返回空字符串。
    """
    values = _git_lines(repo_root, *args)
    return values[0] if values else ''


# 根据基线、当前提交与目标分支差异判定集成位置状态。
def _target_status(*, base: str, head: str, target_head: str, ahead: int, behind: int) -> str:
    """参数：
        base: 运行基线提交。
        head: 当前 checkout 提交。
        target_head: 目标分支提交。
        ahead: 当前结果相对目标超前的提交数。
        behind: 当前结果相对目标落后的提交数。

    返回：
        目标分支与当前结果的位置状态。
    """
    if not target_head:
        return 'MISSING'
    if target_head == head:
        return 'AT_RESULT'
    if target_head == base:
        return 'UNCHANGED_FROM_BASE'
    if ahead and behind:
        return 'DIVERGED'
    if behind:
        return 'TARGET_AHEAD'
    if ahead:
        return 'RESULT_AHEAD'
    return 'UNKNOWN'


# 为单个 Registry 绑定运行采集 Stop 与 finalize 共享的 Git 真实事实。
def collect_git_evidence(repo_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    """参数：
        repo_root: 运行绑定的 checkout 根目录。
        record: Registry 绑定的运行记录。

    返回：
        已提交、未提交、未跟踪、目标分支与主 checkout 事实的统一证据映射。

    异常：
        GitEvidenceError: 运行基线、主 checkout 或必需 Git 事实无法证明时抛出。
    """

    base = str(record.get('baseCommit') or '')
    if not base:
        raise GitEvidenceError('run record has no baseCommit')
    snapshot_before = checkout_content_snapshot(repo_root)
    head = _git_value_required(repo_root, 'rev-parse', 'HEAD')
    checkout_branch = _git_optional_value(
        repo_root,
        'symbolic-ref',
        '--quiet',
        '--short',
        'HEAD',
    )
    committed = sorted(changed_file_utils.dedupe_paths(
        _git_lines_required(repo_root, 'diff', '--name-only', f'{base}...HEAD')
    ))
    uncommitted = sorted(changed_file_utils.dedupe_paths(
        _git_lines_required(repo_root, 'diff', '--name-only')
        + _git_lines_required(repo_root, 'diff', '--cached', '--name-only')
    ))
    untracked = sorted(changed_file_utils.dedupe_paths(
        _git_lines_required(repo_root, 'ls-files', '--others', '--exclude-standard')
    ))
    commits = _git_lines_required(repo_root, 'rev-list', '--reverse', f'{base}..HEAD')

    target_branch = str(record.get('targetBranch') or '')
    target_ref = f'refs/heads/{target_branch}' if target_branch else ''
    target_head = _git_optional_value(repo_root, 'rev-parse', '--verify', target_ref) if target_ref else ''
    ahead = behind = 0
    merge_base = ''
    if target_head:
        counts = _git_value_required(
            repo_root,
            'rev-list',
            '--left-right',
            '--count',
            f'{target_ref}...HEAD',
        )
        try:
            behind, ahead = (int(item) for item in counts.split())
        except (TypeError, ValueError) as exc:
            raise GitEvidenceError(f'invalid ahead/behind result: {counts!r}') from exc
        merge_base = _git_value_required(repo_root, 'merge-base', target_ref, 'HEAD')

    primary_raw = str(record.get('primaryRepoRoot') or '')
    if not primary_raw:
        raise GitEvidenceError('run record has no primaryRepoRoot')
    primary_root = Path(primary_raw).expanduser()
    if not primary_root.exists():
        raise GitEvidenceError('primary checkout is unavailable')
    primary_head = _git_value_required(primary_root, 'rev-parse', 'HEAD')
    primary_branch = _git_optional_value(
        primary_root,
        'symbolic-ref',
        '--quiet',
        '--short',
        'HEAD',
    )
    primary_tracked = sorted(changed_file_utils.dedupe_paths(
        _git_lines_required(primary_root, 'diff', '--name-only')
        + _git_lines_required(primary_root, 'diff', '--cached', '--name-only')
    ))
    primary_untracked = sorted(changed_file_utils.dedupe_paths(
        _git_lines_required(primary_root, 'ls-files', '--others', '--exclude-standard')
    ))
    initial_dirty = record.get('initialDirtySnapshot')
    if not isinstance(initial_dirty, dict):
        raise GitEvidenceError('run record initialDirtySnapshot is invalid')
    target_state = _target_status(
        base=base,
        head=head,
        target_head=target_head,
        ahead=ahead,
        behind=behind,
    )
    checkout_status = {
        'checkoutRoot': str(repo_root.resolve()),
        'headCommit': head,
        'branch': checkout_branch,
        'detached': bool(head and not checkout_branch),
        'clean': not (uncommitted or untracked),
        'trackedFiles': uncommitted,
        'untrackedFiles': untracked,
    }
    primary_status = {
        'checkoutRoot': str(primary_root.resolve()),
        'headCommit': primary_head,
        'branch': primary_branch,
        'detached': bool(primary_head and not primary_branch),
        'clean': not (primary_tracked or primary_untracked),
        'dirty': bool(primary_tracked or primary_untracked),
        'trackedFiles': primary_tracked,
        'untrackedFiles': primary_untracked,
    }
    target_status = {
        'branch': target_branch,
        'exists': bool(target_head),
        'headCommit': target_head,
        'state': target_state,
        'movedSinceBase': bool(target_head and target_head != base),
        'checkedOutInPrimary': bool(target_branch and target_branch == primary_branch),
    }
    snapshot_after = checkout_content_snapshot(repo_root)
    if snapshot_before['fingerprint'] != snapshot_after['fingerprint']:
        raise GitEvidenceError('checkout changed while collecting Git evidence')
    if head != snapshot_after['headCommit']:
        raise GitEvidenceError('checkout HEAD changed while collecting Git evidence')

    return {
        'headCommit': head,
        'baseCommit': base,
        'commits': commits,
        'committedFiles': committed,
        'uncommittedFiles': uncommitted,
        'untrackedFiles': untracked,
        'changedFiles': changed_file_utils.dedupe_paths(committed + uncommitted + untracked),
        'ahead': ahead,
        'behind': behind,
        'aheadBehind': {'ahead': ahead, 'behind': behind},
        'mergeBase': merge_base,
        'initialDirtySnapshot': initial_dirty,
        'initialDirtyBaseline': initial_dirty,
        'changeAttribution': record.get('changeAttribution', {}),
        'checkoutKind': str(record.get('checkoutKind') or ''),
        'checkoutCreator': str(record.get('checkoutCreator') or 'unknown'),
        'checkoutIdentity': {
            'repoKey': str(record.get('repoKey') or ''),
            'worktreeId': str(record.get('worktreeId') or ''),
            'checkoutRoot': str(repo_root.resolve()),
        },
        'targetBranch': target_branch,
        'targetHead': target_head,
        'targetState': target_state,
        'targetStatus': target_status,
        'targetMovedSinceBase': bool(target_head and target_head != base),
        'checkoutStatus': checkout_status,
        'checkoutSnapshot': snapshot_after,
        'checkoutFingerprint': snapshot_after['fingerprint'],
        'primary': primary_status,
        'primaryStatus': primary_status,
        'queryErrors': [],
    }


# 计算 dirty 状态指纹。
def git_dirty_hash(repo_root: Path) -> str:
    """参数：
        repo_root: 仓库根目录。

    返回：
        当前 dirty 状态哈希。
    """
    import hashlib

    state = changed_file_utils.read_git_dirty_state(repo_root)
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# 执行 Git 命令并返回非空行。
def _git_lines(repo_root: Path, *args: str) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        args: git 子命令参数。

    返回：
        stdout 中的非空行；命令失败时返回空列表。
    """
    try:
        proc = subprocess.run(
            ['git', '-C', str(repo_root), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


# 解析 identity 对应 changed-files 审计路径。
def identity_changed_file_paths(identity: runtime_paths.RuntimeIdentity, repo_root: Path | None = None) -> list[Path]:
    """参数：
        identity: 运行时身份对象。
        repo_root: 可选仓库根目录。

    返回：
        identity 对应的 changed-files JSONL 路径列表。
    """
    repo_root = repo_root or REPO_ROOT
    include_agents = not identity.is_agent
    return [
        log_dir / 'changed-files.jsonl'
        for log_dir in runtime_paths.session_log_dirs(repo_root, identity, include_agents=include_agents)
    ]


# 读取 identity 对应 changed-files 审计。
def read_identity_changed_files(identity: runtime_paths.RuntimeIdentity, repo_root: Path | None = None) -> list[str]:
    """参数：
        identity: 运行时身份对象。
        repo_root: 可选仓库根目录。

    返回：
        审计记录中的 changed-files 列表。
    """
    repo_root = repo_root or REPO_ROOT
    agent_filter = identity.raw_agent_id if identity.is_agent else None
    return changed_file_utils.read_recorded_changed_files_from_paths(
        identity_changed_file_paths(identity, repo_root=repo_root),
        identity.raw_session_id,
        agent_id=agent_filter,
    )


# 读取 identity 对应 hook events。
def read_identity_hook_events(identity: runtime_paths.RuntimeIdentity, repo_root: Path | None = None) -> list[dict[str, Any]]:
    """参数：
        identity: 运行时身份对象。
        repo_root: 可选仓库根目录。

    返回：
        过滤到当前 identity 的 hook event 记录。
    """
    repo_root = repo_root or REPO_ROOT
    events: list[dict[str, Any]] = []
    for changed_path in identity_changed_file_paths(identity, repo_root=repo_root):
        path = changed_path.with_name('hook-events.jsonl')
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding='utf-8').splitlines():
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get('sessionId') != identity.raw_session_id:
                continue
            if identity.is_agent and (record.get('agentId') or '') != identity.raw_agent_id:
                continue
            events.append(record)
    return events


# 判断 Bash snapshot 缺失是否应阻断。
def _bash_snapshot_missing_blocks(event: dict[str, Any], pre_event: dict[str, Any] | None) -> bool:
    """参数：
        event: 当前 hook event。
        pre_event: 同一工具调用标识的前置 Bash 事件。

    返回：
        缺失 snapshot 是否属于阻断性 attribution gap。
    """
    if pre_bash_exempts_missing_snapshot(pre_event):
        return False
    if event.get('bashSnapshotRequired') is True or event.get('bashMutationTracking') is True:
        return True
    if pre_event and pre_event.get('bashMutationTracking') is True:
        return True
    return False


# 汇总 identity attribution gap 失败。
def identity_attribution_gap_failures(identity: runtime_paths.RuntimeIdentity, repo_root: Path | None = None) -> list[str]:
    """参数：
        identity: 运行时身份对象。
        repo_root: 可选仓库根目录。

    返回：
        attribution gap 失败说明列表。
    """
    repo_root = repo_root or REPO_ROOT
    failures: list[str] = []
    events = read_identity_hook_events(identity, repo_root=repo_root)
    pre_events: dict[str, dict[str, Any]] = {}
    for event in events:
        tool_use = event.get('toolUseId')
        if isinstance(tool_use, str) and tool_use and event.get('event') == 'pre-bash':
            pre_events[tool_use] = event
    for event in events:
        if event.get('status') == 'BASH_SNAPSHOT_MISSING':
            tool_use = event.get('toolUseId') or 'unknown'
            if _bash_snapshot_missing_blocks(event, pre_events.get(tool_use)):
                failures.append(f'BASH_SNAPSHOT_MISSING attribution gap for toolUseId={tool_use}')
    return failures


@dataclass(frozen=True)
class StopChangedFiles:
    changed_files: list[str]
    evidence_mode: str
    evidence_warnings_or_failures: list[str]
    git_dirty_files: list[str]

    # 兼容旧 tuple 解包调用。
    def __iter__(self):
        """返回：
            依次产出 changed_files 和 evidence_mode。
        """
        yield self.changed_files
        yield self.evidence_mode


# 收集 Stop 阶段 changed-files 证据。
def collect_stop_changed_files(
    identity: runtime_paths.RuntimeIdentity | str | None,
    fallback_session_id: str | None,
    agent_id: str | None = None,
    repo_root: Path | None = None,
) -> StopChangedFiles:
    """参数：
        identity: 已解析运行时身份或旧会话标识。
        fallback_session_id: identity 缺失时的 session id。
        agent_id: 可选 agent id。
        repo_root: 可选仓库根目录。

    返回：
        Stop 已变更文件及证据模式。
    """
    repo_root = repo_root or REPO_ROOT
    if isinstance(identity, str):
        return StopChangedFiles(
            changed_file_utils.collect_changed_files(identity, include_git=False, repo_root=repo_root, agent_id=agent_id),
            'session',
            [],
            [],
        )
    if identity is not None and identity.has_session:
        changed = read_identity_changed_files(identity, repo_root=repo_root)
        dirty = read_git_dirty_files(repo_root)
        failures = identity_attribution_gap_failures(identity, repo_root)
        return StopChangedFiles(changed, 'identity-agent' if identity.is_agent else 'identity-session', failures, dirty)
    dirty = read_git_dirty_files(repo_root)
    if dirty:
        return StopChangedFiles(dirty, 'fail-closed-git', [], dirty)
    changed = changed_file_utils.collect_changed_files(fallback_session_id, include_git=True, repo_root=repo_root, agent_id=agent_id)
    return StopChangedFiles(changed, 'fail-closed', [], dirty)


# 读取 active change id。
def _read_active_change_id(identity: runtime_paths.RuntimeIdentity, repo_root: Path | None = None) -> str | None:
    """参数：
        identity: 运行时身份对象。
        repo_root: 可选仓库根目录。

    返回：
        active change id；无法解析时返回 None。
    """
    repo_root = repo_root or REPO_ROOT
    paths = runtime_paths.build_paths(repo_root, identity=identity)
    candidates = paths.active_change_candidates
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
    return None


# 解析当前 change id。
def resolve_change_id(identity: runtime_paths.RuntimeIdentity | None = None) -> str:
    """参数：
        identity: 可选运行时身份对象。

    返回：
        ACTIVE_CHANGE_ID、active_change 文件或 unknown。
    """
    import os

    env = os.environ.get('ACTIVE_CHANGE_ID', '')
    if env:
        return env
    if identity is not None:
        cid = _read_active_change_id(identity)
        if cid:
            return cid
    return 'unknown'


# 判断变更是否需要 OpenSpec。
def changed_files_require_openspec(changed_files: list[str]) -> bool:
    """参数：
        changed_files: 已变更文件列表。

    返回：
        任一 protected path 命中时返回 True。
    """
    return any(runtime_policy.is_protected_path(path, REPO_ROOT) for path in changed_files)


# 检查 local-only 路径。
def check_local_only_status(changed_files: list[str] | None = None) -> list[str]:
    """参数：
        changed_files: 可选 changed-files 列表。

    返回：
        local-only 路径警告列表。
    """
    if changed_files is not None:
        warnings: list[str] = []
        for changed in changed_files:
            normalized = _normalize(changed)
            if any(normalized == local or normalized.startswith(f'{local.rstrip("/")}/') for local in LOCAL_ONLY_PATHS):
                warnings.append(f'{normalized} 是 local-only 路径')
        return warnings
    return []


# 计算 changed-files 对应 required targets。
def required_targets(changed_files: list[str]) -> list[str]:
    """参数：
        changed_files: 已变更文件列表。

    返回：
        需要执行的质量目标。
    """
    classifier = importlib.import_module('scripts.claude_hooks.classify')
    return classifier.required_quality_targets(changed_files)
