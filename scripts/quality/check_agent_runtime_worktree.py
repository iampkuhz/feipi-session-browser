#!/usr/bin/env python3
"""Deterministic checker for main-session git worktree isolation."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_runtime.worktree import assignment_marker_path, check_session_worktree, expected_worktree_path, read_assignment_marker  # noqa: E402
from scripts.claude_hooks.paths import identity_from_values  # noqa: E402
from scripts.claude_hooks.policy.bash_policy import is_read_only_command  # noqa: E402

GATE_NAME = 'agentRuntimeWorktree'



# 运行测试用 git 命令。
def _run(cmd, cwd):
    """参数：
        cmd: 命令参数列表。
        cwd: 命令工作目录。

    返回：
        命令成功时无返回；失败时抛出异常。
    """
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)



# 创建临时 git 仓库。
def _git_repo(tmp_root):
    """参数：
        tmp_root: 临时目录根路径。

    返回：
        已初始化并提交初始文件的仓库路径。
    """
    repo = tmp_root / 'repo'
    repo.mkdir()
    _run(['git', 'init'], repo)
    _run(['git', 'config', 'user.email', 'agent-runtime@example.invalid'], repo)
    _run(['git', 'config', 'user.name', 'Agent Runtime Gate'], repo)
    (repo / 'README.md').write_text('# synthetic repo\n', encoding='utf-8')
    _run(['git', 'add', 'README.md'], repo)
    _run(['git', 'commit', '-m', 'initial'], repo)
    return repo



# 记录断言错误。
def _expect(condition, message, errors):
    """参数：
        condition: 期望为真的条件。
        message: 条件失败时记录的错误信息。
        errors: 错误收集列表。

    返回：
        无返回，失败时向 errors 追加信息。
    """
    if not condition:
        errors.append(message)



# 运行 worktree 隔离检查。
def run_checks():
    """返回：
        检查失败信息列表；空列表表示通过。
    """
    errors = []
    old_root = os.environ.get('FEIPI_AGENT_WORKTREE_ROOT')
    try:
        with tempfile.TemporaryDirectory(prefix='agent-runtime-worktree-') as tmp:
            tmp_root = Path(tmp).resolve()
            os.environ['FEIPI_AGENT_WORKTREE_ROOT'] = str(tmp_root / 'worktrees')
            repo = _git_repo(tmp_root)
            identities = [identity_from_values(client, 'same-session', '') for client in ('claude', 'codex', 'qoder')]
            paths = [expected_worktree_path(repo, identity) for identity in identities]
            _expect(len(set(paths)) == 3, 'same session id across clients did not produce 3 worktrees', errors)
            _expect(all(not path.is_relative_to(repo) for path in paths), 'worktree path was inside repo root', errors)
            _expect(is_read_only_command(f'cd {paths[0]} && git status --short'), 'simple cd read-only command was not recognized', errors)
            _expect(not is_read_only_command("git status $(python3 -c 'print(1)')"), 'shell expansion was treated as read-only', errors)
            session_a = expected_worktree_path(repo, identity_from_values('codex', 'session-a', ''))
            session_b = expected_worktree_path(repo, identity_from_values('codex', 'session-b', ''))
            _expect(session_a != session_b, 'same client sessions share one worktree path', errors)
            claude = identity_from_values('claude', 'session-a', '')
            decision = check_session_worktree(repo, claude, create=True)
            _expect(decision.required and not decision.allowed and decision.assigned, 'main creation did not block shared checkout', errors)
            _expect(Path(decision.expected_root).is_dir(), 'git worktree was not created', errors)
            _expect(read_assignment_marker(repo, claude) is not None, 'assignment marker missing', errors)
            retry = check_session_worktree(Path(decision.expected_root), claude, create=False)
            _expect(retry.allowed and retry.assigned, 'assigned worktree did not allow retry', errors)
            subagent = identity_from_values('claude', 'session-a', 'worker-1')
            subagent_wrong = check_session_worktree(repo, subagent, create=True)
            _expect(not subagent_wrong.allowed, 'subagent outside assigned worktree was not blocked', errors)
            _expect(assignment_marker_path(repo, subagent) == assignment_marker_path(repo, claude), 'subagent did not share main assignment marker', errors)
            qoder = identity_from_values('qoder', 'session-q', '')
            legacy = check_session_worktree(repo, qoder, create=False)
            _expect(legacy.allowed and not legacy.assigned, 'legacy no-assignment stop should not be blocked', errors)
            qoder_created = check_session_worktree(repo, qoder, create=True)
            qoder_stop = check_session_worktree(repo, qoder, create=False)
            _expect(not qoder_created.allowed and not qoder_stop.allowed, 'Qoder assignment did not enforce wrong checkout', errors)
            missing = check_session_worktree(repo, identity_from_values('codex', '', ''), create=True)
            _expect(missing.allowed and not missing.required, 'missing session id unexpectedly allocated worktree', errors)
    finally:
        if old_root is None:
            os.environ.pop('FEIPI_AGENT_WORKTREE_ROOT', None)
        else:
            os.environ['FEIPI_AGENT_WORKTREE_ROOT'] = old_root
    return errors



# 解析命令行入口。
def main():
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
