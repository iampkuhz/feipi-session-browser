"""Claude/Codex/Qoder 主 session git worktree 隔离工具。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from scripts.claude_hooks.paths import RuntimeIdentity, identity_from_values


SUPPORTED_CLIENTS = {'claude', 'codex', 'qoder'}
WORKTREE_STATE_DIR = 'feipi-agent-runtime/worktrees'
WORKTREE_LOCK_NAME = 'feipi-agent-runtime/worktree-create.lock'
WORKTREE_LOCK_STALE_SECONDS = 2 * 60 * 60


@dataclass(frozen=True)
class WorktreeDecision:
    """表示当前 runtime identity 的 worktree 判定结果。"""

    required: bool
    allowed: bool
    created: bool
    assigned: bool
    current_root: str
    expected_root: str
    marker_path: str
    reason: str = ''

    # 转为可写入 hook evidence 的 JSON 对象。
    def as_dict(self) -> dict[str, object]:
        """返回：
            可序列化的 worktree 判定详情。
        """
        return {
            'required': self.required,
            'allowed': self.allowed,
            'created': self.created,
            'assigned': self.assigned,
            'currentRoot': self.current_root,
            'expectedRoot': self.expected_root,
            'markerPath': self.marker_path,
            'reason': self.reason,
        }


# 返回当前 UTC timestamp。
def _utc_now() -> str:
    """返回：
        当前 UTC timestamp as ISO-8601 字符串。
    """
    return datetime.now(timezone.utc).isoformat()


# 执行 git 命令并返回 stdout。
def _git_output(repo_root: Path, *args: str) -> str:
    """参数：
        repo_root: git repository 或 worktree 根目录。
        args: git 子命令参数。

    返回：
        去除首尾空白的 stdout。
    """
    return subprocess.check_output(
        ['git', '-C', str(repo_root), *args],
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()


# 解析 git common dir。
def git_common_dir(repo_root: Path) -> Path:
    """参数：
        repo_root: git repository 或 worktree 根目录。

    返回：
        当前 repository 的 git common dir；非 git 目录时使用 ``.git`` 兜底。
    """
    root = repo_root.resolve()
    try:
        raw = _git_output(root, 'rev-parse', '--git-common-dir')
    except Exception:
        return root / '.git'
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


# 解析 primary repository 根目录。
def primary_repo_root(repo_root: Path) -> Path:
    """参数：
        repo_root: 当前检出目录根路径。

    返回：
        git common dir 对应的 primary checkout 根目录。
    """
    common = git_common_dir(repo_root)
    if common.name == '.git':
        return common.parent.resolve()
    try:
        raw = _git_output(repo_root, 'rev-parse', '--show-toplevel')
        return Path(raw).resolve()
    except Exception:
        return repo_root.resolve()


# 判断某路径是否位于另一个路径内部。
def _is_relative_to(path: Path, root: Path) -> bool:
    """参数：
        path: 候选路径。
        root: 根路径。

    返回：
        候选路径位于根路径内部时返回 true。
    """
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# 返回用于存放 session 工作树的父目录。
def worktree_parent_root(repo_root: Path) -> Path:
    """参数：
        repo_root: 当前检出目录根路径。

    返回：
        用于存放 per-session worktree 的父目录。
    """
    override = os.environ.get('FEIPI_AGENT_WORKTREE_ROOT', '').strip()
    if override:
        return Path(override).expanduser().resolve()
    primary = primary_repo_root(repo_root)
    return (primary.parent / f'.{primary.name}-agent-worktrees').resolve()


# 返回是否应为 identity 应用 worktree 边界。
def applies_to_identity(identity: RuntimeIdentity) -> bool:
    """参数：
        identity: 运行时身份。

    返回：
        当前 identity 属于受支持 client 且有 session id 时返回 true。
    """
    return bool(identity.raw_session_id) and identity.client in SUPPORTED_CLIENTS


# 返回 main session 形式的 identity。
def main_session_identity(identity: RuntimeIdentity) -> RuntimeIdentity:
    """参数：
        identity: runtime identity，可能包含 subagent id。

    返回：
        去除 agent id 后的 main-session identity。
    """
    return identity_from_values(identity.client, identity.raw_session_id, '')


# 返回当前 session 的期望 worktree 路径。
def expected_worktree_path(repo_root: Path, identity: RuntimeIdentity) -> Path:
    """参数：
        repo_root: 当前检出目录根路径。
        identity: 运行时身份。

    返回：
        根据 client/session 派生的 deterministic worktree 路径。
    """
    main_identity = main_session_identity(identity)
    return (
        worktree_parent_root(repo_root) / main_identity.client / main_identity.session_id
    ).resolve()


# 返回 assignment marker 路径。
def assignment_marker_path(repo_root: Path, identity: RuntimeIdentity) -> Path:
    """参数：
        repo_root: 当前检出目录根路径。
        identity: 运行时身份。

    返回：
        位于 git common dir 下的 assignment marker 路径。
    """
    main_identity = main_session_identity(identity)
    return (
        git_common_dir(repo_root)
        / WORKTREE_STATE_DIR
        / main_identity.client
        / f'{main_identity.session_id}.json'
    )


# 读取 assignment marker。
def read_assignment_marker(repo_root: Path, identity: RuntimeIdentity) -> dict[str, object] | None:
    """参数：
        repo_root: 当前检出目录根路径。
        identity: 运行时身份。

    返回：
        marker JSON 对象；不存在或非法时返回 None。
    """
    marker = assignment_marker_path(repo_root, identity)
    try:
        data = json.loads(marker.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


# 写入 assignment marker。
def write_assignment_marker(repo_root: Path, identity: RuntimeIdentity, worktree: Path) -> Path:
    """参数：
        repo_root: 当前检出目录根路径。
        identity: 运行时身份。
        worktree: 分配给主 session 的工作树路径。

    返回：
        marker 文件路径。
    """
    main_identity = main_session_identity(identity)
    marker = assignment_marker_path(repo_root, identity)
    payload = {
        'schemaVersion': 1,
        'createdAt': _utc_now(),
        'client': main_identity.client,
        'sessionId': main_identity.raw_session_id,
        'sessionSegment': main_identity.session_id,
        'worktreePath': str(worktree.resolve()),
        'primaryRepoRoot': str(primary_repo_root(repo_root)),
    }
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return marker


# 移除 stale worktree 创建锁。
def _remove_stale_lock(lock_path: Path) -> None:
    """参数：
        lock_path: git common dir 下的锁文件路径。
    """
    try:
        age = time.time() - lock_path.stat().st_mtime
    except (FileNotFoundError, OSError):
        return
    if age <= WORKTREE_LOCK_STALE_SECONDS:
        return
    try:
        lock_path.unlink()
    except OSError:
        pass


# 获取 worktree 创建锁。
def _acquire_lock(repo_root: Path) -> Path | None:
    """参数：
        repo_root: 当前检出目录根路径。

    返回：
        成功时返回锁文件路径，否则返回 None。
    """
    lock_path = git_common_dir(repo_root) / WORKTREE_LOCK_NAME
    _remove_stale_lock(lock_path)
    payload = {
        'schemaVersion': 1,
        'createdAt': _utc_now(),
        'pid': os.getpid(),
    }
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        return None
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + '\n')
    return lock_path


# 释放 worktree 创建锁。
def _release_lock(lock_path: Path | None) -> None:
    """参数：
        lock_path: 需要释放的锁文件路径。
    """
    if lock_path is None:
        return
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


# 判断路径是否是同一个 git repository 的 worktree。
def _is_same_repository_worktree(repo_root: Path, worktree: Path) -> bool:
    """参数：
        repo_root: primary 或当前 checkout 根目录。
        worktree: 候选 worktree 路径。

    返回：
        候选路径是同一 git common dir 的 worktree 时返回 true。
    """
    if not worktree.is_dir():
        return False
    try:
        candidate_top = Path(_git_output(worktree, 'rev-parse', '--show-toplevel')).resolve()
        return candidate_top == worktree.resolve() and git_common_dir(worktree) == git_common_dir(repo_root)
    except Exception:
        return False


# 创建或复用 git worktree。
def ensure_git_worktree(repo_root: Path, identity: RuntimeIdentity) -> tuple[bool, str]:
    """参数：
        repo_root: 当前检出目录根路径。
        identity: 运行时身份。

    返回：
        ``(created, error_message)``；error_message 非空表示无法创建或复用。
    """
    target = expected_worktree_path(repo_root, identity)
    if _is_same_repository_worktree(repo_root, target):
        write_assignment_marker(repo_root, identity, target)
        return False, ''
    if target.exists():
        return False, f'worktree target exists but is not this repository worktree: {target}'

    lock_path = _acquire_lock(repo_root)
    if lock_path is None:
        return False, 'worktree creation lock is busy; retry the mutation after the active creation finishes'
    try:
        if _is_same_repository_worktree(repo_root, target):
            write_assignment_marker(repo_root, identity, target)
            return False, ''
        target.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ['git', '-C', str(repo_root), 'worktree', 'add', '--detach', str(target), 'HEAD'],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or '').strip()
            return False, f'git worktree add failed: {detail or proc.returncode}'
        write_assignment_marker(repo_root, identity, target)
        return True, ''
    finally:
        _release_lock(lock_path)


# 构造用户可执行的迁移提示。
def _required_message(target: Path, created: bool) -> str:
    """参数：
        target: 分配的 worktree 路径。
        created: 是否由本次 hook 新建。

    返回：
        面向用户的阻断说明。
    """
    action = '已创建' if created else '已存在'
    return (
        f'WORKTREE_REQUIRED: main agent session must run mutations from its assigned git worktree. '
        f'Assigned worktree {action}: {target}. '
        f'请从该目录继续当前主 agent 任务，或执行: cd {target}'
    )


# 判定当前 checkout 是否满足 session worktree 约束。
def check_session_worktree(
    repo_root: Path,
    identity: RuntimeIdentity,
    *,
    create: bool = False,
) -> WorktreeDecision:
    """参数：
        repo_root: 当前检出目录根路径。
        identity: 运行时身份。
        create: 是否允许在缺失时创建 worktree assignment。

    返回：
        worktree 判定结果；``allowed=False`` 表示调用方应 fail closed。
    """
    root = repo_root.resolve()
    expected = expected_worktree_path(root, identity) if applies_to_identity(identity) else Path('')
    marker = assignment_marker_path(root, identity) if applies_to_identity(identity) else Path('')

    if not applies_to_identity(identity):
        return WorktreeDecision(
            required=False,
            allowed=True,
            created=False,
            assigned=False,
            current_root=str(root),
            expected_root=str(expected) if str(expected) else '',
            marker_path=str(marker) if str(marker) else '',
        )

    if root == expected.resolve():
        write_assignment_marker(root, identity, expected)
        return WorktreeDecision(
            required=True,
            allowed=True,
            created=False,
            assigned=True,
            current_root=str(root),
            expected_root=str(expected),
            marker_path=str(marker),
        )

    if _is_relative_to(expected, root):
        reason = f'computed worktree path is inside repository root: {expected}'
        return WorktreeDecision(
            required=True,
            allowed=False,
            created=False,
            assigned=False,
            current_root=str(root),
            expected_root=str(expected),
            marker_path=str(marker),
            reason=reason,
        )

    marker_data = read_assignment_marker(root, identity)
    marker_has_assignment = bool(marker_data and marker_data.get('worktreePath'))

    if create and not identity.is_agent:
        created, error = ensure_git_worktree(root, identity)
        if error:
            return WorktreeDecision(
                required=True,
                allowed=False,
                created=False,
                assigned=False,
                current_root=str(root),
                expected_root=str(expected),
                marker_path=str(marker),
                reason=error,
            )
        return WorktreeDecision(
            required=True,
            allowed=False,
            created=created,
            assigned=True,
            current_root=str(root),
            expected_root=str(expected),
            marker_path=str(marker),
            reason=_required_message(expected, created),
        )

    if marker_has_assignment:
        reason = _required_message(expected, False)
        return WorktreeDecision(
            required=True,
            allowed=False,
            created=False,
            assigned=True,
            current_root=str(root),
            expected_root=str(expected),
            marker_path=str(marker),
            reason=reason,
        )

    return WorktreeDecision(
        required=True,
        allowed=True,
        created=False,
        assigned=False,
        current_root=str(root),
        expected_root=str(expected),
        marker_path=str(marker),
    )
