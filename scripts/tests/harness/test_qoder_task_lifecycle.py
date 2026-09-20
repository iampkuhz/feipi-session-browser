"""Qoder 任务生命周期的 synthetic 确定性测试。

覆盖 watchdog 调度、ack 身份/幂等、resume 替代链、迟到回调、worker 异常等。
使用 fake clock/process/queue，不真实等待 5 分钟。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.harness import qoder_task
from scripts.harness import qoder_task_lifecycle as lc

# --- Helpers ---


class FakeClock:
    """可注入的 fake 时钟。"""

    def __init__(self, start: float = 0.0) -> None:
        self._time = start

    def __call__(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


class FakeSleep:
    """可注入的 fake sleep，自动推进 fake clock。"""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


def _valid_task(
    *,
    parent_client: str = "codex",
    parent_session_id: str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    session_id: str | None = None,
    task_id: str = "test_001",
    agent_id: str = "agent_test001",
    **overrides: str,
) -> dict[str, str]:
    """构造合法的完整 handoff 任务字典。"""
    base = {
        "goal": "test goal",
        "task_id": task_id,
        "task_source": "test",
        "allowed_files": "/tmp/a",
        "forbidden_files": "/tmp/b",
        "required_context": "AGENTS.md",
        "expected_output": "result",
        "validation_command": "echo ok",
        "failure_policy": "report BLOCKED",
        "session_id": session_id or str(uuid.uuid4()),
        "client": "qoder",
        "parent_client": parent_client,
        "parent_session_id": parent_session_id,
        "agent_id": agent_id,
    }
    base.update(overrides)
    return base


def _make_run(
    task_dir: Path,
    run_id: str | None = None,
    *,
    task: dict | None = None,
    completion: dict | None = None,
    lifecycle: dict | None = None,
) -> Path:
    """创建 run 目录并写入可选文件。"""
    rid = run_id or str(uuid.uuid4())
    run_dir = task_dir / rid
    run_dir.mkdir(mode=0o700, exist_ok=True)
    if task is not None:
        lc._atomic_write_json(run_dir / "task.json", task)
    if completion is not None:
        lc._atomic_write_json(run_dir / "completion.json", completion)
    if lifecycle is not None:
        lc.write_lifecycle(run_dir, lifecycle)
    return run_dir


# --- Watchdog scheduling tests ---


def test_watchdog_initial_delay_is_300s(task_dir: Path) -> None:
    """首次检查在 300 秒后。"""
    run_dir = _make_run(task_dir, task=_valid_task())
    clock = FakeClock()
    sleep = FakeSleep(clock)
    actions: list[str] = []

    def mock_check(_rd, _rr, _sc):
        actions.append("check")
        return "acknowledged"  # 第一次检查后停止

    with patch.object(lc, "watchdog_check", side_effect=mock_check):
        result = lc.watchdog_loop(
            run_dir, Path("."), send_callback=MagicMock(), sleep_fn=sleep, clock_fn=clock
        )

    assert sleep.calls[0] == lc.WATCHDOG_INITIAL_DELAY
    assert result == "acknowledged"


def test_watchdog_subsequent_interval_is_600s(task_dir: Path) -> None:
    """后续检查间隔 600 秒。"""
    run_dir = _make_run(task_dir, task=_valid_task())
    clock = FakeClock()
    sleep = FakeSleep(clock)
    check_count = 0

    def mock_check(_rd, _rr, _sc):
        nonlocal check_count
        check_count += 1
        if check_count >= 3:
            return "acknowledged"
        return "continue"

    with patch.object(lc, "watchdog_check", side_effect=mock_check):
        lc.watchdog_loop(
            run_dir, Path("."), send_callback=MagicMock(), sleep_fn=sleep, clock_fn=clock
        )

    assert sleep.calls[0] == lc.WATCHDOG_INITIAL_DELAY  # 300
    assert sleep.calls[1] == lc.WATCHDOG_INTERVAL  # 600
    assert sleep.calls[2] == lc.WATCHDOG_INTERVAL  # 600
    assert check_count == 3


def test_watchdog_exhausted_after_24h(task_dir: Path) -> None:
    """24 小时后记录 exhausted 并退出。"""
    run_dir = _make_run(task_dir, task=_valid_task())
    clock = FakeClock()
    sleep = FakeSleep(clock)

    def mock_check(_rd, _rr, _sc):
        return "continue"  # 永远不完成

    with patch.object(lc, "watchdog_check", side_effect=mock_check):
        result = lc.watchdog_loop(
            run_dir, Path("."), send_callback=MagicMock(), sleep_fn=sleep, clock_fn=clock
        )

    assert result == "exhausted"
    lifecycle = lc.read_lifecycle(run_dir)
    assert lifecycle["status"] == "exhausted"
    assert "exhausted_at" in lifecycle


def test_watchdog_running_silent_no_action(task_dir: Path) -> None:
    """运行中且无变化时 watchdog 静默。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0, "task_id": "test_001"},
    )
    # 已有 callback，不应重发
    lc._atomic_write_json(
        run_dir / "callback.json",
        {"status": "queued", "message_id": "msg-123"},
    )

    action = lc.watchdog_check(run_dir, Path("."), MagicMock())
    assert action == "continue"


