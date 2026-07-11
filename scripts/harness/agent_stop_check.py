#!/usr/bin/env python3
"""为 Claude Code、Codex 和 Qoder 提供共享 stop gate。"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality import changed_files as changed_file_utils  # noqa: E402
from scripts.claude_hooks import paths as runtime_paths  # noqa: E402
from scripts.claude_hooks.evidence import pre_bash_exempts_missing_snapshot  # noqa: E402
from scripts.agent_runtime import policy as runtime_policy  # noqa: E402
from scripts.agent_runtime import worktree as runtime_worktree  # noqa: E402

AGENT_LOG_BASE = REPO_ROOT / 'tmp' / 'agent_logs'
LEGACY_SESSION_ID_FILE = AGENT_LOG_BASE / 'legacy' / 'session-id.txt'
LEGACY_CHANGED_FILES = AGENT_LOG_BASE / 'legacy' / 'changed-files.jsonl'
CHANGED_FILES = LEGACY_CHANGED_FILES
STOP_LOCK = AGENT_LOG_BASE / 'stop-check' / 'legacy.lock'
STOP_LOCK_STALE_SECONDS = 2 * 60 * 60
PROTECTED_ROOTS = runtime_policy.protected_roots(REPO_ROOT)

LOCAL_ONLY_PATHS = [
    '.claude/settings.local.json',
    '.mcp.json',
    '.env',
    'data',
    'output',
    '.venv',
    '.pytest_cache',
]


# 返回当前 UTC timestamp。
def utc_now() -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return datetime.now(timezone.utc).isoformat()


# 读取JSON stdin。
def _read_json_stdin() -> dict[str, Any]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    try:
        text = sys.stdin.read()
    except Exception:
        return {}
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


# 根据 stop payload 或 hook wrapper 环境切换到实际检出根目录。
def _repo_root_from_stop_context(ctx: dict[str, Any]) -> Path:
    """参数：
        ctx: 停止 hook 载荷。

    返回：
        当前 stop 应检查的 git checkout 根目录。
    """
    raw = ctx.get('cwd') or ctx.get('workingDirectory') or ''
    if isinstance(raw, str) and raw:
        return runtime_paths.find_repo_root(raw)
    if not (REPO_ROOT / 'harness' / 'agent-runtime.manifest.yaml').is_file():
        return REPO_ROOT
    env_cwd = os.environ.get('FEIPI_HOOK_CWD') or ''
    if env_cwd:
        return runtime_paths.find_repo_root(env_cwd)
    return REPO_ROOT


# 更新依赖仓库根目录的模块级路径。
def _use_repo_root(repo_root: Path) -> None:
    """参数：
        repo_root: 实际 git checkout 根目录。
    """
    global REPO_ROOT, AGENT_LOG_BASE, LEGACY_SESSION_ID_FILE, LEGACY_CHANGED_FILES
    global CHANGED_FILES, STOP_LOCK, PROTECTED_ROOTS
    REPO_ROOT = repo_root.resolve()
    AGENT_LOG_BASE = REPO_ROOT / 'tmp' / 'agent_logs'
    LEGACY_SESSION_ID_FILE = AGENT_LOG_BASE / 'legacy' / 'session-id.txt'
    LEGACY_CHANGED_FILES = AGENT_LOG_BASE / 'legacy' / 'changed-files.jsonl'
    CHANGED_FILES = LEGACY_CHANGED_FILES
    STOP_LOCK = AGENT_LOG_BASE / 'stop-check' / 'legacy.lock'
    try:
        PROTECTED_ROOTS = runtime_policy.protected_roots(REPO_ROOT)
    except FileNotFoundError:
        PROTECTED_ROOTS = []


# 维护session id context。
def _session_id_from_context(ctx: dict[str, Any]) -> str | None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    sid = ctx.get('session_id') or ctx.get('sessionId')
    if isinstance(sid, str) and sid:
        return sid
    env = os.environ.get('FEIPI_SESSION_ID', '')
    if env:
        return env
    return None


# 维护session id log state。
def _session_id_from_log_state() -> str | None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if LEGACY_SESSION_ID_FILE.exists():
        value = LEGACY_SESSION_ID_FILE.read_text(encoding='utf-8').strip()
        return value or None
    return None


# 维护agent id context。
def _agent_id_from_context(ctx: dict[str, Any]) -> str | None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    aid = ctx.get('agent_id') or ctx.get('agentId')
    if isinstance(aid, str) and aid:
        return aid
    env = os.environ.get('FEIPI_AGENT_ID', '')
    if env:
        return env
    return None


# 规范化注释文本。
def _normalize(path: str) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return changed_file_utils.normalize_path(path)


# 维护dedupe。
def _dedupe(paths: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return changed_file_utils.dedupe_paths(paths)


# 读取recorded changed-files 文件。
def read_recorded_changed_files(session_id: str | None, agent_id: str | None = None) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return changed_file_utils.read_recorded_changed_files(
        session_id, CHANGED_FILES, agent_id=agent_id
    )


# 解析Git 状态 路径。
def parse_git_status_paths(output: str) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return changed_file_utils.parse_git_status_paths(output)


# 读取Git dirty 文件。
def read_git_dirty_files() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return changed_file_utils.read_git_dirty_files(REPO_ROOT)


# 维护identity changed-files 文件 路径。
def identity_changed_file_paths(
    identity: runtime_paths.RuntimeIdentity,
    repo_root: Path | None = None,
) -> list[Path]:
    """参数：
        identity: 当前 hook runtime 运行身份。
        repo_root: 仓库根目录。

    返回：
        当前 session/agent 归属的 changed file 路径列表。
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    include_agents = not identity.is_agent
    return [
        log_dir / 'changed-files.jsonl'
        for log_dir in runtime_paths.session_log_dirs(
            repo_root, identity, include_agents=include_agents
        )
    ]


