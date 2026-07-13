#!/usr/bin/env python3
"""负责以一次 required Gate 完成本地 commit、轻量 attestation 与 integration。

不负责创建 Worktree、绕过 Gate 或远端发布；由 Harness completion CLI 在任务收口阶段调用。
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.agent_runtime.git_state import run as git  # noqa: E402
from scripts.agent_runtime.session.completion import (  # noqa: E402
    exact_files_hash,
    update_completion,
)
from scripts.agent_runtime.session.errors import SessionctlError  # noqa: E402
from scripts.agent_runtime.session.finalize import cmd_finalize  # noqa: E402
from scripts.agent_runtime.session.lifecycle import cmd_stop, repo_root_from_arg  # noqa: E402
from scripts.agent_runtime.session.registry import Registry  # noqa: E402
from scripts.gates.receipt import attest_pass_receipt, checkout_content_fingerprint  # noqa: E402
from scripts.harness.python_env import resolve_python  # noqa: E402


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """保存重 Gate 前的便宜 capability 事实。"""

    python: str
    python_version: str
    pre_commit: str
    node: str
    playwright: str
    browser: str
    java: str
    gradle: str
    fixture: str
    commit_path: str
    fixture_pid: int = 0
    fixture_managed: bool = False
    heavy_gate_process_count: int = 0


class RetryableCompletionError(SessionctlError):
    """环境、server、timeout 或 pre-commit 能力故障，可在同一 run 修复后重试。"""

    def __init__(self, reason: str, fix_command: str) -> None:
        super().__init__(reason)
        self.fix_command = fix_command


_MANAGED_FIXTURE_PROCESSES: dict[int, subprocess.Popen[str]] = {}


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return git(repo, *args, check=check)


def _nul_paths(output: str) -> set[str]:
    return {value for value in output.split('\0') if value}


def _changed_paths(repo: Path) -> set[str]:
    tracked = _nul_paths(
        _git(repo, 'diff', '--name-only', '--no-renames', '-z', 'HEAD', '--').stdout
    )
    untracked = _nul_paths(
        _git(repo, 'ls-files', '--others', '--exclude-standard', '-z', '--').stdout
    )
    return tracked | untracked


def _staged_paths(repo: Path) -> set[str]:
    return _nul_paths(
        _git(repo, 'diff', '--cached', '--name-only', '--no-renames', '-z', 'HEAD', '--').stdout
    )


def _normalize_files(values: Sequence[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        path = PurePosixPath(value)
        if not value or value.startswith('/') or path.is_absolute() or '..' in path.parts:
            raise SessionctlError(f'invalid repository-relative file: {value!r}')
        normalized = path.as_posix()
        if normalized in {'', '.'}:
            raise SessionctlError(f'invalid repository-relative file: {value!r}')
        result.add(normalized)
    if not result:
        raise SessionctlError('at least one --file is required')
    return result


def _is_forbidden(path: str, forbidden: Sequence[object]) -> bool:
    return any(
        path == str(root).rstrip('/') or path.startswith(f'{str(root).rstrip("/")}/')
        for root in forbidden
        if str(root).rstrip('/')
    )


def _validate_preconditions(repo: Path, record: Mapping[str, object], expected: set[str]) -> None:
    """只检查 source identity/归因/scope；primary 与 detached 不属于 commit 前置。"""
    checkout = Path(str(record.get('checkoutRoot') or '')).resolve()
    if repo.resolve() != checkout:
        raise SessionctlError('selected checkout does not match run checkout')
    begin = record.get('changeBegin')
    if not isinstance(begin, Mapping) or begin.get('status') != 'ATTESTED':
        raise SessionctlError('START_NOT_ENFORCED: begin-change attestation is required')
    initial = record.get('initialDirtySnapshot')
    adopted = bool(begin.get('adopted'))
    if not isinstance(initial, Mapping) or (bool(initial.get('dirty')) and not adopted):
        raise SessionctlError('initial dirty baseline cannot be safely attributed')
    forbidden = record.get('forbiddenPaths')
    forbidden_values = forbidden if isinstance(forbidden, list) else []
    blocked = sorted(path for path in expected if _is_forbidden(path, forbidden_values))
    if blocked:
        raise SessionctlError(f'forbidden files cannot be committed: {blocked}')
    actual = _changed_paths(repo)
    if actual != expected:
        raise SessionctlError(
            f'explicit file scope does not match Git changes: expected={sorted(expected)}, '
            f'actual={sorted(actual)}'
        )
    staged = _staged_paths(repo)
    if staged and staged != expected:
        raise SessionctlError(
            f'pre-existing staged scope mismatch: expected={sorted(expected)}, staged={sorted(staged)}'
        )


def _command_path(repo: Path, name: str) -> Path | None:
    local = repo / '.venv' / 'bin' / name
    if local.is_file() and os.access(local, os.X_OK):
        return local.resolve()
    found = shutil.which(name)
    return Path(found).resolve() if found else None


def _run_version(command: Sequence[str], *, cwd: Path) -> str:
    try:
        result = subprocess.run(
            list(command), cwd=cwd, text=True, capture_output=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RetryableCompletionError(
            f'preflight command unavailable: {command[0]}: {exc}',
            './scripts/session-browser.sh doctor',
        ) from exc
    if result.returncode != 0:
        raise RetryableCompletionError(
            f'preflight command failed: {command[0]}', './scripts/session-browser.sh doctor'
        )
    return (result.stdout or result.stderr).strip().splitlines()[0]


def _browser_binary() -> Path | None:
    configured = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    roots = (
        [Path(configured)]
        if configured
        else [
            Path.home() / 'Library/Caches/ms-playwright',
            Path.home() / '.cache/ms-playwright',
        ]
    )
    names = {'chrome-headless-shell', 'chrome', 'headless_shell'}
    return next(
        (
            path
            for root in roots
            if root.is_dir()
            for path in root.glob('**/*')
            if path.is_file() and path.name in names and os.access(path, os.X_OK)
        ),
        None,
    )


def _fixture_urls(base_url: str) -> tuple[str, ...]:
    root = base_url.rstrip('/')
    return (
        f'{root}/dashboard',
        f'{root}/sessions/claude_code/hifi-viz-session-001',
        f'{root}/sessions/claude_code/long-session-001',
    )


def _fixture_is_ready(base_url: str) -> bool:
    try:
        for url in _fixture_urls(base_url):
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status != 200:
                    return False
    except (OSError, urllib.error.URLError):
        return False
    return True


def _check_external_server(base_url: str) -> str:
    if not _fixture_is_ready(base_url):
        raise RetryableCompletionError(
            f'fixture server identity/readiness check failed: {base_url}',
            'unset BASE_URL to use the node-managed synthetic fixture server',
        )
    return base_url


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(('127.0.0.1', 0))
        return int(server.getsockname()[1])


def _stop_managed_fixture(pid: int) -> None:
    """停止本次 preflight 创建的 synthetic fixture，且不触碰外部 server。"""
    process = _MANAGED_FIXTURE_PROCESSES.pop(pid, None)
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _start_managed_fixture_server(repo: Path, node: Path, starter: Path) -> tuple[str, int]:
    base_url = f'http://127.0.0.1:{_free_loopback_port()}'
    env = dict(os.environ, BASE_URL=base_url)
    process = subprocess.Popen(
        [str(node), str(starter)],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _MANAGED_FIXTURE_PROCESSES[process.pid] = process
    atexit.register(_stop_managed_fixture, process.pid)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if _fixture_is_ready(base_url):
            return base_url, process.pid
        time.sleep(0.5)
    _stop_managed_fixture(process.pid)
    raise RetryableCompletionError(
        'managed synthetic Java fixture server did not become ready',
        './gradlew :java:app-cli:installDist --console=plain',
    )


def _project_python(repo: Path) -> tuple[Path, str]:
    try:
        selected = resolve_python(repo)
    except SystemExit as exc:
        raise RetryableCompletionError(str(exc), 'uv sync --frozen') from exc
    resolved_name = shutil.which(selected) if os.sep not in selected else selected
    executable = Path(resolved_name or selected).expanduser().resolve()
    version = _run_version(
        [str(executable), '-c', 'import sys; print(sys.version.split()[0])'], cwd=repo
    )
    try:
        major, minor, *_ = (int(part) for part in version.split('.'))
    except ValueError as exc:
        raise RetryableCompletionError(
            f'cannot parse project Python version: {version}', 'uv sync --frozen'
        ) from exc
    if (major, minor) != (3, 12):
        raise RetryableCompletionError(
            f'project Python >=3.12,<3.13 required, observed {version}',
            'uv sync --frozen',
        )
    return executable, version


def cheap_preflight(repo: Path) -> PreflightResult:
    """一次性检查 capability；失败前绝不进入 required Gate。"""
    project_python, project_python_version = _project_python(repo)
    pre_commit = _command_path(repo, 'pre-commit')
    node = _command_path(repo, 'node')
    java = _command_path(repo, 'java')
    playwright = repo / 'node_modules' / '.bin' / 'playwright'
    gradle = repo / 'gradlew'
    fixture_source = repo / 'tests' / 'fixtures' / 'generate-session-fixtures.js'
    fixture_starter = repo / 'tests' / 'playwright' / 'start-java-fixture-server.js'
    launcher = repo / 'java' / 'app-cli' / 'build' / 'install' / 'app-cli' / 'bin' / 'app-cli'
    if not pre_commit:
        raise RetryableCompletionError('pre-commit capability missing', 'uv sync --frozen')
    if not node or not playwright.is_file():
        raise RetryableCompletionError('Node/Playwright capability missing', 'npm ci')
    browser = _browser_binary()
    if not browser:
        raise RetryableCompletionError(
            'Playwright browser binary missing', 'npx playwright install chromium'
        )
    if not java or not gradle.is_file() or not os.access(gradle, os.X_OK):
        raise RetryableCompletionError('Java/Gradle capability missing', './gradlew --version')
    if not fixture_source.is_file() or not fixture_starter.is_file():
        raise RetryableCompletionError(
            'synthetic fixture manifest/starter missing',
            'git checkout -- tests/fixtures tests/playwright/start-java-fixture-server.js',
        )
    fixture_text = fixture_source.read_text(encoding='utf-8')
    if 'synthetic: true' not in fixture_text or 'baseTimestampMs' not in fixture_text:
        raise RetryableCompletionError(
            'synthetic fixture lacks explicit marker or fixed clock',
            'git checkout -- tests/fixtures/generate-session-fixtures.js',
        )
    if not launcher.is_file():
        raise RetryableCompletionError(
            'Java fixture distribution is not ready',
            './gradlew :java:app-cli:installDist --console=plain',
        )
    _run_version([str(pre_commit), '--version'], cwd=repo)
    node_version = _run_version([str(node), '--version'], cwd=repo)
    java_version = _run_version([str(java), '-version'], cwd=repo)
    configured_server = os.environ.get('BASE_URL', '')
    if configured_server:
        server = _check_external_server(configured_server)
        fixture_pid = 0
        fixture_managed = False
    else:
        server, fixture_pid = _start_managed_fixture_server(repo, node, fixture_starter)
        fixture_managed = True
    path_parts = [str(project_python.parent), str(repo / '.venv' / 'bin')]
    path_parts.extend(os.environ.get('PATH', '').split(os.pathsep))
    commit_path = os.pathsep.join(dict.fromkeys(part for part in path_parts if part))
    return PreflightResult(
        python=str(project_python),
        python_version=project_python_version,
        pre_commit=str(pre_commit),
        node=f'{node}:{node_version}',
        playwright=str(playwright.resolve()),
        browser=str(browser.resolve()),
        java=f'{java}:{java_version}',
        gradle=str(gradle.resolve()),
        fixture=server,
        commit_path=commit_path,
        fixture_pid=fixture_pid,
        fixture_managed=fixture_managed,
    )


def _stage_exact(repo: Path, expected: set[str]) -> None:
    payload = b''.join(os.fsencode(path) + b'\0' for path in sorted(expected))
    result = subprocess.run(
        [
            'git',
            '-C',
            str(repo),
            'add',
            '-A',
            '--pathspec-from-file=-',
            '--pathspec-file-nul',
        ],
        input=payload,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SessionctlError(
            result.stderr.decode(errors='replace').strip() or 'exact stage failed'
        )
    staged = _staged_paths(repo)
    if staged != expected:
        raise SessionctlError(
            f'staged file scope mismatch: expected={sorted(expected)}, staged={sorted(staged)}'
        )
    if _git(repo, 'diff', '--quiet', '--', check=False).returncode != 0:
        raise SessionctlError('unstaged changes remain after exact staging')
    if _git(repo, 'ls-files', '--others', '--exclude-standard', '--').stdout:
        raise SessionctlError('untracked files remain after exact staging')


def _run_pre_commit(repo: Path, preflight: PreflightResult, expected: set[str]) -> None:
    env = dict(os.environ, PATH=preflight.commit_path)
    result = subprocess.run(
        [preflight.pre_commit, 'run'],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        raise RetryableCompletionError(
            'pre-commit did not stabilize the staged candidate',
            f'{preflight.pre_commit} run',
        )
    if _staged_paths(repo) != expected or _changed_paths(repo) != expected:
        raise RetryableCompletionError(
            'pre-commit changed candidate content or scope', f'{preflight.pre_commit} run'
        )
    if _git(repo, 'diff', '--quiet', '--', check=False).returncode != 0:
        raise RetryableCompletionError(
            'pre-commit left unstaged content', f'{preflight.pre_commit} run'
        )


def _run_stop(repo: Path, run_id: str, base_url: str) -> int:
    """让唯一 candidate-mode Stop 复用已就绪 fixture，并在返回后恢复环境。"""
    previous = os.environ.get('BASE_URL')
    os.environ['BASE_URL'] = base_url
    try:
        return cmd_stop(
            argparse.Namespace(
                repo_root=str(repo),
                run_id=run_id,
                handoff_on_failure=False,
                candidate_mode=True,
            )
        )
    finally:
        if previous is None:
            os.environ.pop('BASE_URL', None)
        else:
            os.environ['BASE_URL'] = previous


def _receipt_attestation(
    repo: Path, validation: Mapping[str, object], expected: set[str]
) -> list[str]:
    """重算非空 PASS receipts 与 summary artifact，返回全部 fail-closed 错误。"""
    errors: list[str] = []
    raw_paths = validation.get('gateReceiptPaths') or []
    if not isinstance(raw_paths, list) or not raw_paths:
        errors.append('required Gate produced no target PASS receipts')
    for raw in raw_paths if isinstance(raw_paths, list) else []:
        valid, reason = attest_pass_receipt(Path(str(raw)), repo, changed_files=sorted(expected))
        if not valid:
            errors.append(f'invalid PASS receipt ({reason}): {raw}')
    artifact = Path(str(validation.get('gateArtifactPath') or ''))
    if not artifact.is_file():
        errors.append('Gate artifact missing after commit')
    else:
        try:
            if json.loads(artifact.read_text(encoding='utf-8')).get('status') != 'PASS':
                errors.append('Gate artifact is not PASS')
        except (OSError, json.JSONDecodeError):
            errors.append('Gate artifact is corrupt')
    return errors


def _attest_commit(
    repo: Path,
    *,
    old_head: str,
    candidate_tree: str,
    expected: set[str],
    result_ref: str,
    validation: Mapping[str, object],
) -> tuple[str, dict[str, object]]:
    commit_sha = _git(repo, 'rev-parse', 'HEAD').stdout.strip()
    committed_tree = _git(repo, 'rev-parse', 'HEAD^{tree}').stdout.strip()
    parent = _git(repo, 'rev-parse', 'HEAD^').stdout.strip()
    committed_paths = _nul_paths(
        _git(
            repo, 'diff-tree', '--no-commit-id', '--name-only', '--no-renames', '-r', '-z', 'HEAD'
        ).stdout
    )
    ref_value = _git(repo, 'rev-parse', '--verify', result_ref).stdout.strip()
    errors = []
    if committed_tree != candidate_tree:
        errors.append('commit tree differs from validated candidate')
    if parent != old_head:
        errors.append('commit parent differs from oldHead')
    if committed_paths != expected:
        errors.append('committed paths differ from exact manifest')
    if _git(repo, 'status', '--porcelain').stdout:
        errors.append('checkout is not clean after commit')
    if ref_value != commit_sha:
        errors.append('result ref does not point to commit')
    if str(validation.get('candidateTree') or '') != candidate_tree:
        errors.append('Stop receipt candidateTree mismatch')
    errors.extend(_receipt_attestation(repo, validation, expected))
    if errors:
        raise SessionctlError('; '.join(errors))
    return commit_sha, {
        'status': 'PASS',
        'candidateTree': candidate_tree,
        'commitTree': committed_tree,
        'parent': parent,
        'committedPaths': sorted(committed_paths),
        'resultRef': result_ref,
        'receiptContentFingerprint': checkout_content_fingerprint(repo),
        'heavyProcessCount': 0,
    }


def _failure_state(repo: Path, run_id: str, exc: BaseException) -> None:
    """按 commit 是否已生成单调记录 retryable 或 handoff 状态，绝不抹除 SHA。"""
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(run_id)
    completion = record.get('completion')
    committed = isinstance(completion, Mapping) and bool(completion.get('commitSha'))
    if committed:
        update_completion(repo, run_id, 'HANDOFF_REQUIRED', reason=str(exc))
        return
    if isinstance(exc, RetryableCompletionError):
        update_completion(
            repo,
            run_id,
            'BLOCKED_RETRYABLE',
            reason=str(exc),
            fixCommand=exc.fix_command,
            heavyGateProcessCount=0,
        )
    else:
        update_completion(repo, run_id, 'HANDOFF_REQUIRED', reason=str(exc))


def complete_change(args: argparse.Namespace) -> int:
    """完成 preflight、exact stage、单次 Gate、commit、attestation 和本地集成。"""
    repo = repo_root_from_arg(args.repo_root)
    expected = _normalize_files(args.file)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
    completion = record.get('completion') if isinstance(record.get('completion'), dict) else {}
    if completion.get('state') == 'INTEGRATED':
        print(
            json.dumps(
                {
                    'status': 'INTEGRATED',
                    'commitSha': completion.get('commitSha'),
                    'idempotent': True,
                }
            )
        )
        return 0
    if completion.get('state') in {'COMMITTED', 'HANDOFF_REQUIRED'} and completion.get('commitSha'):
        return cmd_finalize(argparse.Namespace(repo_root=str(repo), run_id=args.run_id))

    _validate_preconditions(repo, record, expected)
    preflight = cheap_preflight(repo)
    old_head = _git(repo, 'rev-parse', 'HEAD').stdout.strip()
    _stage_exact(repo, expected)
    _run_pre_commit(repo, preflight, expected)
    candidate_tree = _git(repo, 'write-tree').stdout.strip()
    manifest_hash = exact_files_hash(expected)
    previous_validation = completion.get('validationReceipt') or {}
    reusable = bool(
        completion.get('state') == 'VALIDATED_CANDIDATE'
        and completion.get('candidateTree') == candidate_tree
        and completion.get('exactFilesHash') == manifest_hash
        and isinstance(previous_validation, Mapping)
        and previous_validation.get('status') == 'PASS'
    )
    record = update_completion(
        repo,
        args.run_id,
        'STAGED',
        oldHead=old_head,
        exactFiles=sorted(expected),
        exactFilesHash=manifest_hash,
        candidateTree=candidate_tree,
        preflight=preflight.__dict__
        if hasattr(preflight, '__dict__')
        else {field: getattr(preflight, field) for field in preflight.__dataclass_fields__},
        targetHeadObserved=str(record.get('targetHeadAtBootstrap') or ''),
    )
    validation = previous_validation
    if not reusable:
        try:
            if _run_stop(repo, args.run_id, preflight.fixture) != 0:
                raise RetryableCompletionError(
                    'required Stop/Gate did not PASS',
                    f'python3 scripts/harness/complete_change.py --run-id {args.run_id} ...',
                )
        finally:
            if preflight.fixture_managed:
                _stop_managed_fixture(preflight.fixture_pid)
        with registry.locked():
            validated = registry.load_run(args.run_id)
        validation = validated.get('stopValidation')
        if not isinstance(validation, Mapping) or validation.get('status') != 'PASS':
            raise RetryableCompletionError(
                'required Stop produced no PASS receipt',
                f'python3 scripts/harness/complete_change.py --run-id {args.run_id} ...',
            )
        if validation.get('candidateTree') != candidate_tree:
            raise RetryableCompletionError(
                'validated candidate tree changed',
                f'python3 scripts/harness/complete_change.py --run-id {args.run_id} ...',
            )
        previous_runs = int((validated.get('completion') or {}).get('heavyGateRuns') or 0)
        update_completion(
            repo,
            args.run_id,
            'VALIDATED_CANDIDATE',
            validationReceipt=dict(validation),
            heavyGateRuns=previous_runs + 1,
        )
    elif preflight.fixture_managed:
        _stop_managed_fixture(preflight.fixture_pid)

    result_ref = f'refs/heads/codex/result/{args.run_id}'
    existing_ref = _git(repo, 'rev-parse', '--verify', result_ref, check=False).stdout.strip()
    if existing_ref:
        raise SessionctlError(f'result ref unexpectedly exists before commit: {existing_ref}')
    env = dict(os.environ, PATH=preflight.commit_path)
    commit = subprocess.run(
        ['git', '-C', str(repo), 'commit', '-m', args.message],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if commit.returncode != 0:
        raise RetryableCompletionError(
            commit.stderr.strip() or 'git commit failed',
            f'git -C {repo} commit -m {json.dumps(args.message)}',
        )
    commit_sha = _git(repo, 'rev-parse', 'HEAD').stdout.strip()
    update_completion(
        repo,
        args.run_id,
        'COMMITTED',
        commitSha=commit_sha,
        intendedResultRef=result_ref,
        postCommitHeavyProcessCount=0,
    )
    _git(repo, 'update-ref', result_ref, commit_sha, '0' * 40)
    update_completion(repo, args.run_id, 'COMMITTED', resultRef=result_ref)
    with registry.locked():
        after_commit = registry.load_run(args.run_id)
    validation = (after_commit.get('completion') or {}).get('validationReceipt') or validation
    commit_sha, attestation = _attest_commit(
        repo,
        old_head=old_head,
        candidate_tree=candidate_tree,
        expected=expected,
        result_ref=result_ref,
        validation=validation,
    )
    update_completion(
        repo,
        args.run_id,
        'COMMITTED',
        commitSha=commit_sha,
        resultRef=result_ref,
        commitAttestation=attestation,
        postCommitHeavyProcessCount=0,
    )
    return cmd_finalize(argparse.Namespace(repo_root=str(repo), run_id=args.run_id))


def build_parser() -> argparse.ArgumentParser:
    """构造只接受 run、commit message 与 exact file manifest 的 CLI parser。"""
    parser = argparse.ArgumentParser(
        description='Preflight, stage, validate once, commit, attest, and locally integrate'
    )
    parser.add_argument('--repo-root', help='Git checkout root; defaults to cwd')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--message', required=True)
    parser.add_argument('--file', action='append', required=True, help='exact changed file')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行 completion CLI，并把可恢复失败映射为稳定机器状态。"""
    args = build_parser().parse_args(argv)
    repo: Path | None = None
    try:
        repo = repo_root_from_arg(args.repo_root)
        return complete_change(args)
    except (SessionctlError, subprocess.CalledProcessError, OSError) as exc:
        completion: Mapping[str, object] = {}
        if repo is not None:
            try:
                _failure_state(repo, args.run_id, exc)
                registry = Registry(repo)
                with registry.locked():
                    record = registry.load_run(args.run_id)
                raw_completion = record.get('completion')
                if isinstance(raw_completion, Mapping):
                    completion = raw_completion
            except Exception:
                pass
        committed = bool(completion.get('commitSha'))
        status = (
            'COMMITTED_HANDOFF_REQUIRED'
            if committed
            else 'BLOCKED_RETRYABLE'
            if isinstance(exc, RetryableCompletionError)
            else 'HANDOFF_REQUIRED'
        )
        payload = {'status': status, 'reason': str(exc)}
        if committed:
            payload.update(
                {
                    'commitSha': completion.get('commitSha'),
                    'resultRef': completion.get('resultRef') or completion.get('intendedResultRef'),
                }
            )
        if isinstance(exc, RetryableCompletionError):
            payload['fixCommand'] = exc.fix_command
            payload['heavyGateProcessCount'] = 0
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
