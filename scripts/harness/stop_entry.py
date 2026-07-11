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
from scripts.harness import stop_helpers  # noqa: E402
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
        changed = []
        if record:
            base = str(record.get('baseCommit') or '')
            if base:
                changed += _git_paths(repo_root, 'diff', '--name-only', f'{base}...HEAD')
        changed += _git_paths(repo_root, 'diff', '--name-only')
        changed += _git_paths(repo_root, 'ls-files', '--others', '--exclude-standard')
        return _dedupe(changed), 'git-run-record', warnings
    dirty = stop_helpers.read_git_dirty_files(repo_root)
    if identity.has_session:
        changed = stop_helpers.read_identity_changed_files(identity, repo_root=repo_root)
        warnings.append('unbound session Stop uses read-only fail-closed evidence')
        return _dedupe(changed + dirty), 'unbound-session-fail-closed', warnings
    warnings.append('unbound Stop without run record; mutation completion cannot be proven')
    return _dedupe(dirty), 'unbound-fail-closed', warnings


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


# 计算停止流程重入指纹。
def stop_signature(repo_root: Path, failures: list[str]) -> dict[str, str]:
    """参数：
        repo_root: 仓库根目录。
        failures: 当前失败列表。

    返回：
        当前提交、脏状态哈希和失败指纹组成的映射。
    """
    head = _git_paths(repo_root, 'rev-parse', 'HEAD')
    dirty_hash = stop_helpers.git_dirty_hash(repo_root)
    return {
        'head': head[0] if head else '',
        'dirtyHash': dirty_hash,
        'failureFingerprint': fingerprint(failures),
    }


# 判断是否命中相同重入失败。
def matching_reentry_failure(path: Path, repo_root: Path) -> tuple[bool, dict[str, Any]]:
    """参数：
        path: 重入状态文件路径。
        repo_root: 仓库根目录。

    返回：
        是否同一失败，以及已读取状态。
    """
    state = load_reentry(path)
    sig = state.get('lastSignature')
    if not isinstance(sig, dict):
        return False, state
    current_head = (_git_paths(repo_root, 'rev-parse', 'HEAD') or [''])[0]
    current_dirty = stop_helpers.git_dirty_hash(repo_root)
    return sig.get('head') == current_head and sig.get('dirtyHash') == current_dirty and bool(state.get('lastFailures')), state


# 更新停止流程重入状态。
def update_reentry(path: Path, repo_root: Path, failures: list[str]) -> tuple[int, list[str]]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    state = load_reentry(path)
    sig = stop_signature(repo_root, failures)
    fp = sig['failureFingerprint']
    count = int(state.get('continuationCount') or 0)
    extra: list[str] = []
    if failures:
        if state.get('lastFailureFingerprint') == fp:
            count += 1
        else:
            count = 1
        if count > MAX_CONTINUATIONS:
            extra.append('continuation limit reached for identical Stop failure fingerprint')
        state.update({'continuationCount': count, 'lastFailureFingerprint': fp, 'lastFailures': failures, 'lastSignature': sig, 'lastAttemptAt': utc_now()})
    else:
        count = 0
        state.update({'continuationCount': 0, 'lastFailureFingerprint': '', 'lastFailures': [], 'lastSignature': {}, 'lastAttemptAt': utc_now()})
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


# 读取质量目标产物状态。
def _target_artifact_status(report_path: Path, target: str) -> str:
    """参数：
        report_path: 运行报告路径。
        target: 质量目标名称。

    返回：
        质量目标产物状态。
    """
    artifact = report_path.parent / f'quality-gate-summary.{target}.json'
    try:
        data = json.loads(artifact.read_text(encoding='utf-8'))
    except Exception:
        return 'NOT_RUN'
    status = str(data.get('status') or '').upper()
    return status if status in {'PASS', 'FAIL', 'BLOCKED'} else 'BLOCKED'