def test_watchdog_stops_on_acknowledged(task_dir: Path) -> None:
    """收到 ack 后 watchdog 停止。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        lifecycle={"status": "acknowledged"},
    )
    action = lc.watchdog_check(run_dir, Path("."), MagicMock())
    assert action == "acknowledged"


def test_watchdog_stops_on_superseded(task_dir: Path) -> None:
    """被替代后 watchdog 停止。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        lifecycle={"status": "superseded"},
    )
    action = lc.watchdog_check(run_dir, Path("."), MagicMock())
    assert action == "superseded"


# --- Watchdog callback tests ---


def test_watchdog_sends_first_notification_when_no_callback(task_dir: Path) -> None:
    """completion 存在但从未尝试通知时，watchdog 补发首次通知。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0, "task_id": "test_001"},
    )
    mock_send = MagicMock()

    action = lc.watchdog_check(run_dir, Path("."), mock_send)

    assert action == "sent_first"
    mock_send.assert_called_once()


def test_watchdog_no_resend_when_callback_exists(task_dir: Path) -> None:
    """callback.json 存在时不重发。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
    )
    lc._atomic_write_json(
        run_dir / "callback.json",
        {"status": "queued", "message_id": "msg-123"},
    )
    mock_send = MagicMock()

    action = lc.watchdog_check(run_dir, Path("."), mock_send)

    assert action == "continue"
    mock_send.assert_not_called()


def test_watchdog_no_resend_when_claim_exists(task_dir: Path) -> None:
    """callback.claim 存在时不重发。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
    )
    (run_dir / "callback.claim").touch()
    mock_send = MagicMock()

    action = lc.watchdog_check(run_dir, Path("."), mock_send)

    assert action == "continue"
    mock_send.assert_not_called()


def test_watchdog_no_resend_on_queued_status(task_dir: Path) -> None:
    """callback 状态为 queued 时不重发。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
    )
    lc._atomic_write_json(
        run_dir / "callback.json",
        {"status": "queued"},
    )
    mock_send = MagicMock()

    action = lc.watchdog_check(run_dir, Path("."), mock_send)
    assert action == "continue"
    mock_send.assert_not_called()


def test_watchdog_no_resend_on_unknown_status(task_dir: Path) -> None:
    """callback 状态为 unknown 时不重发。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
    )
    lc._atomic_write_json(
        run_dir / "callback.json",
        {"status": "unknown", "error": "timeout"},
    )
    mock_send = MagicMock()

    action = lc.watchdog_check(run_dir, Path("."), mock_send)
    assert action == "continue"
    mock_send.assert_not_called()


def test_watchdog_no_resend_on_failed_status(task_dir: Path) -> None:
    """callback 状态为 failed 时不重发。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
    )
    lc._atomic_write_json(
        run_dir / "callback.json",
        {"status": "failed", "exit_code": 1},
    )
    mock_send = MagicMock()

    action = lc.watchdog_check(run_dir, Path("."), mock_send)
    assert action == "continue"
    mock_send.assert_not_called()


# --- Watchdog claim race tests ---


