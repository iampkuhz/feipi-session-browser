from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from scripts.claude_hooks import paths as runtime_paths
from scripts.harness.port_allocator import reserve_port
from scripts.harness.primary_session import resolve_runtime_root, validate_run_write_authorization
from scripts.harness.resource_lock import NamedResourceLock, ResourceLockSet, ResourceLockTimeout, owner_metadata
from scripts.harness import stop_entry
from scripts.hooks.guard_openspec_change import guard_path

ROOT = Path(__file__).resolve().parents[1]
SESSIONCTL = ROOT / "scripts" / "harness" / "sessionctl.py"

# Acceptance contract bindings for phase-10 A-I:
# HOOK-HARNESS-016 HOOK-HARNESS-017 HOOK-HARNESS-018 HOOK-HARNESS-019 HOOK-HARNESS-020
# HOOK-HARNESS-021 HOOK-HARNESS-022 HOOK-HARNESS-023 HOOK-HARNESS-024


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd or ROOT, env=env, input=input_text, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {cmd}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


def git(repo: Path, *args: str) -> str:
    return run(["git", "-C", str(repo), *args]).stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "main_java"], cwd=repo)
    run(["git", "config", "user.email", "multi-primary@example.invalid"], cwd=repo)
    run(["git", "config", "user.name", "Multi Primary Test"], cwd=repo)
    for rel, text in {
        "README.md": "# synthetic\n",
        ".gitignore": "tmp/\n",
        "docs/.keep": "keep\n",
        "openspec/changes/change-a/proposal.md": "# proposal\n",
        "openspec/changes/change-a/design.md": "# design\n",
        "openspec/changes/change-a/tasks.md": "# tasks\n",
        "openspec/changes/change-a/specs/agent-runtime/spec.md": "# spec\n",
        "harness/agent-runtime.manifest.yaml": "protected_roots:\n  - openspec/\n  - harness/\n  - scripts/\n",
    }.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    run(["git", "add", "."], cwd=repo)
    run(["git", "commit", "-m", "initial"], cwd=repo)
    return repo


def ctl(repo: Path, *args: str, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, str(SESSIONCTL), "--repo-root", str(repo), *args], env=env, check=check)


def create_run(repo: Path, tmp_path: Path, *, client: str, task: str, change: str = "change-a", allowed: str = "docs", session: str | None = None) -> dict[str, object]:
    args = [
        "create",
        "--client",
        client,
        "--task-id",
        task,
        "--change-id",
        change,
        "--base-ref",
        "main_java",
        "--allowed-path",
        allowed,
    ]
    if session:
        args.extend(["--worktree-root", str(tmp_path / "assigned-worktrees" / client / session)])
    else:
        args.extend(["--worktree-parent", str(tmp_path / "worktrees")])
    result = ctl(repo, *args)
    return json.loads(result.stdout)


def bind(repo: Path, record: dict[str, object], session: str) -> dict[str, object]:
    result = ctl(
        repo,
        "bind-session",
        "--run-id",
        str(record["runId"]),
        "--session-id",
        session,
        "--client",
        str(record["client"]),
        "--cwd",
        str(record["worktreeRoot"]),
    )
    return json.loads(result.stdout)


def hook_payload(record: dict[str, object], session: str, *, tool: str, tool_input: dict[str, object], tool_use_id: str, cwd: str | None = None, turn: str = "turn-1") -> str:
    return json.dumps(
        {
            "cwd": cwd or str(record["worktreeRoot"]),
            "client": record["client"],
            "session_id": session,
            "run_id": record["runId"],
            "task_id": record["taskId"],
            "worktree_id": record["worktreeId"],
            "turn_id": turn,
            "tool_name": tool,
            "tool_use_id": tool_use_id,
            "tool_input": tool_input,
        }
    )


def hook(event: str, payload: str) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, "-m", "scripts.claude_hooks.main", event], input_text=payload, check=False)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def log_paths(worktree: Path, record: dict[str, object], session: str) -> runtime_paths.RepoPaths:
    identity = runtime_paths.identity_from_values(
        agent_client=str(record["client"]),
        session_id=session,
        run_id=str(record["runId"]),
        task_id=str(record["taskId"]),
        worktree_id=str(record["worktreeId"]),
        change_id=str(record["changeId"]),
        branch=str(record["branch"]),
        base_commit=str(record["baseCommit"]),
        worktree_root=str(record["worktreeRoot"]),
    )
    return runtime_paths.build_paths(worktree, identity)


