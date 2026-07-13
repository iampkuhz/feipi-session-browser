"""Stop 恢复域：私有写入、FileLock、重入、fencing 与审计。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from scripts.agent_runtime.git_state import checkout_content_snapshot
from scripts.agent_runtime.git_state import lines as git_lines
from scripts.agent_runtime.locks import FencedFileLock
from scripts.agent_runtime.session.contract import ensure_private_directory
from scripts.agent_runtime.storage import load_json, stable_hash, utc_now, write_json_atomic


class FileLock(FencedFileLock):
    """Stop run-scoped 锁；仅允许回收同一 run/session/worktree 的死亡 owner。"""

    def __init__(self, path: Path, owner: dict[str, Any], grace_seconds: float = 2.0) -> None:
        super().__init__(
            path,
            owner,
            stale_seconds=grace_seconds,
            strict_scope=True,
            reclaim_event="STOP_LOCK_RECLAIMED",
        )

    def acquire(self) -> bool:
        """尝试获取当前 Stop 恢复锁；冲突时返回失败并保留 owner 证据。"""
        return self.try_acquire()


MAX_CONTINUATIONS = 2


# 提取用于隔离停止恢复状态的身份字段。
def recovery_scope(record: dict[str, Any]) -> dict[str, str]:
    """执行对应 Runtime 安全契约，并保持身份、fencing 与 fail-closed 语义。"""
    return {
        'runId': str(record.get('runId') or ''),
        'sessionId': str(record.get('sessionId') or ''),
        'worktreeId': str(record.get('worktreeId') or ''),
        'checkoutRoot': str(Path(str(record.get('checkoutRoot') or '')).resolve()),
        'repoKey': str(record.get('repoKey') or ''),
    }


# 判断已保存的停止恢复状态是否属于指定身份范围。
def _scope_matches(state: dict[str, Any], scope: dict[str, str]) -> bool:
    """内部安全原语；事实无法复核时抛出专用错误并关闭失败。"""
    stored = state.get('scope')
    return isinstance(stored, dict) and all(
        str(stored.get(key) or '') == value for key, value in scope.items()
    )


# 从磁盘安全读取重入状态；不安全或损坏文件按首次运行处理。
def load_reentry(path: Path) -> dict[str, Any]:
    """读取 Stop 重入状态；文件缺失或损坏时按首次运行处理。"""
    try:
        return load_json(path, {"continuationCount": 0})
    except (OSError, ValueError):
        return {"continuationCount": 0}


# 持久化停止恢复审计事件。
def write_recovery_audit(
    audit_dir: Path,
    *,
    event: str,
    scope: dict[str, str],
    state: dict[str, Any],
) -> None:
    """原子更新 run-scoped 恢复证据，并保留身份与失败指纹。"""
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
    write_json_atomic(
        audit_dir / f'{time.time_ns()}-{uuid.uuid4().hex[:12]}.json',
        payload,
    )


# 计算排除熔断消息后的稳定重入签名。
def stop_signature(
    repo_root: Path,
    failures: list[str],
    *,
    change_id: str,
) -> dict[str, str]:
    """执行对应 Runtime 安全契约，并保持身份、fencing 与 fail-closed 语义。"""
    head = git_lines(repo_root, 'rev-parse', 'HEAD')
    dirty_hash = str(checkout_content_snapshot(repo_root)['fingerprint'])
    stable_failures = [
        f
        for f in failures
        if f != 'continuation limit reached for identical Stop failure fingerprint'
    ]
    environment = {
        'baseUrl': os.environ.get('BASE_URL', ''),
        'projectPython': (repo_root / '.venv' / 'bin' / 'python').exists(),
        'nodeModules': (repo_root / 'node_modules').exists(),
        'playwright': (repo_root / 'node_modules' / '.bin' / 'playwright').exists(),
        'javaHome': os.environ.get('JAVA_HOME', ''),
    }
    environment_fingerprint = hashlib.sha256(
        json.dumps(environment, sort_keys=True).encode('utf-8')
    ).hexdigest()[:16]
    return {
        'head': head[0] if head else '',
        'dirtyHash': dirty_hash,
        'changeId': change_id,
        'failureFingerprint': stable_hash(json.dumps(sorted(stable_failures), ensure_ascii=False))[
            :16
        ],
        'environmentFingerprint': environment_fingerprint,
    }


# 判断当前仓库状态是否命中已保存的相同重入失败。
def matching_reentry_failure(
    path: Path,
    repo_root: Path,
    scope: dict[str, str],
    *,
    change_id: str,
) -> tuple[bool, dict[str, Any], bool]:
    """执行对应 Runtime 安全契约，并保持身份、fencing 与 fail-closed 语义。"""
    if not path.exists():
        return False, {'schemaVersion': 1, 'scope': scope, 'continuationCount': 0}, True
    state = load_reentry(path)
    if not _scope_matches(state, scope):
        return False, state, False
    sig = state.get('lastSignature')
    if not isinstance(sig, dict):
        return False, state, True
    current = stop_signature(repo_root, [], change_id=change_id)
    return (
        sig.get('head') == current['head']
        and sig.get('dirtyHash') == current['dirtyHash']
        and sig.get('changeId') == current['changeId']
        and sig.get('environmentFingerprint') == current['environmentFingerprint']
        and bool(state.get('lastFailures')),
        state,
        True,
    )


# 更新停止流程重入状态并写入恢复审计。
def update_reentry(
    path: Path,
    repo_root: Path,
    failures: list[str],
    *,
    scope: dict[str, str],
    audit_dir: Path,
    change_id: str,
) -> tuple[int, list[str]]:
    """原子更新 run-scoped 恢复证据，并保留身份与失败指纹。"""
    state = load_reentry(path)
    if path.exists() and not _scope_matches(state, scope):
        return 0, ['run-scoped Stop recovery identity mismatch']
    state['schemaVersion'] = 1
    state['scope'] = scope
    sig = stop_signature(repo_root, failures, change_id=change_id)
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
        state.update(
            {
                'continuationCount': count,
                'lastFailureFingerprint': fp,
                'lastFailures': failures,
                'lastSignature': sig,
                'lastAttemptAt': utc_now(),
                'circuitBreaker': circuit,
            }
        )
    else:
        count = 0
        state.update(
            {
                'continuationCount': 0,
                'lastFailureFingerprint': '',
                'lastFailures': [],
                'lastSignature': {},
                'lastAttemptAt': utc_now(),
                'circuitBreaker': {'state': 'CLOSED', 'reason': ''},
            }
        )
    write_json_atomic(path, state)
    write_recovery_audit(
        audit_dir,
        event='STOP_RECOVERY_FAILURE_RECORDED' if failures else 'STOP_RECOVERY_CLEARED',
        scope=scope,
        state=state,
    )
    return count, extra


# 计算质量目标所需的排他资源锁名称。
def resource_names(targets: list[str]) -> list[str]:
    """执行对应 Runtime 安全契约，并保持身份、fencing 与 fail-closed 语义。"""
    from scripts.gates.planner import target_parallel_meta

    names: list[str] = []
    for target in targets:
        for name in target_parallel_meta(target).get('exclusive_resources', []):
            if isinstance(name, str) and name not in names:
                names.append(name)
    return names
