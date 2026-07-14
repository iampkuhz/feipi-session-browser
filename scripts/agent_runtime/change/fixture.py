"""负责 Change controller 内部的 managed fixture supervisor。

只通过单一 identity endpoint 判定 readiness；不负责构建 distribution、不读取真实
Session，也不依赖调用端持有后台 shell/PTTY。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from scripts.agent_runtime.storage import StorageError, load_json, utc_now

from .runtime import (
    ManagedProcess,
    ManagedProcessError,
    log_tail,
    process_identity_status,
    spawn_managed,
    terminate_managed_group,
    write_atomic_json,
)

FIXTURE_SCHEMA_VERSION = 1
DEFAULT_IDENTITY_ENDPOINT = '/__feipi_fixture_identity'
DEFAULT_READINESS_TIMEOUT_SECONDS = 15.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 1.0
IDENTITY_RESPONSE_LIMIT = 16 * 1024
READY_POLL_SECONDS = 0.05


class FixtureError(RuntimeError):
    """Fixture 的结构化错误；stdout 仅需返回 code/reason/tail/artifact path。"""

    code = 'INTERNAL_ERROR'

    def __init__(self, reason_code: str, message: str, *, tail: str = '') -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.tail = tail


class FixtureUnavailableError(FixtureError):
    """启动、提前退出或 readiness timeout 等可修复 capability 失败。"""

    code = 'CAPABILITY_RETRYABLE'


class FixtureIdentityError(FixtureError):
    """Server/PID/PGID 身份不匹配时关闭失败，绝不向未知进程发送 signal。"""

    code = 'TERMINAL_BLOCKED'


@dataclass(frozen=True, slots=True)
class FixtureHandle:
    """供 Gate 使用的最小 fixture 事实；完整诊断保存在 state/log artifact。"""

    base_url: str
    managed: bool
    resumed: bool
    pid: int
    process_start_time: str
    process_group_id: int
    log_path: str
    state_path: str


@dataclass(frozen=True, slots=True)
class IdentityProbe:
    """保存单次 identity 探测结果；不负责重试或进程清理。"""

    status: str
    observed: dict[str, Any]
    error: str


def _normalized_base_url(base_url: str, *, managed: bool) -> str:
    raw = base_url.strip().rstrip('/')
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise FixtureIdentityError('FIXTURE_URL_INVALID', 'fixture URL must be absolute HTTP(S)')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise FixtureIdentityError(
            'FIXTURE_URL_INVALID', 'fixture URL cannot contain credentials, query or fragment'
        )
    if managed and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise FixtureIdentityError(
            'FIXTURE_URL_INVALID', 'managed fixture must bind a loopback address'
        )
    return raw


class FixtureSupervisor:
    """持久化并恢复一个 run-scoped fixture process group。

    state 先原子记录 PID/start/PGID，再轮询唯一 identity endpoint。恢复时必须区分
    dead leader、orphan group、PID reuse 和 live owner；Session 结束由 ``cleanup``
    确定性回收整个 group。
    """

    def __init__(
        self,
        runtime_dir: Path | str,
        *,
        expected_identity: Mapping[str, Any],
        identity_endpoint: str = DEFAULT_IDENTITY_ENDPOINT,
        readiness_timeout: float = DEFAULT_READINESS_TIMEOUT_SECONDS,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        if not expected_identity:
            raise ValueError('fixture expected_identity must be non-empty')
        if (
            not identity_endpoint.startswith('/')
            or '?' in identity_endpoint
            or '#' in identity_endpoint
        ):
            raise ValueError('fixture identity_endpoint must be an absolute URL path')
        if readiness_timeout <= 0 or request_timeout <= 0:
            raise ValueError('fixture timeouts must be positive')
        self.runtime_dir = Path(runtime_dir)
        self.state_path = self.runtime_dir / 'fixture-state.json'
        self.expected_identity = dict(expected_identity)
        self.identity_endpoint = identity_endpoint
        self.readiness_timeout = min(readiness_timeout, DEFAULT_READINESS_TIMEOUT_SECONDS)
        self.request_timeout = request_timeout
        self._process: ManagedProcess | None = None

    def _load_state(self) -> dict[str, Any]:
        """安全读取 fixture state；损坏或未知 schema 一律关闭失败。"""
        try:
            state = load_json(self.state_path, {})
        except (OSError, StorageError, ValueError) as exc:
            raise FixtureIdentityError(
                'FIXTURE_STATE_CORRUPT', f'fixture state cannot be read safely: {exc}'
            ) from exc
        if state and state.get('schemaVersion') != FIXTURE_SCHEMA_VERSION:
            raise FixtureIdentityError(
                'FIXTURE_STATE_SCHEMA_UNSUPPORTED', 'fixture state schema is unsupported'
            )
        return state

    def _persist(self, state: Mapping[str, Any]) -> None:
        write_atomic_json(self.state_path, state)

    def _probe(self, base_url: str, *, timeout: float | None = None) -> IdentityProbe:
        url = f'{base_url}{self.identity_endpoint}'
        request = urllib.request.Request(url, headers={'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(
                request, timeout=self.request_timeout if timeout is None else timeout
            ) as response:
                if response.status != 200:
                    return IdentityProbe('UNAVAILABLE', {}, f'HTTP {response.status}')
                raw = response.read(IDENTITY_RESPONSE_LIMIT + 1)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            return IdentityProbe('UNAVAILABLE', {}, str(exc))
        if len(raw) > IDENTITY_RESPONSE_LIMIT:
            return IdentityProbe('MISMATCH', {}, 'identity response exceeds 16 KiB')
        try:
            observed = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return IdentityProbe('MISMATCH', {}, f'invalid identity JSON: {exc}')
        if not isinstance(observed, dict):
            return IdentityProbe('MISMATCH', {}, 'identity response must be an object')
        status = 'MATCH' if observed == self.expected_identity else 'MISMATCH'
        return IdentityProbe(status, observed, '' if status == 'MATCH' else 'identity mismatch')

    def _managed_handle(self, state: Mapping[str, Any], *, resumed: bool) -> FixtureHandle:
        return FixtureHandle(
            base_url=str(state['baseUrl']),
            managed=True,
            resumed=resumed,
            pid=int(state['pid']),
            process_start_time=str(state['processStartTime']),
            process_group_id=int(state['processGroupId']),
            log_path=str(state['logPath']),
            state_path=str(self.state_path),
        )

    def _terminate(self, state: dict[str, Any], *, status: str, reason: str) -> None:
        try:
            cleaned = terminate_managed_group(
                pid=int(state['pid']),
                process_start_time=str(state['processStartTime']),
                process_group_id=int(state['processGroupId']),
                process=self._process.process if self._process is not None else None,
            )
        except (KeyError, TypeError, ValueError, ManagedProcessError) as exc:
            raise FixtureIdentityError(
                'FIXTURE_PROCESS_IDENTITY_UNPROVEN',
                str(exc),
                tail=log_tail(state.get('logPath', '')),
            ) from exc
        if not cleaned:
            raise FixtureError(
                'FIXTURE_PROCESS_GROUP_SURVIVED',
                'fixture process group survived TERM/KILL cleanup',
                tail=log_tail(state.get('logPath', '')),
            )
        state.update(status=status, reason=reason, finishedAt=utc_now())
        self._persist(state)
        self._process = None

    def _await_ready(
        self,
        state: dict[str, Any],
        *,
        resumed: bool,
    ) -> FixtureHandle:
        deadline = time.monotonic() + self.readiness_timeout
        while time.monotonic() < deadline:
            if self._process is not None and self._process.process.poll() is not None:
                code = self._process.process.returncode
                self._terminate(state, status='FAILED', reason='FIXTURE_EARLY_EXIT')
                raise FixtureUnavailableError(
                    'FIXTURE_EARLY_EXIT',
                    f'managed fixture exited before readiness: {code}',
                    tail=log_tail(state['logPath']),
                )
            identity = process_identity_status(int(state['pid']), str(state['processStartTime']))
            if identity == 'PID_REUSED' or identity == 'UNKNOWN':
                raise FixtureIdentityError(
                    'FIXTURE_PROCESS_IDENTITY_UNPROVEN',
                    f'managed fixture process identity: {identity}',
                    tail=log_tail(state['logPath']),
                )
            if identity == 'DEAD':
                self._terminate(state, status='FAILED', reason='FIXTURE_EARLY_EXIT')
                raise FixtureUnavailableError(
                    'FIXTURE_EARLY_EXIT',
                    'managed fixture exited before readiness',
                    tail=log_tail(state['logPath']),
                )
            remaining = max(0.01, deadline - time.monotonic())
            probe = self._probe(str(state['baseUrl']), timeout=min(self.request_timeout, remaining))
            if probe.status == 'MATCH':
                state.update(status='READY', readyAt=utc_now(), observedIdentity=probe.observed)
                self._persist(state)
                return self._managed_handle(state, resumed=resumed)
            if probe.status == 'MISMATCH':
                state['observedIdentity'] = probe.observed
                self._terminate(state, status='FAILED', reason='FIXTURE_IDENTITY_MISMATCH')
                raise FixtureIdentityError(
                    'FIXTURE_IDENTITY_MISMATCH',
                    probe.error,
                    tail=log_tail(state['logPath']),
                )
            time.sleep(READY_POLL_SECONDS)
        self._terminate(state, status='FAILED', reason='FIXTURE_READINESS_TIMEOUT')
        raise FixtureUnavailableError(
            'FIXTURE_READINESS_TIMEOUT',
            f'managed fixture did not become ready within {self.readiness_timeout:g} seconds',
            tail=log_tail(state['logPath']),
        )

    def start_managed(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | str,
        base_url: str,
        env: Mapping[str, str | None] | None = None,
    ) -> FixtureHandle:
        """启动或恢复 controller-owned fixture；绝不读取隐式 ``BASE_URL``。"""
        selected_url = _normalized_base_url(base_url, managed=True)
        resumed = self.resume()
        if resumed is not None:
            if resumed.base_url != selected_url:
                raise FixtureIdentityError(
                    'FIXTURE_URL_CHANGED', 'active managed fixture uses another base URL'
                )
            return resumed
        log_path = self.runtime_dir / f'fixture-{time.time_ns()}.log'
        child_env = dict(env or {})
        child_env['BASE_URL'] = selected_url
        try:
            managed = spawn_managed(argv, cwd=cwd, env=child_env, log_path=log_path)
        except ManagedProcessError as exc:
            raise FixtureUnavailableError(
                'FIXTURE_START_FAILED', str(exc), tail=log_tail(log_path)
            ) from exc
        self._process = managed
        state = {
            'schemaVersion': FIXTURE_SCHEMA_VERSION,
            'mode': 'MANAGED',
            'status': 'STARTING',
            'pid': managed.pid,
            'processStartTime': managed.process_start_time,
            'processGroupId': managed.process_group_id,
            'baseUrl': selected_url,
            'identityEndpoint': self.identity_endpoint,
            'expectedIdentity': self.expected_identity,
            'logPath': managed.log_path,
            'statePath': str(self.state_path),
            'commandFingerprint': managed.command_fingerprint,
            'environmentFingerprint': managed.environment_fingerprint,
            'startedAt': managed.started_at,
        }
        self._persist(state)
        return self._await_ready(state, resumed=False)

    def use_external(self, *, base_url: str) -> FixtureHandle:
        """仅验证调用端显式提供的 external URL；不回退、启动或猜测 server。"""
        selected_url = _normalized_base_url(base_url, managed=False)
        state = self._load_state()
        if state.get('mode') == 'MANAGED' and state.get('status') in {'STARTING', 'READY'}:
            raise FixtureIdentityError(
                'FIXTURE_MANAGED_PROCESS_ACTIVE', 'cannot replace an active managed fixture'
            )
        probe = self._probe(selected_url)
        external = {
            'schemaVersion': FIXTURE_SCHEMA_VERSION,
            'mode': 'EXTERNAL',
            'status': 'READY' if probe.status == 'MATCH' else 'FAILED',
            'pid': 0,
            'processStartTime': '',
            'processGroupId': 0,
            'baseUrl': selected_url,
            'identityEndpoint': self.identity_endpoint,
            'expectedIdentity': self.expected_identity,
            'observedIdentity': probe.observed,
            'probeError': probe.error,
            'logPath': '',
            'statePath': str(self.state_path),
            'checkedAt': utc_now(),
        }
        self._persist(external)
        if probe.status == 'UNAVAILABLE':
            raise FixtureUnavailableError(
                'EXTERNAL_FIXTURE_UNAVAILABLE', f'external fixture unavailable: {probe.error}'
            )
        if probe.status != 'MATCH':
            raise FixtureIdentityError('EXTERNAL_FIXTURE_IDENTITY_MISMATCH', probe.error)
        return FixtureHandle(
            base_url=selected_url,
            managed=False,
            resumed=False,
            pid=0,
            process_start_time='',
            process_group_id=0,
            log_path='',
            state_path=str(self.state_path),
        )

    def resume(self) -> FixtureHandle | None:
        """恢复 live fixture，或原地回收 dead leader 遗留的 orphan process group。"""
        state = self._load_state()
        if not state or state.get('mode') != 'MANAGED':
            return None
        if state.get('status') not in {'STARTING', 'READY'}:
            return None
        required = {
            'pid',
            'processStartTime',
            'processGroupId',
            'baseUrl',
            'logPath',
            'identityEndpoint',
            'expectedIdentity',
        }
        if not required.issubset(state):
            raise FixtureIdentityError(
                'FIXTURE_STATE_CORRUPT', 'managed fixture state lacks process identity'
            )
        if (
            state['identityEndpoint'] != self.identity_endpoint
            or state['expectedIdentity'] != self.expected_identity
        ):
            raise FixtureIdentityError(
                'FIXTURE_IDENTITY_CONTRACT_CHANGED', 'fixture identity contract changed on resume'
            )
        identity = process_identity_status(int(state['pid']), str(state['processStartTime']))
        if identity == 'PID_REUSED' or identity == 'UNKNOWN':
            raise FixtureIdentityError(
                'FIXTURE_PROCESS_IDENTITY_UNPROVEN', f'cannot resume fixture process: {identity}'
            )
        if identity == 'DEAD':
            # Leader 已死仍可能留下同 PGID 孙进程；在原 runtime dir 回收，不建恢复 worktree。
            self._terminate(state, status='STOPPED', reason='FIXTURE_ORPHAN_RECLAIMED')
            return None
        return self._await_ready(state, resumed=True)

    def cleanup(self) -> bool:
        """Session/controller 结束时确定性清理 managed fixture；external server 从不触碰。"""
        state = self._load_state()
        if not state or state.get('mode') != 'MANAGED':
            return False
        if state.get('status') == 'STOPPED':
            return True
        self._terminate(state, status='STOPPED', reason='FIXTURE_CLEANUP')
        return True