def test_watchdog_claim_race_with_worker(task_dir: Path) -> None:
    """worker 和 watchdog 竞争 claim，只有一个能发送。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
    )
    # 模拟 worker 已获取 claim
    (run_dir / "callback.claim").touch()
    mock_send = MagicMock()

    action = lc.watchdog_check(run_dir, Path("."), mock_send)

    assert action == "continue"
    mock_send.assert_not_called()


# --- Worker death tests ---


def test_watchdog_records_unknown_when_worker_dead(task_dir: Path) -> None:
    """worker 死亡且无 completion 时记录 unknown。"""
    run_dir = _make_run(task_dir, task=_valid_task())
    # 写入 PID 文件但进程不存在
    lc._atomic_write_json(run_dir / "worker.pid", {"pid": 99999})
    (run_dir / "worker.pid").write_text("99999")
    mock_send = MagicMock()

    with patch.object(lc, "_is_pid_alive", return_value=False):
        action = lc.watchdog_check(run_dir, Path("."), mock_send)

    assert action == "recorded_unknown"
    lifecycle = lc.read_lifecycle(run_dir)
    assert lifecycle["status"] == "unknown"
    assert "anomaly" in lifecycle


def test_watchdog_anomaly_notification_uses_claim(task_dir: Path) -> None:
    """异常通知使用相同 claim 闸门。"""
    run_dir = _make_run(task_dir, task=_valid_task())
    (run_dir / "worker.pid").write_text("99999")
    mock_send = MagicMock()

    with patch.object(lc, "_is_pid_alive", return_value=False):
        lc.watchdog_check(run_dir, Path("."), mock_send)

    # 应该尝试发送异常通知
    mock_send.assert_called_once()
    # 检查发送的 completion 包含 unknown 状态
    call_args = mock_send.call_args
    completion = call_args[0][2]  # third positional arg
    assert completion["status"] == "unknown"
    assert "worker died" in completion.get("error", "")


def test_watchdog_no_anomaly_resend_when_claim_exists(task_dir: Path) -> None:
    """已有 claim 时不发送异常通知。"""
    run_dir = _make_run(task_dir, task=_valid_task())
    (run_dir / "worker.pid").write_text("99999")
    (run_dir / "callback.claim").touch()
    mock_send = MagicMock()

    with patch.object(lc, "_is_pid_alive", return_value=False):
        action = lc.watchdog_check(run_dir, Path("."), mock_send)

    assert action == "recorded_unknown"  # 仍记录 anomaly
    mock_send.assert_not_called()  # 但不发送


def test_watchdog_no_action_when_worker_alive(task_dir: Path) -> None:
    """worker 仍存活时不采取行动。"""
    run_dir = _make_run(task_dir, task=_valid_task())
    (run_dir / "worker.pid").write_text(str(os.getpid()))
    mock_send = MagicMock()

    action = lc.watchdog_check(run_dir, Path("."), mock_send)

    assert action == "continue"
    mock_send.assert_not_called()


# --- Watchdog unique claim tests ---


def test_watchdog_unique_claim_prevents_duplicate(task_dir: Path) -> None:
    """watchdog.claim 保证每个 run 只有一个 watchdog。"""
    run_dir = _make_run(task_dir, task=_valid_task())
    # 预先创建 watchdog claim
    lc._atomic_write_json(run_dir / "watchdog.claim", {"pid": 12345})

    # watchdog_entry 应该立即返回
    result = lc.watchdog_entry(str(task_dir), run_dir.name, str(task_dir.parent))
    assert result == 0  # 成功退出，不启动第二个 watchdog


# --- Watchdog non-codex tests ---


def test_watchdog_skips_non_codex_task(task_dir: Path) -> None:
    """非 codex 任务不触发 watchdog 检查。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(parent_client="local", parent_session_id=""),
    )
    mock_send = MagicMock()

    action = lc.watchdog_check(run_dir, Path("."), mock_send)

    assert action == "continue"
    mock_send.assert_not_called()


# --- Ack tests ---


def test_ack_correct_identity(task_dir: Path) -> None:
    """正确身份的首次 ack 成功。"""
    parent_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    session_id = str(uuid.uuid4())
    task = _valid_task(parent_session_id=parent_sid, session_id=session_id)
    run_dir = _make_run(
        task_dir,
        task=task,
        completion={
            "status": "finished",
            "exit_code": 0,
            "session_id": session_id,
            "task_id": "test_001",
            "agent_id": "agent_test001",
            "client": "qoder",
            "parent_client": "codex",
            "parent_session_id": parent_sid,
        },
    )

    ack_data = lc.ack_run(
        task_dir,
        run_dir.name,
        parent_sid,
        codex_thread_id=parent_sid,
    )

    assert ack_data["run_id"] == run_dir.name
    assert ack_data["parent_session_id"] == parent_sid
    assert ack_data["completion_status"] == "finished"

    # 验证 lifecycle 更新
    lifecycle = lc.read_lifecycle(run_dir)
    assert lifecycle["status"] == "acknowledged"


def test_ack_idempotent(task_dir: Path) -> None:
    """重复 ack 返回相同结果。"""
    parent_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    session_id = str(uuid.uuid4())
    task = _valid_task(parent_session_id=parent_sid, session_id=session_id)
    run_dir = _make_run(
        task_dir,
        task=task,
        completion={
            "status": "finished",
            "exit_code": 0,
            "session_id": session_id,
            "task_id": "test_001",
            "agent_id": "agent_test001",
            "client": "qoder",
            "parent_client": "codex",
            "parent_session_id": parent_sid,
        },
    )

    ack1 = lc.ack_run(task_dir, run_dir.name, parent_sid, codex_thread_id=parent_sid)
    ack2 = lc.ack_run(task_dir, run_dir.name, parent_sid, codex_thread_id=parent_sid)

    assert ack1["run_id"] == ack2["run_id"]
    assert ack1["acknowledged_at"] == ack2["acknowledged_at"]


