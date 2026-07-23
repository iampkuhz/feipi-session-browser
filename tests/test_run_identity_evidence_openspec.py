from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from scripts.agent_runtime.context import HookContext
from scripts.agent_runtime.events.evidence import record_hook_event
from scripts.agent_runtime.paths import build_paths, identity_from_values, quality_dir
from scripts.checks.check_css_ownership import artifact_dir as css_artifact_dir
from scripts.agent_runtime.session.contract import (
    resolve_checkout_identity,
    resolve_runtime_root,
    validate_run_write_authorization,
)
from scripts.hooks.guard_openspec_change import guard_path

if TYPE_CHECKING:
    from pathlib import Path


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


def run_record(
    repo: Path,
    run_id: str,
    *,
    client="codex",
    session="session-a",
    change="change-a",
    branch="main",
    status="",
    worktree: Path | None = None,
) -> dict:
    root = worktree or repo
    head = git(root, "rev-parse", "HEAD")
    facts = resolve_checkout_identity(root, checkout_creator="unknown", base_commit=head)
    writer_status = status or (
        "LOCAL_WRITER" if facts["checkoutKind"] == "primary-checkout" else "ISOLATED_WRITER"
    )
    return {
        "schemaVersion": 2,
        "runId": run_id,
        "repoKey": facts["repoKey"],
        "client": client,
        "taskId": "task-1",
        "sessionId": session,
        "worktreeId": facts["worktreeId"],
        "checkoutRoot": facts["checkoutRoot"],
        "checkoutKind": facts["checkoutKind"],
        "checkoutCreator": facts["checkoutCreator"],
        "gitCommonDir": facts["gitCommonDir"],
        "branch": branch,
        "detached": facts["detached"],
        "targetBranch": branch,
        "primaryRepoRoot": facts["primaryRepoRoot"],
        "baseCommit": head,
        "headCommit": head,
        "initialDirtySnapshot": {
            "dirty": False,
            "tracked": [],
            "untracked": [],
            "capturedAt": "2026-01-01T00:00:00Z",
        },
        "changeAttribution": {
            "baseline": "initialDirtySnapshot",
            "preexistingChangesAttributedToRun": False,
            "requiresHandoffIfIndistinguishable": False,
        },
        "changeId": change,
        "status": writer_status,
        "allowedPaths": ["scripts", "openspec/changes/change-a"],
        "forbiddenPaths": [".env", "tmp/agent_logs"],
        "writerLease": {
            "leaseId": f"lease-{run_id}",
            "holderRunId": run_id,
            "holderSessionId": session,
            "epoch": 1,
            "fencingToken": f"fence-{run_id}",
        },
        "hookActivation": {"confirmed": True, "client": client},
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }


def save_records(repo: Path, *records: dict) -> None:
    runtime = resolve_runtime_root(repo)
    root = runtime / "runs"
    root.mkdir(parents=True, exist_ok=True)
    leases = runtime / "writer-leases"
    leases.mkdir(parents=True, exist_ok=True)
    for record in records:
        (root / f"{record['runId']}.json").write_text(json.dumps(record), encoding="utf-8")
        lease = {
            **record["writerLease"],
            "repoKey": record["repoKey"],
            "worktreeId": record["worktreeId"],
            "checkoutRoot": record["checkoutRoot"],
            "state": "ACTIVE",
        }
        (leases / f"{record['worktreeId']}.json").write_text(json.dumps(lease), encoding="utf-8")
    (root / "index.json").write_text(
        json.dumps({"schemaVersion": 2, "runs": [r["runId"] for r in records]}), encoding="utf-8"
    )


