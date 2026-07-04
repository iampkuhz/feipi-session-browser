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

AGENT_LOG_BASE = REPO_ROOT / 'tmp' / 'agent_logs'
LEGACY_SESSION_ID_FILE = AGENT_LOG_BASE / 'legacy' / 'session-id.txt'
LEGACY_CHANGED_FILES = AGENT_LOG_BASE / 'legacy' / 'changed-files.jsonl'
CHANGED_FILES = LEGACY_CHANGED_FILES
STOP_LOCK = AGENT_LOG_BASE / 'stop-check' / 'legacy.lock'
STOP_LOCK_STALE_SECONDS = 2 * 60 * 60
PROTECTED_ROOTS = [
    'CLAUDE.md',
    'AGENTS.md',
    'openspec/',
    '.claude/',
    '.codex/',
    '.qoder/',
    'scripts/',
    'harness/',
    'src/',
]

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
    """返回：
        当前 UTC timestamp 字符串。
    """
    return datetime.now(timezone.utc).isoformat()


# 读取JSON stdin。
def _read_json_stdin() -> dict[str, Any]:
    """返回：
        已解析的JSON 对象, 或 空 映射 当 输入 缺失 或 无效。
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


# 维护session id context。
def _session_id_from_context(ctx: dict[str, Any]) -> str | None:
    """参数：
        ctx: hook stdin 解析出的 context。

    返回：
        session id 当 可用；否则 None。
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
    """返回：
        日志状态文件中的 session id 字符串。
    """
    if LEGACY_SESSION_ID_FILE.exists():
        value = LEGACY_SESSION_ID_FILE.read_text(encoding='utf-8').strip()
        return value or None
    return None


# 维护agent id context。
def _agent_id_from_context(ctx: dict[str, Any]) -> str | None:
    """参数：
        ctx: hook stdin 解析出的 context。

    返回：
        agent id 当 可用；否则 None。
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
        path: 原始路径从hook 日志 或 git 输出。

    返回：
        normalize 字符串。
    """
    return changed_file_utils.normalize_path(path)


# 维护dedupe。
def _dedupe(paths: list[str]) -> list[str]:
    """参数：
        paths: 原始路径 字符串到normalize 和 deduplicate。

    返回：
        Ordered 去重后的 规范化 路径。
    """
    return changed_file_utils.dedupe_paths(paths)


# 读取recorded changed-files 文件。
def read_recorded_changed_files(session_id: str | None, agent_id: str | None = None) -> list[str]:
    """参数：
        session_id: 可选session id used到filter hook record。
        agent_id: 可选agent id used到filter record到a specific agent。

    返回：
        结果列表。
    """
    return changed_file_utils.read_recorded_changed_files(
        session_id, CHANGED_FILES, agent_id=agent_id
    )


# 解析Git 状态 路径。
def parse_git_status_paths(output: str) -> list[str]:
    """参数：
        output: 原始输出从``git 状态 --short``。

    返回：
        规范化 changed 路径, including both sides of rename record。
    """
    return changed_file_utils.parse_git_status_paths(output)


# 读取Git dirty 文件。
def read_git_dirty_files() -> list[str]:
    """返回：
        规范化 dirty 路径, 或 空 列表 当 git 状态 不可用。
    """
    return changed_file_utils.read_git_dirty_files(REPO_ROOT)


# 维护identity changed-files 文件 路径。
def identity_changed_file_paths(identity: runtime_paths.RuntimeIdentity) -> list[Path]:
    """参数：
        identity: 当前 hook runtime 运行身份。

    返回：
        当前 session/agent 归属的 changed file 路径列表。
    """
    include_agents = not identity.is_agent
    return [
        log_dir / 'changed-files.jsonl'
        for log_dir in runtime_paths.session_log_dirs(
            REPO_ROOT, identity, include_agents=include_agents
        )
    ]


# 读取当前 identity 作用域记录的 changed files。
def read_identity_changed_files(identity: runtime_paths.RuntimeIdentity) -> list[str]:
    """参数：
        identity: 当前 hook 运行time identity。

    返回：
        结果列表。
    """
    agent_filter = identity.raw_agent_id if identity.is_agent else None
    return changed_file_utils.read_recorded_changed_files_from_paths(
        identity_changed_file_paths(identity),
        identity.raw_session_id,
        agent_id=agent_filter,
    )


