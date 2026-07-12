import argparse
import json
import os
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SESSIONCTL = ROOT / "scripts" / "harness" / "sessionctl.py"

from scripts.claude_hooks.paths import identity_from_values
from scripts.harness import sessionctl, stop_entry
from scripts.harness.primary_session import (
    resolve_git_common_dir,
    resolve_repo_key,
    resolve_runtime_root,
    validate_run_write_authorization,
)
from scripts.harness.sessionctl import classify_tool_call
from scripts.harness.stop_entry import collect_run_changed_files


@pytest.fixture(autouse=True)
def isolated_runtime_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))


def run(cmd, cwd=None, check=True, env=None):
    result = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {cmd}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "main_java"], cwd=repo)
    run(["git", "config", "user.email", "sessionctl@example.invalid"], cwd=repo)
    run(["git", "config", "user.name", "Sessionctl Test"], cwd=repo)
    (repo / "README.md").write_text("# synthetic\n", encoding="utf-8")
    run(["git", "add", "README.md"], cwd=repo)
    run(["git", "commit", "-m", "initial"], cwd=repo)
    (repo / ".git" / "info" / "exclude").write_text(
        "tmp/agent_logs/\ntmp/quality/\n", encoding="utf-8"
    )
    return repo


def ctl(repo, *args, check=True, env=None):
    return run(
        [sys.executable, str(SESSIONCTL), "--repo-root", str(repo), *args],
        cwd=ROOT,
        check=check,
        env=env,
    )


def bootstrap(repo, session_id, hook_event="SessionStart", client="codex", *, env=None, extra=()):
    result = ctl(
        repo,
        "bootstrap",
        "--client",
        client,
        "--session-id",
        session_id,
        "--cwd",
        str(repo),
        "--hook-event",
        hook_event,
        *extra,
        env=env,
    )
    return json.loads(result.stdout)


def install_fake_stop_pass(monkeypatch):
    def fake_run_stop(client, payload, *, handoff_on_failure=False, adapter_mode='hook'):
        checkout = Path(payload["cwd"])
        registry = sessionctl.Registry(checkout)
        with registry.locked():
            record = registry.load_run(payload["runId"])
        facts = stop_entry.collect_git_evidence(checkout, record)
        summary = (
            checkout
            / "tmp"
            / "agent_logs"
            / client
            / payload["sessionId"]
            / "runs"
            / payload["runId"]
            / "main"
            / "stop-check-summary.json"
        )
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(json.dumps({"status": "PASS"}) + "\n", encoding="utf-8")
        sessionctl.record_stop_result(
            checkout,
            payload["runId"],
            stop_exit=0,
            summary_status="PASS",
            validated_facts=facts,
            handoff_on_failure=handoff_on_failure,
        )
        return 0

    monkeypatch.setattr(stop_entry, "run_stop", fake_run_stop)


def stop_with_fake_pass(repo, record, monkeypatch, capsys):
    install_fake_stop_pass(monkeypatch)
    result = sessionctl.cmd_stop(
        argparse.Namespace(repo_root=str(repo), run_id=record["runId"])
    )
    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["status"] == "VALIDATED"
    return output


def finalize_in_process(repo, record, capsys):
    result = sessionctl.cmd_finalize(
        argparse.Namespace(repo_root=str(repo), run_id=record["runId"])
    )
    output = json.loads(capsys.readouterr().out)
    return result, output


def acquire_for_session(checkout, session_id, client="codex"):
    return json.loads(
        ctl(
            checkout,
            "acquire-writer-lease",
            "--client",
            client,
            "--session-id",
            session_id,
            "--cwd",
            str(checkout),
        ).stdout
    )