def simulate_write_and_bash(record: dict[str, object], session: str, rel: str, bash_rel: str, barrier: threading.Barrier) -> None:
    worktree = Path(str(record["worktreeRoot"]))
    payload = hook_payload(record, session, tool="Write", tool_input={"file_path": rel}, tool_use_id=f"write-{session}")
    assert hook("pre-write", payload).returncode == 0
    target = worktree / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{session}\n", encoding="utf-8")
    assert hook("post-write", payload).returncode == 0

    bash_payload = hook_payload(record, session, tool="Bash", tool_input={"command": f"python3 -c 'from pathlib import Path; Path(\"{bash_rel}\").write_text(\"{session}\\n\")'"}, tool_use_id=f"bash-{session}")
    assert hook("pre-bash", bash_payload).returncode == 0
    barrier.wait(timeout=10)
    bash_target = worktree / bash_rel
    bash_target.parent.mkdir(parents=True, exist_ok=True)
    bash_target.write_text(f"bash {session}\n", encoding="utf-8")
    assert hook("post-bash", bash_payload).returncode == 0


def test_a_two_primary_runs_parallel_in_distinct_git_worktrees_isolate_evidence_and_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("FEIPI_AGENT_WORKTREE_ROOT", str(tmp_path / "assigned-worktrees"))
    qoder = create_run(repo, tmp_path, client="qoder", task="task-a", change="change-a", allowed="docs/qoder", session="qoder-session")
    codex = create_run(repo, tmp_path, client="codex", task="task-b", change="change-a", allowed="docs/codex", session="codex-session")
    bind(repo, qoder, "qoder-session")
    bind(repo, codex, "codex-session")
    assert git(Path(str(qoder["worktreeRoot"])), "rev-parse", "--is-inside-work-tree") == "true"
    assert git(Path(str(codex["worktreeRoot"])), "rev-parse", "--is-inside-work-tree") == "true"

    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(target=simulate_write_and_bash, args=(qoder, "qoder-session", "docs/qoder/a.txt", "docs/qoder/bash.txt", barrier)),
        threading.Thread(target=simulate_write_and_bash, args=(codex, "codex-session", "docs/codex/b.txt", "docs/codex/bash.txt", barrier)),
    ]
    for item in threads:
        item.start()
    for item in threads:
        item.join(timeout=20)
        assert not item.is_alive()

    q_paths = log_paths(Path(str(qoder["worktreeRoot"])), qoder, "qoder-session")
    c_paths = log_paths(Path(str(codex["worktreeRoot"])), codex, "codex-session")
    q_changed = {item["file"] for item in read_jsonl(q_paths.changed_files)}
    c_changed = {item["file"] for item in read_jsonl(c_paths.changed_files)}
    assert q_changed == {"docs/qoder/a.txt", "docs/qoder/bash.txt"}
    assert c_changed == {"docs/codex/b.txt", "docs/codex/bash.txt"}
    assert q_paths.hook_events != c_paths.hook_events
    assert q_paths.quality_dir != c_paths.quality_dir
    assert q_paths.stop_summary != c_paths.stop_summary
    assert json.loads(ctl(repo, "status", "--run-id", str(qoder["runId"])).stdout)["status"] == "running"
    assert json.loads((q_paths.active_change).read_text(encoding="utf-8"))["changeId"] == "change-a"
    assert json.loads((c_paths.active_change).read_text(encoding="utf-8"))["changeId"] == "change-a"


def test_b_same_worktree_second_writer_blocks_before_file_change_but_read_only_bind_is_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    first = create_run(repo, tmp_path, client="codex", task="task-a", allowed="docs/a")
    before = git(Path(str(first["worktreeRoot"])), "status", "--porcelain")
    blocked = ctl(
        repo,
        "create",
        "--client",
        "qoder",
        "--task-id",
        "task-b",
        "--change-id",
        "change-a",
        "--base-ref",
        "main_java",
        "--allowed-path",
        "docs/b",
        "--worktree-root",
        str(first["worktreeRoot"]),
        check=False,
    )
    assert blocked.returncode == 2
    assert git(Path(str(first["worktreeRoot"])), "status", "--porcelain") == before

    read_only = ctl(
        repo,
        "create",
        "--client",
        "qoder",
        "--task-id",
        "reader",
        "--change-id",
        "change-a",
        "--base-ref",
        "main_java",
        "--mode",
        "read-only",
        "--worktree-parent",
        str(tmp_path / "readers"),
    )
    assert json.loads(read_only.stdout)["mode"] == "read-only"


