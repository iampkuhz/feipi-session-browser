"""Primary session run contract model and validators."""

from __future__ import annotations

import json
import os
import subprocess
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
    "client",
    "taskId",
    "sessionId",
    "worktreeId",
    "worktreeRoot",
    "branch",
    "targetBranch",
    "primaryRepoRoot",
    "baseCommit",
    "headCommit",
    "changeId",
    "mode",
    "status",
    "allowedPaths",
    "forbiddenPaths",
    "resourceAllocations",
    "writerLease",
    "hookActivation",
    "processes",
    "createdAt",
    "updatedAt",
]

RUN_MODES = {"read-only", "writable"}
RUN_STATUSES = {
    "CREATED",
    "STARTING",
    "RUNNING",
    "VALIDATING",
    "VALIDATED",
    "COMMITTED",
    "INTEGRATING",
    "INTEGRATED",
    "CLEANED",
    "BLOCKED",
    "HANDOFF_REQUIRED",
    "FAILED",
}
TERMINAL_STATUSES = {"INTEGRATED", "CLEANED", "FAILED", "HANDOFF_REQUIRED"}
ACTIVE_WRITER_STATUSES = RUN_STATUSES - TERMINAL_STATUSES - {"BLOCKED"}
WRITABLE_READY_STATUSES = {"RUNNING", "VALIDATING", "VALIDATED", "COMMITTED"}
ALLOWED_TRANSITIONS = {
    "CREATED": {"STARTING", "RUNNING", "BLOCKED", "FAILED"},
    "STARTING": {"RUNNING", "BLOCKED", "FAILED"},
    "RUNNING": {"VALIDATING", "BLOCKED", "FAILED"},
    "VALIDATING": {"RUNNING", "VALIDATED", "BLOCKED", "FAILED"},
    "VALIDATED": {"COMMITTED", "INTEGRATING", "BLOCKED", "HANDOFF_REQUIRED", "FAILED"},
    "COMMITTED": {"INTEGRATING", "HANDOFF_REQUIRED", "FAILED"},
    "INTEGRATING": {"INTEGRATED", "HANDOFF_REQUIRED", "FAILED"},
    "INTEGRATED": {"CLEANED"},
    "BLOCKED": {"STARTING", "RUNNING", "VALIDATING", "HANDOFF_REQUIRED", "FAILED"},
    "HANDOFF_REQUIRED": {"STARTING", "RUNNING", "FAILED", "CLEANED"},
    "FAILED": {"CLEANED"},
    "CLEANED": set(),
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
            raise PrimarySessionValidationError(f"fallback YAML parser cannot parse line: {raw_line}")
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
    """Raised when a primary session manifest or run record is invalid."""


@dataclass(frozen=True)
class Collision:
    """A machine-readable run collision."""

    kind: str
    message: str
    first_run_id: str
    second_run_id: str


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


# 解析共享运行时根目录。
def resolve_runtime_root(repo_root: Path) -> Path:
    """参数：
        repo_root: 仓库根目录。

    返回：
        未跟踪的 primary session 运行时根目录。
    """

    override = os.environ.get("FEIPI_AGENT_RUNTIME_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    root = repo_root.resolve()
    try:
        common_raw = _git_output(root, "rev-parse", "--git-common-dir")
    except Exception:
        common_dir = root / ".git"
    else:
        common_dir = Path(common_raw)
        if not common_dir.is_absolute():
            common_dir = root / common_dir
    return (common_dir.resolve() / RUNTIME_DIR_NAME)


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
        raise PrimarySessionValidationError(f"illegal status transition: {from_status} -> {to_status}")


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

    if record["mode"] not in RUN_MODES:
        raise PrimarySessionValidationError(f"invalid run mode: {record['mode']}")
    if record["status"] not in RUN_STATUSES:
        raise PrimarySessionValidationError(f"invalid run status: {record['status']}")

    _path_set(record["allowedPaths"])
    _path_set(record["forbiddenPaths"])

    if record["mode"] == "writable":
        if not str(record.get("sessionId", "")).strip() and record["status"] not in {"CREATED", "STARTING", "BLOCKED"}:
            raise PrimarySessionValidationError("writable run without sessionId may only perform startup handshake")
        writer_lease = record.get("writerLease")
        if not isinstance(writer_lease, dict):
            raise PrimarySessionValidationError("writable run requires writerLease mapping")
        if record["status"] in ACTIVE_WRITER_STATUSES and not writer_lease.get("leaseId"):
            raise PrimarySessionValidationError("active writable run requires writerLease.leaseId")
        hook_activation = record.get("hookActivation")
        if not isinstance(hook_activation, dict):
            raise PrimarySessionValidationError("writable run requires hookActivation mapping")
        if record["status"] in WRITABLE_READY_STATUSES and hook_activation.get("confirmed") is not True:
            raise PrimarySessionValidationError("hook activation must be confirmed before writable-ready status")


# 判断运行记录是否为活跃写入者。
def _is_active_writer(record: dict[str, Any]) -> bool:
    """参数：
        record: 待检查的运行记录。

    返回：
        是活跃写入者时返回 true，否则返回 false。
    """
    return record.get("mode") == "writable" and record.get("status") in ACTIVE_WRITER_STATUSES


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
            if first.get("worktreeRoot") == second.get("worktreeRoot"):
                collisions.append(Collision("same-worktree-writer", "same worktree second writer is blocked", first_id, second_id))
            if first.get("branch") == second.get("branch"):
                collisions.append(Collision("same-branch-writer", "same branch active writable runs are blocked", first_id, second_id))
            if paths_intersect(first.get("allowedPaths", []), second.get("allowedPaths", [])):
                override = bool(first.get("writeScopeOverride", {}).get("highRiskAccepted")) or bool(
                    second.get("writeScopeOverride", {}).get("highRiskAccepted")
                )
                risk_records = first.get("highRiskRecords") or second.get("highRiskRecords")
                if not override or not risk_records:
                    collisions.append(Collision("write-scope-intersection", "write scope intersection is blocked by default", first_id, second_id))
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
    if primary.get("writable_isolation") != "git-worktree-required":
        raise PrimarySessionValidationError("primary_sessions.writable_isolation must be git-worktree-required")
    if primary.get("same_worktree_max_writers") != 1:
        raise PrimarySessionValidationError("primary_sessions.same_worktree_max_writers must be 1")
    if primary.get("read_only_sessions_allowed") is not True:
        raise PrimarySessionValidationError("primary_sessions.read_only_sessions_allowed must be true")

    run_record = data.get("run_record")
    if not isinstance(run_record, dict):
        raise PrimarySessionValidationError("missing run_record mapping")
    required = run_record.get("required_fields")
    if required != REQUIRED_RUN_FIELDS:
        raise PrimarySessionValidationError("run_record.required_fields does not match contract")
    if set(run_record.get("modes", [])) != RUN_MODES:
        raise PrimarySessionValidationError("run_record.modes must define read-only and writable")
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
    expected = ["FEIPI_AGENT_RUNTIME_ROOT", "git-common-dir/feipi-agent-runtime"]
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

RUN_WRITE_OK_STATUSES = {"RUNNING", "VALIDATING", "VALIDATED", "COMMITTED"}
PRIMARY_SESSION_MODES = {
    "managed-worktree",
    "read-only-unbound",
    "blocked",
}


# 读取 JSON 文件，失败时返回空映射。
def _load_json_file(path: Path) -> dict[str, Any]:
    """参数：
        path: JSON 文件路径。

    返回：
        JSON 对象映射；读取失败时返回空映射。
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
    if run_id:
        record = load_run_record(repo_root, run_id)
        if record and (not client or record.get("client") == client):
            return record
        return None
    if not session_id:
        return None
    for path in _run_record_paths(repo_root):
        record = _load_json_file(path)
        if record.get("client") == client and record.get("sessionId") == session_id:
            return record
    return None


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
        if record.get("mode") == "writable" and record.get("status") in ACTIVE_WRITER_STATUSES:
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
    worktree = Path(str(record.get("worktreeRoot", ""))).resolve()
    if repo_root.resolve() != worktree:
        errors.append("cwd realpath does not match run worktree root")
    if _current_branch(repo_root) != record.get("branch"):
        errors.append("current branch does not match run branch")
    if record.get("sessionId") != session_id:
        errors.append("session id is not bound to run")
    if record.get("mode") != "writable":
        errors.append("run is not writable")
    if record.get("status") not in RUN_WRITE_OK_STATUSES:
        errors.append("run status does not allow writes")
    lease = record.get("writerLease") if isinstance(record.get("writerLease"), dict) else {}
    if lease.get("holderRunId") != record.get("runId") or not lease.get("leaseId"):
        errors.append("writer lease is missing or not held by run")
    if change_id and record.get("changeId") != change_id:
        errors.append("current change id does not match run record")
    for other_path in _run_record_paths(repo_root):
        other = _load_json_file(other_path)
        if other.get("runId") == record.get("runId"):
            continue
        if other.get("mode") == "writable" and other.get("status") in ACTIVE_WRITER_STATUSES:
            if Path(str(other.get("worktreeRoot", ""))).resolve() == worktree:
                errors.append("same worktree has a second active writer")
                break
    for raw_path in candidate_paths or []:
        path = Path(raw_path)
        try:
            rel = str((path if path.is_absolute() else repo_root / path).resolve().relative_to(repo_root).as_posix())
        except Exception:
            errors.append(f"target path is outside run worktree: {raw_path}")
            continue
        if not _path_allowed(rel, list(record.get("allowedPaths") or [])):
            errors.append(f"target path is outside allowedPaths: {rel}")
        if _path_forbidden(rel, list(record.get("forbiddenPaths") or [])):
            errors.append(f"target path is under forbiddenPaths: {rel}")
    return not errors, errors, record
