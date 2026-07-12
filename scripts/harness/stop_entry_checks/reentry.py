"""重入检测：指纹计算、重入状态、circuit breaker、审计。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from scripts.harness import stop_helpers
from scripts.harness.primary_session import ensure_private_directory

from ._io import utc_now, write_private_json

MAX_CONTINUATIONS = 2


# 执行 git 命令并返回非空行。
def _git_paths(repo_root: Path, *args: str) -> list[str]:
    """参数：
        repo_root: 当前函数使用的输入参数。
        args: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
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


# 计算失败列表的不可变指纹。
def fingerprint(failures: list[str]) -> str:
    """参数：
        failures: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    raw = json.dumps(sorted(failures), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


# 提取用于隔离 Stop 恢复状态的不可变身份字段。
def recovery_scope(record: dict[str, Any]) -> dict[str, str]:
    """参数：
        record: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
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
        state: 当前函数使用的输入参数。
        scope: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    stored = state.get('scope')
    return isinstance(stored, dict) and all(
        str(stored.get(key) or '') == value for key, value in scope.items()
    )


# 从磁盘读取重入状态。
def load_reentry(path: Path) -> dict[str, Any]:
    """参数：
        path: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
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


# 持久化 Stop 恢复审计事件。
def write_recovery_audit(
    audit_dir: Path,
    *,
    event: str,
    scope: dict[str, str],
    state: dict[str, Any],
) -> None:
    """参数：
        audit_dir: 当前函数使用的输入参数。
        event: 当前函数使用的输入参数。
        scope: 当前函数使用的输入参数。
        state: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
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


# 计算稳定的停止流程重入指纹。
def stop_signature(
    repo_root: Path,
    failures: list[str],
    *,
    change_id: str,
) -> dict[str, str]:
    """参数：
        repo_root: 当前函数使用的输入参数。
        failures: 当前函数使用的输入参数。
        change_id: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    head = _git_paths(repo_root, 'rev-parse', 'HEAD')
    dirty_hash = stop_helpers.git_dirty_hash(repo_root)
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


# 判断是否命中相同重入失败。
def matching_reentry_failure(
    path: Path,
    repo_root: Path,
    scope: dict[str, str],
    *,
    change_id: str,
) -> tuple[bool, dict[str, Any], bool]:
    """参数：
        path: 当前函数使用的输入参数。
        repo_root: 当前函数使用的输入参数。
        scope: 当前函数使用的输入参数。
        change_id: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
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
        and sig.get('changeId') == change_id
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
    change_id: str,
) -> tuple[int, list[str]]:
    """参数：
        path: 当前函数使用的输入参数。
        repo_root: 当前函数使用的输入参数。
        failures: 当前函数使用的输入参数。
        scope: 当前函数使用的输入参数。
        audit_dir: 当前函数使用的输入参数。
        change_id: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
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
        targets: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    from scripts.quality.quality_targets import target_parallel_meta

    names: list[str] = []
    for target in targets:
        for name in target_parallel_meta(target).get('exclusive_resources', []):
            if isinstance(name, str) and name not in names:
                names.append(name)
    return names
