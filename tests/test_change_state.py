from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING

import pytest
import scripts.agent_runtime.change.store as store_module

if TYPE_CHECKING:
    from pathlib import Path
from scripts.agent_runtime.change.model import (
    ALLOWED_CHANGE_TRANSITIONS,
    CHANGE_STATES,
    LIFECYCLE_SCHEMA_VERSION,
    ChangeCAS,
    CommitEvidenceError,
    CompareAndSetError,
    InvalidTransitionError,
    LifecycleModelError,
    attempt_fingerprint,
    current_change,
    new_attempt,
    new_change,
    new_session,
    roll_next_change,
    transition_change,
    validate_attempt,
    validate_session,
)
from scripts.agent_runtime.change.store import (
    ChangeStore,
    ChangeStoreCorruptionError,
    DuplicateAttemptError,
)


def _session(session_id: str = "session-1") -> dict:
    return new_session(
        session_id=session_id,
        client="codex",
        agent_id="agent-main",
        repo_key="repo-key",
        git_common_dir="/repo/.git",
        worktree_id="checkout-1",
        checkout_root="/repo/wt",
        checkout_kind="linked-worktree",
        branch="",
        detached=True,
        target_branch="main_java",
        primary_repo_root="/repo",
        created_at="2026-07-15T00:00:00Z",
    )


def _first_change(session: dict, *, change_id: str = "change-1") -> dict:
    return roll_next_change(
        session,
        change_id=change_id,
        task_key=change_id,
        task_title="稳定生命周期",
        base_commit="a" * 40,
        head_observed="a" * 40,
        target_observed="a" * 40,
        worktree_clean=True,
        expected_current_change_id="",
        expected_current_version=0,
        created_at="2026-07-15T00:00:01Z",
    )


def _change_in_state(state: str) -> dict:
    change = new_change(
        session_id="session-1",
        change_id="change-1",
        change_epoch=1,
        task_key="task",
        task_title="任务",
        base_commit="a" * 40,
        head_observed="a" * 40,
        target_observed="a" * 40,
        created_at="2026-07-15T00:00:00Z",
    )
    change["state"] = state
    change["stateVersion"] = 7
    if state in {"COMMITTED", "COMMITTED_HANDOFF", "INTEGRATED"}:
        change["commitSha"] = "b" * 40
        change["integrationStatus"] = {
            "COMMITTED": "COMMITTED",
            "COMMITTED_HANDOFF": "HANDOFF",
            "INTEGRATED": "INTEGRATED",
        }[state]
    return change


@pytest.mark.parametrize(
    ("source", "target"),
    [(source, target) for source in sorted(CHANGE_STATES) for target in sorted(CHANGE_STATES)],
)
def test_change_transition_table_is_enforced(source: str, target: str) -> None:
    change = _change_in_state(source)
    updates = {"commitSha": "b" * 40} if target == "COMMITTED" else {}
    expected = ChangeCAS(source, 7, "", "")
    allowed = source == target or target in ALLOWED_CHANGE_TRANSITIONS[source]

    if allowed:
        result = transition_change(
            change,
            target_state=target,
            expected=expected,
            updates=updates,
            updated_at="2026-07-15T00:01:00Z",
        )
        assert result["state"] == target
    else:
        with pytest.raises(InvalidTransitionError):
            transition_change(change, target_state=target, expected=expected, updates=updates)


@pytest.mark.parametrize(
    "expected",
    [
        ChangeCAS("PREPARED", 1, "tree-1", "attempt-1"),
        ChangeCAS("WORKING", 2, "tree-1", "attempt-1"),
        ChangeCAS("WORKING", 1, "tree-old", "attempt-1"),
        ChangeCAS("WORKING", 1, "tree-1", "attempt-old"),
    ],
)
def test_stale_state_version_candidate_and_attempt_are_rejected(expected: ChangeCAS) -> None:
    change = _change_in_state("WORKING")
    change.update(stateVersion=1, candidateTree="tree-1", currentAttemptId="attempt-1")
    with pytest.raises(CompareAndSetError):
        transition_change(change, target_state="PREPARED", expected=expected)


