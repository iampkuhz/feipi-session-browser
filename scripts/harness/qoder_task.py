"""Qoder CLI 子任务入口。

本模块负责显式启动带完整 handoff 与独立身份的 qodercli 子任务并立即返回 run_id，
Worker 后台阻塞等待 CLI 退出后原子写入完成记录，status/result/resume 提供单次读取；
不负责轮询、自动续跑、读取私人 session 文件、自动绕过权限或传自动提交参数，
退出 0 仅说明进程结束而不自动等价于质量验收 PASS；
由 Qoder 客户端通过 harness/manifest.yaml 中 public_executables 登记的命令调用。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

REQUIRED_HANDOFF: tuple[str, ...] = (
    "goal",
    "task_id",
    "task_source",
    "allowed_files",
    "forbidden_files",
    "required_context",
    "expected_output",
    "validation_command",
    "failure_policy",
)

VALID_PERMISSION_MODES = frozenset({"default", "accept_edits", "dont_ask"})

_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")


def _find_repo_root(start: Path) -> Path:
    """从 start 向上查找含 .git 的仓库根目录。"""
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(f"repo root (with .git) not found from {start}")


def _find_qoder_cli() -> Path:
    """查找 qodercli 可执行文件，支持环境变量覆盖。"""
    override = os.environ.get("QODER_TASK_CLI")
    if override:
        p = Path(override)
        if not p.is_file() or not os.access(p, os.X_OK):
            raise FileNotFoundError(f"qodercli not found at {override}")
        return p
    found = shutil.which("qodercli")
    if not found:
        raise FileNotFoundError("qodercli not found on PATH")
    return Path(found)


def _validate_run_id(run_id: str) -> str:
    """校验 run_id 格式，防路径穿越。"""
    if not _ID_RE.match(run_id):
        raise ValueError(f"invalid run id: {run_id}")
    return run_id


def _validate_task(task: dict[str, Any]) -> dict[str, Any]:
    """校验任务 JSON 包含完整九项 handoff，含类型与格式检查。"""
    if not isinstance(task, dict):
        raise ValueError("task must be a JSON object")
    for field in REQUIRED_HANDOFF:
        if field not in task:
            raise ValueError(f"missing required handoff field: {field}")
        if not isinstance(task[field], str) or not task[field].strip():
            raise ValueError(f"handoff field {field!r} must be a non-empty string")
    if "task_id" in task:
        if not isinstance(task["task_id"], str) or not _ID_RE.match(task["task_id"]):
            raise ValueError("task_id contains invalid characters")
    if "agent_id" in task:
        if not isinstance(task["agent_id"], str) or not _ID_RE.match(task["agent_id"]):
            raise ValueError("agent_id contains invalid characters")
    if "permission_mode" in task:
        perm = task["permission_mode"]
        if not isinstance(perm, str) or perm not in VALID_PERMISSION_MODES:
            raise ValueError(
                f"permission_mode must be one of {sorted(VALID_PERMISSION_MODES)}, got {perm!r}"
            )
    if "session_id" in task:
        sid = task["session_id"]
        if isinstance(sid, str) and not sid:
            pass
        elif not isinstance(sid, str):
            raise ValueError("session_id must be a string")
        else:
            try:
                uuid.UUID(sid)
            except ValueError:
                raise ValueError(f"session_id is not a valid UUID: {sid}") from None
    if "parent_client" in task and task["parent_client"] is not None:
        if not isinstance(task["parent_client"], str):
            raise ValueError("parent_client must be a string")
    if "parent_session_id" in task and task["parent_session_id"] is not None:
        if not isinstance(task["parent_session_id"], str):
            raise ValueError("parent_session_id must be a string")
    return task


def _check_no_symlink_ancestors(path: Path) -> None:
    """拒绝路径或其任何祖先为符号链接。检查未解析的绝对路径各级。"""
    abs_path = path.absolute()
    for component in [abs_path, *abs_path.parents]:
        if component.is_symlink():
            raise ValueError(f"symlink in path: {component}")


def _task_dir(repo_root: Path) -> Path:
    """返回任务目录，支持环境变量覆盖（须在本仓库内且无符号链接）。"""
    override = os.environ.get("QODER_TASK_DIR")
    if override:
        td = Path(override)
        if not td.exists():
            raise FileNotFoundError(f"QODER_TASK_DIR does not exist: {override}")
        _check_no_symlink_ancestors(td)
        try:
            td.resolve().relative_to(repo_root.resolve())
        except ValueError:
            raise ValueError(f"QODER_TASK_DIR must be inside repo: {override}") from None
        return td
    default = repo_root / "tmp" / "qoder-tasks"
    _check_no_symlink_ancestors(default)
    return default


def _atomic_write_json(path: Path, data: dict[str, Any], mode: int = 0o600) -> None:
    """原子写入 JSON，设置文件权限。"""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.chmod(tmp, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _safe_read_json(path: Path) -> dict[str, Any]:
    """安全读取 JSON，拒绝符号链接。"""
    if path.is_symlink():
        raise ValueError(f"refusing to read symlink: {path}")
    _check_no_symlink_ancestors(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _build_prompt(task: dict[str, Any]) -> str:
    """构建完整 prompt，包含所有 handoff 字段和身份信息。"""
    lines = [
        f"Goal: {task['goal']}",
        f"Task id: {task['task_id']}",
        f"Task source: {task['task_source']}",
        f"Allowed files/directories: {task['allowed_files']}",
        f"Forbidden files/directories: {task['forbidden_files']}",
        f"Required context files: {task['required_context']}",
        f"Expected output: {task['expected_output']}",
        f"Validation command: {task['validation_command']}",
        f"Failure policy: {task['failure_policy']}",
    ]
    if task.get("agent_id"):
        lines.append(f"Agent id: {task['agent_id']}")
    if task.get("client"):
        lines.append(f"Client: {task['client']}")
    if task.get("session_id"):
        lines.append(f"Session id: {task['session_id']}")
    if task.get("parent_client"):
        lines.append(f"Parent client: {task['parent_client']}")
    if task.get("parent_session_id"):
        lines.append(f"Parent session id: {task['parent_session_id']}")
    return "\n".join(lines)


def _build_qodercli_args(task: dict[str, Any], cwd: Path) -> list[str]:
    """构建 qodercli 命令行参数数组。新任务传 --session-id，恢复任务传 --resume。"""
    cli = _find_qoder_cli()
    prompt = _build_prompt(task)
    args = [str(cli), "-p", prompt, "--cwd", str(cwd)]
    perm = task.get("permission_mode", "default")
    args.extend(["--permission-mode", perm])
    args.extend(["--output-format", "json"])
    session_id = task.get("session_id", "")
    if session_id:
        if task.get("_resume_mode"):
            args.extend(["--resume", session_id])
        else:
            args.extend(["--session-id", session_id])
    return args


def _worker_entry(task_dir: Path, run_id: str, cwd: Path) -> None:
    """Worker 入口：从 task.json 读取任务，阻塞执行 CLI，原子写完成记录。"""
    run_dir = task_dir / run_id
    record_path = run_dir / "completion.json"
    stdout_log = run_dir / "stdout.log"
    stderr_log = run_dir / "stderr.log"
    task_file = run_dir / "task.json"
    task: dict[str, Any] = {}
    try:
        task = _validate_task(_safe_read_json(task_file))
        if stdout_log.is_symlink() or stderr_log.is_symlink():
            raise ValueError("log path is a symlink")
        qoder_args = _build_qodercli_args(task, cwd)
        with (
            stdout_log.open("w", encoding="utf-8") as out,
            stderr_log.open("w", encoding="utf-8") as err,
        ):
            proc = subprocess.run(
                qoder_args,
                stdout=out,
                stderr=err,
                check=False,
                cwd=str(cwd),
            )
        exit_code = proc.returncode
        status = "finished" if exit_code == 0 else "failed"
        _atomic_write_json(
            record_path,
            {
                "status": status,
                "exit_code": exit_code,
                "session_id": task.get("session_id", ""),
                "task_id": task["task_id"],
                "agent_id": task.get("agent_id", ""),
                "client": task.get("client", "qoder"),
                "parent_client": task.get("parent_client", ""),
                "parent_session_id": task.get("parent_session_id", ""),
                "stdout_log": str(stdout_log),
                "stderr_log": str(stderr_log),
            },
        )
    except FileNotFoundError as exc:
        _atomic_write_json(
            record_path,
            {
                "status": "failed",
                "exit_code": 127,
                "error": str(exc),
                "session_id": task.get("session_id", ""),
                "task_id": task.get("task_id", ""),
                "agent_id": task.get("agent_id", ""),
                "client": task.get("client", "qoder"),
                "parent_client": task.get("parent_client", ""),
                "parent_session_id": task.get("parent_session_id", ""),
            },
        )
    except Exception as exc:
        _atomic_write_json(
            record_path,
            {
                "status": "failed",
                "exit_code": 1,
                "error": str(exc),
                "session_id": task.get("session_id", ""),
                "task_id": task.get("task_id", ""),
                "agent_id": task.get("agent_id", ""),
                "client": task.get("client", "qoder"),
                "parent_client": task.get("parent_client", ""),
                "parent_session_id": task.get("parent_session_id", ""),
            },
        )


def cmd_start(args: argparse.Namespace) -> None:
    """启动子任务，立即返回 run_id。"""
    repo_root = _find_repo_root(Path.cwd())
    task_dir = _task_dir(repo_root)
    task_path = Path(args.task)
    _check_no_symlink_ancestors(task_path)
    task = _validate_task(json.loads(task_path.read_text(encoding="utf-8")))

    if "_resume_mode" in task:
        raise ValueError("start does not accept _resume_mode field")

    _find_qoder_cli()

    if not task.get("agent_id"):
        task["agent_id"] = f"agent_{uuid.uuid4().hex[:8]}"
    if not task.get("session_id"):
        task["session_id"] = str(uuid.uuid4())
    task["client"] = "qoder"

    run_id = str(uuid.uuid4())
    run_dir = task_dir / run_id
    _check_no_symlink_ancestors(run_dir)
    old_umask = os.umask(0o077)
    try:
        os.makedirs(run_dir, mode=0o700, exist_ok=False)
    finally:
        os.umask(old_umask)

    _atomic_write_json(run_dir / "task.json", task)

    worker_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_worker",
        str(task_dir),
        run_id,
        str(repo_root),
    ]
    env = os.environ.copy()
    env.pop("QODER_SESSION_ID", None)
    env["FEIPI_AGENT_CLIENT"] = "qoder"
    env["FEIPI_SESSION_ID"] = task.get("session_id", "")
    env["FEIPI_AGENT_ID"] = task.get("agent_id", "")
    if task.get("parent_client"):
        env["FEIPI_PARENT_CLIENT"] = task["parent_client"]
    if task.get("parent_session_id"):
        env["FEIPI_PARENT_SESSION_ID"] = task["parent_session_id"]

    subprocess.Popen(
        worker_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
        cwd=str(repo_root),
    )

    print(run_id)


def cmd_status(args: argparse.Namespace) -> None:
    """查询任务状态。"""
    repo_root = _find_repo_root(Path.cwd())
    task_dir = _task_dir(repo_root)
    run_id = _validate_run_id(args.run_id)
    run_dir = task_dir / run_id
    _check_no_symlink_ancestors(run_dir)

    if not run_dir.exists():
        print(f"error: unknown run id: {run_id}", file=sys.stderr)
        sys.exit(1)

    record = run_dir / "completion.json"
    if record.exists():
        data = _safe_read_json(record)
        print(json.dumps({"run_id": run_id, "status": data["status"]}))
        return

    pid_file = run_dir / "worker.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            print(json.dumps({"run_id": run_id, "status": "running", "pid": pid}))
        except (ValueError, ProcessLookupError, PermissionError):
            print(json.dumps({"run_id": run_id, "status": "unknown"}))
    else:
        print(json.dumps({"run_id": run_id, "status": "unknown"}))


def _read_stdout_tail(path: Path, max_bytes: int = 4000) -> str:
    """读取 stdout 日志尾部最多 max_bytes 字节，不读全文件。"""
    if not path.exists():
        return ""
    if path.is_symlink():
        raise ValueError(f"refusing to read symlink: {path}")
    _check_no_symlink_ancestors(path)
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > max_bytes:
            fh.seek(size - max_bytes)
        raw = fh.read(max_bytes)
    return raw.decode("utf-8", errors="replace")


def cmd_result(args: argparse.Namespace) -> None:
    """获取任务结果，包含报告/日志路径与有限 stdout 尾部。"""
    repo_root = _find_repo_root(Path.cwd())
    task_dir = _task_dir(repo_root)
    run_id = _validate_run_id(args.run_id)
    run_dir = task_dir / run_id
    _check_no_symlink_ancestors(run_dir)

    if not run_dir.exists():
        print(f"error: unknown run id: {run_id}", file=sys.stderr)
        sys.exit(1)

    record = run_dir / "completion.json"
    if not record.exists():
        print(json.dumps({"run_id": run_id, "status": "not_ready"}))
        return

    data = _safe_read_json(record)
    data["run_id"] = run_id
    data["task_file"] = str(run_dir / "task.json")
    data["stdout_log"] = str(run_dir / "stdout.log")
    data["stderr_log"] = str(run_dir / "stderr.log")
    stdout_log = run_dir / "stdout.log"
    data["stdout_tail"] = _read_stdout_tail(stdout_log)
    print(json.dumps(data, ensure_ascii=False))


def cmd_resume(args: argparse.Namespace) -> None:
    """使用记录的 session_id 启动新 run，通过 --resume 恢复。--followup 必填。"""
    repo_root = _find_repo_root(Path.cwd())
    task_dir = _task_dir(repo_root)
    run_id = _validate_run_id(args.run_id)
    run_dir = task_dir / run_id
    _check_no_symlink_ancestors(run_dir)

    if not run_dir.exists():
        print(f"error: unknown run id: {run_id}", file=sys.stderr)
        sys.exit(1)

    record = run_dir / "completion.json"
    if not record.exists():
        print("error: task not yet completed", file=sys.stderr)
        sys.exit(1)

    data = _safe_read_json(record)
    if data.get("status") not in ("finished", "completed"):
        print(f"error: task status is {data.get('status')}", file=sys.stderr)
        sys.exit(1)

    session_id = data.get("session_id")
    if not session_id:
        print("error: no saved session id to resume", file=sys.stderr)
        sys.exit(1)

    if not args.followup:
        print("error: --followup is required for resume", file=sys.stderr)
        sys.exit(1)

    followup_path = Path(args.followup)
    _check_no_symlink_ancestors(followup_path)
    try:
        followup = json.loads(followup_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"followup is not valid JSON: {exc}") from None
    if not isinstance(followup, dict):
        raise ValueError("followup must be a JSON object")

    old_task = _safe_read_json(run_dir / "task.json")
    new_task = dict(old_task)
    for k, v in followup.items():
        if k not in ("session_id", "client", "_resume_mode", "agent_id"):
            new_task[k] = v
    new_task["session_id"] = session_id
    new_task["_resume_mode"] = True
    new_task["client"] = "qoder"
    new_task["agent_id"] = f"agent_{uuid.uuid4().hex[:8]}"
    _validate_task(new_task)

    _find_qoder_cli()

    new_run_id = str(uuid.uuid4())
    new_run_dir = task_dir / new_run_id
    _check_no_symlink_ancestors(new_run_dir)
    old_umask = os.umask(0o077)
    try:
        os.makedirs(new_run_dir, mode=0o700, exist_ok=False)
    finally:
        os.umask(old_umask)

    _atomic_write_json(new_run_dir / "task.json", new_task)

    worker_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_worker",
        str(task_dir),
        new_run_id,
        str(repo_root),
    ]
    env = os.environ.copy()
    env.pop("QODER_SESSION_ID", None)
    env["FEIPI_AGENT_CLIENT"] = "qoder"
    env["FEIPI_SESSION_ID"] = session_id
    env["FEIPI_AGENT_ID"] = new_task["agent_id"]
    if old_task.get("parent_client"):
        env["FEIPI_PARENT_CLIENT"] = old_task["parent_client"]
    if old_task.get("parent_session_id"):
        env["FEIPI_PARENT_SESSION_ID"] = old_task["parent_session_id"]

    subprocess.Popen(
        worker_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
        cwd=str(repo_root),
    )

    print(new_run_id)


def _dispatch_worker(argv: list[str]) -> int:
    """接收任务目录、运行标识、工作目录并执行后台子任务。"""
    if len(argv) != 4:
        print("usage: _worker <task_dir> <run_id> <cwd>", file=sys.stderr)
        return 1
    task_dir = Path(argv[1])
    run_id = argv[2]
    cwd = Path(argv[3])
    _validate_run_id(run_id)
    _check_no_symlink_ancestors(task_dir)
    run_dir = task_dir / run_id
    _check_no_symlink_ancestors(run_dir)
    try:
        task_dir.resolve().relative_to(cwd.resolve())
        run_dir.resolve().relative_to(cwd.resolve())
    except ValueError:
        print("error: task_dir/run_dir must be inside cwd", file=sys.stderr)
        return 1
    old_umask = os.umask(0o077)
    try:
        pid_file = run_dir / "worker.pid"
        if pid_file.is_symlink():
            raise ValueError("pid path is a symlink")
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
        _worker_entry(task_dir, run_id, cwd)
    finally:
        os.umask(old_umask)
    return 0


def main(argv: list[str] | None = None) -> int:
    """主入口，解析子命令并执行。"""
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] == "_worker":
        try:
            return _dispatch_worker(argv)
        except (ValueError, FileNotFoundError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    parser = argparse.ArgumentParser(description="Qoder CLI subtask entry")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start a Qoder subtask")
    p_start.add_argument("--task", required=True, help="Path to task JSON file")
    p_start.set_defaults(func=cmd_start)

    p_status = sub.add_parser("status", help="Check task status")
    p_status.add_argument("run_id", help="Run ID (UUID) from start")
    p_status.set_defaults(func=cmd_status)

    p_result = sub.add_parser("result", help="Get task result")
    p_result.add_argument("run_id", help="Run ID (UUID) from start")
    p_result.set_defaults(func=cmd_result)

    p_resume = sub.add_parser("resume", help="Resume with saved session id")
    p_resume.add_argument("run_id", help="Run ID (UUID) from start")
    p_resume.add_argument("--followup", required=True, help="Path to followup JSON")
    p_resume.set_defaults(func=cmd_resume)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