# 读取当前 identity 作用域记录的 changed files。
def read_identity_changed_files(
    identity: runtime_paths.RuntimeIdentity,
    repo_root: Path | None = None,
) -> list[str]:
    """参数：
        identity: 当前 hook 运行time identity。
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    agent_filter = identity.raw_agent_id if identity.is_agent else None
    return changed_file_utils.read_recorded_changed_files_from_paths(
        identity_changed_file_paths(identity, repo_root=repo_root),
        identity.raw_session_id,
        agent_id=agent_filter,
    )


# 维护 read_identity_hook_events 函数行为。
def read_identity_hook_events(
    identity: runtime_paths.RuntimeIdentity,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """参数：
        identity: 当前 hook 运行身份。
        repo_root: 仓库根目录。

    返回：
        当前 identity scope 的 hook event 列表。
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    events: list[dict[str, Any]] = []
    for changed_path in identity_changed_file_paths(identity, repo_root=repo_root):
        path = changed_path.with_name('hook-events.jsonl')
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding='utf-8').splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
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


# 判断 BASH_SNAPSHOT_MISSING 是否代表仍需 Stop fail-closed 的真实缺口。
def _bash_snapshot_missing_blocks(
    event: dict[str, Any],
    pre_event: dict[str, Any] | None,
) -> bool:
    """参数：
        event: post-bash 的 hook 事件记录。
        pre_event: 同一 toolUseId 对应的 pre-bash 事件记录。

    返回：
        Stop 必须阻断时返回 true。
    """
    if pre_bash_exempts_missing_snapshot(pre_event):
        return False
    if event.get('bashSnapshotRequired') is True or event.get('bashMutationTracking') is True:
        return True
    if pre_event and pre_event.get('bashMutationTracking') is True:
        return True
    return False


