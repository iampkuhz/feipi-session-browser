import copy
import subprocess
from pathlib import Path

import pytest

from scripts.harness.primary_session import (
    PrimarySessionValidationError,
    resolve_runtime_root,
    validate_manifest_file,
    validate_run_collisions,
    validate_run_record,
    validate_status_transition,
)


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "primary-session@example.invalid"], repo)
    _run(["git", "config", "user.name", "Primary Session Test"], repo)
    (repo / "README.md").write_text("# synthetic repo\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo)
    _run(["git", "commit", "-m", "initial"], repo)
    return repo


def _record(**overrides):
    record = {
        "schemaVersion": 1,
        "runId": "run-a",
        "client": "codex",
        "taskId": "task-a",
        "sessionId": "session-a",
        "worktreeId": "worktree-a",
        "worktreeRoot": "/tmp/worktree-a",
        "branch": "agent/task-a",
        "baseCommit": "0" * 40,
        "changeId": "support-parallel-primary-sessions",
        "mode": "writable",
        "status": "running",
        "allowedPaths": ["harness"],
        "forbiddenPaths": [".env", ".mcp.json"],
        "resourceAllocations": {"ports": [], "paths": []},
        "writerLease": {"leaseId": "lease-a", "holderRunId": "run-a"},
        "hookActivation": {"confirmed": True, "client": "codex"},
        "processes": [],
        "createdAt": "2026-07-11T00:00:00Z",
        "updatedAt": "2026-07-11T00:00:01Z",
    }
    record.update(overrides)
    return record


def test_primary_session_manifest_is_machine_readable():
    validate_manifest_file(Path("harness/primary-session.manifest.yaml"))


def test_run_record_requires_all_contract_fields():
    record = _record()
    record.pop("writerLease")
    with pytest.raises(PrimarySessionValidationError, match="writerLease"):
        validate_run_record(record)


def test_bind_session_transition_from_created_to_running_is_allowed():
    validate_status_transition("created", "running")


def test_illegal_status_transition_is_rejected():
    with pytest.raises(PrimarySessionValidationError, match="illegal status transition"):
        validate_status_transition("created", "completed")


def test_same_worktree_second_writer_is_rejected():
    first = _record(runId="run-a", writerLease={"leaseId": "lease-a"})
    second = _record(
        runId="run-b",
        sessionId="session-b",
        branch="agent/task-b",
        allowedPaths=["docs"],
        writerLease={"leaseId": "lease-b"},
    )
    collisions = validate_run_collisions([first, second])
    assert [c.kind for c in collisions] == ["same-worktree-writer"]


def test_same_branch_active_writers_are_rejected():
    first = _record(runId="run-a", worktreeRoot="/tmp/worktree-a", writerLease={"leaseId": "lease-a"})
    second = _record(
        runId="run-b",
        sessionId="session-b",
        worktreeRoot="/tmp/worktree-b",
        allowedPaths=["docs"],
        writerLease={"leaseId": "lease-b"},
    )
    collisions = validate_run_collisions([first, second])
    assert [c.kind for c in collisions] == ["same-branch-writer"]


def test_write_scope_intersection_blocks_by_default_and_requires_high_risk_record():
    first = _record(runId="run-a", worktreeRoot="/tmp/worktree-a", branch="agent/a")
    second = _record(
        runId="run-b",
        sessionId="session-b",
        worktreeRoot="/tmp/worktree-b",
        branch="agent/b",
        allowedPaths=["harness/quality"],
        writerLease={"leaseId": "lease-b"},
    )
    collisions = validate_run_collisions([first, second])
    assert [c.kind for c in collisions] == ["write-scope-intersection"]

    accepted = copy.deepcopy(second)
    accepted["writeScopeOverride"] = {"highRiskAccepted": True}
    accepted["highRiskRecords"] = [{"reason": "manual serialized edit"}]
    assert validate_run_collisions([first, accepted]) == []


def test_missing_session_id_cannot_be_writable_ready():
    with pytest.raises(PrimarySessionValidationError, match="sessionId"):
        validate_run_record(_record(sessionId=""))


def test_unconfirmed_hook_activation_blocks_writable_ready():
    with pytest.raises(PrimarySessionValidationError, match="hook activation"):
        validate_run_record(_record(hookActivation={"confirmed": False}))


def test_runtime_root_override_and_git_common_dir(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    override = tmp_path / "runtime-override"
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(override))
    assert resolve_runtime_root(repo) == override.resolve()

    monkeypatch.delenv("FEIPI_AGENT_RUNTIME_ROOT")
    common = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--git-common-dir"], text=True
    ).strip()
    assert resolve_runtime_root(repo) == (repo / common).resolve() / "feipi-agent-runtime"


def test_runtime_root_shared_by_linked_worktree(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.delenv("FEIPI_AGENT_RUNTIME_ROOT", raising=False)
    worktree = tmp_path / "linked-worktree"
    _run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"], repo)
    assert resolve_runtime_root(worktree) == resolve_runtime_root(repo)