def test_ack_wrong_parent_rejected(task_dir: Path) -> None:
    """错误的 parent_session_id 被拒绝。"""
    parent_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    wrong_sid = "11111111-2222-3333-4444-555555555555"
    run_dir = _make_run(
        task_dir,
        task=_valid_task(parent_session_id=parent_sid),
        completion={"status": "finished", "exit_code": 0},
    )

    with pytest.raises(ValueError, match="does not match"):
        lc.ack_run(task_dir, run_dir.name, wrong_sid, codex_thread_id=wrong_sid)


def test_ack_running_task_rejected(task_dir: Path) -> None:
    """运行中的任务不能 ack。"""
    parent_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    run_dir = _make_run(
        task_dir,
        task=_valid_task(parent_session_id=parent_sid),
    )
    # 无 completion，无 anomaly

    with pytest.raises(ValueError, match="not in terminal state"):
        lc.ack_run(task_dir, run_dir.name, parent_sid, codex_thread_id=parent_sid)


def test_ack_missing_codex_thread_id_rejected(task_dir: Path) -> None:
    """缺少 CODEX_THREAD_ID 时 ack 被拒绝。"""
    parent_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    run_dir = _make_run(
        task_dir,
        task=_valid_task(parent_session_id=parent_sid),
        completion={"status": "finished", "exit_code": 0},
    )

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="CODEX_THREAD_ID"):
            lc.ack_run(task_dir, run_dir.name, parent_sid, codex_thread_id=None)


def test_ack_codex_thread_mismatch_rejected(task_dir: Path) -> None:
    """CODEX_THREAD_ID 与 parent_session_id 不匹配时被拒绝。"""
    parent_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    wrong_thread = "11111111-2222-3333-4444-555555555555"
    run_dir = _make_run(
        task_dir,
        task=_valid_task(parent_session_id=parent_sid),
        completion={"status": "finished", "exit_code": 0},
    )

    with pytest.raises(ValueError, match="does not match"):
        lc.ack_run(task_dir, run_dir.name, parent_sid, codex_thread_id=wrong_thread)


def test_ack_anomaly_terminal_accepted(task_dir: Path) -> None:
    """worker 异常的 unknown 状态可以被 ack（需要 worker.pid 且进程已死）。"""
    parent_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    run_dir = _make_run(
        task_dir,
        task=_valid_task(parent_session_id=parent_sid),
        lifecycle={"status": "unknown", "anomaly": "worker died"},
    )
    # 写入 worker.pid（使用一个不存在的 PID 模拟进程已死）
    (run_dir / "worker.pid").write_text("999999999", encoding="utf-8")

    ack_data = lc.ack_run(
        task_dir,
        run_dir.name,
        parent_sid,
        codex_thread_id=parent_sid,
    )

    assert ack_data["completion_status"] == "unknown"


def test_ack_different_parent_rejected(task_dir: Path) -> None:
    """不同 parent 的重复 ack 被拒绝。"""
    parent_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    different_sid = "11111111-2222-3333-4444-555555555555"
    task = _valid_task(parent_session_id=parent_sid)
    run_dir = _make_run(
        task_dir,
        task=task,
        completion={
            "status": "finished",
            "exit_code": 0,
            "session_id": task["session_id"],
            "task_id": "test_001",
            "agent_id": "agent_test001",
            "client": "qoder",
            "parent_client": "codex",
            "parent_session_id": parent_sid,
        },
    )

    # 首次 ack 成功
    lc.ack_run(task_dir, run_dir.name, parent_sid, codex_thread_id=parent_sid)

    # 不同 parent 的 ack 被拒绝（先检查与 saved task 匹配）
    with pytest.raises(ValueError, match="does not match saved task"):
        lc.ack_run(task_dir, run_dir.name, different_sid, codex_thread_id=different_sid)


# --- Supersession tests ---


def test_resume_records_supersession(task_dir: Path) -> None:
    """成功 resume 后记录替代关系。"""
    old_run = _make_run(task_dir, task=_valid_task())
    new_run = _make_run(task_dir, task=_valid_task())

    lc.record_previous_run(new_run, old_run.name)
    lc.record_supersession(old_run, new_run.name)

    # 验证旧 run 被标记 superseded
    old_lifecycle = lc.read_lifecycle(old_run)
    assert old_lifecycle["status"] == "superseded"
    assert old_lifecycle["next_run_id"] == new_run.name

    # 验证新 run 记录了 previous
    new_lifecycle = lc.read_lifecycle(new_run)
    assert new_lifecycle["previous_run_id"] == old_run.name