def test_commit_evidence_is_monotonic_after_commit() -> None:
    committed = _change_in_state("COMMITTED")
    expected = ChangeCAS("COMMITTED", 7, "", "")
    with pytest.raises(CommitEvidenceError):
        transition_change(
            committed,
            target_state="COMMITTED_HANDOFF",
            expected=expected,
            updates={"commitSha": ""},
        )
    with pytest.raises(CommitEvidenceError):
        transition_change(
            committed,
            target_state="COMMITTED_HANDOFF",
            expected=expected,
            updates={"commitSha": "c" * 40},
        )

    handoff = transition_change(committed, target_state="COMMITTED_HANDOFF", expected=expected)
    assert handoff["commitSha"] == "b" * 40
    assert handoff["integrationStatus"] == "HANDOFF"

    with pytest.raises(CommitEvidenceError, match="cannot move backward"):
        transition_change(
            handoff,
            target_state="TERMINAL_BLOCKED",
            expected=ChangeCAS("COMMITTED_HANDOFF", handoff["stateVersion"], "", ""),
            updates={"integrationStatus": "COMMITTED"},
        )


def test_validated_candidate_cannot_be_rewritten_in_place() -> None:
    validated = _change_in_state("VALIDATED")
    validated["candidateTree"] = "tree-1"
    validated["manifestHash"] = "manifest-1"
    with pytest.raises(LifecycleModelError, match="candidateTree"):
        transition_change(
            validated,
            target_state="VALIDATED",
            expected=ChangeCAS("VALIDATED", 7, "tree-1", ""),
            updates={"candidateTree": "tree-2"},
        )


def test_next_change_keeps_session_and_increments_epoch() -> None:
    first = _first_change(_session())
    active = current_change(first)
    active.update(
        state="INTEGRATED",
        stateVersion=9,
        commitSha="b" * 40,
        integrationStatus="INTEGRATED",
    )
    first["changes"][0] = active
    second = roll_next_change(
        first,
        change_id="change-2",
        task_key="task-2",
        task_title="连续任务",
        base_commit="b" * 40,
        head_observed="b" * 40,
        target_observed="b" * 40,
        worktree_clean=True,
        expected_current_change_id="change-1",
        expected_current_version=9,
    )
    assert second["sessionId"] == first["sessionId"]
    assert second["changeEpoch"] == 2
    assert [item["changeEpoch"] for item in second["changes"]] == [1, 2]
    assert current_change(second)["state"] == "WORKING"


@pytest.mark.parametrize("state", ["REPAIR_REQUIRED", "COMMITTED_HANDOFF"])
def test_next_change_is_forbidden_for_non_integrated_current_change(state: str) -> None:
    session = _first_change(_session())
    active = current_change(session)
    active["state"] = state
    active["stateVersion"] = 3
    if state == "COMMITTED_HANDOFF":
        active["commitSha"] = "b" * 40
        active["integrationStatus"] = "HANDOFF"
    session["changes"][0] = active
    with pytest.raises(InvalidTransitionError):
        roll_next_change(
            session,
            change_id="change-2",
            task_key="task-2",
            task_title="不应轮转",
            base_commit="b" * 40,
            head_observed="b" * 40,
            target_observed="b" * 40,
            worktree_clean=True,
            expected_current_change_id="change-1",
            expected_current_version=3,
        )


def test_schema_and_attempt_fingerprint_reject_unknown_or_tampered_data() -> None:
    session = _session()
    session["schemaVersion"] = LIFECYCLE_SCHEMA_VERSION + 1
    with pytest.raises(LifecycleModelError, match="unsupported Session schemaVersion"):
        validate_session(session)

    attempt = new_attempt(
        session_id="session-1",
        change_id="change-1",
        change_epoch=1,
        attempt_id="attempt-1-0001",
        candidate_tree="tree-1",
        manifest_hash="manifest-1",
        plan_fingerprint="plan-1",
        command_fingerprint="command-1",
        environment_fingerprint="environment-1",
        receipt_path="/runtime/receipt.json",
        artifact_path="/runtime/artifact.json",
    )
    assert attempt["fingerprint"] == attempt_fingerprint(
        candidate_tree="tree-1",
        manifest_hash="manifest-1",
        plan_fingerprint="plan-1",
        command_fingerprint="command-1",
        environment_fingerprint="environment-1",
    )
    attempt["candidateTree"] = "tampered"
    with pytest.raises(LifecycleModelError, match="fingerprint"):
        validate_attempt(attempt)


