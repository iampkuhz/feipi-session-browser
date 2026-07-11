"""Pure helpers for unified Stop runtime.

This module intentionally has no CLI entrypoint.  `scripts/harness/stop_entry.py`
is the only production Stop entry.
"""

from __future__ import annotations

import importlib
import json
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


# 解析 git status 输出中的路径。
def parse_git_status_paths(output: str) -> list[str]:
    """参数：
        output: Git 状态命令的 porcelain 输出。

    返回：
        去掉状态列后的路径列表。
    """
    return changed_file_utils.parse_git_status_paths(output)


# 读取当前 Git dirty 文件。
def read_git_dirty_files(repo_root: Path | None = None) -> list[str]:
    """参数：
        repo_root: 可选仓库根目录。

    返回：
        dirty 文件路径列表。
    """
    return changed_file_utils.read_git_dirty_files(repo_root or REPO_ROOT)


# 汇总 base...HEAD、dirty 和 untracked 文件。
def git_changed_files(repo_root: Path, base_commit: str = '') -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        base_commit: 可选 base commit。

    返回：
        Stop 使用的 Git changed-files 真相列表。
    """
    paths: list[str] = []
    if base_commit:
        paths.extend(_git_lines(repo_root, 'diff', '--name-only', f'{base_commit}...HEAD'))
    paths.extend(_git_lines(repo_root, 'diff', '--name-only'))
    paths.extend(_git_lines(repo_root, 'ls-files', '--others', '--exclude-standard'))
    return changed_file_utils.dedupe_paths(paths)


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