# 写入不自证通过的运行报告。
def write_runtime_report(path: Path, *, identity: runtime_paths.RuntimeIdentity, change_id: str, changed_files: list[str], targets: list[str], gates_ok: bool, failures: list[str]) -> None:
    """参数：
        path: 运行报告输出路径。
        identity: 运行时身份对象。
        change_id: OpenSpec 变更标识。
        changed_files: 已变更文件列表。
        targets: 本次触发的质量目标。
        gates_ok: 必需门禁是否通过。
        failures: 失败信息列表。
    """
    gates = [{'name': target, 'status': _target_artifact_status(path, target)} for target in targets]
    if targets and gates_ok:
        for gate in gates:
            if gate['status'] == 'NOT_RUN':
                gate['status'] = 'BLOCKED'
    blocked = list(failures)
    if targets and not gates_ok and 'run_required_quality_gates.py failed' not in blocked:
        blocked.append('required quality gates did not pass')
    if not targets and changed_files:
        blocked.append('changed files did not map to required quality targets')
    final_status = 'PASS' if not blocked and (not targets or all(g['status'] == 'PASS' for g in gates)) else 'BLOCKED'
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
        'expected_outcomes': [{'id': chr(code), 'required': False, 'status': 'NOT_RUN', 'evidence': 'not a runtime-report self-certified outcome'} for code in range(ord('A'), ord('L') + 1)],
        'effect_checks': [{'id': 'git-changed-file-truth', 'status': 'PASS' if not failures else 'FAIL'}],
        'gate_escape_rate': {'status': 'NOT_RUN', 'threshold': 0, 'escape_rate': None},
        'concurrency_matrix': [{'id': 'run-scoped-quality', 'status': 'PASS' if not failures else 'BLOCKED'}],
        'gates': gates,
        'skipped_count': 0,
        'blocked_items': blocked,
        'risks': [],
        'notes': ['run-scoped runtime report generated by scripts/harness/stop_entry.py'],
        'status': final_status,
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
    stop_helpers._use_repo_root(repo_root)
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
    change_id = identity.change_id or (str(record.get('changeId')) if record else '') or stop_helpers.resolve_change_id(identity)
    targets = stop_helpers.required_targets(changed_files)
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
    circuit_final = False
    reused_failures: list[str] | None = None
    same_failure, reentry_state = matching_reentry_failure(reentry_path, repo_root)
    if same_failure:
        previous = [str(item) for item in reentry_state.get('lastFailures', [])]
        count = int(reentry_state.get('continuationCount') or 0) + 1
        reentry_state['continuationCount'] = count
        reentry_state['lastAttemptAt'] = utc_now()
        reentry_path.parent.mkdir(parents=True, exist_ok=True)
        reentry_path.write_text(json.dumps(reentry_state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if count > MAX_CONTINUATIONS:
            circuit_final = True
            previous = previous + ['continuation limit reached for identical HEAD + dirtyHash + failure fingerprint']
        reused_failures = previous
    try:
        if ctx.stop_hook_active:
            warnings.append('stop_hook_active reentry observed; not blocking solely on reentry')
        if reused_failures is not None:
            failures.extend(reused_failures)
            gates_ok = False
            warnings.append('reused persistent Stop failure; heavy gates were not rerun')
        elif not read_only:
            stop_lock = FileLock(run_dir / 'stop-check.lock', {'kind': 'stop', 'runId': identity.raw_run_id, 'client': identity.client})
            locks.append(stop_lock)
            if not stop_lock.acquire():
                failures.append('stop check already running for this run')
            # 目标级独占资源由 run_required_quality_gates.py 获取。
            # Stop 入口提前持有同名资源会让子 runner 自阻塞。
            lock_status = 'acquired' if not failures else 'blocked'
            if stop_helpers.changed_files_require_openspec(changed_files):
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
                for key in list(env):
                    if key.startswith('FEIPI_') and key != 'FEIPI_AGENT_RUNTIME_ROOT':
                        env.pop(key, None)
                env['ACTIVE_CHANGE_ID'] = change_id
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
        if reused_failures is None:
            continuation_count, reentry_failures = update_reentry(reentry_path, repo_root, failures)
            failures.extend(reentry_failures)
        else:
            continuation_count = int(load_reentry(reentry_path).get('continuationCount') or 0)
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
        return 0 if circuit_final else 2
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
