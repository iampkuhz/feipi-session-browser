#!/usr/bin/env python3
"""Deterministic checker for managed run-record worktree isolation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.harness.primary_session import resolve_runtime_root, validate_run_write_authorization  # noqa: E402

GATE_NAME = 'agentRuntimeWorktree'


# 运行命令并捕获输出。
def _run(cmd: list[str], cwd: Path, *, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    """参数：
        cmd: 命令和参数。
        cwd: 工作目录。
        env: 可选环境变量覆盖。
        check: 是否要求 exit 0。

    返回：
        subprocess.CompletedProcess 对象。
    """
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=cwd, env=merged, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


# 创建合成 Git 仓库。
def _git_repo(tmp_root: Path) -> Path:
    """参数：
        tmp_root: 临时根目录。

    返回：
        初始化后的合成仓库路径。
    """
    repo = tmp_root / 'repo'
    repo.mkdir()
    _run(['git', 'init', '-b', 'main_java'], repo)
    _run(['git', 'config', 'user.email', 'agent-runtime@example.invalid'], repo)
    _run(['git', 'config', 'user.name', 'Agent Runtime Gate'], repo)
    (repo / 'README.md').write_text('# synthetic repo\n', encoding='utf-8')
    _run(['git', 'add', 'README.md'], repo)
    _run(['git', 'commit', '-m', 'initial'], repo)
    return repo


# 调用 sessionctl。
def _ctl(repo: Path, runtime_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """参数：
        repo: 合成仓库路径。
        runtime_root: runtime 根目录。
        args: sessionctl 参数。
        check: 是否要求 exit 0。

    返回：
        subprocess.CompletedProcess 对象。
    """
    return _run([sys.executable, str(ROOT / 'scripts/harness/sessionctl.py'), '--repo-root', str(repo), *args], ROOT, env={'FEIPI_AGENT_RUNTIME_ROOT': str(runtime_root)}, check=check)


# 记录断言失败。
def _expect(condition: bool, message: str, errors: list[str]) -> None:
    """参数：
        condition: 断言条件。
        message: 失败信息。
        errors: 错误列表。
    """
    if not condition:
        errors.append(message)


# 执行 deterministic worktree 隔离检查。
def run_checks() -> list[str]:
    """返回：
        检查失败信息列表。
    """
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix='agent-runtime-worktree-') as tmp:
        tmp_root = Path(tmp).resolve()
        runtime_root = tmp_root / 'runtime'
        old_runtime = os.environ.get('FEIPI_AGENT_RUNTIME_ROOT')
        os.environ['FEIPI_AGENT_RUNTIME_ROOT'] = str(runtime_root)
        repo = _git_repo(tmp_root)
        first = json.loads(_ctl(repo, runtime_root, 'create', '--client', 'codex', '--task-id', 'task-a', '--change-id', 'runtime-check', '--base-ref', 'main_java', '--allowed-path', 'docs', '--worktree-parent', str(tmp_root / 'worktrees')).stdout)
        second = json.loads(_ctl(repo, runtime_root, 'create', '--client', 'qoder', '--task-id', 'task-b', '--change-id', 'runtime-check', '--base-ref', 'main_java', '--allowed-path', 'scripts', '--worktree-parent', str(tmp_root / 'worktrees')).stdout)
        _expect(first['worktreeRoot'] != second['worktreeRoot'], 'two managed runs share a worktree', errors)
        _expect(first['branch'] and second['branch'] and first['branch'] != second['branch'], 'managed runs did not get unique named branches', errors)
        _expect(_run(['git', '-C', first['worktreeRoot'], 'branch', '--show-current'], repo).stdout.strip() == first['branch'], 'first worktree is detached or branch mismatch', errors)
        _ctl(repo, runtime_root, 'bind-session', '--run-id', first['runId'], '--session-id', 'session-a', '--client', 'codex', '--cwd', first['worktreeRoot'])
        ok, reasons, _ = validate_run_write_authorization(Path(first['worktreeRoot']), client='codex', session_id='session-a', run_id=first['runId'], candidate_paths=['docs/a.md'])
        _expect(ok, 'assigned worktree write was not authorized: ' + '; '.join(reasons), errors)
        ok, reasons, _ = validate_run_write_authorization(repo, client='codex', session_id='session-a', run_id=first['runId'], candidate_paths=['docs/a.md'])
        _expect(not ok and any('cwd realpath' in item for item in reasons), 'primary checkout write was not blocked for managed run', errors)
        collision = _ctl(repo, runtime_root, 'create', '--client', 'claude', '--task-id', 'task-c', '--change-id', 'runtime-check', '--base-ref', 'main_java', '--allowed-path', 'docs/sub', '--worktree-root', first['worktreeRoot'], '--branch', 'agent/claude/collision', check=False)
        _expect(collision.returncode != 0, 'same worktree second writer was not blocked', errors)
        _expect(resolve_runtime_root(repo) == runtime_root.resolve(), 'runtime root resolution failed', errors)
        if old_runtime is None:
            os.environ.pop('FEIPI_AGENT_RUNTIME_ROOT', None)
        else:
            os.environ['FEIPI_AGENT_RUNTIME_ROOT'] = old_runtime
    return errors


# CLI 入口。
def main() -> int:
    """返回：
        进程退出码。
    """
    errors = run_checks()
    if errors:
        for error in errors:
            print(f'[{GATE_NAME}] FAIL: {error}', file=sys.stderr)
        return 1
    print(f'[{GATE_NAME}] PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
