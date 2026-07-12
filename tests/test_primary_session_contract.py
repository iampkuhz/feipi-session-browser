import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.harness.primary_session import (
    PrimarySessionValidationError,
    ensure_private_directory,
    resolve_checkout_identity,
    resolve_checkout_root,
    resolve_git_common_dir,
    resolve_primary_repo_root,
    resolve_repo_key,
    resolve_runtime_root,
    validate_checkout_record,
    validate_manifest_file,
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
        "schemaVersion": 2,
        "runId": "run-a",
        "client": "codex",
        "taskId": "task-a",
        "sessionId": "session-a",
        "repoKey": "repo-a",
        "worktreeId": "checkout-a",
        "checkoutRoot": "/tmp/worktree-a",
        "checkoutKind": "linked-worktree",
        "checkoutCreator": "codex",
        "gitCommonDir": "/tmp/primary/.git",
        "detached": False,
        "initialDirtySnapshot": {
            "dirty": False,
            "tracked": [],
            "untracked": [],
            "capturedAt": "2026-07-11T00:00:00Z",
        },
        "changeAttribution": {
            "baseline": "initialDirtySnapshot",
            "preexistingChangesAttributedToRun": False,
            "requiresHandoffIfIndistinguishable": False,
        },
        "branch": "agent/task-a",
        "targetBranch": "main_java",
        "primaryRepoRoot": "/tmp/primary",
        "baseCommit": "0" * 40,
        "headCommit": "0" * 40,
        "changeId": "converge-agent-hook-runtime",
        "status": "ISOLATED_WRITER",
        "allowedPaths": ["harness"],
        "forbiddenPaths": [".env", ".mcp.json"],
        "writerLease": {
            "leaseId": "lease-a",
            "holderRunId": "run-a",
            "holderSessionId": "session-a",
            "epoch": 1,
            "fencingToken": "fence-a",
        },
        "hookActivation": {"confirmed": True, "client": "codex"},
        "createdAt": "2026-07-11T00:00:00Z",
        "updatedAt": "2026-07-11T00:00:01Z",
    }
    record.update(overrides)
    return record


def test_primary_session_manifest_is_machine_readable():
    validate_manifest_file(Path("harness/agent-runtime.manifest.yaml"))


def test_run_record_requires_all_contract_fields():
    record = _record()
    record.pop("writerLease")
    with pytest.raises(PrimarySessionValidationError, match="writerLease"):
        validate_run_record(record)


@pytest.mark.parametrize(
    ("source", "target", "allowed"),
    [
        ("BOOTSTRAPPED", "ISOLATED_WRITER", True),
        ("VALIDATING", "READ_ONLY_READY", True),
        ("BLOCKED", "VALIDATING", False),
        ("READ_ONLY_READY", "BOOTSTRAPPED", False),
    ],
)
def test_status_transition_contract(source, target, allowed):
    if allowed:
        validate_status_transition(source, target)
    else:
        with pytest.raises(PrimarySessionValidationError, match="illegal status transition"):
            validate_status_transition(source, target)


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
    assert override.stat().st_mode & 0o777 == 0o700

    monkeypatch.delenv("FEIPI_AGENT_RUNTIME_ROOT")
    temp_root = tmp_path / "system-temp"
    temp_root.mkdir()
    monkeypatch.setenv("TMPDIR", str(temp_root))
    runtime_root = resolve_runtime_root(repo)
    assert runtime_root == temp_root / "feipi-agent-runtime" / resolve_repo_key(repo)
    assert resolve_checkout_root(repo) == repo.resolve()
    assert resolve_git_common_dir(repo) == (repo / ".git").resolve()
    assert resolve_primary_repo_root(repo) == repo.resolve()
    assert runtime_root.stat().st_mode & 0o777 == 0o700
    assert runtime_root.parent.stat().st_mode & 0o777 == 0o700
    assert not (repo / ".git" / "feipi-agent-runtime").exists()