def test_supersession_records_next_run_id_even_when_acknowledged(task_dir: Path) -> None:
    """已 ack 的 run 仍记录 next_run_id（消费和替代是独立维度）。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        lifecycle={"status": "acknowledged"},
    )

    lc.record_supersession(run_dir, "new-run-id")

    lifecycle = lc.read_lifecycle(run_dir)
    # 状态更新为 superseded
    assert lifecycle["status"] == "superseded"
    # 但 next_run_id 被记录
    assert lifecycle["next_run_id"] == "new-run-id"


# --- Result lifecycle tests ---


def test_result_includes_lifecycle_info(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """result 输出包含生命周期信息。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
        lifecycle={"status": "acknowledged", "acknowledged_at": 1234567890},
    )
    (run_dir / "stdout.log").write_text("output")
    monkeypatch.chdir(task_dir)

    qoder_task.main(["result", run_dir.name])
    data = json.loads(capsys.readouterr().out)

    assert "lifecycle" in data
    assert data["lifecycle"]["status"] == "acknowledged"


def test_result_includes_ack_info(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """result 输出包含 ack 信息。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
    )
    (run_dir / "stdout.log").write_text("output")
    lc._atomic_write_json(
        lc.ack_path(run_dir),
        {"run_id": run_dir.name, "parent_session_id": "aaa", "acknowledged_at": 123},
    )
    monkeypatch.chdir(task_dir)

    qoder_task.main(["result", run_dir.name])
    data = json.loads(capsys.readouterr().out)

    assert "ack" in data
    assert data["ack"]["run_id"] == run_dir.name


def test_result_repeated_reads_no_side_effects(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """重复读取 result 不产生副作用。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
    )
    (run_dir / "stdout.log").write_text("output")
    monkeypatch.chdir(task_dir)

    # 多次读取
    for _ in range(3):
        qoder_task.main(["result", run_dir.name])
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "finished"

    # 验证没有生成额外文件
    assert not lc.ack_path(run_dir).exists()


# --- Status lifecycle tests ---


