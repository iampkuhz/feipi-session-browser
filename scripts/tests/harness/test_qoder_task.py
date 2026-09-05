"""Qoder CLI 子任务脚本的确定性测试，使用 fake CLI 隔离。"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from scripts.harness import qoder_task


def _valid_task_dict(**overrides: str) -> dict[str, str]:
    """构造合法的完整九项 handoff 任务字典。"""
    base = {
        "goal": "test goal",
        "task_id": "test_001",
        "task_source": "test",
        "allowed_files": "/tmp/a",
        "forbidden_files": "/tmp/b",
        "required_context": "AGENTS.md",
        "expected_output": "result",
        "validation_command": "echo ok",
        "failure_policy": "report BLOCKED",
    }
    base.update(overrides)
    return base


@pytest.fixture()
def fake_cli(tmp_path: Path) -> Path:
    """创建 fake qodercli，立即退出 0。"""
    cli = tmp_path / "fake-qodercli"
    cli.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    cli.chmod(0o755)
    return cli


@pytest.fixture()
def fake_cli_fail(tmp_path: Path) -> Path:
    """创建 fake qodercli，退出 1。"""
    cli = tmp_path / "fake-qodercli-fail"
    cli.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    cli.chmod(0o755)
    return cli


@pytest.fixture()
def fake_repo_root(tmp_path: Path) -> Path:
    """创建含 .git 的合成仓库根。"""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return root


@pytest.fixture()
def task_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """创建任务目录并设置环境变量，同时创建 .git 使其成为有效仓库根。"""
    (tmp_path / ".git").mkdir()
    td = tmp_path / "tasks"
    td.mkdir()
    monkeypatch.setenv("QODER_TASK_DIR", str(td))
    return td


@pytest.fixture()
def repo_with_task_dir(fake_repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """创建仓库内的任务目录，确保 QODER_TASK_DIR 在仓库内。"""
    td = fake_repo_root / "tmp" / "qoder-tasks"
    td.mkdir(parents=True)
    monkeypatch.setenv("QODER_TASK_DIR", str(td))
    return fake_repo_root, td


@pytest.fixture()
def task_json(tmp_path: Path) -> Path:
    """创建合法的任务 JSON 文件。"""
    task = _valid_task_dict()
    path = tmp_path / "task.json"
    path.write_text(json.dumps(task), encoding="utf-8")
    return path


def test_validate_run_id_rejects_invalid() -> None:
    """校验 run_id 拒绝非法格式。"""
    for bad_id in ["../escape", "a/b", "a\\b", ".", "..", "", " ", "-leading-dash"]:
        with pytest.raises(ValueError, match="invalid run id"):
            qoder_task._validate_run_id(bad_id)


def test_validate_run_id_accepts_valid() -> None:
    """校验 run_id 接受合法格式。"""
    for good_id in ["abc", "a_b.c-d", "A123", "x" * 128]:
        assert qoder_task._validate_run_id(good_id) == good_id


def test_validate_task_missing_field() -> None:
    """缺少必填 handoff 字段应报错。"""
    task = _valid_task_dict()
    del task["goal"]
    with pytest.raises(ValueError, match="missing required handoff field"):
        qoder_task._validate_task(task)


def test_validate_task_empty_field() -> None:
    """空字符串字段应报错。"""
    task = _valid_task_dict(goal="")
    with pytest.raises(ValueError, match="non-empty string"):
        qoder_task._validate_task(task)


def test_validate_task_invalid_task_id() -> None:
    """非法 task_id 应报错。"""
    task = _valid_task_dict(task_id="../bad")
    with pytest.raises(ValueError, match="task_id"):
        qoder_task._validate_task(task)


def test_validate_task_invalid_permission_mode() -> None:
    """非法 permission_mode 应报错。"""
    task = _valid_task_dict(permission_mode="bypass_permissions")
    with pytest.raises(ValueError, match="permission_mode"):
        qoder_task._validate_task(task)


def test_validate_task_permission_mode_list_rejected() -> None:
    """permission_mode 为 list 应报错。"""
    task = _valid_task_dict()
    task["permission_mode"] = ["default"]  # type: ignore[assignment]
    with pytest.raises(ValueError, match="permission_mode"):
        qoder_task._validate_task(task)


def test_validate_task_agent_id_null_rejected() -> None:
    """agent_id 为 null 应报错。"""
    task = _valid_task_dict()
    task["agent_id"] = None  # type: ignore[assignment]
    with pytest.raises(ValueError, match="agent_id"):
        qoder_task._validate_task(task)


def test_validate_task_agent_id_list_rejected() -> None:
    """agent_id 为 list 应报错。"""
    task = _valid_task_dict()
    task["agent_id"] = ["agent_001"]  # type: ignore[assignment]
    with pytest.raises(ValueError, match="agent_id"):
        qoder_task._validate_task(task)


def test_validate_task_session_id_must_be_uuid() -> None:
    """session_id 必须是合法 UUID。"""
    task = _valid_task_dict(session_id="not-a-uuid")
    with pytest.raises(ValueError, match="session_id"):
        qoder_task._validate_task(task)


def test_validate_task_valid_permission_modes() -> None:
    """合法 permission_mode 应通过。"""
    for mode in ["default", "accept_edits", "dont_ask"]:
        task = _valid_task_dict(permission_mode=mode)
        assert qoder_task._validate_task(task)["permission_mode"] == mode


def test_safe_read_json_rejects_symlink(tmp_path: Path) -> None:
    """拒绝读取符号链接。"""
    real = tmp_path / "real.json"
    real.write_text('{"a": 1}', encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        qoder_task._safe_read_json(link)


def test_check_no_symlink_ancestors(tmp_path: Path) -> None:
    """拒绝路径祖先为符号链接。"""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link_dir = tmp_path / "link"
    link_dir.symlink_to(real_dir)
    target = link_dir / "file.txt"
    with pytest.raises(ValueError, match="symlink"):
        qoder_task._check_no_symlink_ancestors(target)


def test_atomic_write_json(tmp_path: Path) -> None:
    """原子写入 JSON 并设置权限。"""
    target = tmp_path / "sub" / "out.json"
    target.parent.mkdir()
    qoder_task._atomic_write_json(target, {"k": "v"})
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == {"k": "v"}
    assert not list(target.parent.glob("*.tmp"))
    assert (target.stat().st_mode & 0o777) == 0o600


def test_build_prompt_includes_all_handoff() -> None:
    """prompt 应包含完整 handoff 和身份信息。"""
    task = _valid_task_dict(
        agent_id="agent_001",
        client="qoder",
        session_id=str(uuid.uuid4()),
        parent_client="codex",
        parent_session_id="parent-sess-456",
    )
    prompt = qoder_task._build_prompt(task)
    assert "Goal: test goal" in prompt
    assert "Task id: test_001" in prompt
    assert "Allowed files/directories: /tmp/a" in prompt
    assert "Forbidden files/directories: /tmp/b" in prompt
    assert "Required context files: AGENTS.md" in prompt
    assert "Validation command: echo ok" in prompt
    assert "Agent id: agent_001" in prompt
    assert "Client: qoder" in prompt
    assert "Session id:" in prompt
    assert "Parent client: codex" in prompt
    assert "Parent session id: parent-sess-456" in prompt


def test_start_returns_uuid_and_is_nonblocking(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    repo_with_task_dir: tuple[Path, Path],
    task_json: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """start 应立即返回 UUID，不等待 worker。"""
    fake_repo_root, _task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    monkeypatch.chdir(fake_repo_root)

    mock_popen = MagicMock()
    mock_popen.return_value = MagicMock()
    with patch("subprocess.Popen", mock_popen):
        assert qoder_task.main(["start", "--task", str(task_json)]) == 0

    run_id = capsys.readouterr().out.strip()
    assert run_id
    assert len(run_id) == 36, f"run_id should be UUID, got {run_id}"
    assert "-" in run_id
    mock_popen.assert_called_once()


def test_start_missing_cli_fails(
    monkeypatch: pytest.MonkeyPatch,
    repo_with_task_dir: tuple[Path, Path],
    task_json: Path,
) -> None:
    """缺少 CLI 应明确失败，不创建假的成功任务。"""
    fake_repo_root, _task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", "/nonexistent/qodercli-xyz")
    monkeypatch.chdir(fake_repo_root)

    assert qoder_task.main(["start", "--task", str(task_json)]) == 1


def test_start_invalid_task_fails(
    monkeypatch: pytest.MonkeyPatch,
    repo_with_task_dir: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """非法任务 JSON 应明确失败。"""
    fake_repo_root, _task_dir = repo_with_task_dir
    monkeypatch.chdir(fake_repo_root)
    bad = tmp_path / "bad.json"
    bad.write_text('{"goal": "x"}', encoding="utf-8")
    assert qoder_task.main(["start", "--task", str(bad)]) == 1


def test_start_rejects_resume_mode(
    monkeypatch: pytest.MonkeyPatch,
    repo_with_task_dir: tuple[Path, Path],
    tmp_path: Path,
    fake_cli: Path,
) -> None:
    """start 不接受 _resume_mode 字段。"""
    fake_repo_root, _task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    monkeypatch.chdir(fake_repo_root)
    task = _valid_task_dict()
    task["_resume_mode"] = True  # type: ignore[assignment]
    path = tmp_path / "task.json"
    path.write_text(json.dumps(task), encoding="utf-8")
    assert qoder_task.main(["start", "--task", str(path)]) == 1


def test_worker_completes_with_fake_cli(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    repo_with_task_dir: tuple[Path, Path],
) -> None:
    """Worker 应阻塞等待 CLI 退出并写入完成记录。"""
    fake_repo_root, task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    monkeypatch.chdir(fake_repo_root)

    task = _valid_task_dict(session_id=str(uuid.uuid4()))
    run_id = str(uuid.uuid4())
    run_dir = task_dir / run_id
    run_dir.mkdir()
    (run_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

    qoder_task._worker_entry(task_dir, run_id, fake_repo_root)

    result = json.loads((run_dir / "completion.json").read_text("utf-8"))
    assert result["exit_code"] == 0
    assert result["status"] == "finished"
    assert result["task_id"] == "test_001"
    assert result["client"] == "qoder"
    assert result["session_id"] == task["session_id"]


def test_worker_cli_nonzero_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli_fail: Path,
    repo_with_task_dir: tuple[Path, Path],
) -> None:
    """CLI 非零退出应标记为 failed。"""
    fake_repo_root, task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli_fail))
    monkeypatch.chdir(fake_repo_root)

    task = _valid_task_dict(session_id=str(uuid.uuid4()))
    run_id = str(uuid.uuid4())
    run_dir = task_dir / run_id
    run_dir.mkdir()
    (run_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

    qoder_task._worker_entry(task_dir, run_id, fake_repo_root)

    result = json.loads((run_dir / "completion.json").read_text("utf-8"))
    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert result["client"] == "qoder"
    assert result["session_id"] == task["session_id"]


def test_worker_saves_identity_on_exception(
    monkeypatch: pytest.MonkeyPatch,
    repo_with_task_dir: tuple[Path, Path],
) -> None:
    """Worker 异常也应保存身份信息。"""
    fake_repo_root, task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", "/nonexistent/cli")
    monkeypatch.chdir(fake_repo_root)

    session_id = str(uuid.uuid4())
    task = _valid_task_dict(
        session_id=session_id,
        agent_id="agent_test",
        parent_client="codex",
        parent_session_id="parent-sess",
    )
    run_id = str(uuid.uuid4())
    run_dir = task_dir / run_id
    run_dir.mkdir()
    (run_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

    qoder_task._worker_entry(task_dir, run_id, fake_repo_root)

    result = json.loads((run_dir / "completion.json").read_text("utf-8"))
    assert result["status"] == "failed"
    assert result["session_id"] == session_id
    assert result["agent_id"] == "agent_test"
    assert result["client"] == "qoder"
    assert result["parent_client"] == "codex"
    assert result["parent_session_id"] == "parent-sess"


def test_status_unknown_run_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
) -> None:
    """未知 run_id 应非零退出。"""
    monkeypatch.chdir(task_dir)
    with pytest.raises(SystemExit):
        qoder_task.main(["status", "nonexistent-uuid"])


def test_status_running_shows_pid(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """运行中的 worker 应显示 PID。"""
    run_id = str(uuid.uuid4())
    run_dir = task_dir / run_id
    run_dir.mkdir()
    (run_dir / "worker.pid").write_text(str(os.getpid()), encoding="utf-8")
    monkeypatch.chdir(task_dir)

    qoder_task.main(["status", run_id])
    output = capsys.readouterr().out
    data = json.loads(output)
    assert data["status"] == "running"
    assert data["pid"] == os.getpid()


def test_status_completed(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """已完成任务应显示 finished。"""
    run_dir = task_dir / "run_x2"
    run_dir.mkdir()
    (run_dir / "completion.json").write_text(
        json.dumps({"status": "finished", "exit_code": 0}),
        encoding="utf-8",
    )
    monkeypatch.chdir(task_dir)
    qoder_task.main(["status", "run_x2"])
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "finished"


def test_result_not_ready(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """未完成任务应显示 not_ready。"""
    run_dir = task_dir / "run_x3"
    run_dir.mkdir()
    monkeypatch.chdir(task_dir)
    qoder_task.main(["result", "run_x3"])
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "not_ready"


def test_result_includes_paths_and_tail(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """结果应包含报告/日志路径与 stdout 尾部。"""
    run_dir = task_dir / "run_x4"
    run_dir.mkdir()
    (run_dir / "completion.json").write_text(
        json.dumps({"status": "finished", "exit_code": 0, "session_id": str(uuid.uuid4())}),
        encoding="utf-8",
    )
    (run_dir / "stdout.log").write_text("test output", encoding="utf-8")
    monkeypatch.chdir(task_dir)
    qoder_task.main(["result", "run_x4"])
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "finished"
    assert "task_file" in data
    assert "stdout_log" in data
    assert "stderr_log" in data
    assert data["stdout_tail"] == "test output"


def test_result_stdout_tail_limited(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """stdout 尾部最多读取 4000 字节。"""
    run_dir = task_dir / "run_x5"
    run_dir.mkdir()
    (run_dir / "completion.json").write_text(
        json.dumps({"status": "finished", "exit_code": 0}),
        encoding="utf-8",
    )
    large_output = "x" * 5000
    (run_dir / "stdout.log").write_text(large_output, encoding="utf-8")
    monkeypatch.chdir(task_dir)
    qoder_task.main(["result", "run_x5"])
    data = json.loads(capsys.readouterr().out)
    assert len(data["stdout_tail"]) == 4000


def test_result_unknown_run_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
) -> None:
    """未知 run_id 应非零退出。"""
    monkeypatch.chdir(task_dir)
    with pytest.raises(SystemExit):
        qoder_task.main(["result", "nonexistent-uuid"])


def test_resume_uses_recorded_session_id(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    task_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """resume 应使用记录的 session_id 并通过 --resume 参数启动新 run。"""
    recorded_session_id = str(uuid.uuid4())
    run_dir = task_dir / "run_x6"
    run_dir.mkdir()
    (run_dir / "completion.json").write_text(
        json.dumps({"status": "finished", "session_id": recorded_session_id}),
        encoding="utf-8",
    )
    (run_dir / "task.json").write_text(
        json.dumps(_valid_task_dict(session_id=recorded_session_id)),
        encoding="utf-8",
    )

    followup = _valid_task_dict(goal="new goal")
    followup_path = task_dir / "followup.json"
    followup_path.write_text(json.dumps(followup), encoding="utf-8")

    monkeypatch.chdir(task_dir)
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))

    mock_popen = MagicMock()
    mock_popen.return_value = MagicMock()
    with patch("subprocess.Popen", mock_popen):
        assert qoder_task.main(["resume", "run_x6", "--followup", str(followup_path)]) == 0

    new_run_id = capsys.readouterr().out.strip()
    assert new_run_id
    assert new_run_id != "run_x6"

    new_run_dir = task_dir / new_run_id
    new_task = json.loads((new_run_dir / "task.json").read_text("utf-8"))
    assert new_task["_resume_mode"] is True
    assert new_task["session_id"] == recorded_session_id
    assert new_task["goal"] == "new goal"
    assert new_task["client"] == "qoder"
    assert new_task["agent_id"] != "agent_001"

    mock_popen.assert_called_once()


def test_resume_requires_followup(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
) -> None:
    """resume 必须提供 --followup。"""
    run_dir = task_dir / "run_x7"
    run_dir.mkdir()
    (run_dir / "completion.json").write_text(
        json.dumps({"status": "finished", "session_id": str(uuid.uuid4())}),
        encoding="utf-8",
    )
    monkeypatch.chdir(task_dir)
    with pytest.raises(SystemExit):
        qoder_task.main(["resume", "run_x7"])


def test_resume_fails_when_not_completed(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
) -> None:
    """未完成的任务 resume 应非零退出。"""
    run_dir = task_dir / "run_x8"
    run_dir.mkdir()
    monkeypatch.chdir(task_dir)
    with pytest.raises(SystemExit):
        qoder_task.main(["resume", "run_x8", "--followup", "/tmp/f.json"])


def test_resume_unknown_run_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
) -> None:
    """未知 run_id resume 应非零退出。"""
    monkeypatch.chdir(task_dir)
    with pytest.raises(SystemExit):
        qoder_task.main(["resume", "nonexistent-uuid", "--followup", "/tmp/f.json"])


def test_start_symlink_task_rejected(
    monkeypatch: pytest.MonkeyPatch,
    repo_with_task_dir: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """符号链接任务文件应被拒绝。"""
    fake_repo_root, _task_dir = repo_with_task_dir
    real = tmp_path / "real.json"
    real.write_text(json.dumps(_valid_task_dict()), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    monkeypatch.chdir(fake_repo_root)
    assert qoder_task.main(["start", "--task", str(link)]) == 1


def test_start_permission_bypass_rejected(
    monkeypatch: pytest.MonkeyPatch,
    repo_with_task_dir: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """bypass_permissions 应被拒绝。"""
    fake_repo_root, _task_dir = repo_with_task_dir
    task = _valid_task_dict(permission_mode="bypass_permissions")
    path = tmp_path / "task.json"
    path.write_text(json.dumps(task), encoding="utf-8")
    monkeypatch.chdir(fake_repo_root)
    assert qoder_task.main(["start", "--task", str(path)]) == 1


def test_build_qodercli_args_passes_session_id(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    fake_repo_root: Path,
) -> None:
    """新任务应传 --session-id。"""
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    session_id = str(uuid.uuid4())
    task = _valid_task_dict(session_id=session_id)
    args = qoder_task._build_qodercli_args(task, fake_repo_root)
    assert "--session-id" in args
    assert session_id in args
    assert "--resume" not in args


def test_build_qodercli_args_passes_resume(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    fake_repo_root: Path,
) -> None:
    """恢复任务应传 --resume。"""
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    session_id = str(uuid.uuid4())
    task = _valid_task_dict(session_id=session_id, _resume_mode="true")  # type: ignore[arg-type]
    args = qoder_task._build_qodercli_args(task, fake_repo_root)
    assert "--resume" in args
    assert session_id in args
    assert "--session-id" not in args


def test_dispatch_worker_creates_files_with_0600(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    repo_with_task_dir: tuple[Path, Path],
) -> None:
    """Worker 创建的输出文件权限应为 0600。"""
    fake_repo_root, task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    monkeypatch.chdir(fake_repo_root)

    task = _valid_task_dict(session_id=str(uuid.uuid4()))
    run_id = str(uuid.uuid4())
    run_dir = task_dir / run_id
    run_dir.mkdir(mode=0o700)
    (run_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

    argv = ["_worker", str(task_dir), run_id, str(fake_repo_root)]
    assert qoder_task._dispatch_worker(argv) == 0

    completion = run_dir / "completion.json"
    stdout_log = run_dir / "stdout.log"
    stderr_log = run_dir / "stderr.log"
    assert completion.exists()
    assert stdout_log.exists()
    assert stderr_log.exists()
    assert (completion.stat().st_mode & 0o777) == 0o600
    assert (stdout_log.stat().st_mode & 0o777) == 0o600
    assert (stderr_log.stat().st_mode & 0o777) == 0o600


def test_dispatch_worker_creates_run_dir_with_0700(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    repo_with_task_dir: tuple[Path, Path],
) -> None:
    """start 创建的 run 目录权限应为 0700。"""
    fake_repo_root, task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    monkeypatch.chdir(fake_repo_root)

    task = _valid_task_dict()
    task_path = task_dir / "task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")

    mock_popen = MagicMock()
    mock_popen.return_value = MagicMock()
    with patch("subprocess.Popen", mock_popen):
        assert qoder_task.main(["start", "--task", str(task_path)]) == 0

    run_dirs = [d for d in task_dir.iterdir() if d.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (run_dir.stat().st_mode & 0o777) == 0o700


def test_dispatch_worker_rejects_pid_symlink(
    monkeypatch: pytest.MonkeyPatch,
    repo_with_task_dir: tuple[Path, Path],
) -> None:
    """Worker 应拒绝 pid 路径为符号链接。"""
    fake_repo_root, task_dir = repo_with_task_dir
    monkeypatch.chdir(fake_repo_root)

    task = _valid_task_dict(session_id=str(uuid.uuid4()))
    run_id = str(uuid.uuid4())
    run_dir = task_dir / run_id
    run_dir.mkdir(mode=0o700)
    (run_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

    real_pid = task_dir / "real.pid"
    real_pid.write_text("12345", encoding="utf-8")
    pid_link = run_dir / "worker.pid"
    pid_link.symlink_to(real_pid)

    argv = ["_worker", str(task_dir), run_id, str(fake_repo_root)]
    with pytest.raises(ValueError, match="symlink"):
        qoder_task._dispatch_worker(argv)
    assert real_pid.read_text() == "12345"


def test_status_rejects_run_dir_symlink(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
) -> None:
    """status 应拒绝 run_dir 为符号链接。"""
    real_run = task_dir / "real_run"
    real_run.mkdir()
    (real_run / "completion.json").write_text(json.dumps({"status": "finished"}), encoding="utf-8")
    link_run = task_dir / "link_run"
    link_run.symlink_to(real_run)

    monkeypatch.chdir(task_dir)
    assert qoder_task.main(["status", "link_run"]) == 1


def test_result_rejects_run_dir_symlink(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
) -> None:
    """result 应拒绝 run_dir 为符号链接。"""
    real_run = task_dir / "real_run2"
    real_run.mkdir()
    (real_run / "completion.json").write_text(json.dumps({"status": "finished"}), encoding="utf-8")
    link_run = task_dir / "link_run2"
    link_run.symlink_to(real_run)

    monkeypatch.chdir(task_dir)
    assert qoder_task.main(["result", "link_run2"]) == 1


def test_resume_rejects_run_dir_symlink(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
) -> None:
    """resume 应拒绝 run_dir 为符号链接。"""
    real_run = task_dir / "real_run3"
    real_run.mkdir()
    (real_run / "completion.json").write_text(
        json.dumps({"status": "finished", "session_id": str(uuid.uuid4())}),
        encoding="utf-8",
    )
    link_run = task_dir / "link_run3"
    link_run.symlink_to(real_run)

    monkeypatch.chdir(task_dir)
    assert qoder_task.main(["resume", "link_run3", "--followup", "/tmp/f.json"]) == 1


def test_resume_rejects_non_dict_followup(
    monkeypatch: pytest.MonkeyPatch,
    task_dir: Path,
) -> None:
    """resume 应拒绝 followup 非 dict。"""
    run_id = str(uuid.uuid4())
    run_dir = task_dir / run_id
    run_dir.mkdir()
    (run_dir / "completion.json").write_text(
        json.dumps({"status": "finished", "session_id": str(uuid.uuid4())}),
        encoding="utf-8",
    )
    (run_dir / "task.json").write_text(json.dumps(_valid_task_dict()), encoding="utf-8")

    followup_path = task_dir / "followup.json"
    followup_path.write_text('["not", "a", "dict"]', encoding="utf-8")

    monkeypatch.chdir(task_dir)
    assert qoder_task.main(["resume", run_id, "--followup", str(followup_path)]) == 1


def test_validate_task_session_id_none_rejected() -> None:
    """session_id 为 None 应报错。"""
    task = _valid_task_dict()
    task["session_id"] = None  # type: ignore[assignment]
    with pytest.raises(ValueError, match="session_id"):
        qoder_task._validate_task(task)


def test_validate_task_session_id_list_rejected() -> None:
    """session_id 为 list 应报错。"""
    task = _valid_task_dict()
    task["session_id"] = ["uuid"]  # type: ignore[assignment]
    with pytest.raises(ValueError, match="session_id"):
        qoder_task._validate_task(task)


def test_validate_task_session_id_int_rejected() -> None:
    """session_id 为 int 应报错。"""
    task = _valid_task_dict()
    task["session_id"] = 0  # type: ignore[assignment]
    with pytest.raises(ValueError, match="session_id"):
        qoder_task._validate_task(task)


def test_validate_task_parent_client_list_rejected() -> None:
    """parent_client 为 list 应报错。"""
    task = _valid_task_dict()
    task["parent_client"] = ["codex"]  # type: ignore[assignment]
    with pytest.raises(ValueError, match="parent_client"):
        qoder_task._validate_task(task)


def test_validate_task_parent_session_id_int_rejected() -> None:
    """parent_session_id 为 int 应报错。"""
    task = _valid_task_dict()
    task["parent_session_id"] = 123  # type: ignore[assignment]
    with pytest.raises(ValueError, match="parent_session_id"):
        qoder_task._validate_task(task)


def test_start_child_env_pops_qoder_session_id_and_uses_feipi(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    repo_with_task_dir: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """start 子 env 必须 pop QODER_SESSION_ID 并使用 FEIPI_* 身份变量。"""
    fake_repo_root, _task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    monkeypatch.setenv("QODER_SESSION_ID", "should-be-removed")
    monkeypatch.chdir(fake_repo_root)

    task = _valid_task_dict(
        parent_client="codex",
        parent_session_id="00000000-0000-4000-8000-000000000001",
    )
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")

    mock_popen = MagicMock()
    mock_popen.return_value = MagicMock()
    with patch("subprocess.Popen", mock_popen):
        assert qoder_task.main(["start", "--task", str(task_path)]) == 0

    call_env = mock_popen.call_args.kwargs["env"]
    assert "QODER_SESSION_ID" not in call_env
    assert call_env["FEIPI_AGENT_CLIENT"] == "qoder"
    assert "FEIPI_SESSION_ID" in call_env
    assert uuid.UUID(call_env["FEIPI_SESSION_ID"])
    assert call_env["FEIPI_AGENT_ID"].startswith("agent_")
    assert call_env["FEIPI_PARENT_CLIENT"] == "codex"
    assert call_env["FEIPI_PARENT_SESSION_ID"] == "00000000-0000-4000-8000-000000000001"


def test_resume_argv_has_resume_not_session_id_and_env_feipi(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    task_dir: Path,
) -> None:
    """resume argv 必须只有 --resume 无 --session-id；child env 必须 pop QODER_SESSION_ID 并使用 FEIPI_*。"""
    recorded_session_id = str(uuid.uuid4())
    run_dir = task_dir / "run_env1"
    run_dir.mkdir()
    (run_dir / "completion.json").write_text(
        json.dumps({"status": "finished", "session_id": recorded_session_id}),
        encoding="utf-8",
    )
    (run_dir / "task.json").write_text(
        json.dumps(
            _valid_task_dict(
                session_id=recorded_session_id,
                parent_client="codex",
                parent_session_id="00000000-0000-4000-8000-000000000001",
            )
        ),
        encoding="utf-8",
    )

    followup = _valid_task_dict(goal="followup goal")
    followup_path = task_dir / "followup.json"
    followup_path.write_text(json.dumps(followup), encoding="utf-8")

    monkeypatch.chdir(task_dir)
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    monkeypatch.setenv("QODER_SESSION_ID", "should-be-removed-in-child")

    mock_popen = MagicMock()
    mock_popen.return_value = MagicMock()
    with patch("subprocess.Popen", mock_popen):
        assert qoder_task.main(["resume", "run_env1", "--followup", str(followup_path)]) == 0

    worker_cmd = mock_popen.call_args.args[0]
    inner_task_dir = Path(worker_cmd[3])
    inner_run_id = worker_cmd[4]
    inner_cwd = Path(worker_cmd[5])
    inner_task = json.loads(
        (inner_task_dir / inner_run_id / "task.json").read_text(encoding="utf-8")
    )
    inner_argv = qoder_task._build_qodercli_args(inner_task, inner_cwd)
    assert "--resume" in inner_argv
    assert recorded_session_id in inner_argv
    assert "--session-id" not in inner_argv

    call_env = mock_popen.call_args.kwargs["env"]
    assert "QODER_SESSION_ID" not in call_env
    assert call_env["FEIPI_AGENT_CLIENT"] == "qoder"
    assert call_env["FEIPI_SESSION_ID"] == recorded_session_id
    assert call_env["FEIPI_AGENT_ID"].startswith("agent_")
    assert call_env["FEIPI_PARENT_CLIENT"] == "codex"
    assert call_env["FEIPI_PARENT_SESSION_ID"] == "00000000-0000-4000-8000-000000000001"


def test_start_argv_has_session_id_for_new_task_and_env_feipi(
    monkeypatch: pytest.MonkeyPatch,
    fake_cli: Path,
    repo_with_task_dir: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """start 新任务 argv 必须含 --session-id；child env 必须使用 FEIPI_*。"""
    fake_repo_root, _task_dir = repo_with_task_dir
    monkeypatch.setenv("QODER_TASK_CLI", str(fake_cli))
    monkeypatch.setenv("QODER_SESSION_ID", "should-be-removed")
    monkeypatch.chdir(fake_repo_root)

    task = _valid_task_dict()
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")

    mock_popen = MagicMock()
    mock_popen.return_value = MagicMock()
    with patch("subprocess.Popen", mock_popen):
        assert qoder_task.main(["start", "--task", str(task_path)]) == 0

    call_env = mock_popen.call_args.kwargs["env"]
    assert "QODER_SESSION_ID" not in call_env
    assert call_env["FEIPI_AGENT_CLIENT"] == "qoder"
    assert "FEIPI_SESSION_ID" in call_env
    assert uuid.UUID(call_env["FEIPI_SESSION_ID"])


def test_public_executable_registration() -> None:
    """harness/manifest.yaml 必须登记 qoder_task 公共入口。"""
    repo_root = Path(__file__).resolve().parents[3]
    manifest_path = repo_root / "harness" / "manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert data["public_executables"]["qoder_task"] == "python3 scripts/harness/qoder_task.py"