def _store_with_change(tmp_path: Path) -> tuple[ChangeStore, dict]:
    store = ChangeStore(tmp_path / "runtime")
    created = store.create_session(_session())
    session = store.roll_next_change(
        created["sessionId"],
        change_id="change-1",
        task_key="task-1",
        task_title="持久化测试",
        base_commit="a" * 40,
        head_observed="a" * 40,
        target_observed="a" * 40,
        worktree_clean=True,
        expected_current_change_id="",
        expected_current_version=0,
        created_at="2026-07-15T00:00:01Z",
    )
    return store, session


def _prepare(store: ChangeStore, session: dict) -> dict:
    change = current_change(session)
    return store.transition(
        session["sessionId"],
        change["changeId"],
        target_state="PREPARED",
        expected=ChangeCAS("WORKING", 1, "", ""),
        updates={"candidateTree": "tree-1", "manifestHash": "manifest-1"},
    )


def test_store_create_is_idempotent_and_cas_appends_audit(tmp_path: Path) -> None:
    store = ChangeStore(tmp_path / "runtime")
    original = _session()
    first = store.create_session(original)
    repeated_start = _session()
    repeated_start["createdAt"] = repeated_start["lastSeenAt"] = "2026-07-15T00:30:00Z"
    second = store.create_session(repeated_start)
    assert first == second
    assert first["auditSequence"] == 1
    assert len(list((tmp_path / "runtime/sessions/session-1/audit").glob("*.json"))) == 1

    rolled = store.roll_next_change(
        "session-1",
        change_id="change-1",
        task_key="task-1",
        task_title="任务",
        base_commit="a" * 40,
        head_observed="a" * 40,
        target_observed="a" * 40,
        worktree_clean=True,
        expected_current_change_id="",
        expected_current_version=0,
    )
    prepared = _prepare(store, rolled)
    assert current_change(prepared)["stateVersion"] == 2
    assert store.load_session("session-1") == prepared
    assert len(list((tmp_path / "runtime/sessions/session-1/audit").glob("*.json"))) == 3


def test_store_attempt_journal_caches_fingerprint_and_counts_failed_child(
    tmp_path: Path,
) -> None:
    store, session = _store_with_change(tmp_path)
    prepared = _prepare(store, session)
    change = current_change(prepared)
    validating, started = store.start_attempt(
        "session-1",
        "change-1",
        expected=ChangeCAS("PREPARED", change["stateVersion"], "tree-1", ""),
        candidate_tree="tree-1",
        manifest_hash="manifest-1",
        plan_fingerprint="plan-1",
        command_fingerprint="command-1",
        environment_fingerprint="environment-1",
        receipt_path="/runtime/receipt-1.json",
        artifact_path="/runtime/artifact-1.json",
    )
    current = current_change(validating)
    repaired, failed = store.finish_attempt(
        "session-1",
        "change-1",
        started["attemptId"],
        expected=ChangeCAS("VALIDATING", current["stateVersion"], "tree-1", started["attemptId"]),
        status="FAIL",
        independent_root_failures=[{"code": "SPOTLESS", "path": "A.java", "line": 3}],
        dependent_blocked_count=12,
    )
    assert failed["status"] == "FAIL"
    assert current_change(repaired)["state"] == "REPAIR_REQUIRED"
    assert (
        store.find_attempt_by_fingerprint("session-1", "change-1", started["fingerprint"]) == failed
    )
    assert store.attempt_metrics("session-1") == {
        "uniqueHeavyAttempts": 1,
        "actualHeavyChildren": 1,
        "passedAttempts": 0,
        "failedAttempts": 1,
        "blockedAttempts": 0,
        "unfinishedAttempts": 0,
    }

    repair_change = current_change(repaired)
    prepared_again = store.transition(
        "session-1",
        "change-1",
        target_state="PREPARED",
        expected=ChangeCAS(
            "REPAIR_REQUIRED",
            repair_change["stateVersion"],
            "tree-1",
            started["attemptId"],
        ),
    )
    next_change = current_change(prepared_again)
    with pytest.raises(DuplicateAttemptError) as duplicate:
        store.start_attempt(
            "session-1",
            "change-1",
            expected=ChangeCAS(
                "PREPARED",
                next_change["stateVersion"],
                "tree-1",
                started["attemptId"],
            ),
            candidate_tree="tree-1",
            manifest_hash="manifest-1",
            plan_fingerprint="plan-1",
            command_fingerprint="command-1",
            environment_fingerprint="environment-1",
            receipt_path="/runtime/receipt-duplicate.json",
            artifact_path="/runtime/artifact-duplicate.json",
        )
    assert duplicate.value.attempt["status"] == "FAIL"
    assert store.attempt_metrics("session-1")["actualHeavyChildren"] == 1