# 维护 identity_attribution_gap_failures 函数行为。
def identity_attribution_gap_failures(
    identity: runtime_paths.RuntimeIdentity,
    repo_root: Path | None = None,
) -> list[str]:
    """参数：
        identity: 当前 hook 运行身份。
        repo_root: 仓库根目录。

    返回：
        hook event 中 stop gate 必须显式暴露的 attribution gap 列表。
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    failures: list[str] = []
    events = read_identity_hook_events(identity, repo_root=repo_root)
    pre_events: dict[str, dict[str, Any]] = {}
    for event in events:
        tool_use = event.get('toolUseId')
        if (
            isinstance(tool_use, str)
            and tool_use
            and event.get('event') == 'pre-bash'
        ):
            pre_events[tool_use] = event
    for event in events:
        if event.get('status') == 'BASH_SNAPSHOT_MISSING':
            tool_use = event.get('toolUseId') or 'unknown'
            pre_event = pre_events.get(tool_use)
            if not _bash_snapshot_missing_blocks(event, pre_event):
                continue
            failures.append(f'BASH_SNAPSHOT_MISSING attribution gap for toolUseId={tool_use}')
    return failures


# 收集当前 session/agent 需要纳入 stop gate 的 changed files。
def collect_changed_files(session_id: str | None, agent_id: str | None = None) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return changed_file_utils.collect_changed_files(
        session_id,
        include_git=True,
        repo_root=REPO_ROOT,
        changed_files_path=CHANGED_FILES,
        agent_id=agent_id,
    )


@dataclass(frozen=True)
class StopChangedFiles:
    """停止门变更文件证据和故障诊断数据类。

    ``__iter__`` 保留历史解包契约 ``changed_files, evidence_mode = ...``，
    同时向停止门入口暴露证据故障信息。
    """

    changed_files: list[str]
    evidence_mode: str
    evidence_warnings_or_failures: list[str]
    git_dirty_files: list[str]

    # 兼容历史解包契约，返回变更文件列表和证据模式。
    def __iter__(self):
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        yield self.changed_files
        yield self.evidence_mode


# 收集指定 identity 作用域下所有 agent 的基准提交哨兵文件路径。
def _identity_base_commit_paths(
    identity: runtime_paths.RuntimeIdentity,
    repo_root: Path | None = None,
) -> list[Path]:
    """参数：
        identity: 当前 hook 运行身份。
        repo_root: 仓库根目录。

    返回：
        基准提交哨兵文件路径列表。
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    return [
        path.with_name('base-commit.txt')
        for path in identity_changed_file_paths(identity, repo_root)
    ]


# 判断当前 identity 的 dirty state 是否等于 session 起点状态。
def _identity_dirty_state_matches_baseline(
    identity: runtime_paths.RuntimeIdentity,
    repo_root: Path | None = None,
) -> bool:
    """参数：
        identity: 当前 hook 运行身份。
        repo_root: 仓库根目录。

    返回：
        当前 dirty state 与 session 起点 dirty-state sentinel 完全一致时返回 true。
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    current = changed_file_utils.read_git_dirty_state(repo_root)
    for base_commit in _identity_base_commit_paths(identity, repo_root):
        baseline = changed_file_utils.read_base_dirty_state(base_commit)
        if baseline is not None and baseline == current:
            return True
    return False


# 收集 session identity 下因证据缺失导致的 fail-closed 故障列表。
def _session_evidence_failures(
    identity: runtime_paths.RuntimeIdentity,
    changed_files: list[str],
    git_dirty_files: list[str],
    repo_root: Path | None = None,
) -> list[str]:
    """参数：
        identity: 当前 hook 运行身份。
        changed_files: 已收集的变更文件列表。
        git_dirty_files: git 脏文件列表。
        repo_root: 仓库根目录。

    返回：
        需要故障关闭的证据缺口列表。
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    failures: list[str] = identity_attribution_gap_failures(identity, repo_root)
    if not git_dirty_files:
        return failures

    if not changed_files:
        if _identity_dirty_state_matches_baseline(identity, repo_root):
            return failures
        failures.append(
            'attribution evidence missing: session has dirty git files but no changed-files evidence'
        )
        if changed_files_require_openspec(git_dirty_files) and not any(
            path.exists() for path in _identity_base_commit_paths(identity, repo_root)
        ):
            failures.append('base commit missing for session attribution evidence')
    return failures


