#!/usr/bin/env python3
"""统一 Stop 入口：解析一次 stdin 并写 run-scoped summary。"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
import uuid
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
    ensure_private_directory,
    load_run_record,
    resolve_runtime_root,
    validate_checkout_record,
    validate_run_record,
)
from scripts.harness.resource_lock import _pid_start_time, process_is_alive  # noqa: E402
from scripts.quality import check_agent_runtime_report  # noqa: E402
from scripts.quality.quality_targets import target_parallel_meta  # noqa: E402

MAX_CONTINUATIONS = 2


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
    raw = ctx.get('cwd') or ctx.get('workingDirectory') or ''
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


# 将当前运行的 Git 证据收集委托给 Stop 与 finalize 共享的权威实现。
def collect_git_evidence(repo_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    """参数：
        repo_root: 当前仓库根目录。
        record: Registry 绑定的运行记录。

    返回：
        Stop 与 finalize 共享的 Git 证据映射。
    """

    return stop_helpers.collect_git_evidence(repo_root, record)


# 维护 collect_run_changed_files 函数行为。
def collect_run_changed_files(repo_root: Path, identity: runtime_paths.RuntimeIdentity, record: dict[str, Any] | None) -> tuple[list[str], str, list[str]]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if identity.has_run and identity.has_session and record:
        return collect_git_evidence(repo_root, record)['changedFiles'], 'git-run-record', []
    return [], 'run-identity-required', ['Stop requires an authoritative run record']


@dataclass
class FileLock:
    path: Path
    owner: dict[str, Any]
    acquired: bool = False
    fencing_token: str = ''
    reclaimed_owner: dict[str, Any] = field(default_factory=dict)

    # 不跟随符号链接且不接受所有者变更地读取锁负载。
    def _read_payload(self) -> dict[str, Any]:
        """返回：
            验证通过的锁负载；文件不安全或不可读时返回空映射。
        """

        try:
            metadata = self.path.lstat()
        except FileNotFoundError:
            return {}
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return {}
        if hasattr(os, 'geteuid') and metadata.st_uid != os.geteuid():
            return {}
        try:
            descriptor = os.open(
                self.path,
                os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0),
            )
        except OSError:
            return {}
        try:
            opened = os.fstat(descriptor)
            if opened.st_ino != metadata.st_ino or opened.st_dev != metadata.st_dev:
                return {}
            raw = os.read(descriptor, 64 * 1024)
        finally:
            os.close(descriptor)
        try:
            data = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # 维护 acquire 函数行为。
    def acquire(self) -> bool:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或校验结果。
        """
        self._remove_stale()
        ensure_private_directory(self.path.parent)
        payload = dict(self.owner)
        self.fencing_token = uuid.uuid4().hex
        payload.update({
            'schemaVersion': 1,
            'pid': os.getpid(),
            'processStartTime': _pid_start_time(os.getpid()),
            'fencingToken': self.fencing_token,
            'createdAt': utc_now(),
            'heartbeatAt': utc_now(),
        })
        try:
            fd = os.open(
                str(self.path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0),
                0o600,
            )
        except FileExistsError:
            return False
        except OSError:
            return False
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        self.acquired = True
        return True

    # 维护 release 函数行为。
    def release(self) -> bool:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或校验结果。
        """
        if not self.acquired:
            return False
        released = False
        try:
            data = self._read_payload()
            if not isinstance(data, dict) or data.get('fencingToken') != self.fencing_token:
                return False
            for field_name in ('runId', 'sessionId', 'worktreeId'):
                if str(data.get(field_name) or '') != str(self.owner.get(field_name) or ''):
                    return False
            self.path.unlink()
            released = True
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False
            self.fencing_token = ''
        return released

    # 维护 _remove_stale 函数行为。
    def _remove_stale(self) -> None:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或校验结果。
        """
        data = self._read_payload()
        if not isinstance(data, dict) or not data:
            return
        for field_name in ('runId', 'sessionId', 'worktreeId'):
            expected = str(self.owner.get(field_name) or '')
            if not expected or str(data.get(field_name) or '') != expected:
                return
        pid = data.get('pid')
        started = str(data.get('processStartTime') or '')
        token = str(data.get('fencingToken') or '')
        if not isinstance(pid, int) or pid <= 0 or not started or not token:
            return
        if process_is_alive(pid, started):
            return
        try:
            metadata = self.path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                return
            if hasattr(os, 'geteuid') and metadata.st_uid != os.geteuid():
                return
            if time.time() - metadata.st_mtime <= 0:
                return
            self.path.unlink()
            self.reclaimed_owner = data
        except OSError:
            return


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
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return {'continuationCount': 0}
        if hasattr(os, 'geteuid') and metadata.st_uid != os.geteuid():
            return {'continuationCount': 0}
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            opened = os.fstat(descriptor)
            if opened.st_ino != metadata.st_ino or opened.st_dev != metadata.st_dev:
                return {'continuationCount': 0}
            raw = os.read(descriptor, 1024 * 1024)
        finally:
            os.close(descriptor)
        data = json.loads(raw.decode('utf-8'))
    except Exception:
        return {'continuationCount': 0}
    return data if isinstance(data, dict) else {'continuationCount': 0}