def test_c_openspec_isolation_requires_current_run_change_not_existing_other_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    run_b = create_run(repo, tmp_path, client="codex", task="task-b", change="change-b", allowed="openspec")
    bind(repo, run_b, "session-b")
    code, message = guard_path(
        "openspec/changes/change-b/tasks.md",
        root=Path(str(run_b["worktreeRoot"]),),
        run_id=str(run_b["runId"]),
        session_id="session-b",
        client="codex",
        change_id="change-a",
    )
    assert code == 2
    assert "current change id does not match run record" in message
    assert "authorization" in message


def test_d_bash_write_race_is_worktree_scoped_and_same_worktree_pre_phase_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("FEIPI_AGENT_WORKTREE_ROOT", str(tmp_path / "assigned-worktrees"))
    a = create_run(repo, tmp_path, client="codex", task="task-a", allowed="docs/a", session="session-a")
    b = create_run(repo, tmp_path, client="qoder", task="task-b", allowed="docs/b", session="session-b")
    bind(repo, a, "session-a")
    bind(repo, b, "session-b")
    payload_a = hook_payload(a, "session-a", tool="Bash", tool_input={"command": "python3 -c 'open(\"docs/a/race.txt\",\"w\").write(\"a\")'"}, tool_use_id="bash-race")
    payload_b = hook_payload(b, "session-b", tool="Write", tool_input={"file_path": "docs/b/race.txt"}, tool_use_id="write-race")
    assert hook("pre-bash", payload_a).returncode == 0
    target_b = Path(str(b["worktreeRoot"])) / "docs/b/race.txt"
    target_b.parent.mkdir(parents=True, exist_ok=True)
    assert hook("pre-write", payload_b).returncode == 0
    target_b.write_text("b\n", encoding="utf-8")
    assert hook("post-write", payload_b).returncode == 0
    target_a = Path(str(a["worktreeRoot"])) / "docs/a/race.txt"
    target_a.parent.mkdir(parents=True, exist_ok=True)
    target_a.write_text("a\n", encoding="utf-8")
    assert hook("post-bash", payload_a).returncode == 0
    a_files = {item["file"] for item in read_jsonl(log_paths(Path(str(a["worktreeRoot"])), a, "session-a").changed_files)}
    assert a_files == {"docs/a/race.txt"}

    wrong_cwd = hook_payload(a, "session-a", tool="Write", tool_input={"file_path": "docs/a/illegal.txt"}, tool_use_id="same-wt", cwd=str(b["worktreeRoot"]))
    blocked = hook("pre-write", wrong_cwd)
    assert blocked.returncode == 2
    assert "worktree" in (blocked.stdout + blocked.stderr).lower()


def test_e_stop_resource_locks_queue_timeout_and_reclaim_after_process_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    owner_a = owner_metadata(run_id="run-a", client="codex", session_id="s-a", worktree_id="wt-a", target="java-build")
    order: list[str] = []
    first_entered = threading.Event()

    def hold_gradle() -> None:
        with ResourceLockSet(repo, ["gradle-daemon"], owner_a, timeout_seconds=1):
            order.append("first")
            first_entered.set()
            time.sleep(0.2)

    thread = threading.Thread(target=hold_gradle)
    thread.start()
    assert first_entered.wait(timeout=5)
    owner_b = owner_metadata(run_id="run-b", client="qoder", session_id="s-b", worktree_id="wt-b", target="java-build")
    with ResourceLockSet(repo, ["fixture-server"], owner_b, timeout_seconds=1):
        assert (resolve_runtime_root(repo) / "locks" / "fixture-server.lock").exists()
    with pytest.raises(ResourceLockTimeout):
        ResourceLockSet(repo, ["gradle-daemon"], owner_b, timeout_seconds=0.01).acquire()
    with ResourceLockSet(repo, ["gradle-daemon"], owner_b, timeout_seconds=2):
        order.append("second")
    thread.join(timeout=5)
    assert order == ["first", "second"]

    script = "from scripts.harness.resource_lock import NamedResourceLock, owner_metadata; from pathlib import Path; l=NamedResourceLock(Path(sys.argv[1]), 'gradle-daemon', owner_metadata(run_id='dead', client='codex', session_id='dead', worktree_id='dead', target='java')); l.try_acquire()"
    run([sys.executable, "-c", "import sys; " + script, str(repo)], cwd=ROOT)
    reclaimed = NamedResourceLock(repo, "gradle-daemon", owner_metadata(run_id="live", client="qoder", session_id="live", worktree_id="live", target="java"))
    assert reclaimed.try_acquire()
    reclaimed.release()


