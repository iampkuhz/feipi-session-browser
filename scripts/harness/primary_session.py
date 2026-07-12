"""本模块负责定义 primary session 运行契约并校验记录。

不负责产品业务处理；由 harness 命令行或受控收口流程调用。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - validator reports this as an environment failure.
    yaml = None


RUNTIME_DIR_NAME = "feipi-agent-runtime"
MANIFEST_PATH = Path("harness/agent-runtime.manifest.yaml")

REQUIRED_RUN_FIELDS = [
    "schemaVersion",
    "runId",
    "repoKey",
    "client",
    "taskId",
    "sessionId",
    "worktreeId",
    "checkoutRoot",
    "checkoutKind",
    "checkoutCreator",
    "gitCommonDir",
    "branch",
    "detached",
    "targetBranch",
    "primaryRepoRoot",
    "baseCommit",
    "headCommit",
    "initialDirtySnapshot",
    "changeAttribution",
    "changeId",
    "status",
    "allowedPaths",
    "forbiddenPaths",
    "writerLease",
    "hookActivation",
    "createdAt",
    "updatedAt",
]

CHECKOUT_KINDS = {"primary-checkout", "linked-worktree"}
CHECKOUT_CREATORS = {"codex", "claude", "qoder", "external", "unknown"}
RUN_STATUSES = {
    "BOOTSTRAPPED",
    "READ_ONLY_READY",
    "ISOLATED_WRITER",
    "LOCAL_WRITER",
    "READ_ONLY_CONFLICT",
    "VALIDATING",
    "VALIDATED",
    "INTEGRATING",
    "INTEGRATED",
    "HANDOFF_REQUIRED",
    "BLOCKED",
}
TERMINAL_STATUSES = {"INTEGRATED", "HANDOFF_REQUIRED", "BLOCKED"}
ACTIVE_WRITER_STATUSES = {
    "ISOLATED_WRITER",
    "LOCAL_WRITER",
}
WRITABLE_READY_STATUSES = {
    "ISOLATED_WRITER",
    "LOCAL_WRITER",
}
ALLOWED_TRANSITIONS = {
    "BOOTSTRAPPED": {
        "READ_ONLY_READY",
        "ISOLATED_WRITER",
        "LOCAL_WRITER",
        "READ_ONLY_CONFLICT",
        "VALIDATING",
        "HANDOFF_REQUIRED",
        "BLOCKED",
    },
    "READ_ONLY_READY": {
        "ISOLATED_WRITER",
        "LOCAL_WRITER",
        "READ_ONLY_CONFLICT",
        "VALIDATING",
        "HANDOFF_REQUIRED",
        "BLOCKED",
    },
    "ISOLATED_WRITER": {"READ_ONLY_READY", "VALIDATING", "HANDOFF_REQUIRED", "BLOCKED"},
    "LOCAL_WRITER": {"READ_ONLY_READY", "VALIDATING", "HANDOFF_REQUIRED", "BLOCKED"},
    "READ_ONLY_CONFLICT": {
        "ISOLATED_WRITER",
        "LOCAL_WRITER",
        "VALIDATING",
        "HANDOFF_REQUIRED",
        "BLOCKED",
    },
    "VALIDATING": {
        "READ_ONLY_READY",
        "VALIDATED",
        "ISOLATED_WRITER",
        "LOCAL_WRITER",
        "HANDOFF_REQUIRED",
        "BLOCKED",
    },
    "VALIDATED": {
        "VALIDATING",
        "ISOLATED_WRITER",
        "LOCAL_WRITER",
        "READ_ONLY_CONFLICT",
        "INTEGRATING",
        "HANDOFF_REQUIRED",
        "BLOCKED",
    },
    "INTEGRATING": {"INTEGRATED", "HANDOFF_REQUIRED", "BLOCKED"},
    "INTEGRATED": set(),
    "HANDOFF_REQUIRED": {
        "VALIDATING",
        "ISOLATED_WRITER",
        "LOCAL_WRITER",
        "READ_ONLY_CONFLICT",
        "INTEGRATING",
        "BLOCKED",
    },
    # BLOCKED 会停止自动重入；仅显式 Stop 重试可开启一次新的验证审计。
    "BLOCKED": {"VALIDATING"},
}


# 解析简化清单中的标量值。
def _parse_scalar(value: str) -> Any:
    """参数：
        value: 原始标量文本。

    返回：
        转换后的布尔值、列表、整数或字符串。
    """
    raw = value.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw == "[]":
        return []
    if raw.isdigit():
        return int(raw)
    return raw.strip('"')


# 在缺少 PyYAML 时读取简化清单。
def _load_simple_yaml(path: Path) -> dict[str, Any]:
    """参数：
        path: 清单文件路径。

    返回：
        清单内容映射。
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, raw_line in enumerate(lines):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(parent, list):
                raise PrimarySessionValidationError("fallback YAML parser expected list parent")
            parent.append(_parse_scalar(line[2:]))
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise PrimarySessionValidationError(
                f"fallback YAML parser cannot parse line: {raw_line}"
            )
        if not isinstance(parent, dict):
            raise PrimarySessionValidationError("fallback YAML parser expected mapping parent")
        if value.strip():
            parent[key] = _parse_scalar(value)
            continue
        next_is_list = False
        for later in lines[index + 1 :]:
            if later.strip() and not later.lstrip().startswith("#"):
                next_is_list = later.strip().startswith("- ")
                break
        child: Any = [] if next_is_list else {}
        parent[key] = child
        stack.append((indent, child))
    return root


