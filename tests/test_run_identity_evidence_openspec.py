from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from scripts.claude_hooks.evidence import record_hook_event
from scripts.claude_hooks.hook_io import HookContext
from scripts.claude_hooks.paths import build_paths, identity_from_hook_context, identity_from_values, quality_dir
from scripts.harness.primary_session import resolve_runtime_root, validate_run_write_authorization
from scripts.hooks.guard_openspec_change import guard_path


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def init_repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.PIPE)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    return repo


def write_change(repo: Path, change_id: str) -> None:
    change = repo / "openspec" / "changes" / change_id
    spec = change / "specs" / "agent-runtime"
    spec.mkdir(parents=True, exist_ok=True)
    for name in ("proposal.md", "design.md", "tasks.md"):
        (change / name).write_text(f"# {name}\n", encoding="utf-8")
    (spec / "spec.md").write_text("# spec\n", encoding="utf-8")
    manifest = repo / "harness" / "agent-runtime.manifest.yaml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("protected_roots:\n  - scripts/\n  - openspec/\n", encoding="utf-8")


def run_record(repo: Path, run_id: str, *, client="codex", session="session-a", change="change-a", branch="main", status="running", worktree: Path | None = None) -> dict:
    root = worktree or repo
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "client": client,
        "taskId": "task-1",
        "sessionId": session,
        "worktreeId": f"wt-{run_id}",
        "worktreeRoot": str(root.resolve()),
        "branch": branch,
        "baseCommit": git(root, "rev-parse", "HEAD"),
        "changeId": change,
        "mode": "writable",
        "status": status,
        "allowedPaths": ["scripts", "openspec/changes/change-a"],
        "forbiddenPaths": [".env", "tmp/agent_logs"],
        "resourceAllocations": {"ports": [], "paths": [str(root.resolve())]},
        "writerLease": {"leaseId": f"lease-{run_id}", "holderRunId": run_id},
        "hookActivation": {"confirmed": True, "client": client},
        "processes": [],
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }


def save_records(repo: Path, *records: dict) -> None:
    root = resolve_runtime_root(repo) / "runs"
    root.mkdir(parents=True, exist_ok=True)
    for record in records:
        (root / f"{record['runId']}.json").write_text(json.dumps(record), encoding="utf-8")
    (root / "index.json").write_text(json.dumps({"schemaVersion": 1, "runs": [r["runId"] for r in records]}), encoding="utf-8")


def test_run_scoped_paths_separate_epochs_and_subagents(tmp_path: Path):
    first = identity_from_values("codex", "same-session", "", run_id="run-a", task_id="task-a")
    second = identity_from_values("codex", "same-session", "", run_id="run-b", task_id="task-b")
    sub = identity_from_values("codex", "same-session", "worker-1", run_id="run-a")

    assert build_paths(tmp_path, first).agent_log_dir == tmp_path / "tmp/agent_logs/codex/same-session/runs/run-a/main"
    assert build_paths(tmp_path, second).agent_log_dir == tmp_path / "tmp/agent_logs/codex/same-session/runs/run-b/main"
    assert build_paths(tmp_path, sub).agent_log_dir == tmp_path / "tmp/agent_logs/codex/same-session/runs/run-a/agents/worker-1"
    assert quality_dir(tmp_path, first) == tmp_path / "tmp/quality/codex/same-session/runs/run-a/main"


def test_hook_context_prefers_payload_over_env_and_bound_record(tmp_path: Path, monkeypatch):
    repo = init_repo(tmp_path, monkeypatch)
    save_records(repo, run_record(repo, "run-bound", session="payload-session"))
    monkeypatch.setenv("FEIPI_RUN_ID", "run-env")
    monkeypatch.setenv("FEIPI_SESSION_ID", "env-session")
    ctx = HookContext("pre-write", {"client": "codex", "session_id": "payload-session", "run_id": "run-payload", "cwd": str(repo)})

    identity = identity_from_hook_context(ctx)

    assert identity.raw_session_id == "payload-session"
    assert identity.raw_run_id == "run-payload"
    assert any("conflicts" in warning for warning in identity.legacy_warnings)