# 收集stop changed-files 文件。
def collect_stop_changed_files(
    identity: runtime_paths.RuntimeIdentity | str | None,
    fallback_session_id: str | None,
    agent_id: str | None = None,
    repo_root: Path | None = None,
) -> StopChangedFiles:
    """参数：
        identity: 当前 hook 运行time identity。
        fallback_session_id: 兜底使用的 session id。
        agent_id: 用于筛选记录的 agent id。
        repo_root: 仓库根目录。

    返回：
        停止门变更文件集合，包含故障关闭诊断信息。
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    if isinstance(identity, str):
        changed = read_recorded_changed_files(identity, agent_id=agent_id)
        return StopChangedFiles(changed, 'session', [], [])
    if identity is None:
        changed = collect_changed_files(fallback_session_id, agent_id=agent_id)
        return StopChangedFiles(changed, 'fail-closed', [], read_git_dirty_files())
    if identity.has_session:
        mode = 'identity-agent' if identity.is_agent else 'identity-session'
        changed = read_identity_changed_files(identity, repo_root=repo_root)
        dirty = read_git_dirty_files()
        failures = _session_evidence_failures(identity, changed, dirty, repo_root)
        return StopChangedFiles(changed, mode, failures, dirty)
    changed = read_git_dirty_files()
    if changed:
        return StopChangedFiles(changed, 'fail-closed-git', [], changed)
    changed = collect_changed_files(fallback_session_id, agent_id=agent_id)
    return StopChangedFiles(changed, 'fail-closed-legacy', [], [])


# 检查local 仅 状态。
def check_local_only_status(changed_files: list[str] | None = None) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if changed_files is not None:
        warnings: list[str] = []
        for changed in changed_files:
            normalized = _normalize(changed)
            if any(
                normalized == local or normalized.startswith(f'{local.rstrip("/")}/')
                for local in LOCAL_ONLY_PATHS
            ):
                warnings.append(f'{normalized} 是 local-only 路径')
        return warnings
    try:
        proc = subprocess.run(
            ['git', 'status', '--short', '--', *LOCAL_ONLY_PATHS],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return []
    lines = [line for line in (proc.stdout or '').splitlines() if line.strip()]
    return lines if proc.returncode == 0 else []


# 读取active change id。
def _read_active_change_id(
    identity: runtime_paths.RuntimeIdentity,
    repo_root: Path | None = None,
) -> str | None:
    """参数：
        identity: 当前 hook 运行time identity。
        repo_root: 仓库根目录。

    返回：
        读取到的 active change id 字符串。
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    paths = runtime_paths.build_paths(repo_root, identity=identity)
    if identity.has_session:
        candidates = paths.active_change_candidates
    else:
        candidates = [runtime_paths.legacy_active_change_path(repo_root)]
    for active_change in candidates:
        if active_change.exists():
            try:
                data = json.loads(active_change.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                continue
            cid = data.get('change_id') or data.get('changeId') or ''
            if isinstance(cid, str) and cid:
                return cid
    return None


# 解析change id。
def resolve_change_id(identity: runtime_paths.RuntimeIdentity | None = None) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    env = os.environ.get('ACTIVE_CHANGE_ID', '')
    if env:
        return env
    if identity is not None:
        cid = _read_active_change_id(identity)
        if cid:
            return cid
    return 'unknown'


# 维护changed-files 文件 校验 OpenSpec。
def changed_files_require_openspec(changed_files: list[str]) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return any(runtime_policy.is_protected_path(path, REPO_ROOT) for path in changed_files)


# 运行step。
def run_step(name: str, cmd: list[str], env_overrides: dict[str, str] | None = None) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    print(f'[agent_stop_check] running {name}: {" ".join(cmd)}', file=sys.stderr)
    try:
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)
        proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False, env=env)
    except Exception as exc:
        print(f'[agent_stop_check] {name} failed to start: {exc}', file=sys.stderr)
        return False
    if proc.returncode != 0:
        print(f'[agent_stop_check] {name} failed: exit={proc.returncode}', file=sys.stderr)
        return False
    return True


# 维护任务 ledger warning。
def task_ledger_warnings() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    ledger = REPO_ROOT / 'tmp' / 'task-ledger.md'
    if not ledger.exists():
        return []
    text = ledger.read_text(encoding='utf-8', errors='ignore')
    if '| ID ' in text or '|ID' in text:
        return []
    return ['tmp/task-ledger.md 表头格式不正确']