def test_f_ports_base_url_and_output_directories_are_run_scoped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("FEIPI_AGENT_WORKTREE_ROOT", str(tmp_path / "assigned-worktrees"))
    a = create_run(repo, tmp_path, client="codex", task="task-a", allowed="docs/a", session="session-a")
    b = create_run(repo, tmp_path, client="qoder", task="task-b", allowed="docs/b", session="session-b")
    bind(repo, a, "session-a")
    bind(repo, b, "session-b")
    monkeypatch.setenv("FEIPI_RUN_ID", str(a["runId"]))
    port_a = reserve_port(Path(str(a["worktreeRoot"])), "fixture", hold_socket=True)
    monkeypatch.setenv("FEIPI_RUN_ID", str(b["runId"]))
    port_b = reserve_port(Path(str(b["worktreeRoot"])), "fixture", hold_socket=True)
    try:
        assert port_a.port != port_b.port
        assert f":{port_a.port}" != f":{port_b.port}"
        paths_a = log_paths(Path(str(a["worktreeRoot"])), a, "session-a")
        paths_b = log_paths(Path(str(b["worktreeRoot"])), b, "session-b")
        assert paths_a.quality_dir != paths_b.quality_dir
        assert (paths_a.quality_dir / "test-results") != (paths_b.quality_dir / "test-results")
        assert str(paths_a.quality_dir).startswith(str(Path(str(a["worktreeRoot"]))))
        assert str(paths_b.quality_dir).startswith(str(Path(str(b["worktreeRoot"]))))
    finally:
        port_a.close()
        port_b.close()


def test_g_resume_epoch_rebind_and_old_evidence_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    old_run = create_run(repo, tmp_path, client="codex", task="task-a", allowed="docs/a")
    bind(repo, old_run, "same-session")
    rebound = bind(repo, old_run, "same-session")
    assert rebound["status"] == "running"
    wrong_ok, errors, _ = validate_run_write_authorization(Path(str(old_run["worktreeRoot"])).parent, client="codex", session_id="same-session", run_id=str(old_run["runId"]), candidate_paths=["docs/a/x.txt"])
    assert wrong_ok is False
    assert any("worktree" in item for item in errors)

    old_paths = log_paths(Path(str(old_run["worktreeRoot"])), old_run, "same-session")
    old_paths.changed_files.parent.mkdir(parents=True, exist_ok=True)
    old_paths.changed_files.write_text(json.dumps({"file": "docs/a/old.txt", "eventId": "old"}) + "\n", encoding="utf-8")
    new_run = create_run(repo, tmp_path, client="codex", task="task-new", allowed="docs/new")
    bind(repo, new_run, "same-session")
    new_paths = log_paths(Path(str(new_run["worktreeRoot"])), new_run, "same-session")
    assert new_paths.changed_files != old_paths.changed_files
    assert read_jsonl(new_paths.changed_files) == []