def test_evidence_records_runtime_fields_and_duplicate_event_is_idempotent(tmp_path: Path):
    identity = identity_from_values("qoder", "session-a", "", run_id="run-a", task_id="task-a", worktree_id="wt-a", turn_id="turn-a", change_id="change-a", branch="main", base_commit="abc", worktree_root=str(tmp_path))
    paths = build_paths(tmp_path, identity)
    ctx = HookContext("pre-write", {"tool_use_id": "tool-1", "turn_id": "turn-a", "session_id": "session-a"})

    record_hook_event(paths, ctx, status="PASS")
    record_hook_event(paths, ctx, status="PASS")
    lines = paths.hook_events.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])

    assert len(lines) == 1
    assert event["runId"] == "run-a"
    assert event["taskId"] == "task-a"
    assert event["worktreeId"] == "wt-a"
    assert event["changeId"] == "change-a"
    assert event["eventId"]


def test_run_authorization_blocks_change_cwd_branch_session_and_scope_mismatch(tmp_path: Path, monkeypatch):
    repo = init_repo(tmp_path, monkeypatch)
    write_change(repo, "change-a")
    record = run_record(repo, "run-a")
    save_records(repo, record)

    ok, errors, _ = validate_run_write_authorization(repo, client="codex", session_id="session-a", run_id="run-a", change_id="change-a", candidate_paths=["scripts/x.py"])
    assert ok, errors

    assert not validate_run_write_authorization(repo, client="codex", session_id="other", run_id="run-a", change_id="change-a", candidate_paths=["scripts/x.py"])[0]
    assert not validate_run_write_authorization(repo, client="codex", session_id="session-a", run_id="run-a", change_id="change-b", candidate_paths=["scripts/x.py"])[0]
    assert not validate_run_write_authorization(repo, client="codex", session_id="session-a", run_id="run-a", change_id="change-a", candidate_paths=["docs/x.md"])[0]
    git(repo, "checkout", "-b", "other")
    assert not validate_run_write_authorization(repo, client="codex", session_id="session-a", run_id="run-a", change_id="change-a", candidate_paths=["scripts/x.py"])[0]


def test_openspec_guard_uses_run_change_not_global_legacy(tmp_path: Path, monkeypatch):
    repo = init_repo(tmp_path, monkeypatch)
    write_change(repo, "change-a")
    write_change(repo, "change-b")
    save_records(repo, run_record(repo, "run-a", change="change-a"))
    legacy = repo / "tmp" / "active_change.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"change_id": "change-b"}), encoding="utf-8")

    code, message = guard_path("scripts/x.py", root=repo, run_id="run-a", session_id="session-a", client="codex")
    assert code == 0, message
    code, message = guard_path("scripts/x.py", root=repo, change_id="change-b", run_id="run-a", session_id="session-a", client="codex")
    assert code == 2
    assert "run-scoped authorization failed" in message


def test_legacy_active_change_warns_and_does_not_authorize_bound_run_without_session(tmp_path: Path, monkeypatch):
    repo = init_repo(tmp_path, monkeypatch)
    write_change(repo, "change-a")
    save_records(repo, run_record(repo, "run-a", session="session-a"))
    (repo / "tmp").mkdir(exist_ok=True)
    (repo / "tmp" / "active_change.json").write_text(json.dumps({"change_id": "change-a"}), encoding="utf-8")

    code, message = guard_path("scripts/x.py", root=repo, run_id="run-a", client="codex")
    assert code == 2
    assert "session id" in message
    legacy_identity = identity_from_values("codex", "", "")
    assert any("legacy identity" in warning for warning in legacy_identity.legacy_warnings)
