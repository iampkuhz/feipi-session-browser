"""负责平台无关的唯一 Worktree Change lifecycle 编排。

所有 Start/Stop、candidate、Attempt、commit 和 ff-only integration 都由本模块编排。
平台 Hook 与旧 CLI 只能做 payload/argv 适配，不得复制 Git、Gate、锁或恢复逻辑。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.agent_runtime.git_state import run as git
from scripts.agent_runtime.session.common import audit_run
from scripts.agent_runtime.session.contract import resolve_runtime_root
from scripts.agent_runtime.session.errors import SessionctlError
from scripts.agent_runtime.session.registry import Registry
from scripts.agent_runtime.storage import utc_now
from scripts.gates import executor as gate_executor
from scripts.gates import report as gate_report
from scripts.gates.cli import _with_preflight, create_plan, run_service

from .candidate import (
    CandidateError,
    PreparedCandidate,
    collect_manifest,
    prepare_candidate,
    validate_scope,
)
from .fixture import (
    FixtureError,
    FixtureIdentityError,
    FixtureSupervisor,
    FixtureUnavailableError,
)
from .model import (
    ChangeCAS,
    CompareAndSetError,
    LifecycleModelError,
    attempt_fingerprint,
    current_change,
    new_session,
)
from .protocol import (
    BUSY_RETRYABLE,
    CAPABILITY_RETRYABLE,
    COMMITTED_HANDOFF,
    INTERNAL_ERROR,
    PASS,
    REPAIR_REQUIRED,
    TERMINAL_BLOCKED,
    LifecycleError,
    RootFailure,
    classify_gate_failures,
    compact_payload,
    write_artifact,
)
from .runtime import (
    BoundedMetadataLock,
    LockBusyError,
    LockInvariantError,
    run_bounded,
)
from .store import (
    ChangeStore,
    ChangeStoreBusyError,
    ChangeStoreCorruptionError,
    ChangeStoreError,
)


@dataclass(frozen=True, slots=True)
class GateInputs:
    """绑定 Attempt 的 plan/command/environment 完整指纹。"""

    plan_fingerprint: str
    command_fingerprint: str
    environment_fingerprint: str
    planned_child_count: int
    requires_fixture: bool = False


START_ENFORCED = 'START_ENFORCED'
START_NOT_ENFORCED = 'START_NOT_ENFORCED'
ADOPT_CONFIRMATION = 'I_CONFIRM_ADOPT_CURRENT'


def _hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _cas(change: Mapping[str, Any]) -> ChangeCAS:
    return ChangeCAS(
        expected_state=str(change['state']),
        expected_version=int(change['stateVersion']),
        expected_candidate_tree=str(change.get('candidateTree') or ''),
        expected_attempt_id=str(change.get('currentAttemptId') or ''),
    )


def _safe_identifier(value: str) -> str:
    normalized = ''.join(char if char.isalnum() or char in '._-' else '-' for char in value)
    normalized = normalized.strip('.-')[:96]
    return normalized or 'change'


def _git_head(repo: Path) -> str:
    return git(repo, 'rev-parse', 'HEAD', timeout=2).stdout.strip()


def _git_tree(repo: Path, revision: str = 'HEAD') -> str:
    return git(repo, 'rev-parse', f'{revision}^{{tree}}', timeout=2).stdout.strip()


def _manifest_hash(paths: Iterable[str]) -> str:
    """对人工确认的 exact manifest 生成稳定审计哈希。"""
    return _hash(sorted(set(paths)))


def _start_payload(
    record: Mapping[str, Any], *, activation_source: str, capability: str
) -> dict[str, Any]:
    """只从 bootstrap baseline 构造 Start attestation，不重新解释 Git 状态。"""
    initial = record.get('initialDirtySnapshot')
    if not isinstance(initial, Mapping):
        raise SessionctlError('begin-change requires an initial dirty snapshot')
    return {
        'status': 'ATTESTED' if capability == START_ENFORCED else START_NOT_ENFORCED,
        'capability': capability,
        'repoKey': record.get('repoKey', ''),
        'worktreeId': record.get('worktreeId', ''),
        'checkoutRoot': record.get('checkoutRoot', ''),
        'checkoutKind': record.get('checkoutKind', ''),
        'detached': bool(record.get('detached')),
        'client': record.get('client', ''),
        'sessionId': record.get('sessionId', ''),
        'runId': record.get('runId', ''),
        'baseCommit': record.get('baseCommit', ''),
        'targetBranch': record.get('targetBranch', ''),
        'targetHead': record.get('targetHeadAtBootstrap', ''),
        'initialDirtySnapshot': dict(initial),
        'allowedPaths': list(record.get('allowedPaths') or []),
        'forbiddenPaths': list(record.get('forbiddenPaths') or []),
        'startedAt': utc_now(),
        'activationEvidence': activation_source,
    }


def attest_run_start(
    repo_root: Path,
    run_id: str,
    *,
    activation_source: str,
    capability: str = START_ENFORCED,
) -> dict[str, Any]:
    """在 mutation 前保存唯一 Start baseline；late dirty 必须显式 adopt。"""
    repo = Path(repo_root).resolve()
    if capability not in {START_ENFORCED, START_NOT_ENFORCED}:
        raise SessionctlError(f'unsupported start capability: {capability}')
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(run_id)
        existing = record.get('changeBegin')
        if isinstance(existing, Mapping):
            if (
                existing.get('runId') != run_id
                or existing.get('checkoutRoot') != record.get('checkoutRoot')
                or existing.get('baseCommit') != record.get('baseCommit')
            ):
                raise SessionctlError('begin-change identity conflicts with existing attestation')
            return record
        initial = record.get('initialDirtySnapshot')
        if not isinstance(initial, Mapping):
            raise SessionctlError('begin-change has no initial baseline')
        base = str(record.get('baseCommit') or '')
        if _git_head(repo) != base:
            raise SessionctlError('ADOPT_REQUIRED: HEAD changed before begin-change')
        manifest = collect_manifest(repo)
        initial_paths = sorted(
            set(list(initial.get('tracked') or []) + list(initial.get('untracked') or []))
        )
        if list(manifest.paths) != initial_paths:
            raise SessionctlError(
                'ADOPT_REQUIRED: late begin-change found pre-existing dirty content'
            )
        begin = _start_payload(
            record,
            activation_source=activation_source,
            capability=capability,
        )
        record['changeBegin'] = begin
        record['updatedAt'] = utc_now()
        audit_run(
            registry,
            record,
            'CHANGE_BEGIN_ATTESTED' if capability == START_ENFORCED else START_NOT_ENFORCED,
            capability=capability,
            activationEvidence=activation_source,
        )
        registry.save_run(record)
        return record


def adopt_current(
    repo_root: Path,
    run_id: str,
    *,
    base_commit: str,
    exact_files: Iterable[str],
    confirmation: str,
) -> dict[str, Any]:
    """显式接管 late dirty checkout，并绑定 base、scope 与 exact manifest。"""
    repo = Path(repo_root).resolve()
    expected = sorted({str(path) for path in exact_files})
    if confirmation != ADOPT_CONFIRMATION:
        raise SessionctlError('adopt-current requires explicit user confirmation')
    if not expected:
        raise SessionctlError('adopt-current requires an exact non-empty manifest')
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(run_id)
        if base_commit != str(record.get('baseCommit') or ''):
            raise SessionctlError('adopt-current base does not match run base')
        if _git_head(repo) != base_commit:
            raise SessionctlError('adopt-current HEAD does not match confirmed base')
        manifest = collect_manifest(repo)
        if list(manifest.paths) != expected:
            raise SessionctlError(
                'adopt-current exact manifest mismatch: '
                f'expected={expected}, actual={list(manifest.paths)}'
            )
        try:
            validate_scope(manifest, record)
        except CandidateError as exc:
            raise SessionctlError(f'adopt-current {exc.code}: {exc}') from exc
        begin = _start_payload(
            record,
            activation_source='explicit-adopt-current',
            capability=START_ENFORCED,
        )
        begin.update(
            {
                'status': 'ATTESTED',
                'adopted': True,
                'adoptedFiles': expected,
                'adoptedFilesHash': _manifest_hash(expected),
                'userConfirmation': confirmation,
            }
        )
        record['changeBegin'] = begin
        record['changeAttribution'] = {
            'baseline': 'explicit-adopt-current',
            'preexistingChangesAttributedToRun': True,
            'requiresHandoffIfIndistinguishable': False,
        }
        record['updatedAt'] = utc_now()
        audit_run(
            registry,
            record,
            'CURRENT_CHECKOUT_ADOPTED',
            baseCommit=base_commit,
            exactFilesHash=begin['adoptedFilesHash'],
            confirmation=confirmation,
        )
        registry.save_run(record)
        return record


class LifecycleController:
    """持有一次 run 的权威 controller 服务；方法返回紧凑协议对象。"""

    def __init__(
        self,
        repo_root: Path,
        run_record: Mapping[str, Any],
        *,
        store_root: Path | None = None,
        gate_runner: Callable[..., Any] = run_service,
        gate_input_builder: Callable[[Path, Sequence[str], str | None], GateInputs] | None = None,
    ) -> None:
        self.repo = Path(repo_root).resolve()
        self.record = dict(run_record)
        self.session_id = str(run_record.get('sessionId') or '')
        self.run_id = str(run_record.get('runId') or '')
        if not self.session_id or not self.run_id:
            raise LifecycleError(
                TERMINAL_BLOCKED, 'SESSION_IDENTITY_INVALID', 'run identity missing'
            )
        checkout = Path(str(run_record.get('checkoutRoot') or '')).resolve()
        if checkout != self.repo:
            raise LifecycleError(
                TERMINAL_BLOCKED, 'WORKTREE_IDENTITY_MISMATCH', 'run checkout does not match cwd'
            )
        if self.record.get('checkoutKind') != 'linked-worktree':
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'PRIMARY_CHECKOUT_FORBIDDEN',
                'lifecycle mutation requires an independent linked worktree',
            )
        git_dir = Path(
            git(self.repo, 'rev-parse', '--absolute-git-dir', timeout=2).stdout.strip()
        ).resolve()
        common_dir = Path(
            git(self.repo, 'rev-parse', '--git-common-dir', timeout=2).stdout.strip()
        ).resolve()
        recorded_common = Path(str(self.record.get('gitCommonDir') or '')).resolve()
        if git_dir == common_dir or common_dir != recorded_common:
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'WORKTREE_IDENTITY_MISMATCH',
                'linked worktree/common-dir identity cannot be attested',
            )
        runtime_root = resolve_runtime_root(self.repo)
        self.root = Path(store_root or runtime_root / 'change-controller').resolve()
        self.store = ChangeStore(self.root)
        self.gate_runner = gate_runner
        self.gate_input_builder = gate_input_builder or self._default_gate_inputs
        self.artifacts = self.root / 'artifacts' / self.session_id
        client = str(self.record.get('client') or 'unknown')
        self.logs = (
            self.root
            / 'logs'
            / client
            / self.session_id
            / 'runs'
            / self.run_id
            / 'main'
        )

    @classmethod
    def from_run_id(cls, repo_root: Path, run_id: str, **kwargs: Any) -> LifecycleController:
        """只读取 atomic legacy run identity；Change 状态不再写回 run completion。"""
        registry = Registry(Path(repo_root))
        return cls(Path(repo_root), registry.load_run(run_id), **kwargs)

    def _session_identity(self) -> dict[str, Any]:
        return new_session(
            session_id=self.session_id,
            client=str(self.record.get('client') or 'unknown'),
            agent_id=str(self.record.get('agentId') or self.record.get('client') or 'main'),
            repo_key=str(self.record.get('repoKey') or ''),
            git_common_dir=str(self.record.get('gitCommonDir') or ''),
            worktree_id=str(self.record.get('worktreeId') or ''),
            checkout_root=str(self.repo),
            checkout_kind=str(self.record.get('checkoutKind') or ''),
            branch=str(self.record.get('branch') or ''),
            detached=bool(self.record.get('detached')),
            target_branch=str(self.record.get('targetBranch') or ''),
            primary_repo_root=str(self.record.get('primaryRepoRoot') or ''),
        )

    def _worktree_clean(self) -> bool:
        return not bool(
            git(
                self.repo,
                'status',
                '--porcelain=v1',
                '--untracked-files=all',
                timeout=2,
            ).stdout
        )

    def _target_head(self) -> str:
        primary = Path(str(self.record.get('primaryRepoRoot') or ''))
        target = str(self.record.get('targetBranch') or '')
        return git(primary, 'rev-parse', f'refs/heads/{target}', timeout=2).stdout.strip()

    def _assert_terminal_head(self, change: Mapping[str, Any]) -> None:
        """terminal receipt 只能绑定原 commit；clean/dirty 都不能掩盖 HEAD 漂移。"""
        commit_sha = str(change.get('commitSha') or '')
        result_ref = str(change.get('resultRef') or '')
        observed_ref = (
            git(
                self.repo, 'rev-parse', '--verify', result_ref, timeout=2, check=False
            ).stdout.strip()
            if result_ref
            else ''
        )
        if (
            not commit_sha
            or _git_head(self.repo) != commit_sha
            or observed_ref != commit_sha
            or _git_tree(self.repo, commit_sha) != change.get('candidateTree')
        ):
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'STALE_TERMINAL_HEAD',
                'terminal Change no longer matches linked HEAD/result ref/candidate tree',
            )

    def _assert_terminal_target(self, change: Mapping[str, Any]) -> None:
        """clean terminal PASS 要求 target 仍包含已证明 integrated 的 commit。"""
        commit_sha = str(change.get('commitSha') or '')
        if (
            change.get('integrationStatus') != 'INTEGRATED'
            or change.get('primaryNewSha') != commit_sha
        ):
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'STALE_TERMINAL_TARGET',
                'terminal Change no longer carries integrated target evidence',
            )
        target_head = self._target_head()
        primary = Path(str(self.record.get('primaryRepoRoot') or '')).resolve()
        ancestor = git(
            primary,
            'merge-base',
            '--is-ancestor',
            commit_sha,
            target_head,
            timeout=2,
            check=False,
        )
        if ancestor.returncode != 0:
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'STALE_TERMINAL_TARGET',
                'primary target no longer contains the integrated commit',
            )

    def _ensure_start_attestation(self, event: str) -> None:
        """canonical ensure-session 可在 clean baseline 上自愈缺失的 Start。"""
        begin = self.record.get('changeBegin')
        if not isinstance(begin, Mapping):
            self.record = attest_run_start(
                self.repo,
                self.run_id,
                activation_source=f'controller:{event}-self-heal',
            )
            begin = self.record.get('changeBegin')
        if not isinstance(begin, Mapping) or begin.get('status') != 'ATTESTED':
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'START_NOT_ENFORCED',
                'mutation requires an attested local begin-change baseline',
            )

    def _initial_dirty_is_attributed(self) -> bool:
        """只在 attested base/HEAD 与 scope 同时成立时恢复首次 dirty Change。"""
        begin = dict(self.record.get('changeBegin') or {})
        base = str(self.record.get('baseCommit') or begin.get('baseCommit') or '')
        if (
            not base
            or begin.get('baseCommit') not in {None, '', base}
            or _git_head(self.repo) != base
        ):
            return False
        try:
            manifest = collect_manifest(self.repo)
            validate_scope(manifest, self.record)
        except CandidateError:
            return False
        return bool(manifest.paths)

    def ensure_session(
        self,
        *,
        event: str = 'status',
        task_key: str = '',
        task_title: str = '',
    ) -> dict[str, Any]:
        """幂等建立 Session；PromptStart/首次 mutation 可在同 Session 轮转新 epoch。"""
        self._ensure_start_attestation(event)
        try:
            session = self.store.load_session(self.session_id)
        except ChangeStoreError as exc:
            if 'unknown lifecycle Session' not in str(exc):
                raise
            session = self.store.create_session(self._session_identity())
        active = current_change(session)
        if active is not None and active['state'] == 'INTEGRATED':
            self._assert_terminal_head(active)
        clean = self._worktree_clean()
        if active is not None and active['state'] == 'INTEGRATED' and clean:
            self._assert_terminal_target(active)
        terminal_roll = False
        no_change_terminal = bool(
            active is not None
            and active['state'] == 'WORKING'
            and dict(active.get('terminalStopReceipt') or {}).get('code') == 'NO_CHANGES'
        )
        if active is not None and (active['state'] == 'INTEGRATED' or no_change_terminal):
            if not clean or event in {'mutation', 'next-change'}:
                terminal_roll = True
            elif event == 'prompt':
                # 有 turn/task identity 时，同一 prompt 重放保持 terminal receipt；没有该
                # capability 的平台由首次 Prompt/PreTool 事件轮转，仍不依赖模型记忆。
                terminal_roll = not task_key or task_key != active.get('taskKey')
        should_roll = active is None or terminal_roll
        if should_roll:
            initial_dirty_recovery = bool(
                active is None and not clean and self._initial_dirty_is_attributed()
            )
            if active is None and not clean and not initial_dirty_recovery:
                raise LifecycleError(
                    TERMINAL_BLOCKED,
                    'BLOCKED_UNATTRIBUTED_CHANGES',
                    'dirty candidate cannot be attributed to the attested baseline and scope',
                )
            if (
                active is not None
                and (active['state'] == 'INTEGRATED' or no_change_terminal)
                and not clean
            ):
                try:
                    manifest = collect_manifest(self.repo)
                    if not manifest.paths:
                        raise CandidateError(
                            'POST_TERMINAL_MUTATION_UNATTRIBUTED',
                            'dirty worktree has no exact attributable manifest',
                        )
                    validate_scope(manifest, self.record)
                except CandidateError as exc:
                    raise LifecycleError(TERMINAL_BLOCKED, exc.code, str(exc)) from exc
            epoch = int(session['changeEpoch']) + 1
            stable_task = task_key or str(
                self.record.get('changeId') or self.record.get('taskId') or 'task'
            )
            change_id = f'{_safe_identifier(stable_task)}-e{epoch}'
            base = _git_head(self.repo)
            session = self.store.roll_next_change(
                self.session_id,
                change_id=change_id,
                task_key=stable_task,
                task_title=task_title or stable_task,
                base_commit=base,
                head_observed=base,
                target_observed=self._target_head(),
                worktree_clean=clean,
                allow_dirty_roll=bool(
                    initial_dirty_recovery
                    or (
                        active
                        and (active['state'] == 'INTEGRATED' or no_change_terminal)
                        and not clean
                    )
                ),
                expected_current_change_id=str(active['changeId']) if active else '',
                expected_current_version=int(active['stateVersion']) if active else 0,
            )
        return session

    def authorize_mutation(self) -> dict[str, Any]:
        """轮转当前 Change，并在首次写入前原子复核/激活 Start baseline。"""
        session = self.ensure_session(event='mutation')
        change = current_change(session)
        if change and change['state'] == 'COMMITTED_HANDOFF':
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'COMMITTED_HANDOFF_MUTATION_FORBIDDEN',
                'attested commit must be integrated or handed off before another mutation',
            )
        registry = Registry(self.repo)
        with registry.locked():
            record = registry.load_run(self.run_id)
            begin = record.get('changeBegin')
            if not isinstance(begin, Mapping):
                raise SessionctlError('START_NOT_ENFORCED: begin-change baseline is missing')
            if begin.get('status') != 'ATTESTED':
                raise SessionctlError(str(begin.get('status') or START_NOT_ENFORCED))
            if not record.get('firstMutationAt'):
                manifest = collect_manifest(self.repo)
                expected = (
                    tuple(sorted(begin.get('adoptedFiles') or ())) if begin.get('adopted') else ()
                )
                if manifest.paths != expected:
                    raise SessionctlError('mutation baseline changed before first authorized write')
                try:
                    validate_scope(manifest, record)
                except CandidateError as exc:
                    raise SessionctlError(f'mutation baseline {exc.code}: {exc}') from exc
                timestamp = utc_now()
                record['firstMutationAt'] = timestamp
                record['updatedAt'] = timestamp
                audit_run(registry, record, 'FIRST_MUTATION_AUTHORIZED', at=timestamp)
                registry.save_run(record)
            self.record = dict(record)
            return dict(record)

    def _artifact_path(self, change: Mapping[str, Any], name: str) -> Path:
        directory = self.artifacts / str(change['changeId'])
        directory.mkdir(parents=True, exist_ok=True)
        return directory / name

    def _metrics(self, session: Mapping[str, Any], change: Mapping[str, Any]) -> dict[str, int]:
        metrics = self.store.attempt_metrics(self.session_id)
        metrics.update(
            {
                'reusedPassReceipts': int(change.get('reusedPassReceipts') or 0),
                'cachedFailedAttempts': int(change.get('cachedFailedAttempts') or 0),
            }
        )
        return metrics

    def _payload(
        self,
        session: Mapping[str, Any],
        *,
        status: str,
        code: str,
        root_failure: RootFailure | Mapping[str, Any] | None = None,
        dependent: int = 0,
        next_action: str = '',
        artifact: Path | None = None,
        idempotent: bool = False,
    ) -> dict[str, Any]:
        change = current_change(session)
        if change is None:
            return compact_payload(status=status, state='WORKING', code=code)
        return compact_payload(
            status=status,
            state=str(change['state']),
            code=code,
            session_id=self.session_id,
            change_id=str(change['changeId']),
            attempt_id=str(change.get('currentAttemptId') or ''),
            candidate_tree=str(change.get('candidateTree') or ''),
            commit_sha=str(change.get('commitSha') or ''),
            result_ref=str(change.get('resultRef') or ''),
            integration_status=str(change.get('integrationStatus') or ''),
            next_action=next_action,
            root_failure=root_failure,
            dependent_blocked_count=dependent,
            artifact_path=str(artifact) if artifact else '',
            metrics=self._metrics(session, change),
            idempotent=idempotent,
        )

    def status(self) -> dict[str, Any]:
        """返回当前 Change 紧凑状态；不运行 Gate、commit 或 integration。"""
        session = self.ensure_session(event='status')
        change = current_change(session)
        if change and change['state'] == 'INTEGRATED' and self._worktree_clean():
            return self._payload(
                session,
                status=PASS,
                code='CHANGE_INTEGRATED',
                next_action='START_NEXT_CHANGE',
                idempotent=True,
            )
        return self._payload(session, status=PASS, code='CHANGE_STATUS', next_action='CONTINUE')

    def _cheap_preflight(self) -> None:
        """纯只读 capability 检查；不启动 fixture、不构建、不下载。"""
        required = ('git',)
        missing = [name for name in required if not shutil.which(name)]
        if missing:
            raise LifecycleError(
                CAPABILITY_RETRYABLE,
                'EXECUTABLE_MISSING',
                f'missing executables: {missing}',
                repair_argv=('./scripts/session-browser.sh', 'deps'),
            )
        for path in ('config/gates.yaml', 'scripts/gates/cli.py'):
            if not (self.repo / path).is_file():
                raise LifecycleError(
                    CAPABILITY_RETRYABLE,
                    'CONFIG_MISSING',
                    f'required lifecycle config missing: {path}',
                    repair_argv=('git', 'status', '--short'),
                )

    def _default_gate_inputs(
        self, repo: Path, changed_files: Sequence[str], base_url: str | None
    ) -> GateInputs:
        """从冻结 execution plan 计算 Attempt 指纹；不启动任何 Gate child。"""
        gate_plan = create_plan(
            list(changed_files), tier='required', target=None, explicit_changed_files=True
        )
        resolved = gate_executor.build_execution_plan(
            _with_preflight(gate_plan), repo, base_url=base_url
        )
        commands = [list(group.command) for group in resolved.groups]
        identity_environment = self._gate_identity_environment()
        group_env = [
            sorted(
                gate_executor.gate_child_environment(
                    repo,
                    {**dict(group.environment), **identity_environment},
                ).items()
            )
            for group in resolved.groups
        ]
        return GateInputs(
            plan_fingerprint=resolved.fingerprint,
            command_fingerprint=_hash(commands),
            # 指纹直接取 executor 最终传给每个 child 的净化环境；managed fixture
            # 使用 Change 稳定 URL，恢复时既不漂移也不会隐藏实际 BASE_URL。
            environment_fingerprint=_hash(group_env),
            planned_child_count=sum(bool(group.command) for group in resolved.groups),
            requires_fixture=any(
                len(group.command) >= 2
                and Path(group.command[0]).name == 'npx'
                and group.command[1] == 'playwright'
                for group in resolved.groups
            ),
        )

    def _gate_identity_environment(self) -> dict[str, str]:
        """把 controller 的权威 run identity 显式传给 Gate child。"""
        return {
            'FEIPI_AGENT_CLIENT': str(self.record.get('client') or 'unknown'),
            'FEIPI_SESSION_ID': self.session_id,
            'FEIPI_RUN_ID': self.run_id,
            'FEIPI_WORKTREE_ID': str(self.record.get('worktreeId') or ''),
        }

    def _planned_fixture_url(self, change: Mapping[str, Any]) -> str:
        """为一个 Change 生成稳定 loopback URL，使真实 plan/env 指纹可缓存。"""
        external = os.environ.get('BASE_URL', '').strip().rstrip('/')
        if external:
            return external
        seed = _hash([self.session_id, change['changeId'], change['changeEpoch']])
        return f"http://127.0.0.1:{30000 + int(seed[:8], 16) % 10000}"

    def _start_fixture(
        self, change: Mapping[str, Any], base_url: str
    ) -> tuple[FixtureSupervisor, str]:
        expected = {
            'dataset': 'synthetic-hifi-v1',
            'kind': 'feipi-session-browser-fixture',
            'schemaVersion': 1,
        }
        # fixture state 跨 Attempt 共用，controller 崩溃后可校验 PID identity 并原地
        # 恢复/回收；日志仍位于 run-scoped ignored runtime，不创建恢复 worktree。
        supervisor = FixtureSupervisor(
            self.root / 'fixtures' / self.session_id / str(change['changeId']),
            expected_identity=expected,
        )
        external = os.environ.get('BASE_URL', '').strip()
        if external:
            return supervisor, supervisor.use_external(base_url=external).base_url
        node = shutil.which('node')
        starter = self.repo / 'tests' / 'playwright' / 'start-java-fixture-server.js'
        if not node or not starter.is_file():
            raise FixtureError('FIXTURE_CAPABILITY_MISSING', 'Node fixture starter is unavailable')
        launcher = (
            self.repo / 'java' / 'app-cli' / 'build' / 'install' / 'app-cli' / 'bin' / 'app-cli'
        )
        if not launcher.is_file():
            build = run_bounded(
                [str(self.repo / 'gradlew'), ':java:app-cli:installDist', '--console=plain'],
                cwd=self.repo,
                timeout=300,
                env={'FEIPI_RUN_ID': self.run_id},
                log_path=self.logs / str(change['changeId']) / 'fixture-build.log',
            )
            if not build.passed:
                raise FixtureError('FIXTURE_BUILD_FAILED', build.output_tail or build.exit_reason)
        handle = supervisor.start_managed(
            [node, str(starter)],
            cwd=self.repo,
            base_url=base_url,
            env={
                'FEIPI_AGENT_RUNTIME_ROOT': str(resolve_runtime_root(self.repo)),
                'FEIPI_RUN_ID': self.run_id,
            },
        )
        return supervisor, handle.base_url

    def _prepare(
        self,
        session: Mapping[str, Any],
        *,
        expect_manifest_hash: str = '',
        expect_candidate_tree: str = '',
    ) -> tuple[dict[str, Any], PreparedCandidate]:
        change = current_change(session)
        if change is None:
            raise LifecycleError(INTERNAL_ERROR, 'CHANGE_MISSING', 'current Change missing')
        manifest = collect_manifest(self.repo)
        if expect_manifest_hash and manifest.manifest_hash != expect_manifest_hash:
            raise LifecycleError(
                TERMINAL_BLOCKED, 'MANIFEST_GUARD_MISMATCH', 'manifest TOCTOU guard failed'
            )
        try:
            prepared = prepare_candidate(
                self.repo,
                self.record,
                log_dir=self.logs / str(change['changeId']) / 'candidate',
            )
        except CandidateError as exc:
            status = PASS if exc.code == 'NO_CHANGES' else REPAIR_REQUIRED
            raise LifecycleError(
                status if status != PASS else INTERNAL_ERROR, exc.code, str(exc)
            ) from exc
        if expect_candidate_tree and prepared.candidate_tree != expect_candidate_tree:
            raise LifecycleError(
                TERMINAL_BLOCKED, 'CANDIDATE_GUARD_MISMATCH', 'candidate TOCTOU guard failed'
            )
        if change['state'] not in {'WORKING', 'REPAIR_REQUIRED', 'PREPARED', 'VALIDATING'}:
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'STALE_CHANGE_STATE',
                f'cannot prepare candidate in state {change["state"]}',
            )
        if change['state'] == 'VALIDATING':
            return dict(session), prepared
        session = self.store.transition(
            self.session_id,
            str(change['changeId']),
            target_state='PREPARED',
            expected=_cas(change),
            updates={
                'candidateTree': prepared.candidate_tree,
                'manifestHash': prepared.manifest.manifest_hash,
            },
        )
        self._failpoint('candidate-fingerprint-written')
        return session, prepared

    @staticmethod
    def _failpoint(name: str) -> None:
        if os.environ.get('FEIPI_CHANGE_FAILPOINT') == name:
            raise LifecycleError(INTERNAL_ERROR, 'FAILPOINT_CRASH', f'injected crash: {name}')

    def _reuse_attempt(
        self,
        session: Mapping[str, Any],
        change: Mapping[str, Any],
        attempt: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        status = str(attempt['status'])
        if status == 'STARTED':
            recovered_pass = self._pass_attempt_receipt_valid(attempt, raise_on_error=False)
            root = (
                []
                if recovered_pass
                else [{'code': 'ATTEMPT_INTERRUPTED', 'message': 'heavy Gate process interrupted'}]
            )
            session, attempt = self.store.finish_attempt(
                self.session_id,
                str(change['changeId']),
                str(attempt['attemptId']),
                expected=_cas(change),
                status='PASS' if recovered_pass else 'BLOCKED',
                independent_root_failures=root,
                dependent_blocked_count=0,
            )
            return session, attempt
        if status == 'PASS':
            self._pass_attempt_receipt_valid(attempt, raise_on_error=True)
        # 已完成缓存不能再次 finish；只推进 Change state，重 Gate child 为 0。
        validating = self.store.transition(
            self.session_id,
            str(change['changeId']),
            target_state='VALIDATING',
            expected=_cas(change),
            updates={'currentAttemptId': attempt['attemptId']},
        )
        active = current_change(validating)
        assert active is not None
        target = 'VALIDATED' if status == 'PASS' else 'REPAIR_REQUIRED'
        counter = 'reusedPassReceipts' if status == 'PASS' else 'cachedFailedAttempts'
        updated = self.store.transition(
            self.session_id,
            str(active['changeId']),
            target_state=target,
            expected=_cas(active),
            updates={counter: int(active.get(counter) or 0) + 1},
        )
        return updated, dict(attempt)

    def _reuse_unchanged_failed_candidate(
        self, session: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """相同稳定 index 直接命中失败缓存，不再重复 formatter 或 full Gate。"""
        change = current_change(session)
        if change is None or change['state'] != 'REPAIR_REQUIRED':
            return None
        manifest = collect_manifest(self.repo)
        if (
            manifest.manifest_hash != change.get('manifestHash')
            or manifest.staged != manifest.paths
            or manifest.unstaged
            or manifest.untracked
            or git(self.repo, 'write-tree', timeout=2).stdout.strip() != change.get('candidateTree')
        ):
            return None
        preliminary = self.gate_input_builder(self.repo, manifest.paths, None)
        base_url = self._planned_fixture_url(change) if preliminary.requires_fixture else None
        inputs = self.gate_input_builder(self.repo, manifest.paths, base_url)
        fingerprint = attempt_fingerprint(
            candidate_tree=str(change['candidateTree']),
            manifest_hash=manifest.manifest_hash,
            plan_fingerprint=inputs.plan_fingerprint,
            command_fingerprint=inputs.command_fingerprint,
            environment_fingerprint=inputs.environment_fingerprint,
        )
        cached = self.store.find_attempt_by_fingerprint(
            self.session_id, str(change['changeId']), fingerprint
        )
        if cached is None or cached.get('status') not in {'FAIL', 'BLOCKED'}:
            return None
        prepared = self.store.transition(
            self.session_id,
            str(change['changeId']),
            target_state='PREPARED',
            expected=_cas(change),
        )
        active = current_change(prepared)
        assert active is not None
        return self._reuse_attempt(prepared, active, cached)

    def _pass_attempt_receipt_valid(
        self, attempt: Mapping[str, Any], *, raise_on_error: bool
    ) -> bool:
        """PASS cache 必须重新校验 controller receipt、artifact 与所有绑定哈希。"""
        error = ''
        try:
            receipt_path = Path(str(attempt.get('receiptPath') or ''))
            artifact_path = Path(str(attempt.get('artifactPath') or ''))
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            artifact = json.loads(artifact_path.read_text(encoding='utf-8'))
            expected = {
                'status': 'PASS',
                'attemptId': attempt.get('attemptId'),
                'fingerprint': attempt.get('fingerprint'),
                'candidateTree': attempt.get('candidateTree'),
                'manifestHash': attempt.get('manifestHash'),
                'planFingerprint': attempt.get('planFingerprint'),
                'gatePlanFingerprint': attempt.get('planFingerprint'),
                'commandFingerprint': attempt.get('commandFingerprint'),
                'environmentFingerprint': attempt.get('environmentFingerprint'),
            }
            mismatched = [key for key, value in expected.items() if receipt.get(key) != value]
            artifact_plan = str(artifact.get('planFingerprint') or attempt.get('planFingerprint'))
            if mismatched or artifact.get('status') != 'PASS':
                error = f'PASS receipt fields mismatch: {mismatched}'
            elif artifact_plan != attempt.get('planFingerprint'):
                error = 'PASS Gate artifact plan fingerprint mismatch'
            elif receipt.get('gateArtifactSha256') != _file_sha256(artifact_path):
                error = 'PASS gate artifact hash mismatch'
            else:
                for binding in receipt.get('gateReceipts') or []:
                    path = Path(str(binding.get('path') or ''))
                    if not path.is_file() or binding.get('sha256') != _file_sha256(path):
                        error = f'PASS gate receipt hash mismatch: {path}'
                        break
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            error = f'{type(exc).__name__}: {exc}'
        if error and raise_on_error:
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'PASS_RECEIPT_INVALID',
                error,
            )
        return not error

    def _validate_candidate(
        self, session: Mapping[str, Any], prepared: PreparedCandidate
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        change = current_change(session)
        assert change is not None
        preliminary = self.gate_input_builder(self.repo, prepared.manifest.paths, None)
        base_url = self._planned_fixture_url(change) if preliminary.requires_fixture else None
        # 使用真实 fixture URL 重建 execution plan；Attempt 绑定的 plan/environment
        # 指纹必须与随后 Gate child 实际接收的环境完全一致。
        inputs = self.gate_input_builder(self.repo, prepared.manifest.paths, base_url)
        fingerprint = attempt_fingerprint(
            candidate_tree=prepared.candidate_tree,
            manifest_hash=prepared.manifest.manifest_hash,
            plan_fingerprint=inputs.plan_fingerprint,
            command_fingerprint=inputs.command_fingerprint,
            environment_fingerprint=inputs.environment_fingerprint,
        )
        cached = self.store.find_attempt_by_fingerprint(
            self.session_id, str(change['changeId']), fingerprint
        )
        if cached is not None:
            return self._reuse_attempt(session, change, cached)
        attempt_number = int(change.get('attemptSequence') or 0) + 1
        attempt_dir = self._artifact_path(change, f'attempt-{attempt_number:04d}')
        attempt_dir.mkdir(parents=True, exist_ok=True)
        intended_receipt = attempt_dir / 'controller-receipt.json'
        intended_artifact = attempt_dir / 'gate-result.json'
        session, attempt = self.store.start_attempt(
            self.session_id,
            str(change['changeId']),
            expected=_cas(change),
            candidate_tree=prepared.candidate_tree,
            manifest_hash=prepared.manifest.manifest_hash,
            plan_fingerprint=inputs.plan_fingerprint,
            command_fingerprint=inputs.command_fingerprint,
            environment_fingerprint=inputs.environment_fingerprint,
            receipt_path=str(intended_receipt),
            artifact_path=str(intended_artifact),
            heavy_child_started=False,
        )
        validating = current_change(session)
        assert validating is not None
        supervisor: FixtureSupervisor | None = None
        try:
            if inputs.requires_fixture:
                if base_url is None:
                    raise LifecycleError(
                        INTERNAL_ERROR,
                        'FIXTURE_PLAN_INVALID',
                        'fixture-required plan has no attested BASE_URL',
                    )
                supervisor, observed_base_url = self._start_fixture(change, base_url)
                if observed_base_url != base_url:
                    raise LifecycleError(
                        TERMINAL_BLOCKED,
                        'FIXTURE_URL_MISMATCH',
                        'fixture supervisor returned a URL outside the Attempt fingerprint',
                    )
            session, attempt = self.store.mark_attempt_child_started(
                self.session_id,
                str(change['changeId']),
                str(attempt['attemptId']),
                expected=_cas(validating),
            )
            validating = current_change(session)
            assert validating is not None
            result = self.gate_runner(
                repo_root=self.repo,
                changed_files=list(prepared.manifest.paths),
                tier='required',
                change_id=str(change['changeId']),
                out_dir=attempt_dir,
                explicit_changed_files=True,
                include_preflight=True,
                reuse_receipts=False,
                base_url=base_url,
                environment_overrides=self._gate_identity_environment(),
            )
            status = str(result.status).upper()
            status = (
                'PASS'
                if status == gate_report.PASS
                else 'BLOCKED'
                if status == gate_report.BLOCKED
                else 'FAIL'
            )
            _root, dependent, full_failures = classify_gate_failures(result.details)
            gate_artifact = (
                Path(result.artifact_path) if result.artifact_path else intended_artifact
            )
            if gate_artifact != intended_artifact and gate_artifact.is_file():
                write_artifact(
                    intended_artifact,
                    json.loads(gate_artifact.read_text(encoding='utf-8')),
                )
            gate_artifact_facts = json.loads(intended_artifact.read_text(encoding='utf-8'))
            observed_plan_fingerprint = str(
                gate_artifact_facts.get('planFingerprint') or inputs.plan_fingerprint
            )
            if observed_plan_fingerprint != inputs.plan_fingerprint:
                raise LifecycleError(
                    TERMINAL_BLOCKED,
                    'GATE_PLAN_FINGERPRINT_MISMATCH',
                    'Gate artifact plan differs from the Attempt fingerprint',
                )
            gate_receipts = [
                {'path': str(path), 'sha256': _file_sha256(Path(path))}
                for path in result.receipt_paths
            ]
            receipt_facts = {
                'schemaVersion': 2,
                'status': status,
                'attemptId': attempt['attemptId'],
                'fingerprint': attempt['fingerprint'],
                'candidateTree': prepared.candidate_tree,
                'manifestHash': prepared.manifest.manifest_hash,
                'planFingerprint': inputs.plan_fingerprint,
                'gatePlanFingerprint': observed_plan_fingerprint,
                'commandFingerprint': inputs.command_fingerprint,
                'environmentFingerprint': inputs.environment_fingerprint,
                'gateReceipts': gate_receipts,
                'gateArtifactPath': str(intended_artifact),
                'gateArtifactSha256': _file_sha256(intended_artifact),
                'plannedHeavyChildren': inputs.planned_child_count,
            }
            write_artifact(intended_receipt, receipt_facts)
            session, attempt = self.store.finish_attempt(
                self.session_id,
                str(change['changeId']),
                str(attempt['attemptId']),
                expected=_cas(validating),
                status=status,
                independent_root_failures=full_failures,
                dependent_blocked_count=dependent,
                receipt_path=str(intended_receipt),
                artifact_path=str(intended_artifact),
            )
            if status == 'PASS':
                self._failpoint('gate-pass-receipt-written')
            return session, attempt
        except LifecycleError:
            raise
        except FixtureIdentityError as exc:
            failure = [{'code': exc.reason_code, 'message': str(exc)}]
            self.store.finish_attempt(
                self.session_id,
                str(change['changeId']),
                str(attempt['attemptId']),
                expected=_cas(validating),
                status='BLOCKED',
                independent_root_failures=failure,
                dependent_blocked_count=0,
            )
            raise LifecycleError(TERMINAL_BLOCKED, exc.reason_code, str(exc)) from exc
        except FixtureUnavailableError as exc:
            failure = [{'code': exc.reason_code, 'message': str(exc)}]
            session, attempt = self.store.finish_attempt(
                self.session_id,
                str(change['changeId']),
                str(attempt['attemptId']),
                expected=_cas(validating),
                status='BLOCKED',
                independent_root_failures=failure,
                dependent_blocked_count=0,
            )
            return session, attempt
        except BaseException as exc:
            failure = [{'code': 'GATE_RUNTIME_ERROR', 'message': f'{type(exc).__name__}: {exc}'}]
            session, attempt = self.store.finish_attempt(
                self.session_id,
                str(change['changeId']),
                str(attempt['attemptId']),
                expected=_cas(validating),
                status='BLOCKED',
                independent_root_failures=failure,
                dependent_blocked_count=0,
            )
            return session, attempt
        finally:
            if supervisor is not None:
                try:
                    supervisor.cleanup()
                except FixtureError:
                    pass

    def _commit_paths(self, commit_sha: str) -> tuple[str, ...]:
        output = git(
            self.repo,
            'diff-tree',
            '--no-commit-id',
            '--name-only',
            '--no-renames',
            '-r',
            '-z',
            commit_sha,
            timeout=2,
        ).stdout
        return tuple(sorted(item for item in output.split('\0') if item))

    def _validated_attempt(self, change: Mapping[str, Any]) -> dict[str, Any]:
        attempts = self.store.list_attempts(self.session_id, str(change['changeId']))
        attempt = next(
            (item for item in attempts if item.get('attemptId') == change.get('currentAttemptId')),
            None,
        )
        if not attempt or attempt.get('status') != 'PASS':
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'GATE_ATTESTATION_MISSING',
                'commit does not retain a PASS Attempt receipt',
            )
        self._pass_attempt_receipt_valid(attempt, raise_on_error=True)
        return attempt

    def _attest_commit(self, change: Mapping[str, Any], commit_sha: str) -> dict[str, Any]:
        parent = git(self.repo, 'rev-parse', f'{commit_sha}^', timeout=2).stdout.strip()
        tree = _git_tree(self.repo, commit_sha)
        intended = dict(change.get('pendingCommitIntent') or {})
        expected_paths = tuple(intended.get('exactFiles') or ())
        errors = []
        if parent != change['baseCommit']:
            errors.append('commit parent differs from attested base')
        if tree != change['candidateTree']:
            errors.append('commit tree differs from validated candidate')
        if self._commit_paths(commit_sha) != expected_paths:
            errors.append('commit paths differ from exact manifest')
        if not self._worktree_clean():
            errors.append('worktree is dirty after commit')
        if errors:
            raise LifecycleError(TERMINAL_BLOCKED, 'COMMIT_ATTESTATION_FAILED', '; '.join(errors))
        return {
            'status': 'PASS',
            'parent': parent,
            'commitTree': tree,
            'committedPaths': list(expected_paths),
            'candidateTree': change['candidateTree'],
            'attestedAt': utc_now(),
        }

    def _commit(self, session: Mapping[str, Any], message: str) -> dict[str, Any]:
        change = current_change(session)
        assert change is not None
        if change['state'] != 'VALIDATED':
            return dict(session)
        self._validated_attempt(change)
        manifest = collect_manifest(self.repo)
        exact_files = tuple(manifest.paths)
        if manifest.staged != exact_files or manifest.unstaged or manifest.untracked:
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'CANDIDATE_CHANGED_AFTER_GATE',
                'candidate changed after validation',
            )
        intent = dict(change.get('pendingCommitIntent') or {})
        if not intent:
            intent = {
                'baseCommit': change['baseCommit'],
                'candidateTree': change['candidateTree'],
                'manifestHash': change['manifestHash'],
                'exactFiles': list(exact_files),
                'message': message,
                'createdAt': utc_now(),
            }
            session = self.store.transition(
                self.session_id,
                str(change['changeId']),
                target_state='VALIDATED',
                expected=_cas(change),
                updates={'pendingCommitIntent': intent},
            )
            change = current_change(session)
            assert change is not None
        head = _git_head(self.repo)
        commit_sha = ''
        if head != change['baseCommit']:
            subject = git(self.repo, 'show', '-s', '--format=%s', head, timeout=2).stdout.strip()
            if subject != intent['message']:
                raise LifecycleError(
                    TERMINAL_BLOCKED,
                    'UNATTRIBUTED_COMMIT',
                    'HEAD commit does not match pending intent',
                )
            commit_sha = head
        else:
            log_path = self.logs / str(change['changeId']) / 'git-commit.log'
            result = run_bounded(
                ['git', '-C', str(self.repo), 'commit', '-m', str(intent['message'])],
                cwd=self.repo,
                timeout=120,
                env={'FEIPI_RUN_ID': self.run_id},
                log_path=log_path,
            )
            if not result.passed:
                raise LifecycleError(
                    CAPABILITY_RETRYABLE,
                    'GIT_COMMIT_FAILED',
                    result.output_tail[-1000:] or result.exit_reason,
                    repair_argv=('git', 'status', '--short'),
                )
            commit_sha = _git_head(self.repo)
            self._failpoint('git-commit-succeeded')
        # Git commit 成功后先单调保存 commitSha。后续 attestation/result-ref 即使失败，
        # snapshot 也不得回退成“无 commit”；resume 只补证据，不创建第二个 commit。
        session = self.store.transition(
            self.session_id,
            str(change['changeId']),
            target_state='COMMITTED',
            expected=_cas(change),
            updates={'commitSha': commit_sha},
        )
        return self._complete_commit_evidence(session)

    def _complete_commit_evidence(self, session: Mapping[str, Any]) -> dict[str, Any]:
        """为已持久化 commit 单调补齐 attestation 与 durable result ref。"""
        change = current_change(session)
        assert change is not None
        if change['state'] not in {'COMMITTED', 'COMMITTED_HANDOFF'}:
            return dict(session)
        commit_sha = str(change.get('commitSha') or '')
        attestation = dict(change.get('commitAttestation') or {})
        result_ref = f"refs/heads/codex/result/{_safe_identifier(str(change['changeId']))}"
        if (
            attestation.get('status') == 'PASS'
            and change.get('resultRef') == result_ref
            and git(
                self.repo, 'rev-parse', '--verify', result_ref, timeout=2, check=False
            ).stdout.strip()
            == commit_sha
        ):
            return dict(session)
        attestation = self._attest_commit(change, commit_sha)
        existing = git(
            self.repo, 'rev-parse', '--verify', result_ref, timeout=2, check=False
        ).stdout.strip()
        if existing and existing != commit_sha:
            raise LifecycleError(
                TERMINAL_BLOCKED, 'RESULT_REF_CONFLICT', 'durable result ref points elsewhere'
            )
        if not existing:
            update = git(
                self.repo,
                'update-ref',
                result_ref,
                commit_sha,
                '0' * 40,
                timeout=2,
                check=False,
            )
            if update.returncode != 0:
                raise LifecycleError(
                    TERMINAL_BLOCKED, 'RESULT_REF_FAILED', 'cannot create durable result ref'
                )
        self._failpoint('result-ref-created')
        return self.store.transition(
            self.session_id,
            str(change['changeId']),
            target_state=str(change['state']),
            expected=_cas(change),
            updates={
                'resultRef': result_ref,
                'commitAttestation': attestation,
            },
        )

    def _handoff(self, session: Mapping[str, Any], reason_code: str) -> dict[str, Any]:
        change = current_change(session)
        assert change is not None
        if (
            change['state'] == 'COMMITTED_HANDOFF'
            and change.get('integrationReasonCode') == reason_code
        ):
            return dict(session)
        return self.store.transition(
            self.session_id,
            str(change['changeId']),
            target_state='COMMITTED_HANDOFF',
            expected=_cas(change),
            updates={'integrationReasonCode': reason_code},
        )

    def _integrate(self, session: Mapping[str, Any]) -> dict[str, Any]:
        change = current_change(session)
        assert change is not None
        if change['state'] == 'INTEGRATED':
            return dict(session)
        if change['state'] not in {'COMMITTED', 'COMMITTED_HANDOFF'}:
            raise LifecycleError(INTERNAL_ERROR, 'COMMIT_REQUIRED', 'integration requires commit')
        primary = Path(str(self.record.get('primaryRepoRoot') or '')).resolve()
        target = str(self.record.get('targetBranch') or '')
        commit_sha = str(change['commitSha'])
        attestation = dict(change.get('commitAttestation') or {})
        if (
            not commit_sha
            or attestation.get('status') != 'PASS'
            or attestation.get('commitTree') != change.get('candidateTree')
        ):
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'COMMIT_ATTESTATION_MISSING',
                'commit evidence is incomplete or differs from the validated candidate',
            )
        result_ref = str(change.get('resultRef') or '')
        ref_sha = git(
            self.repo, 'rev-parse', '--verify', result_ref, timeout=2, check=False
        ).stdout.strip()
        if ref_sha != commit_sha or _git_tree(self.repo, commit_sha) != change['candidateTree']:
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'COMMIT_ATTESTATION_STALE',
                'durable result ref or commit tree no longer matches attested commit',
            )
        self._validated_attempt(change)
        if _git_head(self.repo) != commit_sha or not self._worktree_clean():
            return self._handoff(session, 'SOURCE_DIRTY_OR_ADVANCED')
        if git(primary, 'status', '--porcelain=v1', '--untracked-files=all', timeout=2).stdout:
            return self._handoff(session, 'PRIMARY_DIRTY')
        branch = git(primary, 'branch', '--show-current', timeout=2).stdout.strip()
        if branch != target:
            return self._handoff(session, 'TARGET_BRANCH_MISMATCH')
        primary_head = _git_head(primary)
        if primary_head == commit_sha:
            return self.store.transition(
                self.session_id,
                str(change['changeId']),
                target_state='INTEGRATED',
                expected=_cas(change),
                updates={'primaryOldSha': change['baseCommit'], 'primaryNewSha': commit_sha},
            )
        if primary_head != change['baseCommit']:
            return self._handoff(session, 'TARGET_ADVANCED')
        lock = BoundedMetadataLock(
            self.root / 'locks' / 'integration.lock',
            session_id=self.session_id,
            change_id=str(change['changeId']),
            epoch=int(change['changeEpoch']),
        )
        try:
            lock.acquire()
        except LockBusyError:
            return self._handoff(session, 'LOCK_BUSY')
        try:
            # 锁内重读 primary facts，禁止 TOCTOU 后猜测或重写历史。
            if git(primary, 'status', '--porcelain=v1', '--untracked-files=all', timeout=2).stdout:
                return self._handoff(session, 'PRIMARY_DIRTY')
            if _git_head(primary) != change['baseCommit']:
                return self._handoff(session, 'TARGET_ADVANCED')
            result = run_bounded(
                ['git', '-C', str(primary), 'merge', '--ff-only', commit_sha],
                cwd=primary,
                timeout=5,
                env={'FEIPI_RUN_ID': self.run_id},
                log_path=self.logs / str(change['changeId']) / 'integration.log',
            )
            if not result.passed or _git_head(primary) != commit_sha:
                return self._handoff(session, 'FF_ONLY_FAILED')
            self._failpoint('primary-ff-completed')
            return self.store.transition(
                self.session_id,
                str(change['changeId']),
                target_state='INTEGRATED',
                expected=_cas(change),
                updates={'primaryOldSha': primary_head, 'primaryNewSha': commit_sha},
            )
        finally:
            lock.release()

    def on_stop(
        self,
        *,
        message: str,
        turn_key: str = '',
        expect_manifest_hash: str = '',
        expect_candidate_tree: str = '',
    ) -> dict[str, Any]:
        """有任务改动时强制 prepare→Gate→commit→ff-only integration。"""
        started = time.monotonic()
        session = self.ensure_session(event='stop', task_key=turn_key)
        change = current_change(session)
        assert change is not None
        if change['state'] == 'INTEGRATED' and self._worktree_clean():
            return self._payload(
                session,
                status=PASS,
                code='CHANGE_INTEGRATED',
                next_action='START_NEXT_CHANGE',
                idempotent=True,
            )
        if (
            dict(change.get('terminalStopReceipt') or {}).get('code') == 'NO_CHANGES'
            and self._worktree_clean()
        ):
            return self._payload(
                session,
                status=PASS,
                code='NO_CHANGES',
                next_action='WAIT_FOR_NEXT_PROMPT',
                idempotent=True,
            )
        if change['state'] in {'COMMITTED', 'COMMITTED_HANDOFF'}:
            session = self._complete_commit_evidence(session)
            session = self._integrate(session)
            return self._completion_payload(session, started)
        if change['state'] == 'VALIDATED':
            session = self._commit(session, message)
            session = self._integrate(session)
            return self._completion_payload(session, started)
        if self._worktree_clean():
            receipt = {
                'code': 'NO_CHANGES',
                'turnKey': turn_key or str(change.get('taskKey') or ''),
                'stoppedAt': utc_now(),
                'gateRuns': 0,
                'commitCount': 0,
                'integrationCount': 0,
            }
            session = self.store.transition(
                self.session_id,
                str(change['changeId']),
                target_state='WORKING',
                expected=_cas(change),
                updates={'terminalStopReceipt': receipt},
            )
            return self._payload(
                session,
                status=PASS,
                code='NO_CHANGES',
                next_action='WAIT_FOR_NEXT_PROMPT',
                idempotent=True,
            )
        self._cheap_preflight()
        lock = BoundedMetadataLock(
            self.root / 'locks' / f"writer-{self.record['worktreeId']}.lock",
            session_id=self.session_id,
            change_id=str(change['changeId']),
            epoch=int(change['changeEpoch']),
        )
        try:
            lock.acquire()
        except LockBusyError as exc:
            raise LifecycleError(
                BUSY_RETRYABLE,
                'WRITER_LOCK_BUSY',
                str(exc),
                details={'owner': exc.owner, 'waitedSeconds': exc.waited_seconds},
            ) from exc
        try:
            cached_repair = self._reuse_unchanged_failed_candidate(session)
            if cached_repair is not None:
                session, attempt = cached_repair
                change = current_change(session)
                assert change is not None
                failures = list(attempt.get('independentRootFailures') or [])
                root = (
                    failures[0]
                    if failures
                    else {'code': 'GATE_FAILED', 'message': 'required Gate did not pass'}
                )
                artifact = Path(str(attempt.get('artifactPath') or ''))
                return self._payload(
                    session,
                    status=CAPABILITY_RETRYABLE
                    if attempt['status'] == 'BLOCKED'
                    else REPAIR_REQUIRED,
                    code='CACHED_GATE_FAILURE',
                    root_failure=root,
                    dependent=int(attempt.get('dependentBlockedCount') or 0),
                    next_action='FIX_AND_RETRY',
                    artifact=artifact if artifact.is_file() else None,
                )
            session, prepared = self._prepare(
                session,
                expect_manifest_hash=expect_manifest_hash,
                expect_candidate_tree=expect_candidate_tree,
            )
            self._failpoint('exact-stage-completed')
            session, attempt = self._validate_candidate(session, prepared)
            change = current_change(session)
            assert change is not None
            if change['state'] == 'REPAIR_REQUIRED':
                failures = list(attempt.get('independentRootFailures') or [])
                root = (
                    failures[0]
                    if failures
                    else {'code': 'GATE_FAILED', 'message': 'required Gate did not pass'}
                )
                status = CAPABILITY_RETRYABLE if attempt['status'] == 'BLOCKED' else REPAIR_REQUIRED
                artifact = Path(str(attempt.get('artifactPath') or ''))
                return self._payload(
                    session,
                    status=status,
                    code='CACHED_GATE_FAILURE'
                    if int(change.get('cachedFailedAttempts') or 0)
                    else 'GATE_FAILED',
                    root_failure=root,
                    dependent=int(attempt.get('dependentBlockedCount') or 0),
                    next_action='FIX_AND_RETRY',
                    artifact=artifact if artifact.is_file() else None,
                )
            session = self._commit(session, message)
            session = self._integrate(session)
            return self._completion_payload(session, started)
        finally:
            lock.release()

    def _completion_payload(self, session: Mapping[str, Any], started: float) -> dict[str, Any]:
        change = current_change(session)
        assert change is not None
        artifact = self._artifact_path(change, 'completion.json')
        facts = {
            'schemaVersion': 1,
            'session': dict(session),
            'attempts': self.store.list_attempts(self.session_id, str(change['changeId'])),
            'metrics': self._metrics(session, change),
            'durationSeconds': round(time.monotonic() - started, 6),
        }
        write_artifact(artifact, facts)
        if change['state'] == 'INTEGRATED':
            return self._payload(
                session,
                status=PASS,
                code='CHANGE_INTEGRATED',
                next_action='START_NEXT_CHANGE',
                artifact=artifact,
            )
        if change['state'] == 'COMMITTED_HANDOFF':
            return self._payload(
                session,
                status=COMMITTED_HANDOFF,
                code=str(change.get('integrationReasonCode') or 'INTEGRATION_HANDOFF'),
                next_action='INTEGRATE_COMMIT',
                artifact=artifact,
            )
        raise LifecycleError(INTERNAL_ERROR, 'COMPLETION_STATE_INVALID', str(change['state']))

    def next_change(self, *, task_key: str, task_title: str) -> dict[str, Any]:
        """显式创建下一 Change；非 INTEGRATED 状态一律关闭失败。"""
        existing = self.ensure_session(event='status')
        active = current_change(existing)
        no_change_terminal = bool(
            active is not None
            and dict(active.get('terminalStopReceipt') or {}).get('code') == 'NO_CHANGES'
        )
        if active is not None and active['state'] != 'INTEGRATED' and not no_change_terminal:
            raise LifecycleError(
                TERMINAL_BLOCKED,
                'NEXT_CHANGE_FORBIDDEN',
                f"cannot create next Change from state {active['state']}",
            )
        session = self.ensure_session(event='next-change', task_key=task_key, task_title=task_title)
        return self._payload(
            session, status=PASS, code='NEXT_CHANGE_CREATED', next_action='CONTINUE'
        )

    def abort(self) -> dict[str, Any]:
        """仅响应人工显式中止并保留现场；不自动丢弃 candidate 或 commit。"""
        session = self.ensure_session(event='status')
        change = current_change(session)
        assert change is not None
        if change['state'] in {'INTEGRATED', 'TERMINAL_BLOCKED'}:
            return self._payload(session, status=PASS, code='ABORT_IDEMPOTENT', idempotent=True)
        session = self.store.transition(
            self.session_id,
            str(change['changeId']),
            target_state='TERMINAL_BLOCKED',
            expected=_cas(change),
            updates={'terminalReasonCode': 'ABORTED_BY_USER'},
        )
        return self._payload(
            session,
            status=TERMINAL_BLOCKED,
            code='ABORTED_BY_USER',
            next_action='MANUAL_RECOVERY',
        )


def map_controller_exception(exc: BaseException) -> LifecycleError:
    """集中映射 store/lock/CAS/Candidate 错误，移除 generic HANDOFF_REQUIRED。"""
    if isinstance(exc, LifecycleError):
        return exc
    if isinstance(exc, (ChangeStoreBusyError, LockBusyError)):
        return LifecycleError(BUSY_RETRYABLE, 'LOCK_BUSY', str(exc))
    if isinstance(exc, (ChangeStoreCorruptionError, LockInvariantError)):
        return LifecycleError(TERMINAL_BLOCKED, 'REGISTRY_CORRUPT', str(exc))
    if isinstance(exc, (FileNotFoundError, subprocess.TimeoutExpired)):
        return LifecycleError(CAPABILITY_RETRYABLE, 'CAPABILITY_UNAVAILABLE', str(exc))
    if isinstance(exc, (SessionctlError, subprocess.CalledProcessError)):
        return LifecycleError(TERMINAL_BLOCKED, 'SESSION_INVARIANT', str(exc))
    if isinstance(exc, (CompareAndSetError, LifecycleModelError, ChangeStoreError, CandidateError)):
        return LifecycleError(TERMINAL_BLOCKED, 'LIFECYCLE_INVARIANT', str(exc))
    return LifecycleError(INTERNAL_ERROR, 'CONTROLLER_BUG', f'{type(exc).__name__}: {exc}')