# 收集当前 session/agent 需要纳入 stop gate 的 changed files。
def collect_changed_files(session_id: str | None, agent_id: str | None = None) -> list[str]:
    """参数：
        session_id: 可选session id used到filter hook record。
        agent_id: 可选agent id used到filter record到a specific agent。

    返回：
        Deduplicated 路径从recorded hook 写入 和 当前 git 状态。
    """
    return changed_file_utils.collect_changed_files(
        session_id,
        include_git=True,
        repo_root=REPO_ROOT,
        changed_files_path=CHANGED_FILES,
        agent_id=agent_id,
    )


# 收集stop changed-files 文件。
def collect_stop_changed_files(
    identity: runtime_paths.RuntimeIdentity | str | None,
    fallback_session_id: str | None,
    agent_id: str | None = None,
) -> tuple[list[str], str]:
    """参数：
        identity: 当前 hook 运行time identity。
        fallback_session_id: 兜底使用的 session id。
        agent_id: 用于筛选记录的 agent id。

    返回：
        结果 tuple。
    """
    if isinstance(identity, str):
        return read_recorded_changed_files(identity, agent_id=agent_id), 'session'
    if identity is None:
        return collect_changed_files(fallback_session_id, agent_id=agent_id), 'fail-closed'
    if identity.has_session:
        mode = 'identity-agent' if identity.is_agent else 'identity-session'
        return read_identity_changed_files(identity), mode
    changed = read_git_dirty_files()
    if changed:
        return changed, 'fail-closed-git'
    return collect_changed_files(fallback_session_id, agent_id=agent_id), 'fail-closed-legacy'


# 检查local 仅 状态。
def check_local_only_status(changed_files: list[str] | None = None) -> list[str]:
    """参数：
        changed_files: 待检查的文件列表。

    返回：
        Git short-状态 行用于local-仅 路径, 或 空 列表 当 clean。
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
def _read_active_change_id(identity: runtime_paths.RuntimeIdentity) -> str | None:
    """参数：
        identity: 当前 hook 运行time identity。

    返回：
        读取到的 active change id 字符串。
    """
    paths = runtime_paths.build_paths(REPO_ROOT, identity=identity)
    if identity.has_session:
        candidates = paths.active_change_candidates
    else:
        candidates = [runtime_paths.legacy_active_change_path(REPO_ROOT)]
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
        identity: 当前 hook 运行time identity。

    返回：
        resolve change id 字符串。
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
        changed_files: 待检查的文件列表。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    for path in changed_files:
        normalized = _normalize(path)
        for root in PROTECTED_ROOTS:
            clean = root.rstrip('/')
            if normalized == clean or normalized.startswith(f'{clean}/'):
                return True
    return False


# 运行step。
def run_step(name: str, cmd: list[str], env_overrides: dict[str, str] | None = None) -> bool:
    """参数：
        name: 人类可读的 step name用于stderr 诊断信息。
        cmd: 待执行的命令。
        env_overrides: 覆盖 subprocess 环境变量的映射。

    返回：
        满足条件时返回 true，否则返回 false。
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
    """返回：
        结果列表。
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
        changed_files: 待检查的文件列表。

    返回：
        结果列表。
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


# 写入summary。
def write_summary(summary: StopSummary) -> None:
    """参数：
        summary: summary 参数。
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
        """返回：
            满足条件时返回 true，否则返回 false。
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
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description='Run shared agent stop checks.')
    parser.add_argument('--agent', default='unknown', help='Agent entrypoint name')
    parser.add_argument('--agent-id', default=None, help='Agent id for per-agent file filtering')
    args = parser.parse_args()

    ctx = _read_json_stdin()
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

    changed_files, evidence_mode = collect_stop_changed_files(
        identity, session_id if session_id != 'unknown' else None, agent_id=agent_id
    )
    targets = required_targets(changed_files)
    warnings: list[str] = []
    failures: list[str] = []

    if not changed_files:
        write_summary(
            StopSummary(
                agent=args.agent,
                session_id=session_id,
                read_only=True,
                status='PASS',
                evidence_mode=evidence_mode,
                lock_status='skipped-read-only',
                changed_files=[],
                targets=[],
                failures=[],
                warnings=[],
                identity=identity,
            )
        )
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
    raise SystemExit(main())
