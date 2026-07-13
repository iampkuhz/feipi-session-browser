"""保存并校验内容敏感 PASS receipt，不承担 Gate 选择或执行。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.gates.catalog import CATALOG_VERSION
from scripts.gates.report import PASS


@dataclass(frozen=True, slots=True)
class GateReceipt:
    """表示同一内容、catalog 与环境下可复用的 target PASS receipt。"""

    schema_version: int
    target: str
    change_id: str
    status: str
    cache_key: str
    catalog_version: str
    changed_files: tuple[str, ...]
    created_at: str
    artifact_path: str
    artifact_sha256: str
    checkout_fingerprint: str
    attribution_fingerprint: str
    plan_fingerprint: str
    command_fingerprint: str
    environment_fingerprint: str
    gate_input_fingerprint: str
    attribution: dict[str, Any]
    environment_bindings: dict[str, str]
    gate_inputs: dict[str, Any]


# 读取短小 Git identity；Git 不可用时返回空字符串。
def _git_value(repo_root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ['git', *args],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return ''
    return (proc.stdout or '').strip() if proc.returncode == 0 else ''


def _sha256_bytes(value: bytes) -> str:
    """计算原始字节的 SHA-256。"""
    return hashlib.sha256(value).hexdigest()


def _file_manifest(repo_root: Path) -> list[dict[str, str]]:
    """读取 worktree/untracked 当前内容、类型与 mode，返回稳定 manifest。"""
    try:
        proc = subprocess.run(
            ['git', 'ls-files', '-co', '--exclude-standard', '-z'],
            cwd=repo_root,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    result: list[dict[str, str]] = []
    for raw in sorted(part for part in proc.stdout.split(b'\0') if part):
        path = raw.decode('utf-8', errors='surrogateescape')
        absolute = repo_root / path
        try:
            if absolute.is_symlink():
                content = os.readlink(absolute).encode('utf-8', errors='surrogateescape')
                kind = 'symlink'
            elif absolute.is_file():
                content = absolute.read_bytes()
                kind = 'file'
            else:
                content = b'<deleted>'
                kind = 'missing'
        except OSError as exc:
            content = f'<unreadable:{exc.errno}>'.encode()
            kind = 'unreadable'
        try:
            mode = f'{absolute.lstat().st_mode & 0o7777:04o}'
        except OSError:
            mode = '0000'
        result.append({'path': path, 'kind': kind, 'mode': mode, 'sha256': _sha256_bytes(content)})
    return result


def checkout_content_fingerprint(repo_root: Path) -> str:
    """绑定 effective candidate，不把 HEAD/commit identity 混入内容 cache key。"""
    payload = {
        'indexTree': _git_value(repo_root, 'write-tree'),
        'files': _file_manifest(repo_root),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return _sha256_bytes(raw.encode('utf-8'))


def _stable_fingerprint(value: object) -> str:
    """计算结构化输入的稳定 SHA-256。"""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return _sha256_bytes(raw.encode('utf-8'))


def _cache_key_from_fingerprints(
    *,
    target: str,
    changed_files: list[str] | tuple[str, ...],
    checkout_fingerprint: str,
    attribution_fingerprint: str,
    plan_fingerprint: str,
    command_fingerprint: str,
    environment_fingerprint: str,
    gate_input_fingerprint: str,
) -> str:
    """只用 receipt 可审计字段构造 cache key，便于 commit 后重新证明。"""
    return _stable_fingerprint(
        {
            'target': target,
            'changedFiles': list(changed_files),
            'checkoutFingerprint': checkout_fingerprint,
            'attributionFingerprint': attribution_fingerprint,
            'catalogVersion': CATALOG_VERSION,
            'planFingerprint': plan_fingerprint,
            'commandFingerprint': command_fingerprint,
            'environmentFingerprint': environment_fingerprint,
            'gateInputFingerprint': gate_input_fingerprint,
        }
    )


def relevant_environment_fingerprint(environment: dict[str, str] | None = None) -> str:
    """只绑定会改变 Gate 解析或执行结果的环境字段。"""
    names = (
        'JAVA_HOME',
        'GRADLE_USER_HOME',
        'QUALITY_GATE_TIER',
        'FEIPI_REUSE_CPD_MODE',
        'QUALITY_REUSE_CPD_MODE',
        'BASE_URL',
        'SESSION_BROWSER_PYTHON',
    )
    values = {name: os.environ.get(name, '') for name in names}
    values.update(environment or {})
    values['pythonVersion'] = sys.version.split()[0]
    values['pythonExecutable'] = sys.executable
    return _stable_fingerprint(values)


# 按 target、内容状态、catalog 与关键环境生成 SHA-256 cache key。
def content_cache_key(
    target: str,
    changed_files: list[str] | tuple[str, ...],
    repo_root: Path,
    environment: dict[str, str] | None = None,
    *,
    attribution: dict[str, Any] | None = None,
    plan_fingerprint: str = '',
    command_fingerprint: str = '',
    gate_inputs: dict[str, Any] | None = None,
) -> str:
    """按 target、内容状态、catalog 与关键环境生成 SHA-256 cache key。"""
    return _cache_key_from_fingerprints(
        target=target,
        changed_files=changed_files,
        checkout_fingerprint=checkout_content_fingerprint(repo_root),
        attribution_fingerprint=_stable_fingerprint(
            {'changedFiles': list(changed_files), **(attribution or {})}
        ),
        plan_fingerprint=plan_fingerprint,
        command_fingerprint=command_fingerprint,
        environment_fingerprint=relevant_environment_fingerprint(environment),
        gate_input_fingerprint=_stable_fingerprint(gate_inputs or {}),
    )


# 返回 target receipt 的稳定路径。
def receipt_path(base_dir: Path, change_id: str, target: str) -> Path:
    """返回 target receipt 的稳定路径。"""
    return base_dir / change_id / f'quality-gate-receipt.{target}.json'


# 原子写入仅表示 PASS 的内容敏感 receipt。
def write_pass_receipt(
    base_dir: Path,
    *,
    target: str,
    change_id: str,
    changed_files: list[str] | tuple[str, ...],
    cache_key: str,
    artifact_path: str,
    repo_root: Path | None = None,
    attribution: dict[str, Any] | None = None,
    plan_fingerprint: str = '',
    command_fingerprint: str = '',
    environment: dict[str, str] | None = None,
    gate_inputs: dict[str, Any] | None = None,
) -> Path:
    """原子写入仅表示 PASS 的内容敏感 receipt。"""
    artifact = Path(artifact_path)
    artifact_sha256 = _sha256_bytes(artifact.read_bytes()) if artifact.is_file() else ''
    root = repo_root or Path.cwd()
    normalized_attribution = dict(attribution or {})
    normalized_environment = dict(environment or {})
    normalized_gate_inputs = dict(gate_inputs or {})
    checkout_fingerprint = checkout_content_fingerprint(root)
    attribution_fingerprint = _stable_fingerprint(
        {'changedFiles': list(changed_files), **normalized_attribution}
    )
    environment_fingerprint = relevant_environment_fingerprint(normalized_environment)
    gate_input_fingerprint = _stable_fingerprint(normalized_gate_inputs)
    expected_cache_key = _cache_key_from_fingerprints(
        target=target,
        changed_files=changed_files,
        checkout_fingerprint=checkout_fingerprint,
        attribution_fingerprint=attribution_fingerprint,
        plan_fingerprint=plan_fingerprint,
        command_fingerprint=command_fingerprint,
        environment_fingerprint=environment_fingerprint,
        gate_input_fingerprint=gate_input_fingerprint,
    )
    if cache_key != expected_cache_key:
        raise ValueError('receipt cache key does not match its bound inputs')
    receipt = GateReceipt(
        schema_version=2,
        target=target,
        change_id=change_id,
        status=PASS,
        cache_key=cache_key,
        catalog_version=CATALOG_VERSION,
        changed_files=tuple(changed_files),
        created_at=datetime.now(UTC).isoformat(),
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        checkout_fingerprint=checkout_fingerprint,
        attribution_fingerprint=attribution_fingerprint,
        plan_fingerprint=plan_fingerprint,
        command_fingerprint=command_fingerprint,
        environment_fingerprint=environment_fingerprint,
        gate_input_fingerprint=gate_input_fingerprint,
        attribution=normalized_attribution,
        environment_bindings=normalized_environment,
        gate_inputs=normalized_gate_inputs,
    )
    path = receipt_path(base_dir, change_id, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(asdict(receipt), ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)
    return path


# 读取 receipt；缺失、损坏或类型错误时 fail closed。
def read_receipt(path: Path) -> dict[str, Any] | None:
    """读取 receipt；缺失、损坏或类型错误时 fail closed。"""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# 仅当状态、cache key 与 catalog version 都一致时允许复用。
def reuse_decision(path: Path, cache_key: str) -> tuple[bool, str]:
    """返回 fail-closed receipt 复用决定及稳定原因码。"""
    data = read_receipt(path)
    if data is None:
        return False, 'missing-or-corrupt-receipt'
    if data.get('schema_version') != 2:
        return False, 'foreign-schema'
    if data.get('status') != PASS:
        return False, 'non-pass-receipt'
    if data.get('catalog_version') != CATALOG_VERSION:
        return False, 'catalog-mismatch'
    if data.get('cache_key') != cache_key:
        return False, 'input-fingerprint-mismatch'
    artifact_path = Path(str(data.get('artifact_path') or ''))
    try:
        artifact_bytes = artifact_path.read_bytes()
        artifact = json.loads(artifact_bytes.decode('utf-8'))
    except (OSError, json.JSONDecodeError):
        return False, 'artifact-missing-or-corrupt'
    if (
        not isinstance(artifact, dict)
        or artifact.get('status') != PASS
        or _sha256_bytes(artifact_bytes) != data.get('artifact_sha256')
    ):
        return False, 'artifact-status-or-hash-mismatch'
    expected_report_hash = artifact.get('reportHash')
    hash_payload = dict(artifact)
    hash_payload['reportHash'] = ''
    encoded = json.dumps(hash_payload, ensure_ascii=False, indent=2, sort_keys=True)
    if expected_report_hash != hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:12]:
        return False, 'report-hash-mismatch'
    required = artifact.get('requiredGates') or {}
    valid = (
        isinstance(required, dict)
        and bool(required)
        and all(str(status).upper() == PASS for status in required.values())
    )
    return (
        (True, 'all-bound-fingerprints-matched')
        if valid
        else (False, 'required-gate-status-invalid')
    )


def attest_pass_receipt(
    path: Path,
    repo_root: Path,
    *,
    changed_files: list[str] | tuple[str, ...],
) -> tuple[bool, str]:
    """在 commit 后重新计算 receipt、artifact 和全部输入绑定，禁止空壳 PASS。"""
    data = read_receipt(path)
    if data is None:
        return False, 'missing-or-corrupt-receipt'
    required_strings = (
        'target',
        'cache_key',
        'checkout_fingerprint',
        'attribution_fingerprint',
        'plan_fingerprint',
        'command_fingerprint',
        'environment_fingerprint',
        'gate_input_fingerprint',
    )
    if any(not str(data.get(name) or '') for name in required_strings):
        return False, 'missing-bound-fingerprint'
    expected_files = list(changed_files)
    if list(data.get('changed_files') or []) != expected_files:
        return False, 'changed-files-mismatch'
    attribution = data.get('attribution')
    environment = data.get('environment_bindings')
    gate_inputs = data.get('gate_inputs')
    if not isinstance(attribution, dict) or not isinstance(environment, dict):
        return False, 'missing-bound-inputs'
    if not isinstance(gate_inputs, dict) or gate_inputs.get('changedFiles') != expected_files:
        return False, 'gate-inputs-mismatch'
    checkout_fingerprint = checkout_content_fingerprint(repo_root)
    attribution_fingerprint = _stable_fingerprint({'changedFiles': expected_files, **attribution})
    environment_fingerprint = relevant_environment_fingerprint(environment)
    gate_input_fingerprint = _stable_fingerprint(gate_inputs)
    recomputed = _cache_key_from_fingerprints(
        target=str(data['target']),
        changed_files=expected_files,
        checkout_fingerprint=checkout_fingerprint,
        attribution_fingerprint=attribution_fingerprint,
        plan_fingerprint=str(data['plan_fingerprint']),
        command_fingerprint=str(data['command_fingerprint']),
        environment_fingerprint=environment_fingerprint,
        gate_input_fingerprint=gate_input_fingerprint,
    )
    if data.get('checkout_fingerprint') != checkout_fingerprint:
        return False, 'checkout-content-mismatch'
    if data.get('attribution_fingerprint') != attribution_fingerprint:
        return False, 'attribution-mismatch'
    if data.get('environment_fingerprint') != environment_fingerprint:
        return False, 'environment-mismatch'
    if data.get('gate_input_fingerprint') != gate_input_fingerprint:
        return False, 'gate-input-fingerprint-mismatch'
    valid, reason = reuse_decision(path, recomputed)
    if not valid:
        return False, reason
    artifact = read_receipt(Path(str(data.get('artifact_path') or '')))
    if artifact is None:
        return False, 'artifact-missing-or-corrupt'
    command_groups = artifact.get('commandGroups')
    if not isinstance(command_groups, list):
        return False, 'artifact-command-groups-missing'
    artifact_command_fingerprint = _stable_fingerprint(
        [group.get('command') for group in command_groups if isinstance(group, dict)]
    )
    if artifact.get('checkoutFingerprint') != checkout_fingerprint:
        return False, 'artifact-checkout-mismatch'
    if artifact.get('catalogVersion') != CATALOG_VERSION:
        return False, 'artifact-catalog-mismatch'
    if artifact.get('planFingerprint') != data.get('plan_fingerprint'):
        return False, 'artifact-plan-mismatch'
    if artifact_command_fingerprint != data.get('command_fingerprint'):
        return False, 'artifact-command-mismatch'
    return True, 'all-bound-fingerprints-attested'


def is_reusable_pass(path: Path, cache_key: str) -> bool:
    """仅当 receipt 与 artifact 全部字段可信时允许复用。"""
    return reuse_decision(path, cache_key)[0]