# 以原子替换方式写入仅当前用户可访问的 JSON 文档。
def _write_private_json(path: Path, data: dict[str, Any]) -> None:
    """参数：
        path: 目标 JSON 文件路径。
        data: 待序列化的数据映射。

    异常：
        RuntimeError: 目标文件类型或所有者不安全时抛出。
    """

    ensure_private_directory(path.parent)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
            raise RuntimeError(f'refusing unsafe Stop state target: {path}')
        if hasattr(os, 'geteuid') and existing.st_uid != os.geteuid():
            raise RuntimeError(f'Stop state is not owned by current user: {path}')
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        payload = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
        with os.fdopen(descriptor, 'wb', closefd=False) as handle:
            handle.write(payload)
            handle.flush()
        os.fsync(descriptor)
        os.replace(temporary, path)
    finally:
        os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


# 提取用于隔离 Stop 恢复状态的不可变身份字段。
def _recovery_scope(record: dict[str, Any]) -> dict[str, str]:
    """参数：
        record: Registry 绑定的运行记录。

    返回：
        Stop 恢复状态的身份隔离范围。
    """

    return {
        'runId': str(record.get('runId') or ''),
        'sessionId': str(record.get('sessionId') or ''),
        'worktreeId': str(record.get('worktreeId') or ''),
        'checkoutRoot': str(Path(str(record.get('checkoutRoot') or '')).resolve()),
        'repoKey': str(record.get('repoKey') or ''),
    }


# 判断已保存的 Stop 恢复状态是否属于指定身份范围。
def _scope_matches(state: dict[str, Any], scope: dict[str, str]) -> bool:
    """参数：
        state: 已保存的 Stop 恢复状态。
        scope: 期望的身份隔离范围。

    返回：
        状态范围与期望范围完全一致时返回 true。
    """
    stored = state.get('scope')
    return isinstance(stored, dict) and all(str(stored.get(key) or '') == value for key, value in scope.items())