def test_bootstrap_without_hints_is_idempotent_and_adopts_real_checkout_facts(tmp_path):
    repo = git_repo(tmp_path)

    started = bootstrap(repo, "session-cold", "SessionStart")
    resumed = bootstrap(repo, "session-cold", "resume")
    compacted = bootstrap(repo, "session-cold", "compact")

    assert started["runId"] == resumed["runId"] == compacted["runId"]
    assert started["repoKey"] == resolve_repo_key(repo)
    assert started["worktreeId"].startswith("checkout-")
    assert not started["worktreeId"].startswith("wt-")
    assert started["checkoutRoot"] == str(repo.resolve())
    assert started["checkoutKind"] == "primary-checkout"
    assert started["branch"] == "main_java"
    assert started["detached"] is False
    assert started["baseCommit"] == started["headCommit"]
    assert started["initialDirtySnapshot"]["dirty"] is False
    assert started["changeId"] == ""
    assert started["taskId"] == "session:session-cold"
    assert started["allowedPaths"] == ["."]
    assert started["status"] == "BOOTSTRAPPED"
    assert started["writerLease"] == {}
    assert compacted["bootstrap"]["firstHookEvent"] == "SessionStart"
    assert compacted["bootstrap"]["lastHookEvent"] == "compact"

    linked = tmp_path / "random-client-checkout"
    run(["git", "worktree", "add", "--detach", str(linked), "HEAD"], cwd=repo)
    (linked / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    before = run(["git", "worktree", "list", "--porcelain"], cwd=repo).stdout
    adopted = bootstrap(
        linked,
        "session-linked",
        "UserPromptSubmit",
        client="qoder",
        extra=("--checkout-creator", "external"),
    )
    after = run(["git", "worktree", "list", "--porcelain"], cwd=repo).stdout

    assert before == after
    assert adopted["checkoutKind"] == "linked-worktree"
    assert adopted["checkoutCreator"] == "external"
    assert adopted["branch"] == ""
    assert adopted["detached"] is True
    assert adopted["initialDirtySnapshot"]["dirty"] is True
    assert adopted["initialDirtySnapshot"]["untracked"] == ["untracked.txt"]
    assert adopted["worktreeId"] != started["worktreeId"]


def test_claude_cwd_changed_rebinds_same_run_before_first_mutation(tmp_path):
    repo = git_repo(tmp_path)
    started = bootstrap(repo, "session-claude-worktree", client="claude")
    linked = tmp_path / "claude-native-worktree"
    run(["git", "worktree", "add", "--detach", str(linked), "HEAD"], cwd=repo)

    rebound = bootstrap(
        linked,
        started["sessionId"],
        "CwdChanged",
        client="claude",
        extra=("--checkout-creator", "claude"),
    )

    assert rebound["runId"] == started["runId"]
    assert rebound["checkoutRoot"] == str(linked.resolve())
    assert rebound["checkoutKind"] == "linked-worktree"
    assert rebound["worktreeId"] != started["worktreeId"]
    assert any(
        event.get("event") == "SESSION_CHECKOUT_REBOUND"
        for event in rebound["auditEvents"]
    )
    writable = acquire_for_session(linked, rebound["sessionId"], client="claude")
    assert writable["status"] == "ISOLATED_WRITER"
    assert validate_run_write_authorization(
        linked,
        client="claude",
        session_id=rebound["sessionId"],
        run_id=rebound["runId"],
        candidate_paths=["README.md"],
    )[0]
    assert not validate_run_write_authorization(
        linked,
        client="claude",
        session_id=rebound["sessionId"],
        run_id=rebound["runId"],
        candidate_paths=[str(repo / "README.md")],
    )[0]


def test_claude_cwd_changed_rejects_rebind_after_writer_activation(tmp_path):
    repo = git_repo(tmp_path)
    started = bootstrap(repo, "session-claude-writer", client="claude")
    acquire_for_session(repo, started["sessionId"], client="claude")
    linked = tmp_path / "late-claude-worktree"
    run(["git", "worktree", "add", "--detach", str(linked), "HEAD"], cwd=repo)

    result = ctl(
        linked,
        "bootstrap",
        "--client",
        "claude",
        "--session-id",
        started["sessionId"],
        "--cwd",
        str(linked),
        "--hook-event",
        "CwdChanged",
        "--checkout-creator",
        "claude",
        check=False,
    )

    assert result.returncode == 2
    assert "cannot change after writer activation" in result.stderr
    current = sessionctl.Registry(repo).load_run(started["runId"])
    assert current["checkoutRoot"] == str(repo.resolve())


def test_claude_cwd_changed_rejects_rebind_after_writer_lease_release(tmp_path):
    repo = git_repo(tmp_path)
    started = bootstrap(repo, "session-claude-released-writer", client="claude")
    acquired = acquire_for_session(repo, started["sessionId"], client="claude")
    lease = acquired["writerLease"]
    released = json.loads(
        ctl(
            repo,
            "release-writer-lease",
            "--client",
            "claude",
            "--session-id",
            started["sessionId"],
            "--cwd",
            str(repo),
            "--epoch",
            str(lease["epoch"]),
            "--fencing-token",
            lease["fencingToken"],
        ).stdout
    )
    assert released["status"] == "READ_ONLY_READY"
    assert released["writerLease"] == {}
    assert released["releasedWriterLease"]["state"] == "RELEASED"

    linked = tmp_path / "released-claude-worktree"
    run(["git", "worktree", "add", "--detach", str(linked), "HEAD"], cwd=repo)
    result = ctl(
        linked,
        "bootstrap",
        "--client",
        "claude",
        "--session-id",
        started["sessionId"],
        "--cwd",
        str(linked),
        "--hook-event",
        "CwdChanged",
        "--checkout-creator",
        "claude",
        check=False,
    )

    assert result.returncode == 2
    assert "cannot change after writer activation" in result.stderr
    current = sessionctl.Registry(repo).load_run(started["runId"])
    assert current["checkoutRoot"] == str(repo.resolve())


def test_concurrent_bootstrap_reuses_one_registry_run(tmp_path):
    repo = git_repo(tmp_path)

    def start(_):
        return bootstrap(repo, "session-concurrent", "UserPromptSubmit")["runId"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        run_ids = list(pool.map(start, range(12)))

    assert len(set(run_ids)) == 1
    listed = json.loads(ctl(repo, "list", "--json").stdout)
    assert [item["runId"] for item in listed] == [run_ids[0]]


@pytest.mark.contract_case("HOOK-HARNESS-016")
def test_checkout_writer_lease_real_concurrency_and_worktree_isolation(tmp_path):
    repo = git_repo(tmp_path)
    for session_id in ("session-a", "session-b"):
        assert bootstrap(repo, session_id)["status"] == "BOOTSTRAPPED"

    def ready(session_id):
        return json.loads(
            ctl(
                repo,
                "mark-read-only-ready",
                "--client",
                "codex",
                "--session-id",
                session_id,
                "--cwd",
                str(repo),
            ).stdout
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        ready_records = list(pool.map(ready, ("session-a", "session-b")))
    assert {item["status"] for item in ready_records} == {"READ_ONLY_READY"}
    leases_dir = resolve_runtime_root(repo) / "writer-leases"
    assert list(leases_dir.glob("*.json")) == []

    def acquire(session_id):
        return session_id, ctl(
            repo,
            "acquire-writer-lease",
            "--client",
            "codex",
            "--session-id",
            session_id,
            "--cwd",
            str(repo),
            check=False,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(acquire, ("session-a", "session-b")))
    successes = [(session, result) for session, result in attempts if result.returncode == 0]
    conflicts = [(session, result) for session, result in attempts if result.returncode == 2]
    assert len(successes) == len(conflicts) == 1
    winner, won = successes[0]
    loser, blocked = conflicts[0]
    winner_record = json.loads(won.stdout)
    assert winner_record["status"] == "LOCAL_WRITER"
    assert "writer lease is held" in blocked.stderr
    assert bootstrap(repo, loser, "PreToolUse")["status"] == "READ_ONLY_CONFLICT"
    lease_files = list(leases_dir.glob("*.json"))
    assert len(lease_files) == 1
    assert stat.S_IMODE(lease_files[0].stat().st_mode) == 0o600

    linked_a = tmp_path / "provider-a"
    linked_b = tmp_path / "provider-b"
    run(["git", "worktree", "add", "--detach", str(linked_a), "HEAD"], cwd=repo)
    run(["git", "worktree", "add", "--detach", str(linked_b), "HEAD"], cwd=repo)
    bootstrap(linked_a, "session-linked-a")
    bootstrap(linked_b, "session-linked-b")

    def acquire_linked(values):
        checkout, session_id = values
        return json.loads(
            ctl(
                checkout,
                "acquire-writer-lease",
                "--client",
                "codex",
                "--session-id",
                session_id,
                "--cwd",
                str(checkout),
            ).stdout
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        linked_records = list(
            pool.map(
                acquire_linked,
                ((linked_a, "session-linked-a"), (linked_b, "session-linked-b")),
            )
        )
    assert {item["status"] for item in linked_records} == {"ISOLATED_WRITER"}
    assert len({item["worktreeId"] for item in linked_records}) == 2

    bootstrap(linked_a, "session-linked-conflict")
    linked_conflict = ctl(
        linked_a,
        "acquire-writer-lease",
        "--client",
        "codex",
        "--session-id",
        "session-linked-conflict",
        "--cwd",
        str(linked_a),
        check=False,
    )
    assert linked_conflict.returncode == 2
    assert bootstrap(linked_a, "session-linked-conflict", "PreToolUse")["status"] == "READ_ONLY_CONFLICT"


@pytest.mark.contract_case("HOOK-HARNESS-017")
def test_writer_lease_fencing_reclaim_heartbeat_and_precise_release(tmp_path):
    repo = git_repo(tmp_path)
    owner = bootstrap(repo, "session-owner")
    requester = bootstrap(repo, "session-requester")
    acquired = json.loads(
        ctl(
            repo,
            "acquire-writer-lease",
            "--client",
            "codex",
            "--session-id",
            "session-owner",
            "--cwd",
            str(repo),
            "--owner-pid",
            "999999",
            "--owner-start-time",
            "not-alive",
        ).stdout
    )
    lease = acquired["writerLease"]
    heartbeat = json.loads(
        ctl(
            repo,
            "heartbeat-writer-lease",
            "--client",
            "codex",
            "--session-id",
            "session-owner",
            "--cwd",
            str(repo),
            "--epoch",
            str(lease["epoch"]),
            "--fencing-token",
            lease["fencingToken"],
        ).stdout
    )
    assert heartbeat["writerLease"]["leaseId"] == lease["leaseId"]
    assert heartbeat["writerLease"]["epoch"] == lease["epoch"]

    fresh = ctl(
        repo,
        "reclaim-writer-lease",
        "--client",
        "codex",
        "--session-id",
        "session-requester",
        "--cwd",
        str(repo),
        "--expected-epoch",
        str(lease["epoch"]),
        "--expected-holder-run-id",
        owner["runId"],
        "--expected-holder-session-id",
        "session-owner",
        check=False,
    )
    assert fresh.returncode == 2
    assert "heartbeat is not stale" in fresh.stderr

    reclaimed = json.loads(
        ctl(
            repo,
            "reclaim-writer-lease",
            "--client",
            "codex",
            "--session-id",
            "session-requester",
            "--cwd",
            str(repo),
            "--expected-epoch",
            str(lease["epoch"]),
            "--expected-holder-run-id",
            owner["runId"],
            "--expected-holder-session-id",
            "session-owner",
            "--stale-after-seconds",
            "0",
        ).stdout
    )
    assert reclaimed["lease"]["state"] == "RELEASED"
    assert reclaimed["lease"]["epoch"] == lease["epoch"] + 1
    assert bootstrap(repo, "session-owner", "PreToolUse")["status"] == "BLOCKED"

    fenced = ctl(
        repo,
        "heartbeat-writer-lease",
        "--client",
        "codex",
        "--session-id",
        "session-owner",
        "--cwd",
        str(repo),
        "--epoch",
        str(lease["epoch"]),
        "--fencing-token",
        lease["fencingToken"],
        check=False,
    )
    assert fenced.returncode == 2
    assert "does not match" in fenced.stderr

    new_owner = json.loads(
        ctl(
            repo,
            "acquire-writer-lease",
            "--client",
            "codex",
            "--session-id",
            "session-requester",
            "--cwd",
            str(repo),
        ).stdout
    )
    assert new_owner["writerLease"]["epoch"] > reclaimed["lease"]["epoch"]
    released = json.loads(
        ctl(
            repo,
            "release-writer-lease",
            "--client",
            "codex",
            "--session-id",
            "session-requester",
            "--cwd",
            str(repo),
            "--epoch",
            str(new_owner["writerLease"]["epoch"]),
            "--fencing-token",
            new_owner["writerLease"]["fencingToken"],
        ).stdout
    )
    assert released["status"] == "READ_ONLY_READY"
    persisted = json.loads(
        (resolve_runtime_root(repo) / "writer-leases" / f"{requester['worktreeId']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["state"] == "RELEASED"
    assert persisted["epoch"] == new_owner["writerLease"]["epoch"]


def test_subagent_reuses_parent_run_and_dirty_attribution_boundary(tmp_path):
    repo = git_repo(tmp_path)
    (repo / "preexisting.txt").write_text("before bootstrap\n", encoding="utf-8")
    parent = bootstrap(repo, "session-parent")
    assert parent["initialDirtySnapshot"]["dirty"] is True
    assert parent["changeAttribution"]["preexistingChangesAttributedToRun"] is False
    assert parent["changeAttribution"]["requiresHandoffIfIndistinguishable"] is True

    inherited = bootstrap(
        repo,
        "session-subagent",
        "PreToolUse",
        extra=("--parent-run-id", parent["runId"]),
    )
    assert inherited["runId"] == parent["runId"]
    assert inherited["sessionId"] == "session-parent"
    assert len(json.loads(ctl(repo, "list", "--json").stdout)) == 1

    writer = json.loads(
        ctl(
            repo,
            "acquire-writer-lease",
            "--client",
            "codex",
            "--session-id",
            "session-subagent",
            "--cwd",
            str(repo),
            "--parent-run-id",
            parent["runId"],
        ).stdout
    )
    assert writer["writerLease"]["holderRunId"] == parent["runId"]
    assert writer["writerLease"]["holderSessionId"] == "session-parent"
    assert len(list((resolve_runtime_root(repo) / "writer-leases").glob("*.json"))) == 1

    subagent_end = json.loads(
        ctl(
            repo,
            "release-writer-lease",
            "--client",
            "codex",
            "--session-id",
            "session-subagent",
            "--cwd",
            str(repo),
            "--parent-run-id",
            parent["runId"],
            "--epoch",
            str(writer["writerLease"]["epoch"]),
            "--fencing-token",
            writer["writerLease"]["fencingToken"],
        ).stdout
    )
    assert subagent_end["status"] == "LOCAL_WRITER"
    lease_file = next((resolve_runtime_root(repo) / "writer-leases").glob("*.json"))
    assert json.loads(lease_file.read_text(encoding="utf-8"))["state"] == "ACTIVE"


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "expected"),
    [
        ("Read", {"path": "README.md"}, "read-only"),
        ("apply_patch", {"patch": "..."}, "mutation"),
        ("Bash", {"command": "git status --short"}, "read-only"),
        ("Bash", {"command": "python3 -m pytest -q tests/test_x.py"}, "validation"),
        ("Bash", {"command": "printf x > config.txt"}, "mutation"),
        ("Bash", {"command": "unknown-build-command"}, "mutation"),
    ],
)
def test_tool_call_classification(tool_name, tool_input, expected):
    assert classify_tool_call(tool_name, tool_input) == expected


def test_default_registry_is_private_atomic_and_outside_git_common_dir(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    temp_root = tmp_path / "system-temp"
    temp_root.mkdir(mode=0o700)
    monkeypatch.delenv("FEIPI_AGENT_RUNTIME_ROOT")
    monkeypatch.setenv("TMPDIR", str(temp_root))

    record = bootstrap(repo, "session-secure")
    runtime = resolve_runtime_root(repo)
    common_dir = resolve_git_common_dir(repo)

    assert runtime == temp_root / "feipi-agent-runtime" / resolve_repo_key(repo)
    assert common_dir not in runtime.parents
    assert not (common_dir / "feipi-agent-runtime").exists()
    for directory in [runtime, runtime / "runs", runtime / "locks", runtime / "audit"]:
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert directory.stat().st_uid == os.geteuid()
    for file_path in [
        runtime / "runs" / "index.json",
        runtime / "runs" / f"{record['runId']}.json",
        runtime / "locks" / "registry.lock",
    ]:
        assert stat.S_IMODE(file_path.stat().st_mode) == 0o600
        assert file_path.stat().st_uid == os.geteuid()
    assert not list(runtime.rglob(".*.tmp"))

    lock = json.loads((runtime / "locks" / "registry.lock").read_text(encoding="utf-8"))
    assert lock["owner"] == f"uid:{os.geteuid()}"
    assert lock["ownerUid"] == os.geteuid()
    assert lock["pid"] > 0
    assert lock["processStartTime"]
    assert lock["client"] == "codex"
    assert lock["sessionId"] == "session-secure"
    assert lock["runId"] == record["runId"]
    assert lock["epoch"] > 0
    assert lock["acquiredAt"] and lock["updatedAt"] and lock["releasedAt"]


@pytest.mark.parametrize("attack", ["runs-directory", "registry-lock"])
def test_registry_rejects_symbolic_link_targets(tmp_path, attack):
    repo = git_repo(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    target = tmp_path / "attacker-target"
    if attack == "runs-directory":
        target.mkdir()
        (runtime / "runs").symlink_to(target, target_is_directory=True)
    else:
        (runtime / "locks").mkdir(mode=0o700)
        target.write_text("not a lock\n", encoding="utf-8")
        (runtime / "locks" / "registry.lock").symlink_to(target)

    result = ctl(
        repo,
        "bootstrap",
        "--client",
        "codex",
        "--session-id",
        "session-symlink",
        "--cwd",
        str(repo),
        "--hook-event",
        "SessionStart",
        check=False,
    )

    assert result.returncode == 2
    assert "symbolic link" in result.stderr or "Too many levels" in result.stderr


def test_registry_identity_wins_conflicting_hints_and_set_change_uses_session(tmp_path):
    repo = git_repo(tmp_path)
    (repo / "openspec" / "changes" / "adopt-client-checkout-runtime").mkdir(parents=True)
    authoritative = bootstrap(repo, "session-authority")
    other = bootstrap(repo, "session-other")
    resolved = bootstrap(
        repo,
        "session-authority",
        "resume",
        extra=("--run-id", other["runId"]),
    )

    assert resolved["runId"] == authoritative["runId"]
    assert resolved["changeId"] == ""
    ignored = {(event["source"], event["field"]) for event in resolved["auditEvents"]}
    assert ("payload", "runId") in ignored

    changed = json.loads(
        ctl(
            repo,
            "set-change",
            "--client",
            "codex",
            "--session-id",
            "session-authority",
            "--cwd",
            str(repo),
            "--change-id",
            "adopt-client-checkout-runtime",
            "--task-id",
            "runtime-adoption",
        ).stdout
    )
    assert changed["runId"] == authoritative["runId"]
    assert changed["changeId"] == "adopt-client-checkout-runtime"
    assert changed["taskId"] == "runtime-adoption"
    assert bootstrap(repo, "session-other")["changeId"] == ""
    audit_files = list((resolve_runtime_root(repo) / "audit").glob("*.json"))
    audit_events = {json.loads(path.read_text(encoding="utf-8"))["event"] for path in audit_files}
    assert audit_events == {"IDENTITY_HINT_IGNORED", "CHANGE_BOUND"}


def test_random_detached_checkout_write_stop_evidence_and_handoff_ignore_branch_name(tmp_path):
    repo = git_repo(tmp_path)
    linked = tmp_path / "provider worktrees" / "random-checkout"
    linked.parent.mkdir()
    run(["git", "worktree", "add", "--detach", str(linked), "HEAD"], cwd=repo)
    record = bootstrap(
        linked,
        "session-detached",
        "SessionStart",
        extra=("--checkout-creator", "external"),
    )
    record = json.loads(
        ctl(
            linked,
            "acquire-writer-lease",
            "--client",
            "codex",
            "--session-id",
            "session-detached",
            "--cwd",
            str(linked),
        ).stdout
    )
    assert record["status"] == "ISOLATED_WRITER"
    run(["git", "switch", "-c", "arbitrary-provider-branch"], cwd=linked)

    allowed, errors, _ = validate_run_write_authorization(
        linked,
        client="codex",
        session_id="session-detached",
        run_id=record["runId"],
        candidate_paths=["README.md"],
    )
    assert allowed, errors
    assert not validate_run_write_authorization(
        linked,
        client="codex",
        session_id="session-detached",
        run_id=record["runId"],
        candidate_paths=[str(tmp_path / "outside.txt")],
    )[0]

    (linked / "README.md").write_text("changed\n", encoding="utf-8")
    (linked / "untracked.txt").write_text("new\n", encoding="utf-8")
    identity = identity_from_values(
        "codex",
        "session-detached",
        "",
        run_id=record["runId"],
        worktree_id=record["worktreeId"],
        branch=record["branch"],
        base_commit=record["baseCommit"],
        checkout_root=str(linked),
    )
    changed, evidence_mode, warnings = collect_run_changed_files(linked, identity, record)
    assert changed == ["README.md", "untracked.txt"]
    assert evidence_mode == "git-run-record"
    assert warnings == []

    handoff = json.loads(ctl(linked, "handoff", "--run-id", record["runId"]).stdout)
    assert handoff["checkoutKind"] == "linked-worktree"
    assert handoff["checkoutCreator"] == "external"
    assert handoff["observedBranch"] == "arbitrary-provider-branch"
    assert handoff["changedFiles"] == ["README.md", "untracked.txt"]
    assert handoff["committedFiles"] == []
    assert handoff["uncommittedFiles"] == ["README.md"]
    assert handoff["untrackedFiles"] == ["untracked.txt"]
    assert handoff["initialDirtyBaseline"]["dirty"] is False
    assert handoff["targetStatus"]["branch"] == "main_java"
    assert handoff["primaryStatus"]["clean"] is True
    assert not any("branch mismatch" in failure for failure in handoff["blockingFailures"])
    assert linked.exists()


@pytest.mark.contract_case("HOOK-HARNESS-024")
def test_cleanup_releases_exact_run_evidence_and_preserves_provider_checkout(tmp_path):
    repo = git_repo(tmp_path)
    linked = tmp_path / "provider-owned-checkout"
    run(["git", "worktree", "add", "--detach", str(linked), "HEAD"], cwd=repo)
    record = bootstrap(
        linked,
        "session-cleanup",
        extra=("--checkout-creator", "external"),
    )
    record = json.loads(
        ctl(
            linked,
            "acquire-writer-lease",
            "--client",
            "codex",
            "--session-id",
            "session-cleanup",
            "--cwd",
            str(linked),
        ).stdout
    )
    dirty = linked / "provider-change.txt"
    dirty.write_text("provider owns this checkout\n", encoding="utf-8")
    run_evidence = linked / "tmp" / "agent_logs" / "codex" / "session-cleanup" / "runs" / record["runId"]
    run_evidence.mkdir(parents=True)
    (run_evidence / "event.json").write_text("{}\n", encoding="utf-8")
    sibling_evidence = run_evidence.parent / "other-run"
    sibling_evidence.mkdir()
    (sibling_evidence / "keep.txt").write_text("keep\n", encoding="utf-8")

    dry_run = json.loads(ctl(linked, "cleanup", "--run-id", record["runId"]).stdout)
    assert dry_run["status"] == "dry-run"
    assert dry_run["actions"]["removeCheckout"] is False
    assert dry_run["actions"]["removeBranch"] is False
    assert linked.exists() and dirty.exists() and run_evidence.exists()

    cleaned = json.loads(
        ctl(linked, "cleanup", "--run-id", record["runId"], "--execute").stdout
    )
    assert cleaned["status"] == "cleanup-complete"
    assert linked.exists() and dirty.exists()
    assert str(linked.resolve()) in run(["git", "worktree", "list", "--porcelain"], cwd=repo).stdout
    assert not run_evidence.exists()
    assert (sibling_evidence / "keep.txt").is_file()
    assert not (resolve_runtime_root(linked) / "runs" / f"{record['runId']}.json").exists()
    persisted_lease = json.loads(
        (resolve_runtime_root(linked) / "writer-leases" / f"{record['worktreeId']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted_lease["state"] == "RELEASED"


def test_registry_concurrent_writes_keep_valid_json(tmp_path):
    repo = git_repo(tmp_path)

    def make(i):
        return bootstrap(repo, f"session-{i}", "SessionStart")["runId"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        run_ids = list(pool.map(make, range(4)))
    listed = json.loads(ctl(repo, "list", "--json").stdout)
    assert set(run_ids) <= {item["runId"] for item in listed}


def test_handoff_includes_canonical_checkout_and_run_fields(tmp_path):
    repo = git_repo(tmp_path)
    record = bootstrap(repo, "session-handoff")
    handoff = json.loads(ctl(repo, "handoff", "--run-id", record["runId"]).stdout)

    assert handoff["runId"] == record["runId"]
    assert handoff["taskId"] == "session:session-handoff"
    assert handoff["client"] == "codex"
    assert handoff["checkoutRoot"] == record["checkoutRoot"]
    assert handoff["checkoutKind"] == "primary-checkout"
    assert handoff["checkoutCreator"] == "unknown"
    assert handoff["branch"] == record["branch"]
    assert handoff["baseCommit"] == record["baseCommit"]
    assert handoff["commits"] == []
    assert handoff["aheadBehind"] == {"ahead": 0, "behind": 0}
    assert handoff["mergeBase"] == record["baseCommit"]
    assert handoff["committedFiles"] == []
    assert handoff["uncommittedFiles"] == []
    assert handoff["untrackedFiles"] == []
    assert handoff["initialDirtyBaseline"]["dirty"] is False
    assert handoff["targetStatus"]["checkedOutInPrimary"] is True
    assert handoff["primaryStatus"]["clean"] is True
    assert handoff["requiredTargetSummary"]["allowedPaths"] == ["."]
    assert "runRecord" in handoff["artifactPaths"]
    assert "blockingFailures" in handoff
    assert "writeScopeOverlap" in handoff["mergeRisk"]
    assert any("finalize --run-id" in step for step in handoff["manualNextSteps"])


def test_stop_records_canonical_git_facts_and_never_claims_integration(
    tmp_path, monkeypatch, capsys
):
    repo = git_repo(tmp_path)
    record = bootstrap(repo, "session-stop")
    (repo / "committed.txt").write_text("committed\n", encoding="utf-8")
    run(["git", "add", "committed.txt"], cwd=repo)
    run(["git", "commit", "-m", "session result"], cwd=repo)
    (repo / "README.md").write_text("uncommitted\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    stopped = stop_with_fake_pass(repo, record, monkeypatch, capsys)

    assert stopped["status"] == "VALIDATED"
    assert stopped["stopExitCode"] == 0
    assert stopped["status"] != "INTEGRATED"
    facts = stopped["gitFacts"]
    assert facts["committedFiles"] == ["committed.txt"]
    assert facts["uncommittedFiles"] == ["README.md"]
    assert facts["untrackedFiles"] == ["untracked.txt"]
    assert set(facts["changedFiles"]) == {"README.md", "committed.txt", "untracked.txt"}
    assert len(facts["commits"]) == 1
    assert facts["initialDirtyBaseline"]["dirty"] is False
    assert facts["checkoutKind"] == "primary-checkout"
    assert facts["checkoutCreator"] == "unknown"
    assert facts["targetStatus"]["headCommit"] == facts["headCommit"]
    assert facts["primaryStatus"]["dirty"] is True
    latest = json.loads(
        (
            resolve_runtime_root(repo)
            / "runs"
            / f"{record['runId']}.json"
        ).read_text(encoding="utf-8")
    )
    assert latest["status"] == "VALIDATED"
    assert latest["stopValidation"]["fresh"] is True
    assert latest["stopValidation"]["headCommit"] == facts["headCommit"]


def test_stop_validation_fingerprint_detects_same_path_content_change(
    tmp_path, monkeypatch, capsys
):
    repo = git_repo(tmp_path)
    record = bootstrap(repo, "session-content-freshness")
    acquire_for_session(repo, record["sessionId"])
    (repo / "README.md").write_text("first-content\n", encoding="utf-8")
    stop_with_fake_pass(repo, record, monkeypatch, capsys)

    registry = sessionctl.Registry(repo)
    with registry.locked():
        validated = registry.load_run(record["runId"])
    original_fingerprint = validated["stopValidation"]["checkoutFingerprint"]

    (repo / "README.md").write_text("other-content\n", encoding="utf-8")
    current_facts = sessionctl._collect_git_facts(validated)

    assert current_facts["uncommittedFiles"] == ["README.md"]
    assert current_facts["checkoutFingerprint"] != original_fingerprint
    assert sessionctl._fresh_validation_error(
        validated, current_facts, require_target_match=False
    ) == "checkout Git state changed after Stop validation"


@pytest.mark.parametrize("checkout_creator", ["codex", "external"])
def test_finalize_ff_only_preserves_provider_checkout_and_releases_exact_lease(
    tmp_path, monkeypatch, capsys, checkout_creator
):
    repo = git_repo(tmp_path)
    linked = tmp_path / f"{checkout_creator} provider checkout"
    run(["git", "worktree", "add", "-b", f"feature-{checkout_creator}", str(linked), "HEAD"], cwd=repo)
    record = bootstrap(
        linked,
        f"session-finalize-{checkout_creator}",
        extra=("--checkout-creator", checkout_creator),
    )
    assert record["targetBranch"] == "main_java"
    assert record["targetHeadAtBootstrap"] == record["baseCommit"]
    leased = acquire_for_session(linked, record["sessionId"])
    (linked / "result.txt").write_text(f"{checkout_creator}\n", encoding="utf-8")
    run(["git", "add", "result.txt"], cwd=linked)
    run(["git", "commit", "-m", "provider result"], cwd=linked)
    stop_with_fake_pass(linked, record, monkeypatch, capsys)

    result, summary = finalize_in_process(linked, record, capsys)

    assert result == 0
    assert summary["status"] == "INTEGRATED"
    assert summary["strategy"] == "ff-only"
    assert summary["checkoutCreator"] == checkout_creator
    assert summary["checkoutPreserved"] is True
    assert summary["pushed"] is False
    assert linked.exists()
    assert run(["git", "branch", "--show-current"], cwd=repo).stdout.strip() == "main_java"
    assert run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip() == run(
        ["git", "rev-parse", "HEAD"], cwd=linked
    ).stdout.strip()
    runtime = resolve_runtime_root(linked)
    latest = json.loads(
        (runtime / "runs" / f"{record['runId']}.json").read_text(encoding="utf-8")
    )
    lease = json.loads(
        (runtime / "writer-leases" / f"{record['worktreeId']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert latest["status"] == "INTEGRATED"
    assert latest["writerLease"] == {}
    assert lease["state"] == "RELEASED"
    assert lease["leaseId"] == leased["writerLease"]["leaseId"]
    assert lease["releaseReason"] == "finalize-integrated"
    assert {event["event"] for event in latest["auditEvents"]} >= {
        "WRITER_LEASE_RELEASED",
        "RUN_INTEGRATED",
    }


def test_finalize_primary_checkout_is_already_on_target_and_preserves_status_on_release(
    tmp_path, monkeypatch, capsys
):
    repo = git_repo(tmp_path)
    record = bootstrap(repo, "session-finalize-primary")
    acquire_for_session(repo, record["sessionId"])
    (repo / "primary-result.txt").write_text("result\n", encoding="utf-8")
    run(["git", "add", "primary-result.txt"], cwd=repo)
    run(["git", "commit", "-m", "primary result"], cwd=repo)
    stop_with_fake_pass(repo, record, monkeypatch, capsys)

    result, summary = finalize_in_process(repo, record, capsys)

    assert result == 0
    assert summary["strategy"] == "already-on-target"
    assert summary["checkoutKind"] == "primary-checkout"
    latest = json.loads(
        (
            resolve_runtime_root(repo)
            / "runs"
            / f"{record['runId']}.json"
        ).read_text(encoding="utf-8")
    )
    assert latest["status"] == "INTEGRATED"
    assert latest["writerLease"] == {}
    assert repo.exists()


def test_finalize_rebases_target_advance_revalidates_and_ff_only_integrates(
    tmp_path, monkeypatch, capsys
):
    repo = git_repo(tmp_path)
    linked = tmp_path / "provider-rebase"
    run(["git", "worktree", "add", "-b", "feature-rebase", str(linked), "HEAD"], cwd=repo)
    record = bootstrap(
        linked,
        "session-finalize-rebase",
        extra=("--checkout-creator", "external"),
    )
    acquire_for_session(linked, record["sessionId"])
    (linked / "feature.txt").write_text("feature\n", encoding="utf-8")
    run(["git", "add", "feature.txt"], cwd=linked)
    run(["git", "commit", "-m", "feature result"], cwd=linked)
    stop_with_fake_pass(linked, record, monkeypatch, capsys)
    (repo / "target.txt").write_text("target advanced\n", encoding="utf-8")
    run(["git", "add", "target.txt"], cwd=repo)
    run(["git", "commit", "-m", "target advance"], cwd=repo)

    result, summary = finalize_in_process(linked, record, capsys)

    assert result == 0
    assert summary["strategy"] == "rebase-then-ff"
    assert (repo / "feature.txt").read_text(encoding="utf-8") == "feature\n"
    assert (repo / "target.txt").read_text(encoding="utf-8") == "target advanced\n"
    assert linked.exists()
    latest = json.loads(
        (
            resolve_runtime_root(linked)
            / "runs"
            / f"{record['runId']}.json"
        ).read_text(encoding="utf-8")
    )
    assert latest["status"] == "INTEGRATED"
    assert sum(event["event"] == "STOP_VALIDATED" for event in latest["auditEvents"]) == 2


def test_finalize_target_advance_revalidation_failure_handoffs_and_exits_two(
    tmp_path, monkeypatch, capsys
):
    repo = git_repo(tmp_path)
    linked = tmp_path / "provider-revalidation-failure"
    run(
        ["git", "worktree", "add", "-b", "feature-revalidation-failure", str(linked), "HEAD"],
        cwd=repo,
    )
    record = bootstrap(
        linked,
        "session-revalidation-failure",
        extra=("--checkout-creator", "external"),
    )
    acquire_for_session(linked, record["sessionId"])
    (linked / "feature.txt").write_text("feature\n", encoding="utf-8")
    run(["git", "add", "feature.txt"], cwd=linked)
    run(["git", "commit", "-m", "feature result"], cwd=linked)
    stop_with_fake_pass(linked, record, monkeypatch, capsys)
    (repo / "target.txt").write_text("target advanced\n", encoding="utf-8")
    run(["git", "add", "target.txt"], cwd=repo)
    run(["git", "commit", "-m", "target advance"], cwd=repo)
    target_head = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

    def fake_stop_failure(
        _client,
        payload,
        *,
        handoff_on_failure=False,
        adapter_mode='hook',
    ):
        checkout = Path(payload["cwd"])
        registry = sessionctl.Registry(checkout)
        with registry.locked():
            current = registry.load_run(payload["runId"])
        facts = stop_entry.collect_git_evidence(checkout, current)
        sessionctl.record_stop_result(
            checkout,
            payload["runId"],
            stop_exit=2,
            summary_status="BLOCKED",
            validated_facts=facts,
            handoff_on_failure=handoff_on_failure,
        )
        return 2

    monkeypatch.setattr(stop_entry, "run_stop", fake_stop_failure)
    result, summary = finalize_in_process(linked, record, capsys)

    assert result == 2
    assert summary["status"] == "HANDOFF_REQUIRED"
    assert summary["reason"] == "revalidation failed after target advanced"
    assert run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip() == target_head
    runtime = resolve_runtime_root(linked)
    latest = json.loads(
        (runtime / "runs" / f"{record['runId']}.json").read_text(encoding="utf-8")
    )
    assert latest["status"] == "HANDOFF_REQUIRED"
    assert latest["stopValidation"]["status"] == "FAIL"
    assert latest["writerLease"] == {}
    assert "STOP_HANDOFF_REQUIRED" in {
        event["event"] for event in latest["auditEvents"]
    }


@pytest.mark.parametrize(
    "unsafe_state, expected_reason",
    [
        ("dirty-and-untracked", "uncommitted or untracked"),
        ("detached", "detached HEAD"),
        ("primary-dirty", "primary checkout dirty"),
        ("primary-branch-mismatch", "not on the recorded target branch"),
        ("initial-dirty", "initial dirty baseline"),
        ("validation-stale", "HEAD changed after Stop validation"),
    ],
)
def test_finalize_unsafe_git_states_require_handoff_without_deleting_checkout(
    tmp_path, monkeypatch, capsys, unsafe_state, expected_reason
):
    repo = git_repo(tmp_path)
    linked = tmp_path / f"unsafe {unsafe_state}"
    if unsafe_state == "detached":
        run(["git", "worktree", "add", "--detach", str(linked), "HEAD"], cwd=repo)
    else:
        run(
            ["git", "worktree", "add", "-b", f"feature-{unsafe_state}", str(linked), "HEAD"],
            cwd=repo,
        )
    if unsafe_state == "initial-dirty":
        (linked / "README.md").write_text("preexisting\n", encoding="utf-8")
    record = bootstrap(
        linked,
        f"session-{unsafe_state}",
        extra=("--checkout-creator", "external"),
    )
    acquire_for_session(linked, record["sessionId"])

    if unsafe_state == "dirty-and-untracked":
        (linked / "README.md").write_text("dirty\n", encoding="utf-8")
        (linked / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    else:
        (linked / "README.md").write_text(f"{unsafe_state}\n", encoding="utf-8")
        run(["git", "add", "README.md"], cwd=linked)
        run(["git", "commit", "-m", f"result {unsafe_state}"], cwd=linked)
    stop_with_fake_pass(linked, record, monkeypatch, capsys)

    if unsafe_state == "primary-dirty":
        (repo / "primary-untracked.txt").write_text("keep\n", encoding="utf-8")
    elif unsafe_state == "primary-branch-mismatch":
        run(["git", "switch", "-c", "other-primary-branch"], cwd=repo)
    elif unsafe_state == "validation-stale":
        (linked / "after-stop.txt").write_text("later\n", encoding="utf-8")
        run(["git", "add", "after-stop.txt"], cwd=linked)
        run(["git", "commit", "-m", "changed after stop"], cwd=linked)

    result, summary = finalize_in_process(linked, record, capsys)

    assert result == 2
    assert summary["status"] == "HANDOFF_REQUIRED"
    assert expected_reason in summary["reason"]
    assert linked.exists()
    if unsafe_state == "primary-branch-mismatch":
        assert run(["git", "branch", "--show-current"], cwd=repo).stdout.strip() == "other-primary-branch"
    runtime = resolve_runtime_root(linked)
    latest = json.loads(
        (runtime / "runs" / f"{record['runId']}.json").read_text(encoding="utf-8")
    )
    lease = json.loads(
        (runtime / "writer-leases" / f"{record['worktreeId']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert latest["status"] == "HANDOFF_REQUIRED"
    assert latest["writerLease"] == {}
    assert lease["state"] == "RELEASED"
    handoff = json.loads(Path(latest["handoffSummary"]).read_text(encoding="utf-8"))
    assert handoff["checkoutRoot"] == str(linked.resolve())
    assert handoff["checkoutCreator"] == "external"
    assert handoff["initialDirtyBaseline"]["dirty"] is (unsafe_state == "initial-dirty")


def test_finalize_rebase_conflict_aborts_and_handoffs_without_moving_target(
    tmp_path, monkeypatch, capsys
):
    repo = git_repo(tmp_path)
    linked = tmp_path / "provider-conflict"
    run(["git", "worktree", "add", "-b", "feature-conflict", str(linked), "HEAD"], cwd=repo)
    record = bootstrap(
        linked,
        "session-finalize-conflict",
        extra=("--checkout-creator", "external"),
    )
    acquire_for_session(linked, record["sessionId"])
    (linked / "README.md").write_text("feature\n", encoding="utf-8")
    run(["git", "add", "README.md"], cwd=linked)
    run(["git", "commit", "-m", "feature conflict"], cwd=linked)
    feature_head = run(["git", "rev-parse", "HEAD"], cwd=linked).stdout.strip()
    stop_with_fake_pass(linked, record, monkeypatch, capsys)
    (repo / "README.md").write_text("target\n", encoding="utf-8")
    run(["git", "add", "README.md"], cwd=repo)
    run(["git", "commit", "-m", "target conflict"], cwd=repo)
    target_head = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

    result, summary = finalize_in_process(linked, record, capsys)

    assert result == 2
    assert summary["status"] == "HANDOFF_REQUIRED"
    assert summary["reason"] == "target advanced with conflicts"
    assert run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip() == target_head
    assert run(["git", "rev-parse", "HEAD"], cwd=linked).stdout.strip() == feature_head
    assert run(["git", "status", "--porcelain"], cwd=linked).stdout == ""
    assert linked.exists()
