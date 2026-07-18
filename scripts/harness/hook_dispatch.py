#!/usr/bin/env python3
"""三平台 Hook 的唯一输入适配器。

本文件只负责校验 checkout、选择项目 Python、保留 stdin 并把事件转发给
唯一 Hook 权威入口；不承载策略、evidence 或 Gate 业务。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.harness.python_env import (  # noqa: E402
    ProjectPythonNotReadyError,
    resolve_python,
)

CLIENTS = frozenset({'claude', 'codex', 'qoder'})
TRACE_PHASES = frozenset({'ENTERED', 'PYTHON_NOT_READY', 'DISPATCHED', 'FAILED'})
TRACE_PHASE_LIMIT = 8
TRACE_FILE_LIMIT = 256


class BootstrapTraceError(RuntimeError):
    """表示最早期 trace 无法安全写入非 tracked runtime 目录。"""


def trusted_checkout() -> tuple[Path, Path]:
    """用单次 Git 查询校验 checkout root，并解析跨 worktree 的 common-dir。"""

    result = subprocess.run(
        [
            'git',
            '-C',
            str(ROOT),
            'rev-parse',
            '--show-toplevel',
            '--path-format=absolute',
            '--git-common-dir',
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=0.8,
    )
    lines = result.stdout.splitlines()
    observed = Path(lines[0]).resolve() if result.returncode == 0 and len(lines) == 2 else None
    if observed != ROOT:
        raise RuntimeError('hook dispatcher is not inside a trusted Git checkout root')
    common_dir = Path(lines[1]).resolve()
    return ROOT, common_dir


def trusted_root() -> Path:
    """保留公开 helper；实际 checkout 校验由 ``trusted_checkout`` 完成。"""

    return trusted_checkout()[0]


def _private_trace_directory(common_dir: Path) -> Path:
    """在系统临时 runtime root 下创建属主私有、跨 worktree 的 trace 目录。"""

    override = os.environ.get('FEIPI_AGENT_RUNTIME_ROOT', '').strip()
    if override:
        repo_runtime = Path(override).expanduser().resolve()
        private_roots = (repo_runtime,)
    else:
        repo_key = hashlib.sha256(str(common_dir).encode('utf-8')).hexdigest()
        runtime_base = Path(tempfile.gettempdir()).resolve() / 'feipi-agent-runtime'
        repo_runtime = runtime_base / repo_key
        private_roots = (runtime_base, repo_runtime)
    trace_dir = repo_runtime / 'hook-bootstrap'
    for component in (*reversed(trace_dir.parents), trace_dir):
        if component == Path(component.anchor) or not os.path.lexists(component):
            continue
        if stat.S_ISLNK(component.lstat().st_mode):
            raise BootstrapTraceError('bootstrap trace path contains symbolic link')
    trace_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    for path in (*private_roots, trace_dir):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise BootstrapTraceError('unsafe bootstrap trace directory')
        if hasattr(os, 'geteuid') and metadata.st_uid != os.geteuid():
            raise BootstrapTraceError('bootstrap trace directory owner mismatch')
        path.chmod(0o700)
    return trace_dir


def _trace_session_key() -> str:
    """只对宿主 Session 提示做摘要，trace 不保留原始标识。"""

    raw = next(
        (
            os.environ.get(name, '').strip()
            for name in ('CODEX_THREAD_ID', 'CLAUDE_SESSION_ID', 'QODER_SESSION_ID')
            if os.environ.get(name, '').strip()
        ),
        'anonymous',
    )
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _record_bootstrap_trace(
    common_dir: Path,
    *,
    client: str,
    event: str,
    phase: str,
    error_type: str = '',
) -> None:
    """原子保留有界 phase；禁止接收 payload、命令、prompt 或环境正文。"""

    if phase not in TRACE_PHASES:
        raise BootstrapTraceError('unsupported bootstrap trace phase')
    directory = _private_trace_directory(common_dir)
    session_key = _trace_session_key()
    identity = hashlib.sha256(f'{client}\0{event}\0{session_key}'.encode()).hexdigest()
    path = directory / f'{identity}.json'
    existing: dict[str, object] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding='utf-8'))
            existing = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            existing = {}
    phases = list(existing.get('phases') or []) if isinstance(existing.get('phases'), list) else []
    phases.append(
        {
            'phase': phase,
            'atUnixMs': int(time.time() * 1000),
            'errorType': error_type or None,
        }
    )
    payload = {
        'schemaVersion': 1,
        'client': client,
        'event': event,
        'sessionKey': session_key,
        'phases': phases[-TRACE_PHASE_LIMIT:],
    }
    temporary = directory / f'.{identity}.{uuid.uuid4().hex}.tmp'
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0),
            0o600,
        )
        encoded = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode()
        os.write(descriptor, encoded)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        files = sorted(directory.glob('*.json'), key=lambda item: item.stat().st_mtime_ns)
        for expired in files[:-TRACE_FILE_LIMIT]:
            expired.unlink(missing_ok=True)
    except OSError as exc:
        raise BootstrapTraceError('bootstrap trace write failed') from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _executable_path(command: str) -> Path | None:
    candidate = shutil.which(command) if os.sep not in command else command
    return Path(candidate).expanduser().absolute() if candidate else None


def ensure_project_python(argv: list[str]) -> None:
    """如当前解释器不是项目解析结果，保留 stdin 并原地 re-exec。"""

    current = Path(sys.executable).expanduser().absolute()
    if os.environ.get('FEIPI_HOOK_DISPATCH_REEXEC') == '1':
        expected = os.environ.get('FEIPI_HOOK_PROJECT_PYTHON', '').strip()
        if expected and _executable_path(expected) == current:
            return
        raise RuntimeError('project Python re-exec did not converge')
    selected = resolve_python(ROOT)
    if _executable_path(selected) == current:
        return
    env = dict(
        os.environ,
        FEIPI_HOOK_DISPATCH_REEXEC='1',
        FEIPI_HOOK_PROJECT_PYTHON=str(_executable_path(selected) or selected),
    )
    os.execvpe(selected, [selected, str(Path(__file__).resolve()), *argv], env)


def dispatch(client: str, event: str, payload: str, *, common_dir: Path | None = None) -> int:
    """保留 payload 字节内容并转发到唯一 Hook 入口。"""
    from scripts.agent_runtime.events.adapter import RUNTIME_EVENTS

    if client not in CLIENTS or event not in RUNTIME_EVENTS:
        raise ValueError(f'unsupported hook dispatch: client={client} event={event}')
    os.environ['FEIPI_AGENT_CLIENT'] = client
    os.environ.setdefault('FEIPI_HOOK_CWD', os.getcwd())
    original_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(payload)
        from scripts.agent_runtime.hook_entry import main as hook_main

        if common_dir is not None:
            _record_bootstrap_trace(
                common_dir,
                client=client,
                event=event,
                phase='DISPATCHED',
            )

        return hook_main([event])
    finally:
        sys.stdin = original_stdin


def main(argv: list[str] | None = None) -> int:
    """解析 client/event，选择项目 Python 并完整转发 stdin。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', choices=sorted(CLIENTS), required=True)
    parser.add_argument('--event', required=True)
    args = parser.parse_args(argv)
    common_dir: Path | None = None
    try:
        _root, common_dir = trusted_checkout()
        _record_bootstrap_trace(
            common_dir,
            client=args.client,
            event=args.event,
            phase='ENTERED',
        )
        ensure_project_python(argv if argv is not None else sys.argv[1:])
        return dispatch(args.client, args.event, sys.stdin.read(), common_dir=common_dir)
    except ProjectPythonNotReadyError as exc:
        if common_dir is not None:
            try:
                _record_bootstrap_trace(
                    common_dir,
                    client=args.client,
                    event=args.event,
                    phase='PYTHON_NOT_READY',
                    error_type=type(exc).__name__,
                )
            except BootstrapTraceError:
                pass
        print(exc.render(), file=sys.stderr)
        return 2
    except BootstrapTraceError:
        print('BLOCKED_BOOTSTRAP_TRACE_NOT_READY', file=sys.stderr)
        print(f'repoRoot: {ROOT}', file=sys.stderr)
        return 2
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        if common_dir is not None:
            try:
                _record_bootstrap_trace(
                    common_dir,
                    client=args.client,
                    event=args.event,
                    phase='FAILED',
                    error_type=type(exc).__name__,
                )
            except BootstrapTraceError:
                pass
        print('BLOCKED_HOOK_DISPATCH_FAILED', file=sys.stderr)
        print(f'repoRoot: {ROOT}', file=sys.stderr)
        print(f'errorType: {type(exc).__name__}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