# 持久化不可变且身份完整的 Stop 恢复审计事件。
def _write_recovery_audit(audit_dir: Path, *, event: str, scope: dict[str, str], state: dict[str, Any]) -> None:
    """参数：
        audit_dir: 审计事件目录。
        event: 审计事件名称。
        scope: 身份隔离范围。
        state: 当前 Stop 恢复状态。
    """

    ensure_private_directory(audit_dir)
    payload = {
        'schemaVersion': 1,
        'event': event,
        **scope,
        'continuationCount': int(state.get('continuationCount') or 0),
        'failureFingerprint': str(state.get('lastFailureFingerprint') or ''),
        'circuitState': str((state.get('circuitBreaker') or {}).get('state') or 'CLOSED'),
        'at': utc_now(),
    }
    _write_private_json(
        audit_dir / f'{time.time_ns()}-{uuid.uuid4().hex[:12]}.json',
        payload,
    )


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
def matching_reentry_failure(
    path: Path,
    repo_root: Path,
    scope: dict[str, str],
) -> tuple[bool, dict[str, Any], bool]:
    """参数：
        path: 重入状态文件路径。
        repo_root: 仓库根目录。

    返回：
        是否同一失败，以及已读取状态。
    """
    if not path.exists():
        return False, {'schemaVersion': 1, 'scope': scope, 'continuationCount': 0}, True
    state = load_reentry(path)
    if not _scope_matches(state, scope):
        return False, state, False
    sig = state.get('lastSignature')
    if not isinstance(sig, dict):
        return False, state, True
    current_head = (_git_paths(repo_root, 'rev-parse', 'HEAD') or [''])[0]
    current_dirty = stop_helpers.git_dirty_hash(repo_root)
    return (
        sig.get('head') == current_head
        and sig.get('dirtyHash') == current_dirty
        and bool(state.get('lastFailures')),
        state,
        True,
    )


# 更新停止流程重入状态。
def update_reentry(
    path: Path,
    repo_root: Path,
    failures: list[str],
    *,
    scope: dict[str, str],
    audit_dir: Path,
) -> tuple[int, list[str]]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    state = load_reentry(path)
    if path.exists() and not _scope_matches(state, scope):
        return 0, ['run-scoped Stop recovery identity mismatch']
    state['schemaVersion'] = 1
    state['scope'] = scope
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
        circuit = {
            'state': 'OPEN' if count > MAX_CONTINUATIONS else 'CLOSED',
            'reason': 'identical Stop failure fingerprint' if count > MAX_CONTINUATIONS else '',
        }
        if count > MAX_CONTINUATIONS:
            circuit['openedAt'] = utc_now()
        state.update({'continuationCount': count, 'lastFailureFingerprint': fp, 'lastFailures': failures, 'lastSignature': sig, 'lastAttemptAt': utc_now(), 'circuitBreaker': circuit})
    else:
        count = 0
        state.update({'continuationCount': 0, 'lastFailureFingerprint': '', 'lastFailures': [], 'lastSignature': {}, 'lastAttemptAt': utc_now(), 'circuitBreaker': {'state': 'CLOSED', 'reason': ''}})
    _write_private_json(path, state)
    _write_recovery_audit(
        audit_dir,
        event='STOP_RECOVERY_FAILURE_RECORDED' if failures else 'STOP_RECOVERY_CLEARED',
        scope=scope,
        state=state,
    )
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
    if not identity.has_run or not identity.has_session:
        raise ValueError('runtime report requires an authoritative run identity')
    return runtime_paths.quality_dir(repo_root, identity) / change_id / 'runtime-report.json'


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
def write_runtime_report(
    path: Path,
    *,
    identity: runtime_paths.RuntimeIdentity,
    change_id: str,
    changed_files: list[str],
    targets: list[str],
    gates_ok: bool,
    failures: list[str],
    git_evidence: dict[str, Any],
) -> None:
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
        'gitEvidence': git_evidence,
        'commits': git_evidence.get('commits', []),
        'committedFiles': git_evidence.get('committedFiles', []),
        'uncommittedFiles': git_evidence.get('uncommittedFiles', []),
        'untrackedFiles': git_evidence.get('untrackedFiles', []),
        'initialDirtySnapshot': git_evidence.get('initialDirtySnapshot', {}),
        'checkoutKind': git_evidence.get('checkoutKind', ''),
        'checkoutCreator': git_evidence.get('checkoutCreator', 'unknown'),
        'targetBranch': git_evidence.get('targetBranch', ''),
        'targetHead': git_evidence.get('targetHead', ''),
        'targetStatus': git_evidence.get('targetStatus', {}),
        'ahead': git_evidence.get('ahead', 0),
        'behind': git_evidence.get('behind', 0),
        'mergeBase': git_evidence.get('mergeBase', ''),
        'primary': git_evidence.get('primary', {}),
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
    del agent
    if not identity.has_run or not identity.has_session:
        raise ValueError('Stop summary requires an authoritative run identity')
    return runtime_paths.agent_log_dir(repo_root, identity) / 'stop-check-summary.json'