def test_changed_environment_allows_new_attempt_and_old_attempt_cannot_finish_it(
    tmp_path: Path,
) -> None:
    store, session = _store_with_change(tmp_path)
    prepared = _prepare(store, session)
    change = current_change(prepared)
    validating, first = store.start_attempt(
        "session-1",
        "change-1",
        expected=ChangeCAS("PREPARED", change["stateVersion"], "tree-1", ""),
        candidate_tree="tree-1",
        manifest_hash="manifest-1",
        plan_fingerprint="plan-1",
        command_fingerprint="command-1",
        environment_fingerprint="environment-1",
        receipt_path="/runtime/r1.json",
        artifact_path="/runtime/a1.json",
    )
    change = current_change(validating)
    repaired, _ = store.finish_attempt(
        "session-1",
        "change-1",
        first["attemptId"],
        expected=ChangeCAS("VALIDATING", change["stateVersion"], "tree-1", first["attemptId"]),
        status="BLOCKED",
        independent_root_failures=[{"code": "CAPABILITY"}],
        dependent_blocked_count=0,
    )
    change = current_change(repaired)
    prepared = store.transition(
        "session-1",
        "change-1",
        target_state="PREPARED",
        expected=ChangeCAS("REPAIR_REQUIRED", change["stateVersion"], "tree-1", first["attemptId"]),
    )
    change = current_change(prepared)
    validating, second = store.start_attempt(
        "session-1",
        "change-1",
        expected=ChangeCAS("PREPARED", change["stateVersion"], "tree-1", first["attemptId"]),
        candidate_tree="tree-1",
        manifest_hash="manifest-1",
        plan_fingerprint="plan-1",
        command_fingerprint="command-1",
        environment_fingerprint="environment-2",
        receipt_path="/runtime/r2.json",
        artifact_path="/runtime/a2.json",
    )
    assert second["attemptId"] != first["attemptId"]
    assert second["fingerprint"] != first["fingerprint"]
    change = current_change(validating)
    with pytest.raises(CompareAndSetError):
        store.finish_attempt(
            "session-1",
            "change-1",
            first["attemptId"],
            expected=ChangeCAS("VALIDATING", change["stateVersion"], "tree-1", first["attemptId"]),
            status="FAIL",
            independent_root_failures=[{"code": "OLD"}],
            dependent_blocked_count=0,
        )
    assert store.attempt_metrics("session-1")["actualHeavyChildren"] == 2


def test_pass_attempt_receipt_is_reused_without_another_heavy_child(tmp_path: Path) -> None:
    store, session = _store_with_change(tmp_path)
    prepared = _prepare(store, session)
    change = current_change(prepared)
    validating, started = store.start_attempt(
        "session-1",
        "change-1",
        expected=ChangeCAS("PREPARED", change["stateVersion"], "tree-1", ""),
        candidate_tree="tree-1",
        manifest_hash="manifest-1",
        plan_fingerprint="plan-1",
        command_fingerprint="command-1",
        environment_fingerprint="environment-1",
        receipt_path="/runtime/pass.json",
        artifact_path="/runtime/pass-artifact.json",
    )
    change = current_change(validating)
    validated, passed = store.finish_attempt(
        "session-1",
        "change-1",
        started["attemptId"],
        expected=ChangeCAS("VALIDATING", change["stateVersion"], "tree-1", started["attemptId"]),
        status="PASS",
        independent_root_failures=[],
        dependent_blocked_count=0,
    )
    assert current_change(validated)["state"] == "VALIDATED"
    assert passed["status"] == "PASS"
    with pytest.raises(DuplicateAttemptError) as cached:
        store.start_attempt(
            "session-1",
            "change-1",
            expected=ChangeCAS(
                "VALIDATED",
                current_change(validated)["stateVersion"],
                "tree-1",
                started["attemptId"],
            ),
            candidate_tree="tree-1",
            manifest_hash="manifest-1",
            plan_fingerprint="plan-1",
            command_fingerprint="command-1",
            environment_fingerprint="environment-1",
            receipt_path="/runtime/should-not-run.json",
            artifact_path="/runtime/should-not-run-artifact.json",
        )
    assert cached.value.attempt["status"] == "PASS"
    assert store.attempt_metrics("session-1")["actualHeavyChildren"] == 1


