#!/usr/bin/env python3
"""在临时 linked worktree 中验证、提交并本地集成单次 Agent 变更。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.harness import sessionctl  # noqa: E402


# 运行 Git 命令并返回文本结果。
def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """参数：
        repo: Git checkout 根目录。
        *args: Git 子命令参数。
        check: 命令失败时是否抛出异常。

    返回：
        Git 子进程结果。
    """

    return sessionctl.git(repo, *args, check=check)


# 将 NUL 分隔的 Git 路径输出转换为集合。
def _nul_paths(output: str) -> set[str]:
    """参数：
        output: Git 的 NUL 分隔路径输出。

    返回：
        非空仓库相对路径集合。
    """

    return {value for value in output.split("\0") if value}


# 收集相对 HEAD 的全部 tracked 与 untracked 变更。
def _changed_paths(repo: Path) -> set[str]:
    """参数：
        repo: Git checkout 根目录。

    返回：
        不包含 ignored 文件的实际变更路径集合。
    """

    tracked = _nul_paths(
        _git(repo, "diff", "--name-only", "--no-renames", "-z", "HEAD", "--").stdout
    )
    untracked = _nul_paths(
        _git(repo, "ls-files", "--others", "--exclude-standard", "-z", "--").stdout
    )
    return tracked | untracked


# 收集 index 中相对 HEAD 的路径。
def _staged_paths(repo: Path) -> set[str]:
    """参数：
        repo: Git checkout 根目录。

    返回：
        index 中相对 HEAD 的路径集合。
    """

    return _nul_paths(
        _git(repo, "diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD", "--").stdout
    )


# 规范化并校验用户声明的仓库相对路径。
def _normalize_files(values: Sequence[str]) -> set[str]:
    """参数：
        values: CLI 传入的仓库相对路径。

    返回：
        规范化后的非空路径集合。
    """

    result: set[str] = set()
    for value in values:
        path = PurePosixPath(value)
        if not value or value.startswith("/") or path.is_absolute() or ".." in path.parts:
            raise sessionctl.SessionctlError(f"invalid repository-relative file: {value!r}")
        normalized = path.as_posix()
        if normalized in {"", "."}:
            raise sessionctl.SessionctlError(f"invalid repository-relative file: {value!r}")
        result.add(normalized)
    if not result:
        raise sessionctl.SessionctlError("at least one --file is required")
    return result


# 判断路径是否落入运行记录的禁止范围。
def _is_forbidden(path: str, forbidden: Sequence[object]) -> bool:
    """参数：
        path: 待判断的仓库相对路径。
        forbidden: run record 中的禁止路径列表。

    返回：
        路径等于或位于禁止路径下时返回 true。
    """

    return any(
        path == str(root).rstrip("/") or path.startswith(f"{str(root).rstrip('/')}/")
        for root in forbidden
        if str(root).rstrip("/")
    )


# 检查自动提交前不可降级的 checkout 与归因条件。
def _validate_preconditions(repo: Path, record: Mapping[str, object], expected: set[str]) -> None:
    """参数：
        repo: 当前运行的检出目录。
        record: 运行时注册表中的运行记录。
        expected: 显式归因文件集合。

    返回：
        条件满足时无返回值；否则抛出阻断异常。
    """

    checkout = Path(str(record.get("checkoutRoot") or "")).resolve()
    primary = Path(str(record.get("primaryRepoRoot") or "")).resolve()
    target = str(record.get("targetBranch") or "")
    branch = _git(repo, "branch", "--show-current").stdout.strip()
    initial = record.get("initialDirtySnapshot")
    if repo.resolve() != checkout:
        raise sessionctl.SessionctlError("selected checkout does not match run checkout")
    if record.get("checkoutKind") != "linked-worktree":
        raise sessionctl.SessionctlError("automatic completion requires a linked worktree")
    if not branch or bool(record.get("detached")):
        raise sessionctl.SessionctlError("automatic completion requires a named branch")
    if branch != str(record.get("branch") or "") or branch == target:
        raise sessionctl.SessionctlError("run branch is missing, changed, or equals target branch")
    if not isinstance(initial, Mapping) or bool(initial.get("dirty")):
        raise sessionctl.SessionctlError("initial dirty baseline cannot be safely attributed")
    if not primary.exists():
        raise sessionctl.SessionctlError("primary checkout missing")
    if _git(primary, "branch", "--show-current").stdout.strip() != target:
        raise sessionctl.SessionctlError("primary checkout is not on the recorded target branch")
    if _git(primary, "status", "--porcelain").stdout:
        raise sessionctl.SessionctlError("primary checkout dirty")
    if _staged_paths(repo):
        raise sessionctl.SessionctlError("pre-existing staged changes cannot be safely attributed")
    forbidden = record.get("forbiddenPaths")
    forbidden_values = forbidden if isinstance(forbidden, list) else []
    blocked = sorted(path for path in expected if _is_forbidden(path, forbidden_values))
    if blocked:
        raise sessionctl.SessionctlError(f"forbidden files cannot be committed: {blocked}")
    actual = _changed_paths(repo)
    if actual != expected:
        raise sessionctl.SessionctlError(
            f"explicit file scope does not match Git changes: expected={sorted(expected)}, "
            f"actual={sorted(actual)}"
        )


# 调用一次共享 Stop 并要求生成当前 Git snapshot 的 PASS receipt。
def _run_stop(repo: Path, run_id: str) -> int:
    """参数：
        repo: 当前运行的检出目录。
        run_id: Registry run 标识符。

    返回：
        Stop 命令退出码。
    """

    return sessionctl.cmd_stop(
        argparse.Namespace(
            repo_root=str(repo),
            run_id=run_id,
            handoff_on_failure=True,
        )
    )


# 执行验证、精确提交、二次验证和本地 finalize。
def complete_change(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的命令行参数。

    返回：
        完成并集成时返回零；阻断或需要 handoff 时返回非零。
    """

    repo = sessionctl.repo_root_from_arg(args.repo_root)
    expected = _normalize_files(args.file)
    registry = sessionctl.Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
    _validate_preconditions(repo, record, expected)

    if _run_stop(repo, args.run_id) != 0:
        return 2

    with registry.locked():
        record = registry.load_run(args.run_id)
    _validate_preconditions(repo, record, expected)
    _git(repo, "add", "-A", "--", ":/")
    staged = _staged_paths(repo)
    if staged != expected:
        raise sessionctl.SessionctlError(
            f"staged file scope mismatch: expected={sorted(expected)}, staged={sorted(staged)}"
        )
    if _git(repo, "diff", "--quiet", "--", check=False).returncode != 0:
        raise sessionctl.SessionctlError("unstaged changes remain after exact staging")
    if _git(repo, "ls-files", "--others", "--exclude-standard", "--").stdout:
        raise sessionctl.SessionctlError("untracked files remain after exact staging")

    commit = _git(repo, "commit", "-m", args.message, check=False)
    if commit.returncode != 0:
        raise sessionctl.SessionctlError(commit.stderr.strip() or "git commit failed")
    if _git(repo, "status", "--porcelain").stdout:
        raise sessionctl.SessionctlError(
            "checkout changed during commit; preserving branch for handoff"
        )
    if _run_stop(repo, args.run_id) != 0:
        return 2
    return sessionctl.cmd_finalize(argparse.Namespace(repo_root=str(repo), run_id=args.run_id))


# 构造命令行解析器。
def build_parser() -> argparse.ArgumentParser:
    """返回：
    complete-change 命令行解析器。
    """

    parser = argparse.ArgumentParser(
        description="Validate, commit, revalidate, and locally finalize one Agent change"
    )
    parser.add_argument("--repo-root", help="Git checkout root; defaults to cwd")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--file", action="append", required=True, help="exact changed file")
    return parser


# 运行命令行入口并统一输出阻断状态。
def main(argv: Sequence[str] | None = None) -> int:
    """参数：
        argv: 可选命令行参数。

    返回：
        命令退出码。
    """

    args = build_parser().parse_args(argv)
    try:
        return complete_change(args)
    except (sessionctl.SessionctlError, subprocess.CalledProcessError, OSError) as exc:
        print(json.dumps({"status": "HANDOFF_REQUIRED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
