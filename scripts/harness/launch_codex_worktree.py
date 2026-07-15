#!/usr/bin/env python3
"""本模块负责从 primary checkout 的稳定精确 HEAD 创建 worktree 并启动 Codex。

不负责产品业务处理；由 harness 命令行或受控收口流程调用。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import TYPE_CHECKING  # noqa: E402

from scripts.agent_runtime.change.controller import (  # noqa: E402
    START_ENFORCED,
    LifecycleController,
    attest_run_start,
)
from scripts.agent_runtime.change.protocol import EXIT_CODES, encode_compact  # noqa: E402
from scripts.agent_runtime.session.contract import (  # noqa: E402
    PrimaryHeadSnapshot,
    PrimarySessionValidationError,
    capture_primary_head_snapshot,
    resolve_checkout_identity,
    resolve_git_common_dir,
)
from scripts.agent_runtime.session.lifecycle import bootstrap_session  # noqa: E402
from scripts.agent_runtime.session.registry import Registry  # noqa: E402
from scripts.agent_runtime.storage import utc_now  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class LauncherError(RuntimeError):
    """可安全展示给调用方的 launcher 阻断错误。"""

    # 保存稳定错误代码与面向用户的阻断原因。
    def __init__(self, code: str, message: str) -> None:
        """参数：
        code: 机器可读错误代码。
        message: 面向用户的阻断原因。
        """
        super().__init__(message)
        self.code = code


# 运行 Git 命令并保留可诊断的标准错误。
def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """参数：
        repo: Git checkout 路径。
        args: Git 子命令参数。
        check: 非零退出时是否抛出异常。

    返回：
        捕获输出的进程结果。
    """

    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=2,
    )


# 判断候选路径是否位于另一路径内部或与之相等。
def _is_within(candidate: Path, parent: Path) -> bool:
    """参数：
        candidate: 候选路径。
        parent: 预期父路径。

    返回：
        候选路径位于父路径内或相等时为 true。
    """

    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


# 要求 primary checkout 不包含 tracked 或 untracked 变更。
def _require_clean_primary(primary_root: Path) -> None:
    """参数：
        primary_root: primary checkout 根目录。

    异常：
        LauncherError: primary 含未提交内容时抛出。
    """

    result = _git(primary_root, "status", "--porcelain=v1", "--untracked-files=all")
    if result.stdout:
        raise LauncherError(
            "PRIMARY_DIRTY",
            "primary checkout has uncommitted changes; commit them before creating a Codex worktree",
        )


# 比较两次 snapshot，禁止分支或精确提交发生变化。
def _require_same_snapshot(
    expected: PrimaryHeadSnapshot,
    actual: PrimaryHeadSnapshot,
    *,
    phase: str,
) -> None:
    """参数：
        expected: 创建前捕获的 snapshot。
        actual: 复核得到的 snapshot。
        phase: 竞态发生阶段。

    异常：
        LauncherError: 两次 snapshot 不一致时抛出。
    """

    if expected != actual:
        raise LauncherError(
            "PRIMARY_HEAD_RACE",
            f"primary branch or HEAD changed {phase}; acquire a fresh snapshot and retry",
        )


# 解析并验证仓库外的唯一 checkout 路径。
def _resolve_target(primary_root: Path, worktree_root: str | None, name: str) -> Path:
    """参数：
        primary_root: primary checkout 根目录。
        worktree_root: 可选的外部 worktree 父目录。
        name: 唯一任务名称。

    返回：
        已验证且尚不存在的目标路径。
    """

    if not NAME_PATTERN.fullmatch(name):
        raise LauncherError(
            "INVALID_NAME",
            "--name must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}",
        )
    root = (
        Path(worktree_root).expanduser()
        if worktree_root
        else primary_root.parent / f".{primary_root.name}-codex-worktrees"
    ).resolve()
    target = (root / name).resolve()
    if _is_within(root, primary_root) or _is_within(target, primary_root):
        raise LauncherError(
            "WORKTREE_PATH_INSIDE_REPOSITORY",
            "--worktree-root must be outside the primary repository checkout",
        )
    if os.path.lexists(target):
        raise LauncherError(
            "WORKTREE_PATH_EXISTS",
            f"refusing to overwrite existing path: {target}",
        )
    if root.exists() and not root.is_dir():
        raise LauncherError("WORKTREE_ROOT_NOT_DIRECTORY", f"not a directory: {root}")
    return target


# 禁止透传参数覆盖 launcher 强制指定的 Codex checkout。
def _validate_client_args(values: Sequence[str]) -> list[str]:
    """参数：
        values: `--` 后透传参数。

    返回：
        去除分隔符后的安全参数。
    """

    args = list(values)
    if args[:1] == ["--"]:
        args = args[1:]
    for value in args:
        if value.startswith("-C") or value == "--cd" or value.startswith("--cd="):
            raise LauncherError(
                "CHECKOUT_OVERRIDE_FORBIDDEN",
                "arguments after -- must not override the launcher-selected Codex checkout",
            )
    return args


# 从精确 SHA 创建命名 worktree，并验证 Git 身份事实。
def _create_worktree(
    snapshot: PrimaryHeadSnapshot,
    target: Path,
    branch: str,
    expected_common_dir: Path,
) -> dict[str, object]:
    """参数：
        snapshot: 主工作区稳定分支和提交的快照。
        target: 新 worktree 目标路径。
        branch: 新任务分支名称。
        expected_common_dir: 预期的 Git 共享元数据目录。

    返回：
        新 checkout 的 Git 身份事实。
    """

    primary_root = Path(snapshot.primary_repo_root)
    if (
        _git(
            primary_root,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
            check=False,
        ).returncode
        == 0
    ):
        raise LauncherError(
            "WORKTREE_BRANCH_EXISTS", f"refusing to reuse existing branch: {branch}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(target):
        raise LauncherError(
            "WORKTREE_PATH_EXISTS",
            f"refusing to overwrite path created concurrently: {target}",
        )
    created = _git(
        primary_root,
        "worktree",
        "add",
        "-b",
        branch,
        str(target),
        snapshot.head_commit,
        check=False,
    )
    if created.returncode != 0:
        detail = (
            created.stderr.strip().splitlines()[-1]
            if created.stderr.strip()
            else "git worktree add failed"
        )
        raise LauncherError("WORKTREE_CREATE_FAILED", detail)

    try:
        actual_common_dir = resolve_git_common_dir(target)
        identity = resolve_checkout_identity(
            target,
            checkout_creator="codex",
            base_commit=snapshot.head_commit,
        )
    except PrimarySessionValidationError as exc:
        raise LauncherError("WORKTREE_IDENTITY_INVALID", str(exc)) from exc
    if actual_common_dir != expected_common_dir:
        raise LauncherError(
            "WORKTREE_COMMON_DIR_MISMATCH", "created checkout has a foreign Git common-dir"
        )
    if identity["checkoutKind"] != "linked-worktree":
        raise LauncherError("WORKTREE_KIND_MISMATCH", "created checkout is not a linked worktree")
    if identity["headCommit"] != snapshot.head_commit:
        raise LauncherError(
            "WORKTREE_HEAD_MISMATCH",
            "created checkout HEAD does not equal the captured primary HEAD",
        )
    if identity["branch"] != branch or identity["detached"]:
        raise LauncherError(
            "WORKTREE_BRANCH_MISMATCH", "created checkout is not on its task branch"
        )
    return identity


# 构建 Codex CLI 的真实启动命令。
def _launch_command(target: Path, client_args: Sequence[str]) -> list[str]:
    """参数：
        target: 启动器选定的检出目录。
        client_args: 允许透传的 CLI 参数。

    返回：
        Codex CLI 启动命令。
    """

    return ["codex", "-C", str(target), *client_args]


# 创建参数解析器。
def build_parser() -> argparse.ArgumentParser:
    """返回：
    launcher 命令行参数解析器。
    """

    parser = argparse.ArgumentParser(
        description=(
            "Create an external linked worktree from the stable exact HEAD of the primary "
            "checkout, then launch Codex CLI in it."
        )
    )
    parser.add_argument("--client", required=True, choices=("codex-cli",))
    parser.add_argument("--name", required=True, help="unique worktree/task name")
    parser.add_argument(
        "--session-id",
        help="host activation id; defaults to launcher:<name> and is claimed by SessionStart",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="primary or linked checkout used to discover the authoritative primary checkout",
    )
    parser.add_argument(
        "--worktree-root",
        help="external parent directory (default: a hidden sibling of the primary checkout)",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="create and validate the worktree but print the launch command instead of running it",
    )
    parser.add_argument(
        "client_args",
        nargs=argparse.REMAINDER,
        help="Codex CLI arguments after -- (codex-cli only)",
    )
    return parser


# 执行 snapshot、创建、复核与客户端启动事务。
def run(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的 launcher 参数。

    返回：
        验证或客户端进程退出码。
    """

    client_args = _validate_client_args(args.client_args)
    try:
        snapshot = capture_primary_head_snapshot(Path(args.repo_root))
        primary_root = Path(snapshot.primary_repo_root).resolve(strict=True)
        common_dir = resolve_git_common_dir(primary_root)
    except PrimarySessionValidationError as exc:
        raise LauncherError("PRIMARY_SNAPSHOT_INVALID", str(exc)) from exc

    _require_clean_primary(primary_root)
    target = _resolve_target(primary_root, args.worktree_root, args.name)
    branch = f"codex/worktree-{args.name}"

    try:
        before_create = capture_primary_head_snapshot(primary_root)
    except PrimarySessionValidationError as exc:
        raise LauncherError("PRIMARY_SNAPSHOT_INVALID", str(exc)) from exc
    _require_same_snapshot(snapshot, before_create, phase="before worktree creation")
    _require_clean_primary(primary_root)

    identity = _create_worktree(snapshot, target, branch, common_dir)

    try:
        after_create = capture_primary_head_snapshot(primary_root)
    except PrimarySessionValidationError as exc:
        raise LauncherError("PRIMARY_SNAPSHOT_INVALID", str(exc)) from exc
    _require_same_snapshot(snapshot, after_create, phase="during worktree creation")
    _require_clean_primary(primary_root)

    launcher_session = args.session_id or f"launcher:{args.name}"
    record = bootstrap_session(
        client="codex",
        session_id=launcher_session,
        cwd=target,
        hook_event="LauncherPrepare",
        checkout_creator="codex",
    )
    record = attest_run_start(
        target,
        str(record["runId"]),
        activation_source="launcher:codex-cli:before-agent",
        capability=START_ENFORCED,
    )
    # Launcher 在 agent 进程前直接建立 canonical Session/Change，Start 强制不依赖提示词。
    LifecycleController(target, record).ensure_session(event='start')
    registry = Registry(target)
    with registry.locked():
        record = registry.load_run(str(record["runId"]))
        record["launcherPending"] = True
        record["launcherPreparedAt"] = utc_now()
        registry.save_run(record)

    command = _launch_command(target, client_args)
    evidence = {
        "status": "READY" if args.no_launch else "LAUNCHING",
        "client": args.client,
        "primarySnapshot": asdict(snapshot),
        "checkout": identity,
        "runId": record["runId"],
        "startCapability": record["changeBegin"]["capability"],
        "beginBeforeAgent": True,
        "command": command,
    }
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    sys.stdout.flush()
    if args.no_launch:
        return 0
    try:
        env = dict(os.environ)
        env.update(
            {
                "FEIPI_RUN_ID": str(record["runId"]),
                "FEIPI_LAUNCH_RUN_ID": str(record["runId"]),
                "FEIPI_START_ENFORCED": "1",
            }
        )
        completed = subprocess.run(command, check=False, env=env)
    except OSError as exc:
        print(
            json.dumps(
                {"status": "FAIL", "code": "CLIENT_LAUNCH_FAILED", "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    if completed.returncode != 0:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "code": "CLIENT_EXIT_NONZERO",
                    "returnCode": completed.returncode,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return completed.returncode
    completed_record = registry.load_run(str(record["runId"]))
    controller = LifecycleController(target, completed_record)
    reconciled = controller.status()
    terminal_clean = (
        reconciled.get('state') == 'INTEGRATED' and reconciled.get('code') == 'CHANGE_INTEGRATED'
    )
    completion = (
        reconciled
        if terminal_clean
        else controller.on_stop(
            message=f"chore(agent): complete {completed_record.get('changeId') or record['runId']}"
        )
    )
    print(encode_compact(completion))
    return EXIT_CODES.get(str(completion.get('status')), 70)


# CLI 入口：将所有可预期安全失败转换成机器可读 BLOCKED。
def main(argv: Sequence[str] | None = None) -> int:
    """参数：
        argv: 可选命令行参数。

    返回：
        launcher 退出码。
    """

    try:
        return run(build_parser().parse_args(argv))
    except LauncherError as exc:
        print(
            json.dumps(
                {"status": "BLOCKED", "code": exc.code, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "code": "LAUNCHER_COMMAND_FAILED", "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