def test_status_shows_lifecycle_acknowledged(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """status 显示 acknowledged 状态。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        completion={"status": "finished", "exit_code": 0},
        lifecycle={"status": "acknowledged"},
    )
    monkeypatch.chdir(task_dir)

    qoder_task.main(["status", run_dir.name])
    data = json.loads(capsys.readouterr().out)

    assert data["status"] == "finished"
    assert data["lifecycle"] == "acknowledged"


def test_status_shows_superseded(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """status 显示 superseded 状态。"""
    run_dir = _make_run(
        task_dir,
        task=_valid_task(),
        lifecycle={"status": "superseded"},
    )
    monkeypatch.chdir(task_dir)

    qoder_task.main(["status", run_dir.name])
    data = json.loads(capsys.readouterr().out)

    assert data["status"] == "superseded"


# --- Fixtures ---


@pytest.fixture()
def task_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """创建任务目录并设置环境变量。"""
    tmp_path = tmp_path.resolve()
    (tmp_path / ".git").mkdir()
    td = tmp_path / "tasks"
    td.mkdir()
    monkeypatch.setenv("QODER_TASK_DIR", str(td))
    return td


def _terminal_run(task_dir: Path) -> Path:
    task = _valid_task()
    return _make_run(task_dir, task=task, completion={**task, "status": "finished", "exit_code": 0})


@pytest.mark.parametrize(
    "field", ["session_id", "task_id", "agent_id", "client", "parent_client", "parent_session_id"]
)
@pytest.mark.parametrize("mutation", ["missing", "mismatch"])
def test_ack_rejects_incomplete_or_foreign_completion(task_dir, field, mutation):
    run = _terminal_run(task_dir)
    completion = json.loads((run / "completion.json").read_text())
    if mutation == "missing":
        del completion[field]
    else:
        completion[field] = "foreign-identity"
    lc._atomic_write_json(run / "completion.json", completion)
    parent = _valid_task()["parent_session_id"]
    with pytest.raises(ValueError):
        lc.ack_run(task_dir, run.name, parent, codex_thread_id=parent)
    assert not (run / "ack.json").exists()


@pytest.mark.parametrize("field", ["run_id", "qoder_session_id", "task_id", "parent_session_id"])
def test_ack_rejects_corrupt_existing_identity(task_dir, field):
    run = _terminal_run(task_dir)
    parent = _valid_task()["parent_session_id"]
    ack = lc.ack_run(task_dir, run.name, parent, codex_thread_id=parent)
    ack[field] = "foreign-identity"
    lc._atomic_write_json(run / "ack.json", ack)
    before = (run / "ack.json").read_bytes()
    with pytest.raises(ValueError):
        lc.ack_run(task_dir, run.name, parent, codex_thread_id=parent)
    assert (run / "ack.json").read_bytes() == before


def test_ack_rejects_unknown_without_worker_pid(task_dir):
    run = _make_run(
        task_dir, task=_valid_task(), lifecycle={"status": "unknown", "anomaly": "dead"}
    )
    parent = _valid_task()["parent_session_id"]
    with pytest.raises(ValueError, match=r"worker\.pid"):
        lc.ack_run(task_dir, run.name, parent, codex_thread_id=parent)
    assert not (run / "ack.json").exists()


def test_ack_partial_write_remains_authoritative(task_dir, monkeypatch):
    run = _terminal_run(task_dir)
    parent = _valid_task()["parent_session_id"]
    before = (run / "completion.json").read_bytes()
    with monkeypatch.context() as failing:
        failing.setattr(
            lc, "write_lifecycle", MagicMock(side_effect=OSError("synthetic full disk"))
        )
        ack = lc.ack_run(task_dir, run.name, parent, codex_thread_id=parent)
    assert (run / "ack.json").exists()
    assert not (run / "lifecycle.json").exists()
    send = MagicMock()
    assert lc.watchdog_check(run, task_dir.parent, send) == "acknowledged"
    lc._record_anomaly(run, "must not replace consumed state")
    lc._record_exhausted(run)
    assert lc.read_lifecycle(run).get("status") not in ("unknown", "exhausted")
    send.assert_not_called()
    assert lc.ack_run(task_dir, run.name, parent, codex_thread_id=parent) == ack
    assert (run / "completion.json").read_bytes() == before


def test_ack_and_supersession_real_lock_competition(task_dir):
    run = _terminal_run(task_dir)
    parent = _valid_task()["parent_session_id"]
    next_id = str(uuid.uuid4())
    barrier = threading.Barrier(2)

    def consume():
        barrier.wait(timeout=5)
        return lc.ack_run(task_dir, run.name, parent, codex_thread_id=parent)

    def replace():
        barrier.wait(timeout=5)
        lc.record_supersession(run, next_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(consume), pool.submit(replace)
        ack = first.result(timeout=10)
        second.result(timeout=10)
    state = lc.read_lifecycle(run)
    assert state["status"] == "superseded"
    assert state["next_run_id"] == next_id
    assert state["acknowledged_at"]
    assert json.loads((run / "ack.json").read_text()) == ack


def test_watchdog_exits_at_exact_deadline(task_dir):
    run = _make_run(task_dir, task=_valid_task())
    (run / "worker.pid").write_text(str(os.getpid()))
    clock = FakeClock(1234)
    sleep = FakeSleep(clock)
    send = MagicMock()
    assert (
        lc.watchdog_loop(run, task_dir.parent, send_callback=send, sleep_fn=sleep, clock_fn=clock)
        == "exhausted"
    )
    assert clock() == 1234 + 86400
    assert sum(sleep.calls) == 86400
    assert sleep.calls[-1] == 300
    assert not (run / "completion.json").exists()
    send.assert_not_called()


@pytest.mark.parametrize("unsafe", ["outside", "symlink", "traversal"])
def test_standalone_watchdog_rejects_paths_without_writes(tmp_path, unsafe):
    root = tmp_path.resolve()
    repo = root / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    external = root / "external"
    external.mkdir()
    run = _make_run(external, task=_valid_task())
    directory, run_id = external, run.name
    if unsafe == "symlink":
        directory = repo / "link"
        directory.symlink_to(external, target_is_directory=True)
    elif unsafe == "traversal":
        directory = repo
        run_id = "../external/" + run.name
    before = {
        str(p.relative_to(external)): p.read_bytes() for p in external.rglob("*") if p.is_file()
    }
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, lc.__file__, "_watchdog", str(directory), run_id, str(repo)],
        env=env,
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert "error:" in result.stderr
    after = {
        str(p.relative_to(external)): p.read_bytes() for p in external.rglob("*") if p.is_file()
    }
    assert after == before


def test_worker_and_watchdog_real_callback_claim_competition(task_dir, monkeypatch):
    run = _terminal_run(task_dir)
    task = json.loads((run / "task.json").read_text())
    completion = json.loads((run / "completion.json").read_text())
    barrier = threading.Barrier(2)
    calls = []

    def queue(thread, message, **kwargs):
        calls.append((thread, message))
        return subprocess.CompletedProcess(
            [], 0, f"Queued message {uuid.uuid4()} for thread {thread}.\n", ""
        )

    monkeypatch.setattr(qoder_task, "_run_codex_queue_cli", queue)

    def worker():
        barrier.wait(timeout=5)
        qoder_task._attempt_codex_callback(run, run.name, completion, task, task_dir.parent)

    def watchdog():
        barrier.wait(timeout=5)
        lc.watchdog_check(run, task_dir.parent, qoder_task._attempt_codex_callback)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(worker), pool.submit(watchdog)
        first.result(timeout=10)
        second.result(timeout=10)
    assert len(calls) == 1
    assert json.loads((run / "callback.json").read_text())["status"] == "queued"
    assert (run / "callback.claim").exists()


def test_real_worker_two_rounds_and_failed_resume(task_dir, monkeypatch, capsys):
    """真实独立 worker/CLI/queue/watchdog 进程；仅记录外部 spawn 供 finally 回收。"""
    root = task_dir.parent
    parent = _valid_task()["parent_session_id"]
    executable = root / "synthetic-runner"
    release = root / "release"
    executable.write_text(
        f"#!{sys.executable}\nimport pathlib, time\n"
        f"release = pathlib.Path({str(release)!r})\n"
        "deadline = time.monotonic() + 10\n"
        "while not release.exists():\n"
        "    assert time.monotonic() < deadline, 'synthetic release timed out'\n"
        "    time.sleep(0.01)\n"
        "print('synthetic result')\n"
    )
    executable.chmod(0o700)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    queue_log = root / "queue.jsonl"
    codex = bin_dir / "codex"
    codex.write_text(
        f"#!{sys.executable}\nimport json, sys, uuid\n"
        f"assert sys.argv[1:4] == ['queue', '--thread', {parent!r}]\n"
        "assert sys.argv[4] == '--message'\n"
        f"with open({str(queue_log)!r}, 'a') as f:\n"
        "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "print(f'Queued message {uuid.uuid4()} for thread {sys.argv[3]}.')\n"
    )
    codex.chmod(0o700)
    monkeypatch.chdir(root)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", parent)
    monkeypatch.setenv("QODER_TASK_CLI", str(executable))
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    # 不读取宿主 Qoder 运行数据；仅外部 ps 预检隔离，worker/状态机均为真实代码。
    monkeypatch.setattr(qoder_task.subprocess, "check_output", lambda *_args, **_kwargs: "")
    original_spawn = subprocess.Popen
    background = []

    def tracked_spawn(args, *pos, **kwargs):
        process = original_spawn(args, *pos, **kwargs)
        if "_worker" in args or "_watchdog" in args:
            background.append((list(args), process))
        return process

    monkeypatch.setattr(subprocess, "Popen", tracked_spawn)
    task_file = root / "input.json"
    task_file.write_text(json.dumps(_valid_task()))
    followup = root / "followup.json"
    followup.write_text(json.dumps({"goal": "synthetic second round"}))

    def dispatch(args, *, expect_started=True):
        release.unlink(missing_ok=True)
        assert qoder_task.main(args) == 0
        run_id = capsys.readouterr().out.strip().splitlines()[-1]
        uuid.UUID(run_id)
        worker = next(p for command, p in background if "_worker" in command and run_id in command)
        run = task_dir / run_id
        if expect_started:
            deadline = time.monotonic() + 5
            while not (run / "started.json").exists():
                assert worker.poll() is None, "worker exited before confirming startup"
                assert time.monotonic() < deadline, "no startup confirmation"
                time.sleep(0.01)
            started = json.loads((run / "started.json").read_text())
            assert started["pid"] != worker.pid
            os.kill(started["pid"], 0)
            assert int((run / "worker.pid").read_text()) == worker.pid
            assert not (run / "completion.json").exists()
            if args[0] == "resume":
                previous = task_dir / args[1]
                while lc.read_lifecycle(previous).get("next_run_id") != run_id:
                    assert time.monotonic() < deadline, "startup did not establish replacement"
                    time.sleep(0.01)
                assert lc.read_lifecycle(previous)["status"] == "superseded"
                assert not (run / "completion.json").exists()
            release.touch()
        assert worker.wait(timeout=15) == 0
        return run

    def consume(run):
        assert qoder_task.main(["ack", run.name, "--parent-session-id", parent]) == 0
        ack = json.loads(capsys.readouterr().out)
        assert ack["run_id"] == run.name
        assert ack["parent_session_id"] == parent

    try:
        first = dispatch(["start", "--task", str(task_file)])
        consume(first)
        second = dispatch(["resume", first.name, "--followup", str(followup)])
        consume(second)
        third = dispatch(["resume", second.name, "--followup", str(followup)])
        consume(third)
        sessions = []
        for run in (first, second, third):
            completion = json.loads((run / "completion.json").read_text())
            started = json.loads((run / "started.json").read_text())
            callback = json.loads((run / "callback.json").read_text())
            assert completion["status"] == "finished"
            assert completion["exit_code"] == 0
            assert completion["run_id"] == run.name
            assert started["pid"] > 0
            assert started["session_id"] == completion["session_id"]
            assert started["run_id"] == run.name
            assert callback["status"] == "queued"
            assert callback["parent_session_id"] == parent
            sessions.append(completion["session_id"])
        assert len(set(sessions)) == 1
        assert lc.read_lifecycle(first)["next_run_id"] == second.name
        assert lc.read_lifecycle(second)["previous_run_id"] == first.name
        assert lc.read_lifecycle(second)["next_run_id"] == third.name
        assert lc.read_lifecycle(third)["previous_run_id"] == second.name
        assert (first / "ack.json").exists()
        records = [json.loads(line) for line in queue_log.read_text().splitlines()]
        assert len(records) == 3
        assert first.name in records[0][-1]
        assert second.name in records[1][-1]
        assert third.name in records[2][-1]

        # 文件可执行但解释器不存在：预检通过，真实 CLI Popen 必须失败。
        executable.write_text("#!/nonexistent/synthetic-interpreter\n")
        before = (third / "completion.json").read_bytes()
        failed = dispatch(["resume", third.name, "--followup", str(followup)], expect_started=False)
        assert json.loads((failed / "completion.json").read_text())["status"] == "failed"
        assert not (failed / "started.json").exists()
        assert "next_run_id" not in lc.read_lifecycle(third)
        assert not (third / "resume.reservation").exists()
        assert (third / "completion.json").read_bytes() == before
        assert (third / "ack.json").exists()
    finally:
        release.touch()
        for _, process in background:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)


def test_started_metadata_failure_preserves_real_cli_result(task_dir, monkeypatch):
    executable = task_dir.parent / "synthetic-metadata-runner"
    finished = task_dir.parent / "cli-finished"
    executable.write_text(f"#!/bin/sh\nprintf done > '{finished}'\nexit 0\n")
    executable.chmod(0o700)
    monkeypatch.setenv("QODER_TASK_CLI", str(executable))
    run = _make_run(task_dir, task=_valid_task(parent_client="local", parent_session_id=""))
    monkeypatch.setattr(lc, "record_started", MagicMock(side_effect=OSError("synthetic disk full")))
    qoder_task._worker_entry(task_dir, run.name, task_dir.parent)
    completion = json.loads((run / "completion.json").read_text())
    assert finished.read_text() == "done"
    assert completion["exit_code"] == 0
    assert completion["status"] == "finished"
    assert any("synthetic disk full" in error for error in completion["lifecycle_errors"])
    assert not (run / "started.json").exists()


@pytest.mark.parametrize("filename", ["lifecycle.lock", "watchdog.log"])
def test_lifecycle_private_files_reject_symlink(task_dir, monkeypatch, filename):
    run = _make_run(task_dir, task=_valid_task())
    target = task_dir.parent / "untouched"
    target.write_text("original")
    (run / filename).symlink_to(target)
    spawn = MagicMock()
    monkeypatch.setattr(lc.subprocess, "Popen", spawn)
    with pytest.raises((ValueError, OSError)):
        if filename == "lifecycle.lock":
            lc.record_supersession(run, str(uuid.uuid4()))
        else:
            lc.start_watchdog(run, task_dir.parent)
    assert target.read_text() == "original"
    assert not (run / "lifecycle.json").exists()
    spawn.assert_not_called()


@pytest.mark.parametrize("spawn_fails", [False, True])
def test_watchdog_parent_closes_log_descriptor(task_dir, monkeypatch, spawn_fails):
    run = _make_run(task_dir, task=_valid_task())
    descriptors = []

    def spawn(*args, **kwargs):
        descriptors.append(kwargs["stderr"])
        os.fstat(kwargs["stderr"])
        if spawn_fails:
            raise OSError("synthetic spawn failure")
        return MagicMock()

    monkeypatch.setattr(lc.subprocess, "Popen", spawn)
    if spawn_fails:
        with pytest.raises(OSError, match="synthetic spawn failure"):
            lc.start_watchdog(run, task_dir.parent)
    else:
        lc.start_watchdog(run, task_dir.parent)
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
