"""负责验证 checkout 身份、运行记录、writer lease 与写授权契约；不负责状态持久化；由 Hook、Session CLI 和维护检查脚本调用。"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from scripts.agent_runtime.git_state import output as git_output
from scripts.agent_runtime.git_state import run as git
from scripts.agent_runtime.storage import load_json

RUNTIME_DIR_NAME = 'feipi-agent-runtime'
MANIFEST_PATH = Path('harness/agent-runtime.manifest.yaml')
REQUIRED_RUN_FIELDS = [
    'schemaVersion',
    'runId',
    'repoKey',
    'client',
    'taskId',
    'sessionId',
    'worktreeId',
    'checkoutRoot',
    'checkoutKind',
    'checkoutCreator',
    'gitCommonDir',
    'branch',
    'detached',
    'targetBranch',
    'primaryRepoRoot',
    'baseCommit',
    'headCommit',
    'initialDirtySnapshot',
    'changeAttribution',
    'changeId',
    'status',
    'allowedPaths',
    'forbiddenPaths',
    'writerLease',
    'hookActivation',
    'createdAt',
    'updatedAt',
]
CHECKOUT_KINDS = {'primary-checkout', 'linked-worktree'}
CHECKOUT_CREATORS = {'codex', 'claude', 'qoder', 'external', 'unknown'}
RUN_STATUSES = {
    'BOOTSTRAPPED',
    'READ_ONLY_READY',
    'ISOLATED_WRITER',
    'LOCAL_WRITER',
    'READ_ONLY_CONFLICT',
    'VALIDATING',
    'VALIDATED',
    'INTEGRATING',
    'INTEGRATED',
    'HANDOFF_REQUIRED',
    'BLOCKED',
}
ACTIVE_WRITER_STATUSES = {'ISOLATED_WRITER', 'LOCAL_WRITER'}
WRITABLE_READY_STATUSES = ACTIVE_WRITER_STATUSES
_FAILURE_TRANSITIONS = {'HANDOFF_REQUIRED', 'BLOCKED'}
ALLOWED_TRANSITIONS = {
    'BOOTSTRAPPED': ACTIVE_WRITER_STATUSES
    | {'READ_ONLY_READY', 'READ_ONLY_CONFLICT', 'VALIDATING'}
    | _FAILURE_TRANSITIONS,
    'READ_ONLY_READY': ACTIVE_WRITER_STATUSES
    | {'READ_ONLY_CONFLICT', 'VALIDATING'}
    | _FAILURE_TRANSITIONS,
    'ISOLATED_WRITER': {'READ_ONLY_READY', 'VALIDATING'} | _FAILURE_TRANSITIONS,
    'LOCAL_WRITER': {'READ_ONLY_READY', 'VALIDATING'} | _FAILURE_TRANSITIONS,
    'READ_ONLY_CONFLICT': ACTIVE_WRITER_STATUSES | {'VALIDATING'} | _FAILURE_TRANSITIONS,
    'VALIDATING': ACTIVE_WRITER_STATUSES | {'READ_ONLY_READY', 'VALIDATED'} | _FAILURE_TRANSITIONS,
    'VALIDATED': ACTIVE_WRITER_STATUSES
    | {'VALIDATING', 'READ_ONLY_CONFLICT', 'INTEGRATING'}
    | _FAILURE_TRANSITIONS,
    'INTEGRATING': {'INTEGRATED'} | _FAILURE_TRANSITIONS,
    'INTEGRATED': set(),
    'HANDOFF_REQUIRED': ACTIVE_WRITER_STATUSES
    | {'VALIDATING', 'READ_ONLY_CONFLICT', 'INTEGRATING', 'BLOCKED'},
    'BLOCKED': {'VALIDATING'},
}


class PrimarySessionValidationError(ValueError):
    """表示 checkout、manifest 或运行授权事实无法满足 fail-closed 契约。"""

    pass


@dataclass(frozen=True)
class Collision:
    """描述两个活动运行的 writer 冲突及双方 run 身份，供 doctor 报告。"""

    kind: str
    message: str
    first_run_id: str
    second_run_id: str


@dataclass(frozen=True)
class PrimaryHeadSnapshot:
    """保存两次一致读取证明的 primary 分支与 HEAD，作为 worktree 基线。"""

    primary_repo_root: str
    branch: str
    head_commit: str


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def snapshot_path_states(
    repo_root: Path, paths: list[str] | tuple[str, ...] | set[str]
) -> dict[str, dict[str, Any]]:
    """对初始 dirty 路径记录类型、大小和内容摘要，拒绝逃逸与特殊文件。"""
    root = _absolute_path(repo_root)
    states: dict[str, dict[str, Any]] = {}
    for raw_path in sorted(set(paths)):
        normalized = raw_path.replace('\\', '/').strip('/')
        relative = Path(normalized)
        if not normalized or relative.is_absolute() or '..' in relative.parts:
            raise PrimarySessionValidationError(
                f'dirty snapshot path is not repository-relative: {raw_path!r}'
            )
        candidate = root / relative
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            states[normalized] = {'exists': False, 'size': None, 'sha256': None}
            continue
        if stat.S_ISLNK(metadata.st_mode):
            payload = os.readlink(candidate).encode('utf-8', errors='surrogateescape')
        elif stat.S_ISREG(metadata.st_mode):
            digest = hashlib.sha256()
            with candidate.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
            states[normalized] = {
                'exists': True,
                'size': metadata.st_size,
                'sha256': digest.hexdigest(),
            }
            continue
        else:
            raise PrimarySessionValidationError(
                f'dirty snapshot path is not a regular file or symlink: {raw_path!r}'
            )
        states[normalized] = {
            'exists': True,
            'size': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest(),
        }
    return states


def _current_user_id() -> int | None:
    getter = getattr(os, 'geteuid', None) or getattr(os, 'getuid', None)
    return getter() if getter is not None else None


def _reject_symlink_components(path: Path) -> None:
    for component in [*reversed(path.parents), path]:
        if component == Path(component.anchor):
            continue
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise PrimarySessionValidationError(f'runtime path contains symbolic link: {component}')


def ensure_private_directory(path: Path, *, root: Path | None = None) -> Path:
    """创建并复核属主、0700 权限与 inode 不变的运行时目录，拒绝符号链接。"""
    target = _absolute_path(path)
    boundary = _absolute_path(root) if root is not None else target
    try:
        target.relative_to(boundary)
    except ValueError as exc:
        raise PrimarySessionValidationError(f'runtime directory escapes root: {target}') from exc
    if root is not None and boundary != target:
        ensure_private_directory(boundary)
    _reject_symlink_components(target)
    missing: list[Path] = []
    candidate = target
    while not os.path.lexists(candidate):
        missing.append(candidate)
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=448)
        except FileExistsError:
            pass
        _reject_symlink_components(directory)
    try:
        metadata = target.lstat()
    except FileNotFoundError as exc:
        raise PrimarySessionValidationError(
            f'runtime directory could not be created: {target}'
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise PrimarySessionValidationError(f'runtime path is not a private directory: {target}')
    current_user = _current_user_id()
    if current_user is not None and metadata.st_uid != current_user:
        raise PrimarySessionValidationError(
            f'runtime directory is not owned by current user: {target}'
        )
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise PrimarySessionValidationError(
            f'runtime directory cannot be opened safely: {target}'
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or opened.st_ino != metadata.st_ino
            or opened.st_dev != metadata.st_dev
        ):
            raise PrimarySessionValidationError(
                f'runtime directory changed during validation: {target}'
            )
        if current_user is not None and opened.st_uid != current_user:
            raise PrimarySessionValidationError(
                f'runtime directory is not owned by current user: {target}'
            )
        os.fchmod(descriptor, 0o700)
        if stat.S_IMODE(os.fstat(descriptor).st_mode) != 448:
            raise PrimarySessionValidationError(
                f'runtime directory permissions are not 0700: {target}'
            )
    finally:
        os.close(descriptor)
    return target


def resolve_checkout_root(repo_root: Path) -> Path:
    """解析真实 Git checkout 根；路径不存在或查询失败时关闭失败。"""
    try:
        raw = git_output(_absolute_path(repo_root), 'rev-parse', '--show-toplevel')
        return Path(raw).expanduser().resolve(strict=True)
    except Exception as exc:
        raise PrimarySessionValidationError(
            f'cannot resolve Git checkout root: {repo_root}'
        ) from exc


def resolve_git_common_dir(repo_root: Path) -> Path:
    """解析并严格规范化 Git common-dir，用于关联 primary 与 linked worktree。"""
    checkout_root = resolve_checkout_root(repo_root)
    try:
        raw = git_output(checkout_root, 'rev-parse', '--git-common-dir')
        common_dir = Path(raw)
        if not common_dir.is_absolute():
            common_dir = checkout_root / common_dir
        return common_dir.resolve(strict=True)
    except Exception as exc:
        raise PrimarySessionValidationError(f'cannot resolve Git common-dir: {repo_root}') from exc


def _listed_worktree_roots(repo_root: Path) -> list[Path]:
    checkout_root = resolve_checkout_root(repo_root)
    try:
        listing = git_output(checkout_root, 'worktree', 'list', '--porcelain', '-z')
        roots = [
            Path(field.removeprefix('worktree ')).expanduser().resolve()
            for field in listing.split('\x00')
            if field.startswith('worktree ')
        ]
    except Exception as exc:
        raise PrimarySessionValidationError(
            f'cannot read Git worktree metadata: {repo_root}'
        ) from exc
    if not roots or checkout_root not in roots:
        raise PrimarySessionValidationError(
            f'checkout is absent from Git worktree metadata: {checkout_root}'
        )
    return roots


def resolve_primary_repo_root(repo_root: Path) -> Path:
    """从 Git worktree 元数据选择 primary checkout，并复核 common-dir 一致。"""
    checkout_root = resolve_checkout_root(repo_root)
    roots = _listed_worktree_roots(checkout_root)
    primary_root = roots[0]
    if resolve_git_common_dir(primary_root) != resolve_git_common_dir(checkout_root):
        raise PrimarySessionValidationError(
            'primary checkout and current checkout have different Git common-dir'
        )
    return primary_root


def capture_primary_head_snapshot(repo_root: Path) -> PrimaryHeadSnapshot:
    """连续读取 primary 分支与 HEAD；detached 或竞态变化时拒绝作为创建基线。"""
    primary_root = resolve_primary_repo_root(repo_root)
    first_branch = _current_branch(primary_root)
    first_head = git_output(primary_root, 'rev-parse', 'HEAD')
    second_branch = _current_branch(primary_root)
    second_head = git_output(primary_root, 'rev-parse', 'HEAD')
    if not first_branch or not second_branch:
        raise PrimarySessionValidationError(
            'PRIMARY_HEAD_DETACHED: primary checkout must be on a named branch'
        )
    if (first_branch, first_head) != (second_branch, second_head):
        raise PrimarySessionValidationError(
            'PRIMARY_HEAD_RACE: primary branch or HEAD changed while capturing snapshot'
        )
    return PrimaryHeadSnapshot(
        primary_repo_root=str(primary_root), branch=first_branch, head_commit=first_head
    )


def resolve_repo_key(repo_root: Path) -> str:
    """根据规范化 Git common-dir 生成稳定仓库键，隔离不同仓库的运行时状态。"""
    common_dir = resolve_git_common_dir(repo_root)
    return hashlib.sha256(str(common_dir).encode('utf-8')).hexdigest()


def stable_worktree_id(repo_key: str, checkout_root: str | Path) -> str:
    """根据仓库键与真实 checkout 路径生成稳定 worktree 身份。"""
    root = Path(checkout_root).expanduser().resolve(strict=True)
    digest = hashlib.sha256(f'{repo_key}\x00{root}'.encode()).hexdigest()
    return f'checkout-{digest[:24]}'


def resolve_checkout_identity(
    repo_root: Path, *, checkout_creator: str = 'unknown', base_commit: str = ''
) -> dict[str, Any]:
    """采集 checkout、primary、分支、基线和祖先关系的权威身份事实。"""
    checkout_root = resolve_checkout_root(repo_root)
    common_dir = resolve_git_common_dir(checkout_root)
    primary_root = resolve_primary_repo_root(checkout_root)
    repo_key = resolve_repo_key(checkout_root)
    branch = _current_branch(checkout_root)
    head = git_output(checkout_root, 'rev-parse', 'HEAD')
    creator = checkout_creator if checkout_creator in CHECKOUT_CREATORS else 'unknown'
    base = str(base_commit or '').strip()
    base_exists = (
        bool(base)
        and git(checkout_root, 'cat-file', '-e', f'{base}^{{commit}}', check=False).returncode == 0
    )
    base_is_ancestor = None
    if base_exists:
        base_is_ancestor = (
            git(checkout_root, 'merge-base', '--is-ancestor', base, 'HEAD', check=False).returncode
            == 0
        )
    return {
        'repoKey': repo_key,
        'checkoutRoot': str(checkout_root),
        'primaryRepoRoot': str(primary_root),
        'gitCommonDir': str(common_dir),
        'worktreeId': stable_worktree_id(repo_key, checkout_root),
        'checkoutKind': 'primary-checkout' if checkout_root == primary_root else 'linked-worktree',
        'checkoutCreator': creator,
        'branch': branch,
        'detached': not bool(branch),
        'headCommit': head,
        'baseCommit': base,
        'baseCommitExists': base_exists,
        'baseIsAncestorOfHead': base_is_ancestor,
    }


def validate_checkout_record(
    repo_root: Path, record: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """对照当前 Git 元数据验证运行记录中的 checkout 身份并返回全部差异。"""
    facts = resolve_checkout_identity(
        repo_root,
        checkout_creator=str(record.get('checkoutCreator') or 'unknown'),
        base_commit=str(record.get('baseCommit') or ''),
    )
    errors: list[str] = []
    recorded_root = Path(str(record.get('checkoutRoot') or '')).expanduser().resolve()
    if recorded_root != Path(facts['checkoutRoot']):
        errors.append('cwd realpath does not match run checkout root')
    if record.get('checkoutRoot') and Path(
        str(record['checkoutRoot'])
    ).expanduser().resolve() != Path(facts['checkoutRoot']):
        errors.append('run checkoutRoot does not match current checkout')
    creator = str(record.get('checkoutCreator') or 'unknown')
    if creator not in CHECKOUT_CREATORS:
        errors.append('run checkoutCreator is invalid')
    new_identity = bool(record.get('repoKey'))
    if new_identity:
        for field in (
            'repoKey',
            'gitCommonDir',
            'worktreeId',
            'checkoutKind',
            'checkoutRoot',
            'checkoutCreator',
            'primaryRepoRoot',
        ):
            if field not in record:
                errors.append(f'run checkout identity is missing {field}')
            elif str(record.get(field) or '') != str(facts[field]):
                errors.append(f'run {field} does not match current checkout')
    return (facts, errors)


def resolve_runtime_root(repo_root: Path) -> Path:
    """按环境覆盖或系统临时目录解析仓库隔离的属主私有 Runtime 根。"""
    override = os.environ.get('FEIPI_AGENT_RUNTIME_ROOT', '').strip()
    if override:
        return ensure_private_directory(Path(override))
    configured_temp = os.environ.get('TMPDIR', '').strip()
    temp_root = Path(configured_temp or tempfile.gettempdir()).expanduser().resolve(strict=True)
    runtime_base = ensure_private_directory(temp_root / RUNTIME_DIR_NAME)
    return ensure_private_directory(runtime_base / resolve_repo_key(repo_root), root=runtime_base)


def load_yaml(path: Path) -> dict[str, Any]:
    """使用仓库声明的 PyYAML 解析 manifest；缺失、语法错误或非 mapping 都关闭失败。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PrimarySessionValidationError(f"manifest not found: {path}") from exc
    except Exception as exc:
        raise PrimarySessionValidationError(f"manifest parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise PrimarySessionValidationError("manifest root must be a mapping")
    return data


def _required(mapping: dict[str, Any], field: str) -> Any:
    if field not in mapping:
        raise PrimarySessionValidationError(f'missing required run field: {field}')
    return mapping[field]


def _path_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PrimarySessionValidationError('allowedPaths and forbiddenPaths must be string lists')
    return {item.rstrip('/') for item in value}


def validate_status_transition(from_status: str, to_status: str) -> None:
    """验证 Session 状态迁移白名单，未知状态和越级迁移均关闭失败。"""
    if from_status not in RUN_STATUSES:
        raise PrimarySessionValidationError(f'unknown source status: {from_status}')
    if to_status not in RUN_STATUSES:
        raise PrimarySessionValidationError(f'unknown target status: {to_status}')
    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise PrimarySessionValidationError(
            f'illegal status transition: {from_status} -> {to_status}'
        )


def validate_run_record(record: dict[str, Any]) -> None:
    """验证运行记录字段、writer 状态、lease fencing 和 Hook 激活不变量。"""
    if not isinstance(record, dict):
        raise PrimarySessionValidationError('run record must be a mapping')
    for field in REQUIRED_RUN_FIELDS:
        _required(record, field)
    if record['status'] not in RUN_STATUSES:
        raise PrimarySessionValidationError(f"invalid run status: {record['status']}")
    if record['checkoutKind'] not in CHECKOUT_KINDS:
        raise PrimarySessionValidationError(f"invalid checkoutKind: {record['checkoutKind']}")
    if record['checkoutCreator'] not in CHECKOUT_CREATORS:
        raise PrimarySessionValidationError(f"invalid checkoutCreator: {record['checkoutCreator']}")
    if not isinstance(record['detached'], bool):
        raise PrimarySessionValidationError('detached must be boolean')
    if not isinstance(record['initialDirtySnapshot'], dict):
        raise PrimarySessionValidationError('initialDirtySnapshot must be a mapping')
    if not isinstance(record['changeAttribution'], dict):
        raise PrimarySessionValidationError('changeAttribution must be a mapping')
    _path_set(record['allowedPaths'])
    _path_set(record['forbiddenPaths'])
    if record['status'] in {'ISOLATED_WRITER', 'LOCAL_WRITER'}:
        expected_status = (
            'LOCAL_WRITER'
            if record.get('checkoutKind') == 'primary-checkout'
            else 'ISOLATED_WRITER'
        )
        if record['status'] != expected_status:
            raise PrimarySessionValidationError(
                f"{record.get('checkoutKind')} requires {expected_status} status"
            )
    writer_lease = record.get('writerLease')
    if not isinstance(writer_lease, dict):
        raise PrimarySessionValidationError('writerLease must be a mapping')
    if record['status'] in ACTIVE_WRITER_STATUSES and (not writer_lease):
        raise PrimarySessionValidationError('active writer requires writerLease')
    if writer_lease:
        if not str(record.get('sessionId', '')).strip():
            raise PrimarySessionValidationError('writer lease holder requires sessionId')
        for field in ('leaseId', 'holderRunId', 'holderSessionId', 'epoch', 'fencingToken'):
            if not writer_lease.get(field):
                raise PrimarySessionValidationError(
                    f'writer lease holder requires writerLease.{field}'
                )
        try:
            if int(writer_lease['epoch']) <= 0:
                raise PrimarySessionValidationError(
                    'writer lease holder requires positive writerLease.epoch'
                )
        except (TypeError, ValueError) as exc:
            raise PrimarySessionValidationError(
                'writer lease holder requires integer writerLease.epoch'
            ) from exc
        if writer_lease.get('holderRunId') != record.get('runId'):
            raise PrimarySessionValidationError('writerLease holderRunId must match runId')
        if writer_lease.get('holderSessionId') != record.get('sessionId'):
            raise PrimarySessionValidationError('writerLease holderSessionId must match sessionId')
        hook_activation = record.get('hookActivation')
        if not isinstance(hook_activation, dict):
            raise PrimarySessionValidationError(
                'writer lease holder requires hookActivation mapping'
            )
        if (
            record['status'] in WRITABLE_READY_STATUSES
            and hook_activation.get('confirmed') is not True
        ):
            raise PrimarySessionValidationError(
                'hook activation must be confirmed before writable-ready status'
            )


def _is_active_writer(record: dict[str, Any]) -> bool:
    return record.get('status') in ACTIVE_WRITER_STATUSES


def validate_run_collisions(records: list[dict[str, Any]]) -> list[Collision]:
    """检测同一 worktree 的多个活动 writer，返回可审计冲突而不自行修复。"""
    for record in records:
        validate_run_record(record)
    collisions: list[Collision] = []
    active = [record for record in records if _is_active_writer(record)]
    for i, first in enumerate(active):
        for second in active[i + 1 :]:
            first_id = str(first['runId'])
            second_id = str(second['runId'])
            first_root = str(first.get('checkoutRoot') or '')
            second_root = str(second.get('checkoutRoot') or '')
            if (
                first_root
                and second_root
                and (
                    Path(first_root).expanduser().resolve()
                    == Path(second_root).expanduser().resolve()
                )
            ):
                collisions.append(
                    Collision(
                        'same-worktree-writer',
                        'same worktree second writer is blocked',
                        first_id,
                        second_id,
                    )
                )
    return collisions


def validate_manifest(data: dict[str, Any]) -> None:
    """验证 manifest 与代码中的字段、状态机和 Runtime 根策略完全一致。"""
    if data.get('schemaVersion', data.get('version')) != 1:
        raise PrimarySessionValidationError('schemaVersion/version must be 1')
    primary = data.get('primary_sessions')
    if not isinstance(primary, dict):
        raise PrimarySessionValidationError('missing primary_sessions mapping')
    if primary.get('writable_isolation') != 'checkout-writer-lease':
        raise PrimarySessionValidationError(
            'primary_sessions.writable_isolation must be checkout-writer-lease'
        )
    if primary.get('same_worktree_max_writers') != 1:
        raise PrimarySessionValidationError('primary_sessions.same_worktree_max_writers must be 1')
    if primary.get('read_only_sessions_allowed') is not True:
        raise PrimarySessionValidationError(
            'primary_sessions.read_only_sessions_allowed must be true'
        )
    run_record = data.get('run_record')
    if not isinstance(run_record, dict):
        raise PrimarySessionValidationError('missing run_record mapping')
    required = run_record.get('required_fields')
    if required != REQUIRED_RUN_FIELDS:
        raise PrimarySessionValidationError('run_record.required_fields does not match contract')
    if set(run_record.get('statuses', [])) != RUN_STATUSES:
        raise PrimarySessionValidationError('run_record.statuses does not match contract')
    transitions = data.get('status_machine', {}).get('transitions')
    if not isinstance(transitions, dict):
        raise PrimarySessionValidationError('missing status_machine.transitions mapping')
    manifest_transitions = {str(k): set(v or []) for k, v in transitions.items()}
    if manifest_transitions != ALLOWED_TRANSITIONS:
        raise PrimarySessionValidationError('status_machine.transitions does not match validator')
    runtime_root = data.get('runtime_root')
    if not isinstance(runtime_root, dict):
        raise PrimarySessionValidationError('missing runtime_root mapping')
    order = runtime_root.get('resolution_order')
    expected = ['FEIPI_AGENT_RUNTIME_ROOT', 'TMPDIR-or-system-temp/feipi-agent-runtime/<repo-key>']
    if order != expected:
        raise PrimarySessionValidationError('runtime_root.resolution_order does not match contract')


def validate_manifest_file(path: Path) -> None:
    """解析并验证指定 Session manifest，缺失或结构错误时关闭失败。"""
    validate_manifest(load_yaml(path))


RUN_WRITE_OK_STATUSES = ACTIVE_WRITER_STATUSES


def _load_json_file(path: Path) -> dict[str, Any]:
    """复用 owner/inode/no-follow JSON 读取；不可信 Registry 文件按缺失处理。"""
    try:
        return load_json(path, {})
    except (OSError, ValueError):
        return {}


def _run_record_paths(repo_root: Path) -> list[Path]:
    runs_dir = resolve_runtime_root(repo_root) / 'runs'
    index = _load_json_file(runs_dir / 'index.json')
    ids = [str(item) for item in index.get('runs', [])]
    paths = [runs_dir / f'{run_id}.json' for run_id in ids]
    if not paths and runs_dir.is_dir():
        paths = sorted(runs_dir.glob('*.json'))
    return paths


def load_run_record(repo_root: Path, run_id: str) -> dict[str, Any] | None:
    """从仓库隔离的 Runtime 根读取指定 run；缺失或不安全文件返回空值。"""
    if not run_id:
        return None
    path = resolve_runtime_root(repo_root) / 'runs' / f'{run_id}.json'
    record = _load_json_file(path)
    return record or None


def load_checkout_writer_lease(repo_root: Path, worktree_id: str) -> dict[str, Any] | None:
    """仅在 worktree 身份匹配当前 checkout 时读取权威 writer lease。"""
    expected = stable_worktree_id(resolve_repo_key(repo_root), resolve_checkout_root(repo_root))
    if worktree_id != expected:
        return None
    lease_path = resolve_runtime_root(repo_root) / 'writer-leases' / f'{worktree_id}.json'
    lease = _load_json_file(lease_path)
    return lease or None


def validate_writer_lease_fence(repo_root: Path, record: dict[str, Any]) -> list[str]:
    """逐字段对照运行记录与权威 lease，报告 epoch、token 和 owner 差异。"""
    embedded = record.get('writerLease')
    if not isinstance(embedded, dict) or not embedded:
        return ['writer lease is missing from run record']
    lease = load_checkout_writer_lease(repo_root, str(record.get('worktreeId') or ''))
    if not lease:
        return ['authoritative checkout writer lease is missing']
    errors: list[str] = []
    expected_pairs = {
        'leaseId': record.get('writerLease', {}).get('leaseId'),
        'holderRunId': record.get('runId'),
        'holderSessionId': record.get('sessionId'),
        'repoKey': record.get('repoKey'),
        'worktreeId': record.get('worktreeId'),
        'checkoutRoot': record.get('checkoutRoot'),
        'epoch': embedded.get('epoch'),
        'fencingToken': embedded.get('fencingToken'),
    }
    for field, expected in expected_pairs.items():
        if not expected or lease.get(field) != expected:
            errors.append(f'writer lease {field} does not match run fencing proof')
    try:
        if int(lease.get('epoch') or 0) <= 0:
            errors.append('writer lease epoch must be positive')
    except (TypeError, ValueError):
        errors.append('writer lease epoch must be an integer')
    if lease.get('state') != 'ACTIVE':
        errors.append('writer lease is not active')
    return errors


def resolve_bound_run_record(
    repo_root: Path, client: str, session_id: str = '', run_id: str = ''
) -> dict[str, Any] | None:
    """按 client、Session、run 与 checkout 身份解析唯一绑定记录；歧义时返回空值。"""
    try:
        checkout_root = resolve_checkout_root(repo_root)
        repo_key = resolve_repo_key(checkout_root)
    except PrimarySessionValidationError:
        return None

    def matches(record: dict[str, Any]) -> bool:
        """判定候选运行是否与当前 client、Session 和 checkout 身份完全绑定。"""
        if client and record.get('client') != client:
            return False
        if session_id and record.get('sessionId') != session_id:
            return False
        try:
            recorded_root = Path(str(record.get('checkoutRoot') or '')).expanduser().resolve()
        except OSError:
            return False
        if recorded_root != checkout_root:
            return False
        recorded_key = str(record.get('repoKey') or '')
        if recorded_key and recorded_key != repo_key:
            return False
        if recorded_key and record.get('worktreeId') != stable_worktree_id(repo_key, checkout_root):
            return False
        return True

    if run_id:
        record = load_run_record(checkout_root, run_id)
        return record if record and matches(record) else None
    if not session_id:
        return None
    matches_by_session: list[dict[str, Any]] = []
    for path in _run_record_paths(checkout_root):
        record = _load_json_file(path)
        if matches(record):
            matches_by_session.append(record)
    if len(matches_by_session) != 1:
        return None
    return matches_by_session[0]


def _current_branch(repo_root: Path) -> str:
    try:
        return git_output(repo_root, 'branch', '--show-current')
    except Exception:
        return ''


def _path_matches(rel_path: str, scopes: list[str], *, allow_wildcard: bool) -> bool:
    rel = rel_path.strip('/')
    for scope in scopes:
        item = str(scope).strip('/')
        if allow_wildcard and item in {'', '.', '*', '**'}:
            return True
        if rel == item or rel.startswith(f'{item}/'):
            return True
    return False


def validate_run_write_authorization(
    repo_root: Path,
    *,
    client: str,
    session_id: str,
    run_id: str = '',
    change_id: str = '',
    candidate_paths: list[str] | None = None,
) -> tuple[bool, list[str], dict[str, Any] | None]:
    """综合运行状态、checkout、lease fencing、change 与路径范围判定写授权。"""
    record = resolve_bound_run_record(repo_root, client, session_id, run_id)
    if not record:
        if run_id or session_id:
            return (False, ['bound writable run not found for client/session/run'], None)
        return (
            False,
            ['legacy session has no bound writable run; mutating operation blocked'],
            None,
        )
    errors: list[str] = []
    try:
        validate_run_record(record)
    except PrimarySessionValidationError as exc:
        errors.append(str(exc))
    try:
        checkout_facts, checkout_errors = validate_checkout_record(repo_root, record)
        errors.extend(checkout_errors)
        worktree = Path(checkout_facts['checkoutRoot'])
    except PrimarySessionValidationError as exc:
        errors.append(str(exc))
        worktree = Path(str(record.get('checkoutRoot', ''))).resolve()
    if record.get('sessionId') != session_id:
        errors.append('session id is not bound to run')
    if record.get('status') not in RUN_WRITE_OK_STATUSES:
        errors.append('run status does not allow writes')
    errors.extend(validate_writer_lease_fence(worktree, record))
    if change_id and record.get('changeId') != change_id:
        errors.append('current change id does not match run record')
    cwd = Path(repo_root).expanduser().resolve()
    for raw_path in candidate_paths or []:
        path = Path(raw_path)
        try:
            rel = str(
                (path if path.is_absolute() else cwd / path)
                .resolve()
                .relative_to(worktree)
                .as_posix()
            )
        except Exception:
            errors.append(f'target path is outside run worktree: {raw_path}')
            continue
        if not _path_matches(rel, list(record.get('allowedPaths') or []), allow_wildcard=True):
            errors.append(f'target path is outside allowedPaths: {rel}')
        if _path_matches(rel, list(record.get('forbiddenPaths') or []), allow_wildcard=False):
            errors.append(f'target path is under forbiddenPaths: {rel}')
    return (not errors, errors, record)
