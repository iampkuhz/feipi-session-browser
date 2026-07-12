"""重入检测：指纹计算、重入状态、circuit breaker、审计。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
import uuid
from pathlib import Path
from typing import Any

from scripts.harness.primary_session import ensure_private_directory

from ._io import utc_now, write_private_json
from .git_evidence import git_dirty_hash, git_lines

MAX_CONTINUATIONS = 2


# 计算失败列表的稳定指纹。
def fingerprint(failures: list[str]) -> str:
    """参数：
        failures: 失败消息列表。

    返回：
        排序后失败内容的短哈希指纹。
    """
    raw = json.dumps(sorted(failures), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


# 提取用于隔离停止恢复状态的身份字段。
def recovery_scope(record: dict[str, Any]) -> dict[str, str]:
    """参数：
        record: 当前会话记录。

    返回：
        恢复状态身份范围字典。
    """
    return {
        'runId': str(record.get('runId') or ''),
        'sessionId': str(record.get('sessionId') or ''),
        'worktreeId': str(record.get('worktreeId') or ''),
        'checkoutRoot': str(Path(str(record.get('checkoutRoot') or '')).resolve()),
        'repoKey': str(record.get('repoKey') or ''),
    }


# 判断已保存的停止恢复状态是否属于指定身份范围。
def _scope_matches(state: dict[str, Any], scope: dict[str, str]) -> bool:
    """参数：
        state: 已保存的恢复状态。
        scope: 期望的身份范围。

    返回：
        身份字段全部一致时返回 true，否则返回 false。
    """
    stored = state.get('scope')
    return isinstance(stored, dict) and all(
        str(stored.get(key) or '') == value for key, value in scope.items()
    )


# 从磁盘安全读取重入状态。
def load_reentry(path: Path) -> dict[str, Any]:
    """参数：
        path: 重入状态路径。

    返回：
        已读取的重入状态；读取失败时返回初始状态。
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


# 持久化停止恢复审计事件。
def write_recovery_audit(
    audit_dir: Path,
    *,
    event: str,
    scope: dict[str, str],
    state: dict[str, Any],
) -> None:
    """参数：
        audit_dir: 恢复审计目录。
        event: 审计事件名称。
        scope: 当前恢复状态身份范围。
        state: 当前恢复状态。

    返回：
        无返回值。
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
    write_private_json(
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
    """参数：
        repo_root: 仓库根目录。
        failures: 失败消息列表。
        change_id: 变更标识。

    返回：
        包含提交、工作区、变更和失败指纹的签名字典。
    """
    head = git_lines(repo_root, 'rev-parse', 'HEAD')
    dirty_hash = git_dirty_hash(repo_root)
    stable_failures = [
        f for f in failures
        if f != 'continuation limit reached for identical Stop failure fingerprint'
    ]
    return {
        'head': head[0] if head else '',
        'dirtyHash': dirty_hash,
        'changeId': change_id,
        'failureFingerprint': fingerprint(stable_failures),
    }


# 判断当前仓库状态是否命中已保存的相同重入失败。
def matching_reentry_failure(
    path: Path,
    repo_root: Path,
    scope: dict[str, str],
    *,
    change_id: str,
) -> tuple[bool, dict[str, Any], bool]:
    """参数：
        path: 重入状态路径。
        repo_root: 仓库根目录。
        scope: 当前恢复状态身份范围。
        change_id: 变更标识。

    返回：
        是否命中、已保存状态以及身份范围是否一致。
    """
    if not path.exists():
        return False, {'schemaVersion': 1, 'scope': scope, 'continuationCount': 0}, True
    state = load_reentry(path)
    if not _scope_matches(state, scope):
        return False, state, False
    sig = state.get('lastSignature')
    if not isinstance(sig, dict):
        return False, state, True
    current_head = (git_lines(repo_root, 'rev-parse', 'HEAD') or [''])[0]
    current_dirty = git_dirty_hash(repo_root)
    return (
        sig.get('head') == current_head
        and sig.get('dirtyHash') == current_dirty
        and sig.get('changeId') == change_id
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
    """参数：
        path: 重入状态路径。
        repo_root: 仓库根目录。
        failures: 当前失败消息列表。
        scope: 当前恢复状态身份范围。
        audit_dir: 恢复审计目录。
        change_id: 变更标识。

    返回：
        连续失败次数和附加失败列表。
    """
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
        state.update({
            'continuationCount': count,
            'lastFailureFingerprint': fp,
            'lastFailures': failures,
            'lastSignature': sig,
            'lastAttemptAt': utc_now(),
            'circuitBreaker': circuit,
        })
    else:
        count = 0
        state.update({
            'continuationCount': 0,
            'lastFailureFingerprint': '',
            'lastFailures': [],
            'lastSignature': {},
            'lastAttemptAt': utc_now(),
            'circuitBreaker': {'state': 'CLOSED', 'reason': ''},
        })
    write_private_json(path, state)
    write_recovery_audit(
        audit_dir,
        event='STOP_RECOVERY_FAILURE_RECORDED' if failures else 'STOP_RECOVERY_CLEARED',
        scope=scope,
        state=state,
    )
    return count, extra


# 计算质量目标所需的排他资源锁名称。
def resource_names(targets: list[str]) -> list[str]:
    """参数：
        targets: 质量目标列表。

    返回：
        去重后的排他资源锁名称列表。
    """
    from scripts.quality.quality_targets import target_parallel_meta

    names: list[str] = []
    for target in targets:
        for name in target_parallel_meta(target).get('exclusive_resources', []):
            if isinstance(name, str) and name not in names:
                names.append(name)
    return names
