"""Git 证据收集、dirty 文件过滤与底层 Git 查询工具。

本模块是 Stop 流程中所有 Git 事实采集的唯一实现。
`stop_helpers` 保留面向 identity/session 的高层辅助函数。
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from scripts.quality import changed_files as changed_file_utils


# ── 异常 ──────────────────────────────────────────────────────────


class GitEvidenceError(RuntimeError):
    """Raised when a required Git fact cannot be collected without guessing."""


# ── 底层 Git 查询 ─────────────────────────────────────────────────


# 执行可选版本库查询并返回非空行。
def git_lines(repo_root: Path, *args: str) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        *args: 版本库命令参数。

    返回：
        查询成功时返回非空行列表，失败时返回空列表。
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


# 执行必需版本库查询并在事实无法证明时关闭失败。
def _git_lines_required(repo_root: Path, *args: str) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        *args: 版本库命令参数。

    返回：
        查询结果的非空行列表。

    异常：
        GitEvidenceError: 查询无法执行或返回失败状态。
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


# 执行必需版本库查询并要求恰好返回一个值。
def _git_value_required(repo_root: Path, *args: str) -> str:
    """参数：
        repo_root: 仓库根目录。
        *args: 版本库命令参数。

    返回：
        查询返回的唯一值。

    异常：
        GitEvidenceError: 查询失败或结果数量不为一。
    """
    values = _git_lines_required(repo_root, *args)
    if len(values) != 1:
        raise GitEvidenceError(f'Git query did not return one value: {" ".join(args)}')
    return values[0]


# 执行内容敏感的版本库查询并保留原始字节。
def _git_bytes_required(repo_root: Path, *args: str) -> bytes:
    """参数：
        repo_root: 仓库根目录。
        *args: 版本库命令参数。

    返回：
        未经文本规范化的查询输出字节。

    异常：
        GitEvidenceError: 查询无法执行或返回失败状态。
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


# 执行可选版本库查询并取第一个输出值。
def _git_optional_value(repo_root: Path, *args: str) -> str:
    """参数：
        repo_root: 仓库根目录。
        *args: 版本库命令参数。

    返回：
        第一个输出值；没有结果时返回空字符串。
    """
    values = git_lines(repo_root, *args)
    return values[0] if values else ''


# ── checkout 内容快照 ──────────────────────────────────────────────


# 对未跟踪路径的名称、类型、模式和内容计算哈希。
def _hash_untracked_contents(repo_root: Path, raw_paths: bytes) -> tuple[str, int]:
    """参数：
        repo_root: 仓库根目录。
        raw_paths: 以空字节分隔的未跟踪路径。

    返回：
        内容哈希和已处理路径数量。

    异常：
        GitEvidenceError: 路径或文件在采集期间不安全或发生变化。
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


# 采集覆盖提交、索引、工作区与未跟踪文件的内容快照。
def checkout_content_snapshot(repo_root: Path) -> dict[str, Any]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        各内容组成部分及其整体指纹。
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


# ── 目标分支状态 ──────────────────────────────────────────────────


# 根据基线、当前提交与目标分支差异判定集成位置状态。
def _target_status(*, base: str, head: str, target_head: str, ahead: int, behind: int) -> str:
    """参数：
        base: 基线提交。
        head: 当前提交。
        target_head: 目标分支提交。
        ahead: 结果领先目标分支的提交数。
        behind: 结果落后目标分支的提交数。

    返回：
        集成位置状态。
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


# ── 高层证据采集 ──────────────────────────────────────────────────


# 为单个登记运行采集停止与收尾阶段共享的版本库事实。
def collect_git_evidence(repo_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    """参数：
        repo_root: 仓库根目录。
        record: 当前会话记录。

    返回：
        内容快照、变更归属和集成位置等版本库事实。
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


# 计算工作区未提交状态哈希。
def git_dirty_hash(repo_root: Path) -> str:
    """参数：
        repo_root: 仓库根目录。

    返回：
        工作区未提交状态哈希。
    """
    state = changed_file_utils.read_git_dirty_state(repo_root)
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# ── dirty 文件过滤 ────────────────────────────────────────────────


# 排除会话启动前已存在的未提交文件。
def filter_baseline_dirty(
    changed_files: list[str],
    git_evidence: dict[str, Any],
) -> tuple[list[str], set[str]]:
    """参数：
        changed_files: 当前变更文件列表。
        git_evidence: 包含初始未提交快照的版本库证据。

    返回：
        过滤后的变更文件和基线未提交文件集合。
    """
    baseline_dirty: set[str] = set()
    initial_dirty = git_evidence.get('initialDirtySnapshot')
    if isinstance(initial_dirty, dict):
        for f in initial_dirty.get('tracked') or []:
            baseline_dirty.add(f)
        for f in initial_dirty.get('untracked') or []:
            baseline_dirty.add(f)
        changed_files = [f for f in changed_files if f not in baseline_dirty]
    return changed_files, baseline_dirty