def test_store_replays_append_only_audit_when_snapshot_is_stale(tmp_path: Path) -> None:
    store, session = _store_with_change(tmp_path)
    snapshot_path = tmp_path / "runtime/sessions/session-1/snapshot.json"
    stale = copy.deepcopy(session)
    prepared = _prepare(store, session)
    snapshot_path.write_text(json.dumps(stale), encoding="utf-8")
    recovered = store.load_session("session-1")
    assert recovered == prepared
    assert current_change(recovered)["state"] == "PREPARED"


@pytest.mark.parametrize("payload", ["{broken", '{"schemaVersion":999}'])
def test_store_rejects_corrupt_or_unknown_snapshot(tmp_path: Path, payload: str) -> None:
    store, _ = _store_with_change(tmp_path)
    snapshot_path = tmp_path / "runtime/sessions/session-1/snapshot.json"
    snapshot_path.write_text(payload, encoding="utf-8")
    with pytest.raises(ChangeStoreCorruptionError):
        store.load_session("session-1")


def test_store_rejects_unknown_attempt_journal_schema(tmp_path: Path) -> None:
    store, session = _store_with_change(tmp_path)
    prepared = _prepare(store, session)
    change = current_change(prepared)
    store.start_attempt(
        "session-1",
        "change-1",
        expected=ChangeCAS("PREPARED", change["stateVersion"], "tree-1", ""),
        candidate_tree="tree-1",
        manifest_hash="manifest-1",
        plan_fingerprint="plan-1",
        command_fingerprint="command-1",
        environment_fingerprint="environment-1",
        receipt_path="/runtime/r.json",
        artifact_path="/runtime/a.json",
    )
    event_path = next((tmp_path / "runtime/sessions/session-1/attempt-journal").glob("*.json"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["schemaVersion"] = 999
    event_path.write_text(json.dumps(event), encoding="utf-8")
    with pytest.raises(ChangeStoreCorruptionError, match="unsupported lifecycle schemaVersion"):
        store.list_attempts("session-1")


def test_journal_publish_failure_never_exposes_half_written_final_json(
    tmp_path: Path, monkeypatch
) -> None:
    store, session = _store_with_change(tmp_path)
    audit_dir = tmp_path / 'runtime/sessions/session-1/audit'
    before = sorted(audit_dir.glob('*.json'))

    def fail_link(*_args, **_kwargs):
        raise OSError('injected atomic publish failure')

    monkeypatch.setattr(store_module.os, 'link', fail_link)
    with pytest.raises(OSError, match='atomic publish failure'):
        _prepare(store, session)

    assert sorted(audit_dir.glob('*.json')) == before
    assert list(audit_dir.glob('*.tmp')) == []
    assert current_change(store.load_session('session-1'))['state'] == 'WORKING'


def test_attempt_child_count_is_recorded_only_when_child_start_event_is_appended(
    tmp_path: Path,
) -> None:
    store, session = _store_with_change(tmp_path)
    prepared = _prepare(store, session)
    change = current_change(prepared)
    validating, attempt = store.start_attempt(
        'session-1',
        'change-1',
        expected=ChangeCAS('PREPARED', change['stateVersion'], 'tree-1', ''),
        candidate_tree='tree-1',
        manifest_hash='manifest-1',
        plan_fingerprint='plan-1',
        command_fingerprint='command-1',
        environment_fingerprint='environment-1',
        receipt_path='/runtime/r.json',
        artifact_path='/runtime/a.json',
        heavy_child_started=False,
    )
    assert store.attempt_metrics('session-1')['actualHeavyChildren'] == 0
    active = current_change(validating)
    _session_after, marked = store.mark_attempt_child_started(
        'session-1',
        'change-1',
        attempt['attemptId'],
        expected=ChangeCAS('VALIDATING', active['stateVersion'], 'tree-1', attempt['attemptId']),
    )
    assert marked['actualHeavyChildCount'] == 1
    assert store.attempt_metrics('session-1')['actualHeavyChildren'] == 1
