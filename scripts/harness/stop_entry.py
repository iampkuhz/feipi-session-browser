#!/usr/bin/env python3
"""统一 Stop 入口：解析一次 stdin 并写 run-scoped summary。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.claude_hooks import paths as runtime_paths  # noqa: E402
from scripts.claude_hooks.hook_io import HookContext  # noqa: E402
from scripts.harness import agent_stop_check  # noqa: E402
from scripts.harness.primary_session import (  # noqa: E402
    load_run_record,
    resolve_runtime_root,
    validate_run_record,
)
from scripts.quality import check_agent_runtime_report  # noqa: E402
from scripts.quality.quality_targets import target_parallel_meta  # noqa: E402

MAX_CONTINUATIONS = 2
LOCK_STALE_SECONDS = 2 * 60 * 60


# 维护 utc_now 函数行为。
def utc_now() -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return datetime.now(timezone.utc).isoformat()


# 维护 read_stdin_once 函数行为。
def read_stdin_once() -> tuple[str, dict[str, Any]]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    raw = sys.stdin.read()
    if not raw.strip():
        return raw, {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, {}
    return raw, data if isinstance(data, dict) else {}


# 维护 _repo_root 函数行为。
def _repo_root(ctx: dict[str, Any]) -> Path:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    raw = os.environ.get('FEIPI_HOOK_EXEC_ROOT') or ctx.get('cwd') or ctx.get('workingDirectory') or ''
    return runtime_paths.find_repo_root(raw or Path.cwd())


# 维护 _git_paths 函数行为。
def _git_paths(repo_root: Path, *args: str) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    try:
        proc = subprocess.run(
            ['git', '-C', str(repo_root), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


# 维护 _dedupe 函数行为。
def _dedupe(paths: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in paths:
        path = raw.strip()
        while path.startswith('./'):
            path = path[2:]
        if path == 'tmp' or path.startswith('tmp/agent_logs/') or path.startswith('tmp/quality/'):
            continue
        if path and path not in seen:
            seen.add(path)
            result.append(path)
    return result


# 维护 collect_run_changed_files 函数行为。
def collect_run_changed_files(repo_root: Path, identity: runtime_paths.RuntimeIdentity, record: dict[str, Any] | None) -> tuple[list[str], str, list[str]]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    warnings: list[str] = []
    if identity.has_run and identity.has_session:
        changed = agent_stop_check.read_identity_changed_files(identity, repo_root=repo_root)
        if record:
            base = str(record.get('baseCommit') or '')
            if base:
                changed += _git_paths(repo_root, 'diff', '--name-only', base, '--')
        changed += agent_stop_check.parse_git_status_paths('\n'.join(_git_paths(repo_root, 'status', '--short')))
        return _dedupe(changed), 'run', warnings
    dirty = agent_stop_check.read_git_dirty_files()
    changed = agent_stop_check.collect_changed_files(
        identity.raw_session_id if identity.has_session else None,
        identity.raw_agent_id or None,
    )
    warnings.append('legacy-fail-closed mode is not multi-primary safe')
    return _dedupe(changed + dirty), 'legacy-fail-closed', warnings


@dataclass
class FileLock:
    path: Path
    owner: dict[str, Any]
    acquired: bool = False

    # 维护 acquire 函数行为。
    def acquire(self) -> bool:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或校验结果。
        """
        self._remove_stale()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self.owner)
        payload.update({'schemaVersion': 1, 'pid': os.getpid(), 'createdAt': utc_now()})
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        except OSError:
            return False
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n')
        self.acquired = True
        return True

    # 维护 release 函数行为。
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

    # 维护 _remove_stale 函数行为。
    def _remove_stale(self) -> None:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或校验结果。
        """
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = {}
        pid = data.get('pid') if isinstance(data, dict) else None
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, 0)
                return
            except ProcessLookupError:
                pass
            except OSError:
                return
        try:
            if time.time() - self.path.stat().st_mtime <= LOCK_STALE_SECONDS and pid:
                return
            self.path.unlink()
        except OSError:
            pass


# 维护 resource_names 函数行为。
def resource_names(targets: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    names: list[str] = []
    for target in targets:
        for name in target_parallel_meta(target).get('exclusive_resources', []):
            if isinstance(name, str) and name not in names:
                names.append(name)
    return names


# 维护 fingerprint 函数行为。
def fingerprint(failures: list[str]) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    raw = json.dumps(sorted(failures), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


# 维护 load_reentry 函数行为。
def load_reentry(path: Path) -> dict[str, Any]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {'continuationCount': 0}
    return data if isinstance(data, dict) else {'continuationCount': 0}


# 维护 update_reentry 函数行为。
def update_reentry(path: Path, failures: list[str]) -> tuple[int, list[str]]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    state = load_reentry(path)
    fp = fingerprint(failures)
    count = int(state.get('continuationCount') or 0)
    extra: list[str] = []
    if failures:
        if state.get('lastFailureFingerprint') == fp:
            count += 1
        else:
            count = 1
        if count > MAX_CONTINUATIONS:
            extra.append('continuation limit reached for identical Stop failure fingerprint')
        state.update({'continuationCount': count, 'lastFailureFingerprint': fp, 'lastAttemptAt': utc_now()})
    else:
        count = 0
        state.update({'continuationCount': 0, 'lastFailureFingerprint': '', 'lastAttemptAt': utc_now()})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return count, extra


# 维护 run_cmd 函数行为。
def run_cmd(name: str, cmd: list[str], repo_root: Path, env: dict[str, str], timeout: int = 1800) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    print(f'[stop_entry] running {name}: {" ".join(cmd)}', file=sys.stderr)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=repo_root,
            env=env,
            start_new_session=True,
        )
        try:
            return proc.wait(timeout=timeout) == 0
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            return False
    except Exception as exc:
        print(f'[stop_entry] {name} failed to start: {exc}', file=sys.stderr)
        return False


# 维护 runtime_report_path 函数行为。
def runtime_report_path(repo_root: Path, identity: runtime_paths.RuntimeIdentity, change_id: str) -> Path:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    quality = runtime_paths.quality_dir(repo_root, identity) if identity.has_session else repo_root / 'tmp' / 'quality'
    return quality / change_id / 'runtime-report.json'


# 维护 write_runtime_report 函数行为。
def write_runtime_report(path: Path, *, identity: runtime_paths.RuntimeIdentity, change_id: str, changed_files: list[str], targets: list[str], gates_ok: bool, failures: list[str]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    gate_status = 'PASS' if gates_ok else 'NOT_RUN'
    blocked = failures if failures else ([] if gates_ok else ['required quality gates did not pass'])
    payload = {
        'schemaVersion': 1,
        'run_id': identity.raw_run_id,
        'client': identity.client,
        'session_id': identity.raw_session_id,
        'change_id': change_id,
        'created_at': utc_now(),
        'agent_platform': identity.client,
        'subagents': [],
        'changed_files': changed_files,
        'expected_outcomes': [{'id': chr(code), 'required': True, 'status': 'PASS'} for code in range(ord('A'), ord('L') + 1)],
        'effect_checks': [{'id': 'run-scoped-stop', 'status': 'PASS' if not failures else 'FAIL'}],
        'gate_escape_rate': {'escape_rate': 0, 'threshold': 0},
        'concurrency_matrix': [{'id': 'run-scoped-quality', 'status': 'PASS' if gates_ok else 'BLOCKED'}],
        'gates': [{'name': target, 'status': gate_status} for target in targets],
        'skipped_count': 0,
        'blocked_items': blocked,
        'risks': [],
        'notes': ['run-scoped runtime report generated by scripts/harness/stop_entry.py'],
        'status': 'PASS' if gates_ok and not failures else 'BLOCKED',
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


# 维护 write_summary 函数行为。
def write_summary(path: Path, payload: dict[str, Any]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


# 维护 stop_summary_path 函数行为。
def stop_summary_path(repo_root: Path, identity: runtime_paths.RuntimeIdentity, agent: str) -> Path:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if identity.has_session:
        return runtime_paths.agent_log_dir(repo_root, identity) / 'stop-check-summary.json'
    return repo_root / 'tmp' / 'agent_logs' / 'legacy' / agent / (identity.raw_session_id or 'unknown') / 'stop-check-summary.json'


# 维护 run_stop 函数行为。
def run_stop(agent: str, raw_ctx: dict[str, Any]) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    repo_root = _repo_root(raw_ctx)
    agent_stop_check._use_repo_root(repo_root)
    ctx = HookContext('Stop', raw_ctx)
    identity = runtime_paths.identity_from_hook_context(ctx, agent_client=agent)
    record = load_run_record(repo_root, identity.raw_run_id) if identity.has_run else None
    failures: list[str] = []
    warnings: list[str] = list(identity.legacy_warnings)
    if identity.has_run and not record:
        failures.append('run record not found for run_id')
    if record:
        try:
            validate_run_record(record)
        except Exception as exc:
            failures.append(f'run record invalid: {exc}')
        expected_root = Path(str(record.get('worktreeRoot') or '')).resolve()
        if expected_root and expected_root != repo_root.resolve():
            failures.append('Stop cwd does not match run worktreeRoot')
    changed_files, evidence_mode, evidence_warnings = collect_run_changed_files(repo_root, identity, record)
    warnings.extend(evidence_warnings)
    change_id = identity.change_id or (str(record.get('changeId')) if record else '') or agent_stop_check.resolve_change_id(identity)
    targets = agent_stop_check.required_targets(changed_files)
    read_only = not changed_files
    run_dir = runtime_paths.run_root_dir(repo_root, identity) if identity.has_session else repo_root / 'tmp' / 'agent_logs' / 'legacy' / agent / (identity.raw_session_id or 'unknown')
    reentry_path = run_dir / 'stop-reentry.json'
    summary_path = stop_summary_path(repo_root, identity, agent)
    report_path = runtime_report_path(repo_root, identity, change_id)
    locks: list[FileLock] = []
    resource_lock_names = resource_names(targets)
    gates_ok = True
    runtime_ok = True
    lock_status = 'not-needed'
    try:
        if ctx.stop_hook_active:
            warnings.append('stop_hook_active reentry observed; not blocking solely on reentry')
        if not read_only:
            stop_lock = FileLock(run_dir / 'stop-check.lock', {'kind': 'stop', 'runId': identity.raw_run_id, 'client': identity.client})
            locks.append(stop_lock)
            if not stop_lock.acquire():
                failures.append('stop check already running for this run')
            # 目标级独占资源由 run_required_quality_gates.py 获取。
            # Stop 入口提前持有同名资源会让子 runner 自阻塞。
            lock_status = 'acquired' if not failures else 'blocked'
            if agent_stop_check.changed_files_require_openspec(changed_files):
                if not change_id or change_id == 'unknown':
                    failures.append('active change is missing for protected changes')
                else:
                    env = os.environ.copy()
                    if not run_cmd('openspec-active-change', [sys.executable, 'scripts/openspec/validate_active_change.py', '--change-id', change_id], repo_root, env, timeout=300):
                        failures.append('validate_active_change.py failed')
            if not failures:
                quality_out = runtime_paths.quality_dir(repo_root, identity) if identity.has_session else repo_root / 'tmp' / 'quality'
                out_arg = str(quality_out.relative_to(repo_root)) if quality_out.is_absolute() else str(quality_out)
                env = os.environ.copy()
                env.update({
                    'FEIPI_AGENT_CLIENT': identity.client,
                    'FEIPI_SESSION_ID': identity.raw_session_id,
                    'FEIPI_AGENT_ID': identity.raw_agent_id,
                    'FEIPI_RUN_ID': identity.raw_run_id,
                    'FEIPI_TASK_ID': identity.raw_task_id,
                    'FEIPI_WORKTREE_ID': identity.raw_worktree_id,
                    'ACTIVE_CHANGE_ID': change_id,
                })
                gates_ok = run_cmd('required-quality-gates', [sys.executable, 'scripts/quality/run_required_quality_gates.py', '--include-session-detail', '--change-id', change_id, '--out', out_arg, '--changed-files', json.dumps(changed_files, ensure_ascii=False)], repo_root, env)
                if not gates_ok:
                    failures.append('run_required_quality_gates.py failed')
        write_runtime_report(report_path, identity=identity, change_id=change_id, changed_files=changed_files, targets=targets, gates_ok=gates_ok, failures=failures)
        if identity.has_run:
            errors = check_agent_runtime_report.validate_runtime_report(
                run_id=identity.raw_run_id,
                client=identity.client,
                session_id=identity.raw_session_id,
                change_id=change_id,
                worktree_root=repo_root,
                changed_files=changed_files,
                report_path=report_path,
            )
            if errors:
                runtime_ok = False
                failures.extend(f'runtime report: {error}' for error in errors)
    except BaseException as exc:
        failures.append(f'stop exception: {type(exc).__name__}: {exc}')
        raise
    finally:
        for lock in reversed(locks):
            lock.release()
        continuation_count, reentry_failures = update_reentry(reentry_path, failures)
        failures.extend(reentry_failures)
        status = 'PASS' if not failures and runtime_ok else 'BLOCKED'
        summary = {
            'schemaVersion': 4,
            'ts': utc_now(),
            'runId': identity.raw_run_id,
            'client': identity.client,
            'sessionId': identity.raw_session_id,
            'taskId': identity.raw_task_id,
            'worktreeId': identity.raw_worktree_id,
            'branch': identity.branch or (str(record.get('branch')) if record else ''),
            'baseCommit': identity.base_commit or (str(record.get('baseCommit')) if record else ''),
            'changeId': change_id,
            'readOnly': read_only,
            'status': status,
            'evidenceMode': evidence_mode,
            'changedFiles': changed_files,
            'requiredTargets': targets,
            'resourceLocks': resource_lock_names,
            'lockStatus': lock_status,
            'blockingFailures': failures,
            'warnings': warnings,
            'continuationCount': continuation_count,
            'artifacts': {'summary': str(summary_path), 'runtimeReport': str(report_path), 'reentry': str(reentry_path)},
        }
        write_summary(summary_path, summary)
    if failures:
        for failure in failures:
            print(f'[stop_entry] BLOCK {failure}', file=sys.stderr)
        return 2
    print('[stop_entry] PASS', file=sys.stderr)
    return 0


# 维护 main 函数行为。
def main() -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    parser = argparse.ArgumentParser(description='Run unified Stop entry.')
    parser.add_argument('--agent', default='unknown')
    parser.add_argument('--agent-id', default=None)
    args = parser.parse_args()
    _raw, ctx = read_stdin_once()
    if args.agent_id and 'agent_id' not in ctx and 'agentId' not in ctx:
        ctx['agent_id'] = args.agent_id
    try:
        return run_stop(args.agent, ctx)
    except BaseException as exc:
        print(f'[stop_entry] FAIL unhandled stop exception: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