def test_h_hook_activation_marker_parity_subdir_command_and_duplicate_event_dedupe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("FEIPI_AGENT_WORKTREE_ROOT", str(tmp_path / "assigned-worktrees"))
    codex = create_run(repo, tmp_path, client="codex", task="task-a", allowed="docs/a", session="session-a")
    bind(repo, codex, "session-a")
    marker = resolve_runtime_root(repo) / "runs" / str(codex["runId"]) / "hook-activation.json"
    marker.unlink()
    doctor = ctl(repo, "doctor", "--run-id", str(codex["runId"]), check=False)
    assert doctor.returncode == 2
    assert "marker missing" in doctor.stdout

    qoder = create_run(repo, tmp_path, client="qoder", task="task-b", allowed="docs/b")
    qoder_record_path = resolve_runtime_root(repo) / "runs" / f"{qoder['runId']}.json"
    qoder_record = json.loads(qoder_record_path.read_text(encoding="utf-8"))
    qoder_record["status"] = "running"
    qoder_record_path.write_text(json.dumps(qoder_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    qoder_doctor = ctl(repo, "doctor", "--run-id", str(qoder["runId"]), check=False)
    assert qoder_doctor.returncode == 2
    assert "sessionId" in (qoder_doctor.stdout + qoder_doctor.stderr)

    bind(repo, codex, "session-a")
    subdir = Path(str(codex["worktreeRoot"])) / "docs" / "a"
    subdir.mkdir(parents=True, exist_ok=True)
    payload = hook_payload(codex, "session-a", tool="Bash", tool_input={"command": f"cd {subdir} && python3 -c 'open(\"subdir.txt\",\"w\").write(\"ok\")'"}, tool_use_id="dup", cwd=str(subdir))
    assert hook("pre-bash", payload).returncode == 0
    (subdir / "subdir.txt").write_text("ok", encoding="utf-8")
    assert hook("post-bash", payload).returncode == 0
    assert hook("post-bash", payload).returncode == 0
    events = [item for item in read_jsonl(log_paths(Path(str(codex["worktreeRoot"])), codex, "session-a").hook_events) if item.get("toolUseId") == "dup" and item.get("event") == "post-bash"]
    assert len(events) == 1


def test_i_cleanup_refuses_dirty_and_active_pid_then_cleans_completed_without_branch_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    dirty = create_run(repo, tmp_path, client="codex", task="dirty", allowed="docs/a")
    (Path(str(dirty["worktreeRoot"])) / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    assert ctl(repo, "cleanup", "--run-id", str(dirty["runId"]), "--execute", check=False).returncode == 2

    active = create_run(repo, tmp_path, client="qoder", task="active", allowed="docs/b")
    runtime = resolve_runtime_root(repo)
    record_path = runtime / "runs" / f"{active['runId']}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        record["processes"] = [{"pid": sleeper.pid, "kind": "fake-client"}]
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        blocked = ctl(repo, "cleanup", "--run-id", str(active["runId"]), "--execute", check=False)
        assert blocked.returncode == 2
        assert "active process" in blocked.stderr
    finally:
        sleeper.terminate()
        sleeper.wait(timeout=5)

    clean = create_run(repo, tmp_path, client="codex", task="clean", allowed="docs/c")
    dry = json.loads(ctl(repo, "cleanup", "--run-id", str(clean["runId"])).stdout)
    assert dry["status"] == "dry-run"
    branch = str(clean["branch"])
    bind(repo, clean, "clean-session")
    done = json.loads(ctl(repo, "stop", "--run-id", str(clean["runId"])).stdout)
    assert done["status"] == "completed"
    cleaned = json.loads(ctl(repo, "cleanup", "--run-id", str(clean["runId"]), "--execute").stdout)
    assert cleaned["status"] == "cleaned"
    assert git(repo, "show-ref", "--verify", f"refs/heads/{branch}")


def test_stop_summary_paths_are_run_scoped_without_running_real_quality_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    qoder = create_run(repo, tmp_path, client="qoder", task="stop-a", allowed="docs/qoder")
    codex = create_run(repo, tmp_path, client="codex", task="stop-b", allowed="docs/codex")
    bind(repo, qoder, "qoder-stop")
    bind(repo, codex, "codex-stop")
    monkeypatch.setattr(stop_entry, "run_cmd", lambda *args, **kwargs: True)
    monkeypatch.setattr(stop_entry.check_agent_runtime_report, "validate_runtime_report", lambda **kwargs: [])
    for record, session in ((qoder, "qoder-stop"), (codex, "codex-stop")):
        payload = {"cwd": str(record["worktreeRoot"]), "client": record["client"], "session_id": session, "run_id": record["runId"], "task_id": record["taskId"], "worktree_id": record["worktreeId"]}
        assert stop_entry.run_stop(str(record["client"]), payload) == 0
    q_summary = log_paths(Path(str(qoder["worktreeRoot"])), qoder, "qoder-stop").stop_summary
    c_summary = log_paths(Path(str(codex["worktreeRoot"])), codex, "codex-stop").stop_summary
    assert q_summary != c_summary
    assert json.loads(q_summary.read_text(encoding="utf-8"))["runId"] == qoder["runId"]
    assert json.loads(c_summary.read_text(encoding="utf-8"))["runId"] == codex["runId"]