# 维护必需 targets。
def required_targets(changed_files: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    classifier = importlib.import_module('scripts.claude_hooks.classify')
    return classifier.required_quality_targets(changed_files)


@dataclass(frozen=True)
class StopSummary:
    """表示 StopSummary。

    属性：
        agent: agent 参数。
        session_id: 隔离运行数据的 session id。
        read_only: read only 参数。
        status: 状态值。
        evidence_mode: evidence mode 参数。
        lock_status: lock status 参数。
        changed_files: 待检查的文件列表。
        targets: targets 参数。
        failures: failures 参数。
        warnings: 警告列表。
        identity: 当前 hook runtime 运行身份。
    """

    agent: str
    session_id: str
    read_only: bool
    status: str
    evidence_mode: str
    lock_status: str
    changed_files: list[str]
    targets: list[str]
    failures: list[str]
    warnings: list[str]
    identity: runtime_paths.RuntimeIdentity | None = None
    worktree: dict[str, Any] | None = None


# 写入summary。
def write_summary(summary: StopSummary) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if summary.identity and summary.identity.has_session:
        agent_log_dir = runtime_paths.agent_log_dir(REPO_ROOT, summary.identity)
    else:
        agent_log_dir = AGENT_LOG_BASE / 'legacy' / summary.agent / summary.session_id
    agent_log_dir.mkdir(parents=True, exist_ok=True)
    stop_summary_path = agent_log_dir / 'stop-check-summary.json'
    payload = {
        'schemaVersion': 3,
        'ts': utc_now(),
        'agent': summary.agent,
        'readOnly': summary.read_only,
        'status': summary.status,
        'evidenceMode': summary.evidence_mode,
        'lockStatus': summary.lock_status,
        'changeId': resolve_change_id(summary.identity),
        'changedFiles': summary.changed_files,
        'requiredTargets': summary.targets,
        'blockingFailures': summary.failures,
        'warnings': summary.warnings,
    }
    if summary.worktree is not None:
        payload['worktree'] = summary.worktree
    stop_summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )


@dataclass
class StopCheckLock:
    """表示 StopCheckLock。

    属性：
        path: 待检查的路径。
        agent: agent 参数。
        session_id: 隔离运行数据的 session id。
        acquired: acquired 参数。
    """

    path: Path
    agent: str
    session_id: str
    acquired: bool = False

    # 维护acquire。
    def acquire(self) -> bool:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        self._remove_stale_lock()
        payload = {
            'schemaVersion': 1,
            'ts': utc_now(),
            'agent': self.agent,
            'sessionId': self.session_id,
            'pid': os.getpid(),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        except OSError:
            return False
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(json.dumps(payload, ensure_ascii=False) + '\n')
        self.acquired = True
        return True

    # 维护释放。
    def release(self) -> None:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        if not self.acquired:
            return
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False

    # 移除stale 锁。
    def _remove_stale_lock(self) -> None:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        try:
            age = time.time() - self.path.stat().st_mtime
        except FileNotFoundError:
            return
        except OSError:
            return
        if age <= STOP_LOCK_STALE_SECONDS:
            return
        try:
            self.path.unlink()
        except OSError:
            pass


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    parser = argparse.ArgumentParser(description='Run shared agent stop checks.')
    parser.add_argument('--agent', default='unknown', help='Agent entrypoint name')
    parser.add_argument('--agent-id', default=None, help='Agent id for per-agent file filtering')
    args = parser.parse_args()

    ctx = _read_json_stdin()
    _use_repo_root(_repo_root_from_stop_context(ctx))
    scoped_session_id = _session_id_from_context(ctx)
    session_id = scoped_session_id or _session_id_from_log_state() or 'unknown'
    agent_id = args.agent_id or _agent_id_from_context(ctx)
    identity = runtime_paths.identity_from_values(
        agent_client=args.agent,
        session_id=scoped_session_id or '',
        agent_id=agent_id or '',
    )

    if identity.has_session:
        agent_log_dir = runtime_paths.agent_log_dir(REPO_ROOT, identity)
    else:
        agent_log_dir = AGENT_LOG_BASE / 'legacy' / args.agent / session_id
    agent_log_dir.mkdir(parents=True, exist_ok=True)

    try:
        stop_evidence = collect_stop_changed_files(
            identity,
            session_id if session_id != 'unknown' else None,
            agent_id=agent_id,
            repo_root=REPO_ROOT,
        )
    except TypeError as exc:
        if "repo_root" not in str(exc):
            raise
        legacy_changed, legacy_mode = collect_stop_changed_files(
            identity,
            session_id if session_id != 'unknown' else None,
            agent_id=agent_id,
        )
        stop_evidence = StopChangedFiles(legacy_changed, legacy_mode, [], [])
    changed_files = stop_evidence.changed_files
    evidence_mode = stop_evidence.evidence_mode
    targets = required_targets(changed_files)
    warnings: list[str] = []
    failures: list[str] = list(stop_evidence.evidence_warnings_or_failures)
    worktree_decision = runtime_worktree.check_session_worktree(REPO_ROOT, identity, create=False)
    worktree_payload = worktree_decision.as_dict() if worktree_decision.required else None
    if not worktree_decision.allowed and (changed_files or stop_evidence.git_dirty_files):
        failures.append(
            worktree_decision.reason
            or 'main agent session must stop from its assigned git worktree'
        )

    if not changed_files:
        status = 'BLOCKED' if failures else 'PASS'
        write_summary(
            StopSummary(
                agent=args.agent,
                session_id=session_id,
                read_only=True,
                status=status,
                evidence_mode=evidence_mode,
                lock_status='blocked-evidence-gap' if failures else 'skipped-read-only',
                changed_files=[],
                targets=[],
                failures=failures,
                warnings=[],
                identity=identity,
                worktree=worktree_payload,
            )
        )
        if failures:
            for failure in failures:
                print(f'[agent_stop_check] BLOCK {failure}', file=sys.stderr)
            return 2
        print('[agent_stop_check] PASS read-only session', file=sys.stderr)
        return 0

    warnings = check_local_only_status(changed_files if identity.has_session else None)
    if not identity.has_session:
        warnings += task_ledger_warnings()
    change_id = resolve_change_id(identity)
    print(f'[agent_stop_check] changed files: {len(changed_files)}', file=sys.stderr)
    print(
        '[agent_stop_check] required targets: '
        + (', '.join(sorted(targets)) if targets else '(none)'),
        file=sys.stderr,
    )

    if identity.has_session:
        stop_lock_path = agent_log_dir / 'stop-check.lock'
    else:
        stop_lock_path = STOP_LOCK
    stop_lock = StopCheckLock(stop_lock_path, args.agent, session_id)
    if not stop_lock.acquire():
        failures.append('stop check already running; retry after the active Stop finishes')
        write_summary(
            StopSummary(
                agent=args.agent,
                session_id=session_id,
                read_only=False,
                status='BLOCKED',
                evidence_mode=evidence_mode,
                lock_status='busy',
                changed_files=changed_files,
                targets=targets,
                failures=failures,
                warnings=warnings,
                identity=identity,
                worktree=worktree_payload,
            )
        )
        print(
            '[agent_stop_check] BLOCK stop check already running; retry after active Stop finishes',
            file=sys.stderr,
        )
        return 2

    try:
        if changed_files_require_openspec(changed_files):
            if change_id == 'unknown':
                failures.append('active change is missing for protected changes')
            elif not run_step(
                'openspec-active-change',
                [
                    sys.executable,
                    'scripts/openspec/validate_active_change.py',
                    '--change-id',
                    change_id,
                ],
            ):
                failures.append('validate_active_change.py failed')
        elif not identity.has_session and not run_step(
            'openspec-stop-validate',
            [sys.executable, 'scripts/agent_hooks/stop_validate_change.py'],
        ):
            failures.append('stop_validate_change.py failed')

        changed_json = json.dumps(changed_files, ensure_ascii=False)
        quality_out = (
            runtime_paths.quality_dir(REPO_ROOT, identity)
            if identity.has_session
            else REPO_ROOT / 'tmp' / 'quality'
        )
        quality_out_arg = str(quality_out.relative_to(REPO_ROOT))
        child_env = {
            'FEIPI_AGENT_CLIENT': identity.client,
            'FEIPI_SESSION_ID': identity.raw_session_id,
            'FEIPI_AGENT_ID': identity.raw_agent_id,
        }
        if not run_step(
            'required-quality-gates',
            [
                sys.executable,
                'scripts/quality/run_required_quality_gates.py',
                '--include-session-detail',
                '--change-id',
                change_id,
                '--out',
                quality_out_arg,
                '--changed-files',
                changed_json,
            ],
            env_overrides=child_env,
        ):
            failures.append('run_required_quality_gates.py failed')
    finally:
        stop_lock.release()

    status = 'FAIL' if failures else ('WARN' if warnings else 'PASS')
    write_summary(
        StopSummary(
            agent=args.agent,
            session_id=session_id,
            read_only=False,
            status=status,
            evidence_mode=evidence_mode,
            lock_status='acquired',
            changed_files=changed_files,
            targets=targets,
            failures=failures,
            warnings=warnings,
            identity=identity,
            worktree=worktree_payload,
        )
    )

    for warning in warnings:
        print(f'[agent_stop_check] WARN {warning}', file=sys.stderr)
    for failure in failures:
        print(f'[agent_stop_check] BLOCK {failure}', file=sys.stderr)

    if failures:
        return 2
    return 1 if warnings else 0


if __name__ == '__main__':
    from scripts.harness.stop_entry import main as stop_entry_main

    raise SystemExit(stop_entry_main())