class PrimarySessionValidationError(ValueError):
    """primary session manifest 或运行记录无效时抛出。"""


@dataclass(frozen=True)
class Collision:
    """保存机器可读的运行冲突事实，供 CLI 输出诊断。"""

    kind: str
    message: str
    first_run_id: str
    second_run_id: str


@dataclass(frozen=True)
class PrimaryHeadSnapshot:
    """一次稳定读取的 primary checkout 当前分支与提交。"""

    primary_repo_root: str
    branch: str
    head_commit: str


# 执行 git 命令并返回去除首尾空白的 stdout。
def _git_output(repo_root: Path, *args: str) -> str:
    """参数：
        repo_root: 仓库根目录。
        *args: 传给 git 的参数。

    返回：
        命令输出文本。
    """
    return subprocess.check_output(
        ["git", "-C", str(repo_root), *args],
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()


# 将路径规范化为不解析符号链接的绝对路径。
def _absolute_path(path: Path) -> Path:
    """参数：
        path: 待规范化的路径。

    返回：
        不解析符号链接的绝对路径。
    """
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def snapshot_path_states(
    repo_root: Path,
    paths: list[str] | tuple[str, ...] | set[str],
) -> dict[str, dict[str, Any]]:
    """为仓库相对路径生成不含原文的存在性、大小与内容哈希快照。

    删除文件也保留明确状态；无法安全归一化或读取内容时关闭失败，避免把
    无法证明相同的 baseline dirty 静默排除。
    """
    root = _absolute_path(repo_root)
    states: dict[str, dict[str, Any]] = {}
    for raw_path in sorted(set(paths)):
        normalized = raw_path.replace('\\', '/').strip('/')
        relative = Path(normalized)
        if not normalized or relative.is_absolute() or '..' in relative.parts:
            raise PrimarySessionValidationError(
                f"dirty snapshot path is not repository-relative: {raw_path!r}"
            )
        candidate = root / relative
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            states[normalized] = {"exists": False, "size": None, "sha256": None}
            continue
        if stat.S_ISLNK(metadata.st_mode):
            payload = os.readlink(candidate).encode("utf-8", errors="surrogateescape")
        elif stat.S_ISREG(metadata.st_mode):
            digest = hashlib.sha256()
            with candidate.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            states[normalized] = {
                "exists": True,
                "size": metadata.st_size,
                "sha256": digest.hexdigest(),
            }
            continue
        else:
            raise PrimarySessionValidationError(
                f"dirty snapshot path is not a regular file or symlink: {raw_path!r}"
            )
        states[normalized] = {
            "exists": True,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    return states


# 读取当前进程的有效用户标识。
def _current_user_id() -> int | None:
    """返回：
    当前用户标识；平台不支持时返回 None。
    """
    getter = getattr(os, "geteuid", None) or getattr(os, "getuid", None)
    return getter() if getter is not None else None


# 拒绝目标路径中已经存在的符号链接组件。
def _reject_symlink_components(path: Path) -> None:
    """参数：
        path: 待检查的目标路径。

    异常：
        PrimarySessionValidationError: 路径组件包含符号链接时抛出。
    """
    for component in [*reversed(path.parents), path]:
        if component == Path(component.anchor):
            continue
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise PrimarySessionValidationError(f"runtime path contains symbolic link: {component}")


# 安全创建并校验当前用户独占的 0700 运行时目录，同时拒绝符号链接越界。
def ensure_private_directory(path: Path, *, root: Path | None = None) -> Path:
    """参数：
        path: 待创建或校验的目录路径。
        root: 可选边界目录，用于限制目标位于同一运行时根目录。

    返回：
        不跟随符号链接的绝对目录路径。

    异常：
        PrimarySessionValidationError: 目录越界、不安全或权限不合规时抛出。
    """

    target = _absolute_path(path)
    boundary = _absolute_path(root) if root is not None else target
    try:
        target.relative_to(boundary)
    except ValueError as exc:
        raise PrimarySessionValidationError(f"runtime directory escapes root: {target}") from exc

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
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _reject_symlink_components(directory)

    try:
        metadata = target.lstat()
    except FileNotFoundError as exc:
        raise PrimarySessionValidationError(
            f"runtime directory could not be created: {target}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise PrimarySessionValidationError(f"runtime path is not a private directory: {target}")
    current_user = _current_user_id()
    if current_user is not None and metadata.st_uid != current_user:
        raise PrimarySessionValidationError(
            f"runtime directory is not owned by current user: {target}"
        )

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise PrimarySessionValidationError(
            f"runtime directory cannot be opened safely: {target}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or opened.st_ino != metadata.st_ino
            or opened.st_dev != metadata.st_dev
        ):
            raise PrimarySessionValidationError(
                f"runtime directory changed during validation: {target}"
            )
        if current_user is not None and opened.st_uid != current_user:
            raise PrimarySessionValidationError(
                f"runtime directory is not owned by current user: {target}"
            )
        os.fchmod(descriptor, 0o700)
        if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o700:
            raise PrimarySessionValidationError(
                f"runtime directory permissions are not 0700: {target}"
            )
    finally:
        os.close(descriptor)
    return target


# 解析当前 cwd 所属 checkout 的真实根目录。
def resolve_checkout_root(repo_root: Path) -> Path:
    """参数：
        repo_root: 仓库内的起始路径。

    返回：
        当前 checkout 的真实根目录。

    异常：
        PrimarySessionValidationError: 无法从 Git 解析根目录时抛出。
    """
    try:
        raw = _git_output(_absolute_path(repo_root), "rev-parse", "--show-toplevel")
        return Path(raw).expanduser().resolve(strict=True)
    except Exception as exc:
        raise PrimarySessionValidationError(
            f"cannot resolve Git checkout root: {repo_root}"
        ) from exc


# 解析 checkout 共享且只读的 Git common-dir。
def resolve_git_common_dir(repo_root: Path) -> Path:
    """参数：
        repo_root: 仓库内的起始路径。

    返回：
        checkout 共享的 Git common-dir 真实路径。

    异常：
        PrimarySessionValidationError: 无法解析 Git common-dir 时抛出。
    """
    checkout_root = resolve_checkout_root(repo_root)
    try:
        raw = _git_output(checkout_root, "rev-parse", "--git-common-dir")
        common_dir = Path(raw)
        if not common_dir.is_absolute():
            common_dir = checkout_root / common_dir
        return common_dir.resolve(strict=True)
    except Exception as exc:
        raise PrimarySessionValidationError(f"cannot resolve Git common-dir: {repo_root}") from exc


# 从 Git 权威 worktree 清单中读取真实根路径。
def _listed_worktree_roots(repo_root: Path) -> list[Path]:
    """参数：
        repo_root: 仓库内的起始路径。

    返回：
        Git 登记的 worktree 真实根路径列表。

    异常：
        PrimarySessionValidationError: 清单不可读或缺少当前 checkout 时抛出。
    """
    checkout_root = resolve_checkout_root(repo_root)
    try:
        listing = _git_output(checkout_root, "worktree", "list", "--porcelain", "-z")
        roots = [
            Path(field.removeprefix("worktree ")).expanduser().resolve()
            for field in listing.split("\0")
            if field.startswith("worktree ")
        ]
    except Exception as exc:
        raise PrimarySessionValidationError(
            f"cannot read Git worktree metadata: {repo_root}"
        ) from exc
    if not roots or checkout_root not in roots:
        raise PrimarySessionValidationError(
            f"checkout is absent from Git worktree metadata: {checkout_root}"
        )
    return roots


# 解析共享 common-dir 对应的主 checkout 根目录。
def resolve_primary_repo_root(repo_root: Path) -> Path:
    """参数：
        repo_root: 仓库内的起始路径。

    返回：
        共享 Git common-dir 对应的主 checkout 根目录。

    异常：
        PrimarySessionValidationError: 主 checkout 与当前 checkout 不一致时抛出。
    """
    checkout_root = resolve_checkout_root(repo_root)
    roots = _listed_worktree_roots(checkout_root)
    primary_root = roots[0]
    if resolve_git_common_dir(primary_root) != resolve_git_common_dir(checkout_root):
        raise PrimarySessionValidationError(
            "primary checkout and current checkout have different Git common-dir"
        )
    return primary_root


# 稳定读取 primary checkout 的 named branch 与精确 HEAD。
def capture_primary_head_snapshot(repo_root: Path) -> PrimaryHeadSnapshot:
    """参数：
        repo_root: primary 或同仓库 linked checkout 内的路径。

    返回：
        两次读取一致的 primary branch/HEAD snapshot。

    异常：
        PrimarySessionValidationError: primary detached 或读取期间发生竞态时抛出。
    """
    primary_root = resolve_primary_repo_root(repo_root)
    first_branch = _current_branch(primary_root)
    first_head = _git_output(primary_root, "rev-parse", "HEAD")
    second_branch = _current_branch(primary_root)
    second_head = _git_output(primary_root, "rev-parse", "HEAD")
    if not first_branch or not second_branch:
        raise PrimarySessionValidationError(
            "PRIMARY_HEAD_DETACHED: primary checkout must be on a named branch"
        )
    if (first_branch, first_head) != (second_branch, second_head):
        raise PrimarySessionValidationError(
            "PRIMARY_HEAD_RACE: primary branch or HEAD changed while capturing snapshot"
        )
    return PrimaryHeadSnapshot(
        primary_repo_root=str(primary_root),
        branch=first_branch,
        head_commit=first_head,
    )


# 生成主 checkout 与 linked worktree 共用的仓库键。
def resolve_repo_key(repo_root: Path) -> str:
    """参数：
        repo_root: 仓库内的起始路径。

    返回：
        基于 Git common-dir 生成的稳定仓库键。
    """
    common_dir = resolve_git_common_dir(repo_root)
    return hashlib.sha256(str(common_dir).encode("utf-8")).hexdigest()


# 根据仓库键和真实路径生成不受路径名称影响的 checkout 标识。
def stable_worktree_id(repo_key: str, checkout_root: str | Path) -> str:
    """参数：
        repo_key: 稳定仓库键。
        checkout_root: checkout 真实根路径。

    返回：
        稳定的 checkout 标识。
    """
    root = Path(checkout_root).expanduser().resolve(strict=True)
    digest = hashlib.sha256(f"{repo_key}\0{root}".encode()).hexdigest()
    return f"checkout-{digest[:24]}"


# 仅依据 Git 元数据解析 checkout 身份与集成事实。
def resolve_checkout_identity(
    repo_root: Path,
    *,
    checkout_creator: str = "unknown",
    base_commit: str = "",
) -> dict[str, Any]:
    """参数：
        repo_root: 仓库内的起始路径。
        checkout_creator: checkout 的创建端标识。
        base_commit: 可选的基线提交。

    返回：
        checkout 身份、分支、提交与祖先关系事实。
    """
    checkout_root = resolve_checkout_root(repo_root)
    common_dir = resolve_git_common_dir(checkout_root)
    primary_root = resolve_primary_repo_root(checkout_root)
    repo_key = resolve_repo_key(checkout_root)
    branch = _current_branch(checkout_root)
    head = _git_output(checkout_root, "rev-parse", "HEAD")
    creator = checkout_creator if checkout_creator in CHECKOUT_CREATORS else "unknown"
    base = str(base_commit or "").strip()
    base_exists = (
        bool(base)
        and subprocess.run(
            ["git", "-C", str(checkout_root), "cat-file", "-e", f"{base}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    base_is_ancestor = None
    if base_exists:
        base_is_ancestor = (
            subprocess.run(
                ["git", "-C", str(checkout_root), "merge-base", "--is-ancestor", base, "HEAD"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
            == 0
        )
    return {
        "repoKey": repo_key,
        "checkoutRoot": str(checkout_root),
        "primaryRepoRoot": str(primary_root),
        "gitCommonDir": str(common_dir),
        "worktreeId": stable_worktree_id(repo_key, checkout_root),
        "checkoutKind": "primary-checkout" if checkout_root == primary_root else "linked-worktree",
        "checkoutCreator": creator,
        "branch": branch,
        "detached": not bool(branch),
        "headCommit": head,
        "baseCommit": base,
        "baseCommitExists": base_exists,
        "baseIsAncestorOfHead": base_is_ancestor,
    }


# 对比运行记录与当前 Git 事实，仅将祖先关系作为证据而非有效性依据。
def validate_checkout_record(
    repo_root: Path, record: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """参数：
        repo_root: 当前仓库根目录。
        record: 待校验的运行记录。

    返回：
        当前 checkout 事实与不一致错误列表。
    """
    facts = resolve_checkout_identity(
        repo_root,
        checkout_creator=str(record.get("checkoutCreator") or "unknown"),
        base_commit=str(record.get("baseCommit") or ""),
    )
    errors: list[str] = []
    recorded_root = Path(str(record.get("checkoutRoot") or "")).expanduser().resolve()
    if recorded_root != Path(facts["checkoutRoot"]):
        errors.append("cwd realpath does not match run checkout root")
    if record.get("checkoutRoot") and Path(
        str(record["checkoutRoot"])
    ).expanduser().resolve() != Path(facts["checkoutRoot"]):
        errors.append("run checkoutRoot does not match current checkout")
    creator = str(record.get("checkoutCreator") or "unknown")
    if creator not in CHECKOUT_CREATORS:
        errors.append("run checkoutCreator is invalid")
    new_identity = bool(record.get("repoKey"))
    if new_identity:
        for field in (
            "repoKey",
            "gitCommonDir",
            "worktreeId",
            "checkoutKind",
            "checkoutRoot",
            "checkoutCreator",
            "primaryRepoRoot",
        ):
            if field not in record:
                errors.append(f"run checkout identity is missing {field}")
            elif str(record.get(field) or "") != str(facts[field]):
                errors.append(f"run {field} does not match current checkout")
    return facts, errors


# 解析共享运行时根目录。
def resolve_runtime_root(repo_root: Path) -> Path:
    """参数：
        repo_root: 仓库根目录。

    返回：
        未跟踪的 primary session 运行时根目录。
    """

    override = os.environ.get("FEIPI_AGENT_RUNTIME_ROOT", "").strip()
    if override:
        return ensure_private_directory(Path(override))

    configured_temp = os.environ.get("TMPDIR", "").strip()
    temp_root = Path(configured_temp or tempfile.gettempdir()).expanduser().resolve(strict=True)
    runtime_base = ensure_private_directory(temp_root / RUNTIME_DIR_NAME)
    return ensure_private_directory(runtime_base / resolve_repo_key(repo_root), root=runtime_base)


# 使用 PyYAML 或简化解析器读取清单。
def load_yaml(path: Path) -> dict[str, Any]:
    """参数：
        path: 清单文件路径。

    返回：
        清单内容映射。
    """
    if yaml is None:
        data = _load_simple_yaml(path)
    else:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PrimarySessionValidationError(f"manifest not found: {path}") from exc
        except Exception as exc:
            raise PrimarySessionValidationError(f"manifest parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise PrimarySessionValidationError("manifest root must be a mapping")
    return data


# 读取必需字段，缺失时抛出校验错误。
def _required(mapping: dict[str, Any], field: str) -> Any:
    """参数：
        mapping: 待检查的映射。
        field: 必需字段名称。

    返回：
        字段对应的值。
    """
    if field not in mapping:
        raise PrimarySessionValidationError(f"missing required run field: {field}")
    return mapping[field]


# 规范化记录中的路径列表。
def _path_set(value: Any) -> set[str]:
    """参数：
        value: 原始路径列表。

    返回：
        去除结尾斜杠后的路径集合。
    """
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PrimarySessionValidationError("allowedPaths and forbiddenPaths must be string lists")
    return {item.rstrip("/") for item in value}


# 判断两个路径范围是否存在前缀交集。
def paths_intersect(first: list[str], second: list[str]) -> bool:
    """参数：
        first: 第一组路径范围。
        second: 第二组路径范围。

    返回：
        存在交集时返回 true，否则返回 false。
    """
    left = _path_set(first)
    right = _path_set(second)
    for a in left:
        for b in right:
            if a == b or a.startswith(f"{b}/") or b.startswith(f"{a}/"):
                return True
    return False


# 校验运行状态转换是否合法。
def validate_status_transition(from_status: str, to_status: str) -> None:
    """参数：
        from_status: 起始状态。
        to_status: 目标状态。

    返回：
        无返回值。
    """
    if from_status not in RUN_STATUSES:
        raise PrimarySessionValidationError(f"unknown source status: {from_status}")
    if to_status not in RUN_STATUSES:
        raise PrimarySessionValidationError(f"unknown target status: {to_status}")
    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise PrimarySessionValidationError(
            f"illegal status transition: {from_status} -> {to_status}"
        )


# 校验单条运行记录。
def validate_run_record(record: dict[str, Any]) -> None:
    """参数：
        record: 待校验的运行记录。

    返回：
        无返回值。
    """
    if not isinstance(record, dict):
        raise PrimarySessionValidationError("run record must be a mapping")
    for field in REQUIRED_RUN_FIELDS:
        _required(record, field)

    if record["status"] not in RUN_STATUSES:
        raise PrimarySessionValidationError(f"invalid run status: {record['status']}")
    if record["checkoutKind"] not in CHECKOUT_KINDS:
        raise PrimarySessionValidationError(f"invalid checkoutKind: {record['checkoutKind']}")
    if record["checkoutCreator"] not in CHECKOUT_CREATORS:
        raise PrimarySessionValidationError(f"invalid checkoutCreator: {record['checkoutCreator']}")
    if not isinstance(record["detached"], bool):
        raise PrimarySessionValidationError("detached must be boolean")
    if not isinstance(record["initialDirtySnapshot"], dict):
        raise PrimarySessionValidationError("initialDirtySnapshot must be a mapping")
    if not isinstance(record["changeAttribution"], dict):
        raise PrimarySessionValidationError("changeAttribution must be a mapping")

    _path_set(record["allowedPaths"])
    _path_set(record["forbiddenPaths"])

    if record["status"] in {
        "ISOLATED_WRITER",
        "LOCAL_WRITER",
    }:
        expected_status = (
            "LOCAL_WRITER"
            if record.get("checkoutKind") == "primary-checkout"
            else "ISOLATED_WRITER"
        )
        if record["status"] != expected_status:
            raise PrimarySessionValidationError(
                f"{record.get('checkoutKind')} requires {expected_status} status"
            )
    writer_lease = record.get("writerLease")
    if not isinstance(writer_lease, dict):
        raise PrimarySessionValidationError("writerLease must be a mapping")
    if record["status"] in ACTIVE_WRITER_STATUSES and not writer_lease:
        raise PrimarySessionValidationError("active writer requires writerLease")
    if writer_lease:
        if not str(record.get("sessionId", "")).strip():
            raise PrimarySessionValidationError("writer lease holder requires sessionId")
        for field in (
            "leaseId",
            "holderRunId",
            "holderSessionId",
            "epoch",
            "fencingToken",
        ):
            if not writer_lease.get(field):
                raise PrimarySessionValidationError(
                    f"writer lease holder requires writerLease.{field}"
                )
        try:
            if int(writer_lease["epoch"]) <= 0:
                raise PrimarySessionValidationError(
                    "writer lease holder requires positive writerLease.epoch"
                )
        except (TypeError, ValueError) as exc:
            raise PrimarySessionValidationError(
                "writer lease holder requires integer writerLease.epoch"
            ) from exc
        if writer_lease.get("holderRunId") != record.get("runId"):
            raise PrimarySessionValidationError("writerLease holderRunId must match runId")
        if writer_lease.get("holderSessionId") != record.get("sessionId"):
            raise PrimarySessionValidationError("writerLease holderSessionId must match sessionId")
        hook_activation = record.get("hookActivation")
        if not isinstance(hook_activation, dict):
            raise PrimarySessionValidationError(
                "writer lease holder requires hookActivation mapping"
            )
        if (
            record["status"] in WRITABLE_READY_STATUSES
            and hook_activation.get("confirmed") is not True
        ):
            raise PrimarySessionValidationError(
                "hook activation must be confirmed before writable-ready status"
            )


# 判断运行记录是否为活跃写入者。
def _is_active_writer(record: dict[str, Any]) -> bool:
    """参数：
        record: 待检查的运行记录。

    返回：
        是活跃写入者时返回 true，否则返回 false。
    """
    return record.get("status") in ACTIVE_WRITER_STATUSES


# 校验运行记录集合并返回冲突信息。
def validate_run_collisions(records: list[dict[str, Any]]) -> list[Collision]:
    """参数：
        records: 待校验的运行记录列表。

    返回：
        检测到的运行冲突列表。
    """
    for record in records:
        validate_run_record(record)

    collisions: list[Collision] = []
    active = [record for record in records if _is_active_writer(record)]
    for i, first in enumerate(active):
        for second in active[i + 1 :]:
            first_id = str(first["runId"])
            second_id = str(second["runId"])
            first_root = str(first.get("checkoutRoot") or "")
            second_root = str(second.get("checkoutRoot") or "")
            if (
                first_root
                and second_root
                and Path(first_root).expanduser().resolve()
                == Path(second_root).expanduser().resolve()
            ):
                collisions.append(
                    Collision(
                        "same-worktree-writer",
                        "same worktree second writer is blocked",
                        first_id,
                        second_id,
                    )
                )
    return collisions


# 校验 primary session 清单结构。
def validate_manifest(data: dict[str, Any]) -> None:
    """参数：
        data: 待校验的清单映射。

    返回：
        无返回值。
    """
    if data.get("schemaVersion", data.get("version")) != 1:
        raise PrimarySessionValidationError("schemaVersion/version must be 1")
    primary = data.get("primary_sessions")
    if not isinstance(primary, dict):
        raise PrimarySessionValidationError("missing primary_sessions mapping")
    if primary.get("writable_isolation") != "checkout-writer-lease":
        raise PrimarySessionValidationError(
            "primary_sessions.writable_isolation must be checkout-writer-lease"
        )
    if primary.get("same_worktree_max_writers") != 1:
        raise PrimarySessionValidationError("primary_sessions.same_worktree_max_writers must be 1")
    if primary.get("read_only_sessions_allowed") is not True:
        raise PrimarySessionValidationError(
            "primary_sessions.read_only_sessions_allowed must be true"
        )

    run_record = data.get("run_record")
    if not isinstance(run_record, dict):
        raise PrimarySessionValidationError("missing run_record mapping")
    required = run_record.get("required_fields")
    if required != REQUIRED_RUN_FIELDS:
        raise PrimarySessionValidationError("run_record.required_fields does not match contract")
    if set(run_record.get("statuses", [])) != RUN_STATUSES:
        raise PrimarySessionValidationError("run_record.statuses does not match contract")

    transitions = data.get("status_machine", {}).get("transitions")
    if not isinstance(transitions, dict):
        raise PrimarySessionValidationError("missing status_machine.transitions mapping")
    manifest_transitions = {str(k): set(v or []) for k, v in transitions.items()}
    if manifest_transitions != ALLOWED_TRANSITIONS:
        raise PrimarySessionValidationError("status_machine.transitions does not match validator")

    runtime_root = data.get("runtime_root")
    if not isinstance(runtime_root, dict):
        raise PrimarySessionValidationError("missing runtime_root mapping")
    order = runtime_root.get("resolution_order")
    expected = ["FEIPI_AGENT_RUNTIME_ROOT", "TMPDIR-or-system-temp/feipi-agent-runtime/<repo-key>"]
    if order != expected:
        raise PrimarySessionValidationError("runtime_root.resolution_order does not match contract")


# 校验指定路径的清单文件。
def validate_manifest_file(path: Path) -> None:
    """参数：
        path: 清单文件路径。

    返回：
        无返回值。
    """
    validate_manifest(load_yaml(path))


RUN_WRITE_OK_STATUSES = {"ISOLATED_WRITER", "LOCAL_WRITER"}


# 读取 JSON 文件，失败时返回空映射。
def _load_json_file(path: Path) -> dict[str, Any]:
    """参数：
        path: JSON 文件路径。

    返回：
        JSON 对象映射；读取失败时返回空映射。
    """
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return {}
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            return {}
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if opened.st_ino != metadata.st_ino or opened.st_dev != metadata.st_dev:
                return {}
            with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as handle:
                data = json.load(handle)
        finally:
            os.close(descriptor)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


# 列出运行记录文件路径。
def _run_record_paths(repo_root: Path) -> list[Path]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        运行记录文件路径列表。
    """
    runs_dir = resolve_runtime_root(repo_root) / "runs"
    index = _load_json_file(runs_dir / "index.json")
    ids = [str(item) for item in index.get("runs", [])]
    paths = [runs_dir / f"{run_id}.json" for run_id in ids]
    if not paths and runs_dir.is_dir():
        paths = sorted(runs_dir.glob("*.json"))
    return paths


# 按 run id 加载运行记录。
def load_run_record(repo_root: Path, run_id: str) -> dict[str, Any] | None:
    """参数：
        repo_root: 仓库根目录。
        run_id: 运行标识。

    返回：
        运行记录；未找到时返回 None。
    """
    if not run_id:
        return None
    path = resolve_runtime_root(repo_root) / "runs" / f"{run_id}.json"
    record = _load_json_file(path)
    return record or None


# 加载单个物理 checkout 的权威写租约，并仅允许稳定 checkout 标识参与路径构造。
def load_checkout_writer_lease(repo_root: Path, worktree_id: str) -> dict[str, Any] | None:
    """参数：
        repo_root: 当前仓库根目录。
        worktree_id: 稳定的 checkout 标识。

    返回：
        权威写租约；标识不匹配或租约不存在时返回 None。
    """

    expected = stable_worktree_id(resolve_repo_key(repo_root), resolve_checkout_root(repo_root))
    if worktree_id != expected:
        return None
    lease_path = resolve_runtime_root(repo_root) / "writer-leases" / f"{worktree_id}.json"
    lease = _load_json_file(lease_path)
    return lease or None


# 将运行记录内嵌的隔离证明与 checkout 权威写租约进行校验。
def validate_writer_lease_fence(
    repo_root: Path,
    record: dict[str, Any],
) -> list[str]:
    """参数：
        repo_root: 当前仓库根目录。
        record: 包含隔离证明的运行记录。

    返回：
        写租约隔离校验错误列表。
    """

    embedded = record.get("writerLease")
    if not isinstance(embedded, dict) or not embedded:
        return ["writer lease is missing from run record"]
    lease = load_checkout_writer_lease(repo_root, str(record.get("worktreeId") or ""))
    if not lease:
        return ["authoritative checkout writer lease is missing"]

    errors: list[str] = []
    expected_pairs = {
        "leaseId": record.get("writerLease", {}).get("leaseId"),
        "holderRunId": record.get("runId"),
        "holderSessionId": record.get("sessionId"),
        "repoKey": record.get("repoKey"),
        "worktreeId": record.get("worktreeId"),
        "checkoutRoot": record.get("checkoutRoot"),
        "epoch": embedded.get("epoch"),
        "fencingToken": embedded.get("fencingToken"),
    }
    for field, expected in expected_pairs.items():
        if not expected or lease.get(field) != expected:
            errors.append(f"writer lease {field} does not match run fencing proof")
    try:
        if int(lease.get("epoch") or 0) <= 0:
            errors.append("writer lease epoch must be positive")
    except (TypeError, ValueError):
        errors.append("writer lease epoch must be an integer")
    if lease.get("state") != "ACTIVE":
        errors.append("writer lease is not active")
    return errors


# 解析已绑定的运行记录。
def resolve_bound_run_record(
    repo_root: Path,
    client: str,
    session_id: str = "",
    run_id: str = "",
) -> dict[str, Any] | None:
    """参数：
        repo_root: 仓库根目录。
        client: agent client 名称。
        session_id: session 标识。
        run_id: 运行标识。

    返回：
        匹配的运行记录；未找到时返回 None。
    """
    try:
        checkout_root = resolve_checkout_root(repo_root)
        repo_key = resolve_repo_key(checkout_root)
    except PrimarySessionValidationError:
        return None

    # 判断运行记录是否匹配当前 client、session 和 checkout 身份。
    def matches(record: dict[str, Any]) -> bool:
        """参数：
            record: 待匹配的运行记录。

        返回：
            所有绑定条件均匹配时返回 true。
        """
        if client and record.get("client") != client:
            return False
        if session_id and record.get("sessionId") != session_id:
            return False
        try:
            recorded_root = Path(str(record.get("checkoutRoot") or "")).expanduser().resolve()
        except OSError:
            return False
        if recorded_root != checkout_root:
            return False
        recorded_key = str(record.get("repoKey") or "")
        if recorded_key and recorded_key != repo_key:
            return False
        if recorded_key and record.get("worktreeId") != stable_worktree_id(repo_key, checkout_root):
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


# 列出当前 registry 中活跃可写运行。
def active_writable_runs(repo_root: Path) -> list[dict[str, Any]]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        当前运行时 registry 中仍处于活跃写状态的 writable run records。
    """
    records: list[dict[str, Any]] = []
    for path in _run_record_paths(repo_root):
        record = _load_json_file(path)
        if record.get("status") in ACTIVE_WRITER_STATUSES:
            records.append(record)
    return records


# 读取当前 git 分支名称。
def _current_branch(repo_root: Path) -> str:
    """参数：
        repo_root: 仓库根目录。

    返回：
        当前分支名称；读取失败时返回空字符串。
    """
    try:
        return _git_output(repo_root, "branch", "--show-current")
    except Exception:
        return ""


# 判断相对路径是否位于允许范围。
def _path_allowed(rel_path: str, scopes: list[str]) -> bool:
    """参数：
        rel_path: 相对路径。
        scopes: 允许的路径范围。

    返回：
        在允许范围内时返回 true，否则返回 false。
    """
    if not scopes:
        return False
    rel = rel_path.strip("/")
    for scope in scopes:
        item = str(scope).strip("/")
        if item in {"", ".", "*", "**"}:
            return True
        if rel == item or rel.startswith(f"{item}/"):
            return True
    return False


# 判断相对路径是否位于禁止范围。
def _path_forbidden(rel_path: str, scopes: list[str]) -> bool:
    """参数：
        rel_path: 相对路径。
        scopes: 禁止的路径范围。

    返回：
        在禁止范围内时返回 true，否则返回 false。
    """
    rel = rel_path.strip("/")
    for scope in scopes:
        item = str(scope).strip("/")
        if rel == item or rel.startswith(f"{item}/"):
            return True
    return False


# 校验绑定运行是否允许写入候选路径。
def validate_run_write_authorization(
    repo_root: Path,
    *,
    client: str,
    session_id: str,
    run_id: str = "",
    change_id: str = "",
    candidate_paths: list[str] | None = None,
) -> tuple[bool, list[str], dict[str, Any] | None]:
    """参数：
        repo_root: 仓库根目录。
        client: agent client 名称。
        session_id: session 标识。
        run_id: 运行标识。
        change_id: OpenSpec change 标识。
        candidate_paths: 候选写入路径列表。

    返回：
        授权结果、错误列表和匹配运行记录。
    """
    record = resolve_bound_run_record(repo_root, client, session_id, run_id)
    if not record:
        if run_id or session_id:
            return False, ["bound writable run not found for client/session/run"], None
        return False, ["legacy session has no bound writable run; mutating operation blocked"], None
    errors: list[str] = []
    try:
        validate_run_record(record)
    except PrimarySessionValidationError as exc:
        errors.append(str(exc))
    try:
        checkout_facts, checkout_errors = validate_checkout_record(repo_root, record)
        errors.extend(checkout_errors)
        worktree = Path(checkout_facts["checkoutRoot"])
    except PrimarySessionValidationError as exc:
        errors.append(str(exc))
        worktree = Path(str(record.get("checkoutRoot", ""))).resolve()
    if record.get("sessionId") != session_id:
        errors.append("session id is not bound to run")
    if record.get("status") not in RUN_WRITE_OK_STATUSES:
        errors.append("run status does not allow writes")
    errors.extend(validate_writer_lease_fence(worktree, record))
    if change_id and record.get("changeId") != change_id:
        errors.append("current change id does not match run record")
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
            errors.append(f"target path is outside run worktree: {raw_path}")
            continue
        if not _path_allowed(rel, list(record.get("allowedPaths") or [])):
            errors.append(f"target path is outside allowedPaths: {rel}")
        if _path_forbidden(rel, list(record.get("forbiddenPaths") or [])):
            errors.append(f"target path is under forbiddenPaths: {rel}")
    return not errors, errors, record