@pytest.mark.contract_case("HOOK-HARNESS-022")
def test_run_scoped_paths_separate_epochs_and_subagents(tmp_path: Path):
    first = identity_from_values("codex", "same-session", "", run_id="run-a", task_id="task-a")
    second = identity_from_values("codex", "same-session", "", run_id="run-b", task_id="task-b")
    sub = identity_from_values("codex", "same-session", "worker-1", run_id="run-a")

    assert (
        build_paths(tmp_path, first).agent_log_dir
        == tmp_path / "tmp/agent_logs/codex/same-session/runs/run-a/main"
    )
    assert (
        build_paths(tmp_path, second).agent_log_dir
        == tmp_path / "tmp/agent_logs/codex/same-session/runs/run-b/main"
    )
    assert (
        build_paths(tmp_path, sub).agent_log_dir
        == tmp_path / "tmp/agent_logs/codex/same-session/runs/run-a/agents/worker-1"
    )
    assert (
        quality_dir(tmp_path, first) == tmp_path / "tmp/quality/codex/same-session/runs/run-a/main"
    )
    assert css_artifact_dir(tmp_path, first) != css_artifact_dir(tmp_path, second)
    assert css_artifact_dir(tmp_path, first) == (
        tmp_path
        / "tmp/quality/codex/same-session/runs/run-a/main/css-ownership"
    )


def test_evidence_records_runtime_fields_and_duplicate_event_is_idempotent(tmp_path: Path):
    identity = identity_from_values(
        "qoder",
        "session-a",
        "",
        run_id="run-a",
        task_id="task-a",
        worktree_id="checkout-a",
        turn_id="turn-a",
        change_id="change-a",
        branch="main",
        base_commit="abc",
        checkout_root=str(tmp_path),
    )
    paths = build_paths(tmp_path, identity)
    ctx = HookContext(
        "pre-write", {"tool_use_id": "tool-1", "turn_id": "turn-a", "session_id": "session-a"}
    )

    record_hook_event(paths, ctx, status="PASS")
    record_hook_event(paths, ctx, status="PASS")
    lines = paths.hook_events.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])

    assert len(lines) == 1
    assert event["runId"] == "run-a"
    assert event["taskId"] == "task-a"
    assert event["worktreeId"] == "checkout-a"
    assert event["changeId"] == "change-a"
    assert event["eventId"]


def test_run_authorization_blocks_change_session_scope_but_not_branch_name(
    tmp_path: Path, monkeypatch
):
    repo = init_repo(tmp_path, monkeypatch)
    write_change(repo, "change-a")
    record = run_record(repo, "run-a")
    save_records(repo, record)

    ok, errors, _ = validate_run_write_authorization(
        repo,
        client="codex",
        session_id="session-a",
        run_id="run-a",
        change_id="change-a",
        candidate_paths=["scripts/x.py"],
    )
    assert ok, errors

    assert not validate_run_write_authorization(
        repo,
        client="codex",
        session_id="other",
        run_id="run-a",
        change_id="change-a",
        candidate_paths=["scripts/x.py"],
    )[0]
    assert not validate_run_write_authorization(
        repo,
        client="codex",
        session_id="session-a",
        run_id="run-a",
        change_id="change-b",
        candidate_paths=["scripts/x.py"],
    )[0]
    assert not validate_run_write_authorization(
        repo,
        client="codex",
        session_id="session-a",
        run_id="run-a",
        change_id="change-a",
        candidate_paths=["docs/x.md"],
    )[0]
    git(repo, "checkout", "-b", "other")
    allowed, errors, _ = validate_run_write_authorization(
        repo,
        client="codex",
        session_id="session-a",
        run_id="run-a",
        change_id="change-a",
        candidate_paths=["scripts/x.py"],
    )
    assert allowed, errors


@pytest.mark.contract_case("HOOK-HARNESS-018")
def test_openspec_guard_uses_bound_run_change(tmp_path: Path, monkeypatch):
    repo = init_repo(tmp_path, monkeypatch)
    write_change(repo, "change-a")
    save_records(repo, run_record(repo, "run-a", change="change-a"))
    code, message = guard_path(
        "scripts/x.py", root=repo, run_id="run-a", session_id="session-a", client="codex"
    )
    assert code == 0, message
    code, message = guard_path(
        "scripts/x.py",
        root=repo,
        change_id="change-b",
        run_id="run-a",
        session_id="session-a",
        client="codex",
    )
    assert code == 2
    assert "run-scoped authorization failed" in message