# 维护 run_stop 函数行为。
def run_stop(
    agent: str,
    raw_ctx: dict[str, Any],
    *,
    handoff_on_failure: bool = False,
) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    repo_root = _repo_root(raw_ctx)
    stop_helpers._use_repo_root(repo_root)
    ctx = HookContext('Stop', raw_ctx)
    identity = runtime_paths.identity_from_hook_context(ctx, agent_client=agent)
    if not identity.has_run or not identity.has_session:
        print('[stop_entry] BLOCK authoritative run/session identity is required', file=sys.stderr)
        return 2
    record = load_run_record(repo_root, identity.raw_run_id)
    if not record:
        print('[stop_entry] BLOCK run record not found for run_id', file=sys.stderr)
        return 2
    try:
        validate_run_record(record)
        checkout_facts, checkout_errors = validate_checkout_record(repo_root, record)
    except Exception as exc:
        print(f'[stop_entry] BLOCK run identity cannot be proven: {exc}', file=sys.stderr)
        return 2
    if checkout_errors:
        print(
            '[stop_entry] BLOCK checkout identity: ' + '; '.join(checkout_errors),
            file=sys.stderr,
        )
        return 2

    failures: list[str] = []
    warnings: list[str] = list(identity.identity_warnings)
    git_evidence: dict[str, Any] = {'changedFiles': []}
    changed_files: list[str] = []
    evidence_mode = 'git-run-record'
    change_id = identity.change_id or str(record.get('changeId') or '') or 'unknown'
    targets: list[str] = []
    read_only = True
    runtime_root = resolve_runtime_root(repo_root)
    runs_root = ensure_private_directory(runtime_root / 'runs', root=runtime_root)
    run_dir = ensure_private_directory(runs_root / identity.run_id, root=runs_root)
    audit_dir = ensure_private_directory(runtime_root / 'audit', root=runtime_root)
    scope = _recovery_scope(record)
    reentry_path = run_dir / 'stop-reentry.json'
    summary_path = stop_summary_path(repo_root, identity, agent)
    report_path = runtime_report_path(repo_root, identity, change_id)
    resource_lock_names: list[str] = []
    gates_ok = True
    runtime_ok = True
    lock_status = 'blocked'
    continuation_count = 0
    outcome_record: dict[str, Any] = {}
    stop_lock = FileLock(
        run_dir / 'stop-check.lock',
        {
            'kind': 'stop',
            'runId': scope['runId'],
            'sessionId': scope['sessionId'],
            'worktreeId': scope['worktreeId'],
            'checkoutRoot': scope['checkoutRoot'],
            'repoKey': scope['repoKey'],
            'client': identity.client,
        },
    )
    if not stop_lock.acquire():
        print('[stop_entry] BLOCK stop check already running for this run', file=sys.stderr)
        return 2
    lock_status = 'acquired'
    try:
        if stop_lock.reclaimed_owner:
            _write_recovery_audit(
                audit_dir,
                event='STOP_LOCK_RECLAIMED',
                scope=scope,
                state={'continuationCount': 0, 'circuitBreaker': {'state': 'CLOSED'}},
            )
        try:
            git_evidence = collect_git_evidence(repo_root, record)
        except stop_helpers.GitEvidenceError as exc:
            git_evidence = {'queryErrors': [str(exc)], 'changedFiles': []}
            failures.append(f'Git evidence unavailable: {exc}')
        changed_files = list(git_evidence.get('changedFiles') or [])
        targets = stop_helpers.required_targets(changed_files)
        if changed_files and not targets:
            failures.append('changed files did not map to required quality targets')
        read_only = not changed_files
        resource_lock_names = resource_names(targets)
        same_failure, reentry_state, scope_ok = matching_reentry_failure(
            reentry_path,
            repo_root,
            scope,
        )
        if not scope_ok:
            failures.append('run-scoped Stop recovery identity mismatch')
        if ctx.stop_hook_active:
            warnings.append('stop_hook_active reentry observed; not blocking solely on reentry')
        if same_failure and scope_ok:
            previous = [str(item) for item in reentry_state.get('lastFailures', [])]
            failures.extend(previous)
            gates_ok = False
            warnings.append('reused persistent Stop failure; heavy gates were not rerun')
        elif not failures and not read_only:
            if stop_helpers.changed_files_require_openspec(changed_files):
                if change_id == 'unknown':
                    failures.append('active change is missing for protected changes')
                else:
                    env = os.environ.copy()
                    if not run_cmd(
                        'openspec-active-change',
                        [sys.executable, 'scripts/openspec/validate_active_change.py', '--change-id', change_id],
                        repo_root,
                        env,
                        timeout=300,
                    ):
                        failures.append('validate_active_change.py failed')
            if not failures:
                quality_out = runtime_paths.quality_dir(repo_root, identity)
                out_arg = str(quality_out.relative_to(repo_root))
                env = os.environ.copy()
                for key in list(env):
                    if key.startswith('FEIPI_') and key != 'FEIPI_AGENT_RUNTIME_ROOT':
                        env.pop(key, None)
                env['ACTIVE_CHANGE_ID'] = change_id
                gates_ok = run_cmd(
                    'required-quality-gates',
                    [
                        sys.executable,
                        'scripts/quality/run_required_quality_gates.py',
                        '--include-session-detail',
                        '--change-id',
                        change_id,
                        '--out',
                        out_arg,
                        '--changed-files',
                        json.dumps(changed_files, ensure_ascii=False),
                    ],
                    repo_root,
                    env,
                )
                if not gates_ok:
                    failures.append('run_required_quality_gates.py failed')
        if git_evidence.get('checkoutFingerprint'):
            try:
                post_gate_evidence = collect_git_evidence(repo_root, record)
                if post_gate_evidence.get('checkoutFingerprint') != git_evidence.get(
                    'checkoutFingerprint'
                ):
                    gates_ok = False
                    failures.append('checkout Git snapshot changed during Stop validation')
            except stop_helpers.GitEvidenceError as exc:
                gates_ok = False
                failures.append(f'post-gate Git evidence unavailable: {exc}')
        write_runtime_report(
            report_path,
            identity=identity,
            change_id=change_id,
            changed_files=changed_files,
            targets=targets,
            gates_ok=gates_ok,
            failures=failures,
            git_evidence=git_evidence,
        )
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
    except Exception as exc:
        failures.append(f'stop exception: {type(exc).__name__}: {exc}')
    finally:
        failures[:] = list(dict.fromkeys(failures))
        try:
            continuation_count, reentry_failures = update_reentry(
                reentry_path,
                repo_root,
                failures,
                scope=scope,
                audit_dir=audit_dir,
            )
            failures.extend(reentry_failures)
        except Exception as exc:
            failures.append(f'Stop recovery update failed: {exc}')
        failures[:] = list(dict.fromkeys(failures))
        try:
            from scripts.harness.sessionctl import record_stop_result  # noqa: PLC0415

            requested_exit = 2 if failures else 0
            outcome_record, _outcome_facts = record_stop_result(
                repo_root,
                identity.raw_run_id,
                stop_exit=requested_exit,
                summary_status='BLOCKED' if failures else 'PASS',
                validated_facts=git_evidence,
                handoff_on_failure=handoff_on_failure,
            )
            if requested_exit == 0 and outcome_record.get('status') != 'VALIDATED':
                validation = outcome_record.get('stopValidation')
                detail = (
                    str(validation.get('evidenceError') or '')
                    if isinstance(validation, dict)
                    else ''
                )
                failures.append(detail or 'Stop validation receipt did not match gated Git snapshot')
                continuation_count, reentry_failures = update_reentry(
                    reentry_path,
                    repo_root,
                    failures,
                    scope=scope,
                    audit_dir=audit_dir,
                )
                failures.extend(reentry_failures)
                write_runtime_report(
                    report_path,
                    identity=identity,
                    change_id=change_id,
                    changed_files=changed_files,
                    targets=targets,
                    gates_ok=False,
                    failures=failures,
                    git_evidence=git_evidence,
                )
        except Exception as exc:
            failures.append(f'Stop Registry result update failed: {exc}')
        released = stop_lock.release()
        if not released:
            lock_status = 'release-fenced'
            warnings.append('run-scoped Stop lock release was fenced')
        else:
            try:
                _write_recovery_audit(
                    audit_dir,
                    event='STOP_LOCK_RELEASED',
                    scope=scope,
                    state=load_reentry(reentry_path),
                )
            except Exception as exc:
                warnings.append(f'Stop lock release audit failed: {exc}')
        recovery_state = load_reentry(reentry_path)
        circuit_state = str((recovery_state.get('circuitBreaker') or {}).get('state') or 'CLOSED')
        run_status = str(outcome_record.get('status') or 'BLOCKED')
        status = (
            'PASS'
            if not failures and runtime_ok and run_status == 'VALIDATED'
            else 'BLOCKED'
        )
        summary = {
            'schemaVersion': 5,
            'ts': utc_now(),
            'runId': identity.raw_run_id,
            'client': identity.client,
            'sessionId': identity.raw_session_id,
            'taskId': identity.raw_task_id,
            'worktreeId': identity.raw_worktree_id,
            'branch': identity.branch or str(record.get('branch') or ''),
            'observedBranch': str(checkout_facts.get('branch') or ''),
            'detached': bool(checkout_facts.get('detached', record.get('detached', False))),
            'checkoutKind': str(checkout_facts.get('checkoutKind') or record.get('checkoutKind') or ''),
            'checkoutCreator': str(checkout_facts.get('checkoutCreator') or record.get('checkoutCreator') or 'unknown'),
            'gitCommonDir': str(checkout_facts.get('gitCommonDir') or record.get('gitCommonDir') or ''),
            'baseCommit': str(record.get('baseCommit') or ''),
            'baseCommitExists': checkout_facts.get('baseCommitExists'),
            'baseIsAncestorOfHead': checkout_facts.get('baseIsAncestorOfHead'),
            'headCommit': git_evidence.get('headCommit', ''),
            'commits': git_evidence.get('commits', []),
            'committedFiles': git_evidence.get('committedFiles', []),
            'uncommittedFiles': git_evidence.get('uncommittedFiles', []),
            'untrackedFiles': git_evidence.get('untrackedFiles', []),
            'ahead': git_evidence.get('ahead', 0),
            'behind': git_evidence.get('behind', 0),
            'aheadBehind': git_evidence.get('aheadBehind', {'ahead': 0, 'behind': 0}),
            'mergeBase': git_evidence.get('mergeBase', ''),
            'initialDirtySnapshot': git_evidence.get('initialDirtySnapshot', {}),
            'initialDirtyBaseline': git_evidence.get('initialDirtyBaseline', {}),
            'changeAttribution': git_evidence.get('changeAttribution', {}),
            'checkoutStatus': git_evidence.get('checkoutStatus', {}),
            'targetBranch': git_evidence.get('targetBranch', str(record.get('targetBranch') or '')),
            'targetHead': git_evidence.get('targetHead', ''),
            'targetState': git_evidence.get('targetState', 'UNKNOWN'),
            'targetStatus': git_evidence.get('targetStatus', {}),
            'primaryStatus': git_evidence.get('primaryStatus', {}),
            'changeId': change_id,
            'readOnly': read_only,
            'status': status,
            'runStatus': run_status,
            'evidenceMode': evidence_mode,
            'changedFiles': changed_files,
            'requiredTargets': targets,
            'resourceLocks': resource_lock_names,
            'lockStatus': lock_status,
            'blockingFailures': failures,
            'warnings': warnings,
            'continuationCount': continuation_count,
            'circuitState': circuit_state,
            'artifacts': {
                'summary': str(summary_path),
                'runtimeReport': str(report_path),
                'reentry': str(reentry_path),
            },
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
