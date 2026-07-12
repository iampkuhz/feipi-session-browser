#!/usr/bin/env python3
"""验证客户端 checkout 采用与 writer lease 隔离的黑盒检查器。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GATE_NAME = "agentRuntimeWorktree"

from scripts.quality._trigger import add_changed_files_arg, parse_changed_files, skip_if_not_triggered

TRIGGER_PATTERNS = [
    'AGENTS.md', 'CLAUDE.md',
    '.agents/**', '.claude/**', '.codex/**', '.qoder/**',
    'skills/**', 'harness/**',
    'scripts/claude_hooks/**/*.py', 'scripts/hooks/**/*.py',
    'scripts/agent_hooks/**/*.py', 'scripts/harness/**/*.py',
    'scripts/harness/**/*.sh', 'scripts/quality/**/*.py',
]


# 在合成仓库中执行命令并捕获输出。
def _run(
    cmd: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """参数：
        cmd: 待执行命令。
        cwd: 命令工作目录。
        env: 附加环境变量。
        check: 非零退出时是否抛出异常。

    返回：
        完整子进程结果。
    """

    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=merged,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


# 创建一个主 checkout 和一个 provider-owned linked checkout。
def _git_repo(tmp_root: Path) -> tuple[Path, Path, str]:
    """参数：
        tmp_root: 合成仓库根目录。

    返回：
        主 checkout、linked checkout 路径与旧 default branch HEAD。
    """

    repo = tmp_root / "repo"
    linked = tmp_root / "provider checkout"
    repo.mkdir()
    _run(["git", "init", "-b", "main"], repo)
    _run(["git", "config", "user.email", "agent-runtime@example.invalid"], repo)
    _run(["git", "config", "user.name", "Agent Runtime Gate"], repo)
    (repo / "README.md").write_text("# synthetic repo\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo)
    _run(["git", "commit", "-m", "initial"], repo)
    default_head = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    _run(["git", "update-ref", "refs/remotes/origin/main", default_head], repo)
    _run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
        repo,
    )
    _run(["git", "switch", "-c", "main_java"], repo)
    (repo / "README.md").write_text("# current local branch\n", encoding="utf-8")
    _run(["git", "commit", "-am", "current local branch"], repo)
    _run(
        ["git", "worktree", "add", "-b", "provider-linked", str(linked), "HEAD"],
        repo,
    )
    return repo.resolve(), linked.resolve(), default_head


# 通过公开 launcher 创建并检查 Codex CLI/App checkout。
def _launch_checkout(
    repo: Path,
    tmp_root: Path,
    client: str,
) -> tuple[Path, dict]:
    """参数：
        repo: 主工作区检出路径。
        tmp_root: 合成测试临时目录。
        client: Codex 客户端 surface。

    返回：
        launcher 创建的 checkout 与机器可读证据。
    """

    name = f"gate-{client}"
    root = tmp_root / "codex worktrees"
    result = _run(
        [
            sys.executable,
            str(ROOT / "scripts/harness/launch_codex_worktree.py"),
            "--client",
            client,
            "--name",
            name,
            "--repo-root",
            str(repo),
            "--worktree-root",
            str(root),
            "--no-launch",
        ],
        ROOT,
        check=False,
    )
    return (root / name).resolve(), _payload(result, f"launch {client}")


# 使用隔离 Runtime Registry 调用公开 sessionctl CLI。
def _ctl(
    repo: Path,
    runtime_root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """参数：
        repo: 主 Git 仓库。
        runtime_root: 隔离 Runtime 根目录。
        args: sessionctl 子命令参数。
        check: 非零退出时是否抛出异常。

    返回：
        sessionctl 子进程结果。
    """

    return _run(
        [
            sys.executable,
            str(ROOT / "scripts/harness/sessionctl.py"),
            "--repo-root",
            str(repo),
            *args,
        ],
        ROOT,
        env={"FEIPI_AGENT_RUNTIME_ROOT": str(runtime_root)},
        check=check,
    )


# 解析一个成功的 sessionctl JSON 响应。
def _payload(result: subprocess.CompletedProcess[str], operation: str) -> dict:
    """参数：
        result: sessionctl 子进程结果。
        operation: 用于错误信息的操作名。

    返回：
        解析后的 JSON 对象。

    异常：
        RuntimeError: 命令失败或输出不是 JSON 对象。
    """

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise RuntimeError(f"{operation} failed: {detail}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError(f"{operation} returned a non-object payload")
    return value


# 构造基于 checkout 事实的 Session 身份参数。
def _identity_args(client: str, session_id: str, checkout: Path) -> tuple[str, ...]:
    """参数：
        client: 客户端名称。
        session_id: Session 标识。
        checkout: 已选 checkout 路径。

    返回：
        lease CLI 的身份参数。
    """

    return (
        "--client",
        client,
        "--session-id",
        session_id,
        "--cwd",
        str(checkout),
    )


# 在 provider 选定 checkout 后 bootstrap 一个 Session。
def _bootstrap(
    repo: Path,
    runtime_root: Path,
    client: str,
    session_id: str,
    checkout: Path,
) -> subprocess.CompletedProcess[str]:
    """参数：
        repo: 主 Git 仓库。
        runtime_root: 隔离 Runtime 根目录。
        client: 客户端名称。
        session_id: Session 标识。
        checkout: 客户端已选 checkout。

    返回：
        bootstrap 子进程结果。
    """

    return _ctl(
        repo,
        runtime_root,
        "bootstrap",
        *_identity_args(client, session_id, checkout),
        "--hook-event",
        "SessionStart",
        "--checkout-creator",
        client,
        check=False,
    )


# 读取 provider 可见的 Git worktree 集合。
def _worktree_roots(repo: Path) -> list[Path]:
    """参数：
        repo: 主 Git 仓库。

    返回：
        规范化 worktree 路径列表。
    """

    output = _run(["git", "worktree", "list", "--porcelain"], repo).stdout
    return sorted(
        Path(line.removeprefix("worktree ")).resolve()
        for line in output.splitlines()
        if line.startswith("worktree ")
    )


# 记录一条失败的验收断言。
def _expect(condition: bool, message: str, errors: list[str]) -> None:
    """参数：
        condition: 验收条件。
        message: 失败提示。
        errors: 错误汇总列表。
    """

    if not condition:
        errors.append(message)


# 通过公开命令验证 reader 共享与延迟 writer lease。
def run_checks() -> list[str]:
    """返回：
        黑盒验收错误列表；全部通过时为空。
    """

    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agent-runtime-worktree-") as tmp:
        tmp_root = Path(tmp).resolve()
        runtime_root = tmp_root / "runtime"
        repo, linked, default_head = _git_repo(tmp_root)
        current_head = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
        _expect(
            settings.get("worktree", {}).get("baseRef") == "head",
            "Claude worktree.baseRef is not pinned to head",
            errors,
        )
        cli_checkout, cli_launch = _launch_checkout(repo, tmp_root, "codex-cli")
        app_checkout, app_launch = _launch_checkout(repo, tmp_root, "codex-app")
        for label, checkout, evidence in (
            ("codex-cli", cli_checkout, cli_launch),
            ("codex-app", app_checkout, app_launch),
        ):
            _expect(
                evidence.get("primarySnapshot", {}).get("head_commit") == current_head
                and _run(["git", "rev-parse", "HEAD"], checkout).stdout.strip() == current_head
                and current_head != default_head,
                f"{label} launcher did not use the exact current primary HEAD",
                errors,
            )
        mismatch = tmp_root / "wrong default checkout"
        _run(
            ["git", "worktree", "add", "-b", "codex/wrong-default", str(mismatch), default_head],
            repo,
        )
        mismatch_result = _bootstrap(
            repo,
            runtime_root,
            "codex",
            "wrong-default-session",
            mismatch,
        )
        _expect(
            mismatch_result.returncode == 2
            and "WORKTREE_BASE_MISMATCH" in mismatch_result.stderr,
            "wrong Codex App/CLI worktree base did not fail closed",
            errors,
        )
        provider_worktrees = _worktree_roots(repo)
        _expect(
            provider_worktrees
            == sorted([repo, linked, cli_checkout, app_checkout, mismatch.resolve()]),
            "synthetic providers did not establish the expected checkout inventory",
            errors,
        )

        sessions = {
            "primary-a": ("codex", "reader-a", repo),
            "primary-b": ("claude", "reader-b", repo),
            "linked": ("qoder", "linked-reader", linked),
        }
        with ThreadPoolExecutor(max_workers=len(sessions)) as executor:
            bootstrap_results = {
                name: executor.submit(
                    _bootstrap, repo, runtime_root, client, session_id, checkout
                )
                for name, (client, session_id, checkout) in sessions.items()
            }
            bootstrapped = {
                name: _payload(future.result(), f"bootstrap {name}")
                for name, future in bootstrap_results.items()
            }

        _expect(
            all(record.get("status") == "BOOTSTRAPPED" for record in bootstrapped.values()),
            "bootstrap acquired a writer lease or returned an unexpected state",
            errors,
        )
        _expect(
            all(not record.get("writerLease") for record in bootstrapped.values()),
            "bootstrap populated writerLease before a mutation",
            errors,
        )
        _expect(
            bootstrapped["primary-a"].get("worktreeId")
            == bootstrapped["primary-b"].get("worktreeId"),
            "two readers on the same checkout received different physical identities",
            errors,
        )
        _expect(
            bootstrapped["primary-a"].get("worktreeId")
            != bootstrapped["linked"].get("worktreeId"),
            "primary and linked checkouts share a physical identity",
            errors,
        )

        with ThreadPoolExecutor(max_workers=len(sessions)) as executor:
            ready_results = {
                name: executor.submit(
                    _ctl,
                    repo,
                    runtime_root,
                    "mark-read-only-ready",
                    *_identity_args(client, session_id, checkout),
                    check=False,
                )
                for name, (client, session_id, checkout) in sessions.items()
            }
            readers = {
                name: _payload(future.result(), f"mark reader {name}")
                for name, future in ready_results.items()
            }
        _expect(
            all(record.get("status") == "READ_ONLY_READY" for record in readers.values()),
            "concurrent readers were not all read-only ready",
            errors,
        )
        _expect(
            all(not record.get("writerLease") for record in readers.values()),
            "read-only readiness acquired a writer lease",
            errors,
        )

        with ThreadPoolExecutor(max_workers=len(sessions)) as executor:
            acquire_results = {
                name: executor.submit(
                    _ctl,
                    repo,
                    runtime_root,
                    "acquire-writer-lease",
                    *_identity_args(client, session_id, checkout),
                    check=False,
                )
                for name, (client, session_id, checkout) in sessions.items()
            }
            acquired = {name: future.result() for name, future in acquire_results.items()}

        primary_successes = [
            name
            for name in ("primary-a", "primary-b")
            if acquired[name].returncode == 0
        ]
        primary_conflicts = [
            name
            for name in ("primary-a", "primary-b")
            if acquired[name].returncode != 0
        ]
        _expect(
            len(primary_successes) == 1 and len(primary_conflicts) == 1,
            "concurrent mutation attempts on one checkout did not yield one writer and one conflict",
            errors,
        )
        _expect(
            acquired["linked"].returncode == 0,
            "linked checkout could not hold a writer lease alongside the primary checkout",
            errors,
        )

        active: dict[str, dict] = {}
        if primary_successes:
            name = primary_successes[0]
            active[name] = _payload(acquired[name], f"acquire {name}")
            _expect(
                active[name].get("status") == "LOCAL_WRITER",
                "primary checkout writer did not enter LOCAL_WRITER",
                errors,
            )
        if acquired["linked"].returncode == 0:
            active["linked"] = _payload(acquired["linked"], "acquire linked")
            _expect(
                active["linked"].get("status") == "ISOLATED_WRITER",
                "linked checkout writer did not enter ISOLATED_WRITER",
                errors,
            )
        _expect(
            all(record.get("writerLease", {}).get("fencingToken") for record in active.values()),
            "active writer response is missing a fencing token",
            errors,
        )

        if primary_conflicts:
            name = primary_conflicts[0]
            conflict_record = _payload(
                _ctl(
                    repo,
                    runtime_root,
                    "status",
                    "--run-id",
                    str(bootstrapped[name]["runId"]),
                    check=False,
                ),
                f"status {name}",
            )
            _expect(
                conflict_record.get("status") == "READ_ONLY_CONFLICT"
                and not conflict_record.get("writerLease"),
                "same-checkout losing writer was not retained as a read-only conflict",
                errors,
            )

        for name, record in active.items():
            client, session_id, checkout = sessions[name]
            released = _payload(
                _ctl(
                    repo,
                    runtime_root,
                    "release-writer-lease",
                    *_identity_args(client, session_id, checkout),
                    "--epoch",
                    str(record["writerLease"]["epoch"]),
                    "--fencing-token",
                    str(record["writerLease"]["fencingToken"]),
                    "--reason",
                    "quality-gate",
                    check=False,
                ),
                f"release {name}",
            )
            _expect(
                released.get("status") == "READ_ONLY_READY"
                and not released.get("writerLease"),
                f"release {name} did not clear only its writer lease",
                errors,
            )

        _expect(
            _worktree_roots(repo) == provider_worktrees,
            "runtime created or removed a provider-owned Git worktree",
            errors,
        )
        _expect(
            linked.is_dir()
            and _run(["git", "rev-parse", "--is-inside-work-tree"], linked).stdout.strip()
            == "true",
            "provider-owned linked checkout was not preserved after release",
            errors,
        )
    return errors


# 执行检查并输出稳定的 gate 结果。
def main() -> int:
    """返回：
        所有断言通过时返回 0，否则返回 1。
    """
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
        skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)
    else:
        skip_if_not_triggered(None, TRIGGER_PATTERNS)

    try:
        errors = run_checks()
    except (json.JSONDecodeError, KeyError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print(f"[{GATE_NAME}] FAIL: {error}", file=sys.stderr)
        return 1
    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
