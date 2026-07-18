import copy
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

from scripts.agent_runtime.change.controller import attest_run_start  # noqa: E402
from scripts.agent_runtime.paths import identity_from_values  # noqa: E402
from scripts.agent_runtime.session import lifecycle as sessionctl  # noqa: E402
from scripts.agent_runtime.session.contract import (  # noqa: E402
    resolve_git_common_dir,
    resolve_repo_key,
    resolve_runtime_root,
    validate_run_write_authorization,
)
from scripts.agent_runtime.session.lifecycle import classify_tool_call  # noqa: E402
from scripts.agent_runtime.session.registry import Registry  # noqa: E402
from scripts.agent_runtime.stop import evidence as stop_evidence  # noqa: E402
from scripts.agent_runtime.stop.evidence import collect_run_changed_files  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_runtime_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))


def run(cmd, cwd=None, check=True, env=None):
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {cmd}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
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


def _runtime_file_state(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(root)): (path.stat().st_mtime_ns, path.read_bytes())
        for path in root.rglob('*')
        if path.is_file()
    }


def test_current_returns_bounded_unique_attested_run_without_writes(tmp_path):
    repo = git_repo(tmp_path)
    record = bootstrap(repo, 'session-current')
    attest_run_start(
        repo,
        record['runId'],
        activation_source='hook:codex-app:SessionStart',
    )
    runtime = resolve_runtime_root(repo)
    before = _runtime_file_state(runtime)

    result = ctl(
        repo,
        'current',
        '--client',
        'codex',
        '--session-id',
        'session-current',
        '--json',
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload['runId'] == record['runId']
    assert payload['sessionId'] == 'session-current'
    assert payload['checkoutRoot'] == str(repo.resolve())
    assert payload['changeId'] is None
    assert payload['state'] is None
    assert payload['changeBegin']['status'] == 'ATTESTED'
    assert 'auditEvents' not in result.stdout
    assert len(result.stdout.encode()) < 4096
    assert _runtime_file_state(runtime) == before


def test_current_distinguishes_zero_multiple_and_unattested_matches(tmp_path):
    repo = git_repo(tmp_path)
    missing = ctl(
        repo,
        'current',
        '--client',
        'codex',
        '--session-id',
        'missing-session',
        '--json',
        check=False,
    )
    assert missing.returncode == 3
    assert json.loads(missing.stdout)['code'] == 'CURRENT_SESSION_NOT_FOUND'

    unattested_record = bootstrap(repo, 'session-unattested')
    unattested = ctl(
        repo,
        'current',
        '--client',
        'codex',
        '--session-id',
        'session-unattested',
        '--json',
        check=False,
    )
    assert unattested.returncode == 5
    assert json.loads(unattested.stdout)['code'] == 'CURRENT_SESSION_NOT_ATTESTED'

    attested = attest_run_start(
        repo,
        unattested_record['runId'],
        activation_source='hook:codex-app:SessionStart',
    )
    duplicate = copy.deepcopy(attested)
    duplicate['runId'] = 'run-current-duplicate'
    duplicate['changeBegin']['runId'] = duplicate['runId']
    registry = Registry(repo)
    registry.save_run(duplicate)

    ambiguous = ctl(
        repo,
        'current',
        '--client',
        'codex',
        '--session-id',
        'session-unattested',
        '--json',
        check=False,
    )
    assert ambiguous.returncode == 4
    assert json.loads(ambiguous.stdout)['code'] == 'CURRENT_SESSION_AMBIGUOUS'


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
    assert adopted["initialDirtySnapshot"]["pathStates"]["untracked.txt"] == {
        "exists": True,
        "size": 6,
        "sha256": "abe9c2071f1d073a4d40678af6637e240a01cc64637e0862ea1c441e0032910e",
    }
    assert "dirty\n" not in json.dumps(adopted["initialDirtySnapshot"])
    assert adopted["worktreeId"] != started["worktreeId"]


def test_baseline_dirty_same_path_is_planned_after_content_changes(tmp_path):
    repo = git_repo(tmp_path)
    linked = tmp_path / "baseline-dirty-checkout"
    run(["git", "worktree", "add", "--detach", str(linked), "HEAD"], cwd=repo)
    dirty = linked / "scripts" / "gates" / "baseline_case.py"
    dirty.parent.mkdir(parents=True)
    dirty.write_text("value = 1\n", encoding="utf-8")
    record = bootstrap(
        linked,
        "session-baseline-dirty",
        client="codex",
        extra=("--checkout-creator", "external"),
    )

    initial_facts = stop_evidence.collect_git_evidence(linked, record)
    initial_changed, _ = stop_evidence.filter_baseline_dirty(
        initial_facts["changedFiles"], initial_facts
    )
    assert initial_changed == []

    dirty.write_text("value = 2\n", encoding="utf-8")
    modified_facts = stop_evidence.collect_git_evidence(linked, record)
    modified_changed, _ = stop_evidence.filter_baseline_dirty(
        modified_facts["changedFiles"], modified_facts
    )

    assert modified_changed == ["scripts/gates/baseline_case.py"]
    assert "hook-runtime" in stop_evidence.required_targets(modified_changed)


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
    assert any(event.get("event") == "SESSION_CHECKOUT_REBOUND" for event in rebound["auditEvents"])
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
    assert (
        bootstrap(linked_a, "session-linked-conflict", "PreToolUse")["status"]
        == "READ_ONLY_CONFLICT"
    )


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
        (
            resolve_runtime_root(repo) / "writer-leases" / f"{requester['worktreeId']}.json"
        ).read_text(encoding="utf-8")
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


def test_random_detached_checkout_write_evidence_ignores_branch_name(tmp_path):
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
    run_evidence = (
        linked / "tmp" / "agent_logs" / "codex" / "session-cleanup" / "runs" / record["runId"]
    )
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

    cleaned = json.loads(ctl(linked, "cleanup", "--run-id", record["runId"], "--execute").stdout)
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


@pytest.mark.parametrize(
    'command',
    ('begin-change', 'adopt-current', 'completion-status', 'stop', 'finalize', 'handoff'),
)
def test_change_completion_commands_are_not_sessionctl_commands(tmp_path, command):
    repo = git_repo(tmp_path)

    result = ctl(repo, command, check=False)

    assert result.returncode == 2
    assert 'invalid choice' in result.stderr
    assert 'change.py' not in result.stdout