def test_runtime_root_shared_by_linked_worktree(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    monkeypatch.delenv("FEIPI_AGENT_RUNTIME_ROOT", raising=False)
    temp_root = tmp_path / "system-temp"
    temp_root.mkdir()
    monkeypatch.setenv("TMPDIR", str(temp_root))
    worktree = tmp_path / "linked-worktree"
    _run(["git", "worktree", "add", "-b", "linked-runtime-root-test", str(worktree), "HEAD"], repo)
    assert resolve_runtime_root(worktree) == resolve_runtime_root(repo)
    assert resolve_repo_key(worktree) == resolve_repo_key(repo)
    assert resolve_git_common_dir(worktree) == resolve_git_common_dir(repo)
    assert resolve_primary_repo_root(worktree) == repo.resolve()
    nested = worktree / "nested"
    nested.mkdir()
    assert resolve_checkout_root(nested) == worktree.resolve()


def test_checkout_record_authorizes_detached_branch_independently_and_contains_paths(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    worktree = tmp_path / "provider-worktree"
    _run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"], repo)
    identity = resolve_checkout_identity(worktree, checkout_creator="codex")
    record = _record(
        repoKey=identity["repoKey"],
        worktreeId=identity["worktreeId"],
        checkoutRoot=identity["checkoutRoot"],
        checkoutKind=identity["checkoutKind"],
        checkoutCreator="codex",
        gitCommonDir=identity["gitCommonDir"],
        primaryRepoRoot=identity["primaryRepoRoot"],
        branch="stale-observation-must-not-authorize",
        targetBranch="",
        baseCommit=identity["headCommit"],
        headCommit=identity["headCommit"],
        allowedPaths=["."],
        forbiddenPaths=[".env", "tmp/private"],
    )
    _, errors = validate_checkout_record(worktree, record)
    assert errors == []

    runtime = tmp_path / "runtime"
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(runtime))
    runs = resolve_runtime_root(worktree) / "runs"
    runs.mkdir()
    (runs / "run-a.json").write_text(json.dumps(record), encoding="utf-8")
    (runs / "index.json").write_text(json.dumps({"runs": ["run-a"]}), encoding="utf-8")
    leases = resolve_runtime_root(worktree) / "writer-leases"
    leases.mkdir()
    lease = {
        **record["writerLease"],
        "holderRunId": record["runId"],
        "holderSessionId": record["sessionId"],
        "repoKey": record["repoKey"],
        "worktreeId": record["worktreeId"],
        "checkoutRoot": record["checkoutRoot"],
        "state": "ACTIVE",
        "heartbeatAt": "2026-07-11T00:00:02Z",
    }
    (leases / f'{record["worktreeId"]}.json').write_text(json.dumps(lease), encoding="utf-8")

    from scripts.harness.primary_session import validate_run_write_authorization

    ok, errors, _ = validate_run_write_authorization(
        worktree, client="codex", session_id="session-a", run_id="run-a", candidate_paths=["src/new.py"]
    )
    assert ok, errors
    assert not validate_run_write_authorization(
        worktree, client="codex", session_id="session-a", run_id="run-a", candidate_paths=[".env"]
    )[0]
    assert not validate_run_write_authorization(
        worktree, client="codex", session_id="session-a", run_id="run-a", candidate_paths=[str(tmp_path / "escape.py")]
    )[0]

    wrong = dict(record, repoKey="wrong", gitCommonDir=str(tmp_path), worktreeId="directory-name")
    _, mismatch = validate_checkout_record(worktree, wrong)
    assert {"run repoKey does not match current checkout", "run gitCommonDir does not match current checkout", "run worktreeId does not match current checkout"} <= set(mismatch)


def test_private_runtime_directories_are_0700_and_reject_symlinks(tmp_path, monkeypatch):
    root = ensure_private_directory(tmp_path / "runtime")
    child = ensure_private_directory(root / "runs", root=root)
    assert root.stat().st_mode & 0o777 == 0o700
    assert child.stat().st_mode & 0o777 == 0o700

    os.chmod(child, 0o755)
    ensure_private_directory(child, root=root)
    assert child.stat().st_mode & 0o777 == 0o700

    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "linked-locks"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PrimarySessionValidationError, match="symbolic link"):
        ensure_private_directory(link, root=root)

    repo = _git_repo(tmp_path)
    override_link = tmp_path / "runtime-override-link"
    override_link.symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(override_link))
    with pytest.raises(PrimarySessionValidationError, match="symbolic link"):
        resolve_runtime_root(repo)
