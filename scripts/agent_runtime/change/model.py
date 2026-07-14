"""负责定义 Session/Change/Attempt 生命周期模型与 compare-and-set 不变量。

本模块只描述状态和纯内存变换，不负责访问 Git、进程或文件系统。由 Controller 与持久层调用，
必须通过这里执行状态更新，避免旧 Attempt 或旧进程覆盖较新的 candidate/commit 事实。
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from scripts.agent_runtime.storage import utc_now

LIFECYCLE_SCHEMA_VERSION = 3

CHANGE_STATES = frozenset(
    {
        "WORKING",
        "PREPARED",
        "VALIDATING",
        "REPAIR_REQUIRED",
        "VALIDATED",
        "COMMITTED",
        "COMMITTED_HANDOFF",
        "INTEGRATED",
        "TERMINAL_BLOCKED",
    }
)

# 这是 Change 状态的唯一合法迁移表。普通代码、formatter 或 Gate 失败必须回到可修复
# 状态；只有身份、归因或安全不变量不可证明时才允许进入 TERMINAL_BLOCKED。
ALLOWED_CHANGE_TRANSITIONS: dict[str, frozenset[str]] = {
    "WORKING": frozenset({"WORKING", "PREPARED", "TERMINAL_BLOCKED"}),
    "PREPARED": frozenset({"PREPARED", "VALIDATING", "TERMINAL_BLOCKED"}),
    "VALIDATING": frozenset({"VALIDATING", "REPAIR_REQUIRED", "VALIDATED", "TERMINAL_BLOCKED"}),
    "REPAIR_REQUIRED": frozenset({"REPAIR_REQUIRED", "PREPARED", "TERMINAL_BLOCKED"}),
    "VALIDATED": frozenset({"VALIDATED", "COMMITTED", "TERMINAL_BLOCKED"}),
    "COMMITTED": frozenset({"COMMITTED", "COMMITTED_HANDOFF", "INTEGRATED", "TERMINAL_BLOCKED"}),
    "COMMITTED_HANDOFF": frozenset({"COMMITTED_HANDOFF", "INTEGRATED", "TERMINAL_BLOCKED"}),
    "INTEGRATED": frozenset({"INTEGRATED"}),
    "TERMINAL_BLOCKED": frozenset({"TERMINAL_BLOCKED"}),
}

ATTEMPT_STATUSES = frozenset({"STARTED", "PASS", "FAIL", "BLOCKED"})
FINISHED_ATTEMPT_STATUSES = frozenset({"PASS", "FAIL", "BLOCKED"})
INTEGRATION_STATUSES = frozenset({"PENDING", "COMMITTED", "HANDOFF", "INTEGRATED"})
ALLOWED_INTEGRATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"PENDING", "COMMITTED"}),
    "COMMITTED": frozenset({"COMMITTED", "HANDOFF", "INTEGRATED"}),
    "HANDOFF": frozenset({"HANDOFF", "INTEGRATED"}),
    "INTEGRATED": frozenset({"INTEGRATED"}),
}


class LifecycleModelError(RuntimeError):
    """表示 lifecycle schema、状态迁移或单调证据不满足契约。"""


class InvalidTransitionError(LifecycleModelError):
    """表示请求的 Change 状态迁移不在权威迁移表中。"""


class CompareAndSetError(LifecycleModelError):
    """表示调用者观察的状态、版本、candidate 或 Attempt 已经过期。"""


class CommitEvidenceError(LifecycleModelError):
    """表示更新试图清空或改写已经持久化的 commit 证据。"""


@dataclass(frozen=True)
class ChangeCAS:
    """携带状态更新的四层 fencing 条件，缺少任一条件都不能写 Change。"""

    expected_state: str
    expected_version: int
    expected_candidate_tree: str
    expected_attempt_id: str


def _non_empty(value: Any, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise LifecycleModelError(f"{label} must be non-empty")
    return result


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LifecycleModelError(f"{label} must be an integer >= {minimum}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise LifecycleModelError(f"{label} must be a string")
    return value


def _require_schema(value: Mapping[str, Any], label: str) -> None:
    version = value.get("schemaVersion")
    if version != LIFECYCLE_SCHEMA_VERSION:
        raise LifecycleModelError(
            f"unsupported {label} schemaVersion: {version!r}; expected {LIFECYCLE_SCHEMA_VERSION}"
        )


def attempt_fingerprint(
    *,
    candidate_tree: str,
    manifest_hash: str,
    plan_fingerprint: str,
    command_fingerprint: str,
    environment_fingerprint: str,
) -> str:
    """对真正影响 required Gate 的完整输入生成稳定指纹。"""
    values = {
        "candidateTree": _non_empty(candidate_tree, "candidateTree"),
        "manifestHash": _non_empty(manifest_hash, "manifestHash"),
        "planFingerprint": _non_empty(plan_fingerprint, "planFingerprint"),
        "commandFingerprint": _non_empty(command_fingerprint, "commandFingerprint"),
        "environmentFingerprint": _non_empty(environment_fingerprint, "environmentFingerprint"),
    }
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def new_session(
    *,
    session_id: str,
    client: str,
    agent_id: str,
    repo_key: str,
    git_common_dir: str,
    worktree_id: str,
    checkout_root: str,
    checkout_kind: str,
    branch: str,
    detached: bool,
    target_branch: str,
    primary_repo_root: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """创建可包含多个顺序 Change 的长期 Session snapshot。"""
    timestamp = created_at or utc_now()
    session = {
        "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
        "sessionId": _non_empty(session_id, "sessionId"),
        "client": _non_empty(client, "client"),
        "agentId": _non_empty(agent_id, "agentId"),
        "repoKey": _non_empty(repo_key, "repoKey"),
        "gitCommonDir": _non_empty(git_common_dir, "gitCommonDir"),
        "worktreeId": _non_empty(worktree_id, "worktreeId"),
        "checkoutRoot": _non_empty(checkout_root, "checkoutRoot"),
        "checkoutKind": _non_empty(checkout_kind, "checkoutKind"),
        "branch": str(branch or ""),
        "detached": bool(detached),
        "targetBranch": _non_empty(target_branch, "targetBranch"),
        "primaryRepoRoot": _non_empty(primary_repo_root, "primaryRepoRoot"),
        "changeEpoch": 0,
        "currentChangeId": "",
        "changes": [],
        "auditSequence": 0,
        "attemptJournalSequence": 0,
        "createdAt": _non_empty(timestamp, "createdAt"),
        "lastSeenAt": _non_empty(timestamp, "lastSeenAt"),
    }
    validate_session(session)
    return session


def new_change(
    *,
    session_id: str,
    change_id: str,
    change_epoch: int,
    task_key: str,
    task_title: str,
    base_commit: str,
    head_observed: str,
    target_observed: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """创建一个任务专属 Change epoch；commit 证据初始为空且之后只能单调增加。"""
    timestamp = created_at or utc_now()
    change = {
        "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
        "sessionId": _non_empty(session_id, "sessionId"),
        "changeId": _non_empty(change_id, "changeId"),
        "changeEpoch": _integer(change_epoch, "changeEpoch", minimum=1),
        "taskKey": _non_empty(task_key, "taskKey"),
        "taskTitle": _non_empty(task_title, "taskTitle"),
        "baseCommit": _non_empty(base_commit, "baseCommit"),
        "headObserved": _non_empty(head_observed, "headObserved"),
        "targetObserved": _non_empty(target_observed, "targetObserved"),
        "manifestHash": "",
        "candidateTree": "",
        "currentAttemptId": "",
        "attemptSequence": 0,
        "pendingCommitIntent": {},
        "commitSha": "",
        "resultRef": "",
        "integrationStatus": "PENDING",
        "state": "WORKING",
        "stateVersion": 1,
        "createdAt": _non_empty(timestamp, "createdAt"),
        "updatedAt": _non_empty(timestamp, "updatedAt"),
    }
    validate_change(change)
    return change


def new_attempt(
    *,
    session_id: str,
    change_id: str,
    change_epoch: int,
    attempt_id: str,
    candidate_tree: str,
    manifest_hash: str,
    plan_fingerprint: str,
    command_fingerprint: str,
    environment_fingerprint: str,
    receipt_path: str,
    artifact_path: str,
    started_at: str | None = None,
    heavy_child_started: bool = True,
) -> dict[str, Any]:
    """在重 Gate child 启动前创建 Attempt，失败、超时和崩溃也因此会被计数。"""
    timestamp = started_at or utc_now()
    fingerprint = attempt_fingerprint(
        candidate_tree=candidate_tree,
        manifest_hash=manifest_hash,
        plan_fingerprint=plan_fingerprint,
        command_fingerprint=command_fingerprint,
        environment_fingerprint=environment_fingerprint,
    )
    attempt = {
        "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
        "sessionId": _non_empty(session_id, "sessionId"),
        "changeId": _non_empty(change_id, "changeId"),
        "changeEpoch": _integer(change_epoch, "changeEpoch", minimum=1),
        "attemptId": _non_empty(attempt_id, "attemptId"),
        "candidateTree": _non_empty(candidate_tree, "candidateTree"),
        "manifestHash": _non_empty(manifest_hash, "manifestHash"),
        "planFingerprint": _non_empty(plan_fingerprint, "planFingerprint"),
        "commandFingerprint": _non_empty(command_fingerprint, "commandFingerprint"),
        "environmentFingerprint": _non_empty(environment_fingerprint, "environmentFingerprint"),
        "fingerprint": fingerprint,
        "startedAt": _non_empty(timestamp, "startedAt"),
        "finishedAt": "",
        "status": "STARTED",
        "independentRootFailures": [],
        "dependentBlockedCount": 0,
        "receiptPath": _non_empty(receipt_path, "receiptPath"),
        "artifactPath": _non_empty(artifact_path, "artifactPath"),
        "heavyChildStarted": bool(heavy_child_started),
        "actualHeavyChildCount": 1 if heavy_child_started else 0,
    }
    validate_attempt(attempt)
    return attempt


def finish_attempt(
    attempt: Mapping[str, Any],
    *,
    status: str,
    independent_root_failures: Sequence[Mapping[str, Any]],
    dependent_blocked_count: int,
    finished_at: str | None = None,
    receipt_path: str | None = None,
    artifact_path: str | None = None,
) -> dict[str, Any]:
    """结束已启动 Attempt；结果一经写入不得在模型层改写。"""
    validate_attempt(attempt)
    if attempt["status"] != "STARTED":
        raise LifecycleModelError(f"attempt already finished: {attempt['attemptId']}")
    if status not in FINISHED_ATTEMPT_STATUSES:
        raise LifecycleModelError(f"invalid finished attempt status: {status}")
    result = copy.deepcopy(dict(attempt))
    result.update(
        {
            "status": status,
            "finishedAt": finished_at or utc_now(),
            "independentRootFailures": [dict(item) for item in independent_root_failures],
            "dependentBlockedCount": _integer(dependent_blocked_count, "dependentBlockedCount"),
        }
    )
    if receipt_path is not None:
        result["receiptPath"] = _non_empty(receipt_path, "receiptPath")
    if artifact_path is not None:
        result["artifactPath"] = _non_empty(artifact_path, "artifactPath")
    validate_attempt(result)
    return result


def mark_attempt_child_started(
    attempt: Mapping[str, Any], *, child_count: int = 1
) -> dict[str, Any]:
    """在 heavy child 调用前追加启动事实；Attempt 结果仍保持 STARTED。"""
    validate_attempt(attempt)
    if attempt['status'] != 'STARTED':
        raise LifecycleModelError('finished Attempt cannot start another heavy child')
    count = _integer(child_count, 'childCount', minimum=1)
    result = copy.deepcopy(dict(attempt))
    result['heavyChildStarted'] = True
    result['actualHeavyChildCount'] = int(result['actualHeavyChildCount']) + count
    validate_attempt(result)
    return result


def current_change(session: Mapping[str, Any]) -> dict[str, Any] | None:
    """按 currentChangeId 返回当前 Change，并拒绝指向不存在记录的损坏 snapshot。"""
    validate_session(session)
    change_id = session["currentChangeId"]
    if not change_id:
        return None
    for change in session["changes"]:
        if change["changeId"] == change_id:
            return copy.deepcopy(change)
    raise LifecycleModelError(f"currentChangeId has no matching change: {change_id}")


def cas_matches(change: Mapping[str, Any], expected: ChangeCAS) -> None:
    """同时校验 state/version/candidate/Attempt，拒绝部分 fencing 的写入。"""
    actual = {
        "state": change.get("state"),
        "version": change.get("stateVersion"),
        "candidateTree": change.get("candidateTree"),
        "attemptId": change.get("currentAttemptId"),
    }
    wanted = {
        "state": expected.expected_state,
        "version": expected.expected_version,
        "candidateTree": expected.expected_candidate_tree,
        "attemptId": expected.expected_attempt_id,
    }
    if actual != wanted:
        raise CompareAndSetError(
            f"stale change compare-and-set: expected={wanted}, actual={actual}"
        )


def transition_change(
    change: Mapping[str, Any],
    *,
    target_state: str,
    expected: ChangeCAS,
    updates: Mapping[str, Any] | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """执行一次带完整 CAS 的合法迁移，并保持 commit/result ref 证据单调。"""
    validate_change(change)
    cas_matches(change, expected)
    source = str(change["state"])
    if target_state not in CHANGE_STATES:
        raise InvalidTransitionError(f"unknown target Change state: {target_state}")
    if target_state not in ALLOWED_CHANGE_TRANSITIONS[source]:
        raise InvalidTransitionError(
            f"Change transition is not allowed: {source} -> {target_state}"
        )

    values = dict(updates or {})
    immutable = {"schemaVersion", "sessionId", "changeId", "changeEpoch", "createdAt"}
    forbidden = immutable.intersection(values)
    if forbidden:
        raise LifecycleModelError(f"immutable Change fields cannot be updated: {sorted(forbidden)}")

    result = copy.deepcopy(dict(change))
    old_commit = str(result.get("commitSha") or "")
    old_ref = str(result.get("resultRef") or "")
    requested_commit = str(values.get("commitSha", old_commit) or "")
    requested_ref = str(values.get("resultRef", old_ref) or "")
    if old_commit and requested_commit != old_commit:
        raise CommitEvidenceError("persisted commitSha cannot be cleared or replaced")
    if old_ref and requested_ref != old_ref:
        raise CommitEvidenceError("persisted resultRef cannot be cleared or replaced")
    result.update(values)
    result["state"] = target_state

    if result.get("candidateTree") != change.get("candidateTree") and not (
        source in {"WORKING", "REPAIR_REQUIRED"} and target_state == "PREPARED"
    ):
        raise LifecycleModelError("candidateTree can change only while preparing a candidate")
    if result.get("manifestHash") != change.get("manifestHash") and not (
        source in {"WORKING", "REPAIR_REQUIRED"} and target_state == "PREPARED"
    ):
        raise LifecycleModelError("manifestHash can change only while preparing a candidate")
    if (
        result.get("currentAttemptId") != change.get("currentAttemptId")
        and target_state != "VALIDATING"
    ):
        raise LifecycleModelError("currentAttemptId can change only when validation starts")

    if target_state in {"COMMITTED", "COMMITTED_HANDOFF", "INTEGRATED"} and not str(
        result.get("commitSha") or ""
    ):
        raise CommitEvidenceError(f"{target_state} requires commitSha")
    if target_state == "COMMITTED" and result.get("integrationStatus") == "PENDING":
        result["integrationStatus"] = "COMMITTED"
    elif target_state == "COMMITTED_HANDOFF":
        result["integrationStatus"] = "HANDOFF"
    elif target_state == "INTEGRATED":
        result["integrationStatus"] = "INTEGRATED"
    old_integration = str(change["integrationStatus"])
    new_integration = str(result["integrationStatus"])
    if new_integration not in ALLOWED_INTEGRATION_TRANSITIONS[old_integration]:
        raise CommitEvidenceError(
            f"integrationStatus cannot move backward: {old_integration} -> {new_integration}"
        )

    changed = result != dict(change)
    if changed:
        result["stateVersion"] = int(change["stateVersion"]) + 1
        result["updatedAt"] = updated_at or utc_now()
    validate_change(result)
    return result


def replace_change(session: Mapping[str, Any], replacement: Mapping[str, Any]) -> dict[str, Any]:
    """以 changeId 精确替换 Session 内记录，不允许隐式新增或重排 epoch。"""
    validate_session(session)
    validate_change(replacement)
    result = copy.deepcopy(dict(session))
    found = False
    for index, item in enumerate(result["changes"]):
        if item["changeId"] == replacement["changeId"]:
            if item["changeEpoch"] != replacement["changeEpoch"]:
                raise LifecycleModelError("replacement changeEpoch does not match existing Change")
            result["changes"][index] = copy.deepcopy(dict(replacement))
            found = True
            break
    if not found:
        raise LifecycleModelError(f"unknown changeId: {replacement['changeId']}")
    result["lastSeenAt"] = replacement["updatedAt"]
    validate_session(result)
    return result


def roll_next_change(
    session: Mapping[str, Any],
    *,
    change_id: str,
    task_key: str,
    task_title: str,
    base_commit: str,
    head_observed: str,
    target_observed: str,
    worktree_clean: bool,
    expected_current_change_id: str,
    expected_current_version: int,
    allow_dirty_roll: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    """上一 Change 已集成后递增 epoch；dirty 自愈必须由 controller 显式授权。"""
    validate_session(session)
    if not worktree_clean and not allow_dirty_roll:
        raise InvalidTransitionError("next Change requires a clean worktree")
    result = copy.deepcopy(dict(session))
    active = current_change(result)
    if active is None:
        if expected_current_change_id or expected_current_version != 0:
            raise CompareAndSetError("initial Change compare-and-set is stale")
    else:
        if (
            active["changeId"] != expected_current_change_id
            or active["stateVersion"] != expected_current_version
        ):
            raise CompareAndSetError("next Change compare-and-set is stale")
        if active["state"] != "INTEGRATED":
            raise InvalidTransitionError(f"cannot create next Change from state {active['state']}")

    if any(item["changeId"] == change_id for item in result["changes"]):
        raise LifecycleModelError(f"duplicate changeId: {change_id}")
    epoch = int(result["changeEpoch"]) + 1
    change = new_change(
        session_id=result["sessionId"],
        change_id=change_id,
        change_epoch=epoch,
        task_key=task_key,
        task_title=task_title,
        base_commit=base_commit,
        head_observed=head_observed,
        target_observed=target_observed,
        created_at=created_at,
    )
    result["changes"].append(change)
    result["changeEpoch"] = epoch
    result["currentChangeId"] = change["changeId"]
    result["lastSeenAt"] = change["createdAt"]
    validate_session(result)
    return result


def validate_change(change: Mapping[str, Any]) -> None:
    """关闭失败地验证 Change schema、epoch、状态和 commit 单调前置条件。"""
    if not isinstance(change, Mapping):
        raise LifecycleModelError("Change must be a mapping")
    _require_schema(change, "Change")
    for key in (
        "sessionId",
        "changeId",
        "taskKey",
        "taskTitle",
        "baseCommit",
        "headObserved",
        "targetObserved",
        "state",
        "createdAt",
        "updatedAt",
    ):
        _non_empty(change.get(key), f"Change.{key}")
    for key in (
        "manifestHash",
        "candidateTree",
        "currentAttemptId",
        "commitSha",
        "resultRef",
    ):
        _string(change.get(key), f"Change.{key}")
    _integer(change.get("changeEpoch"), "Change.changeEpoch", minimum=1)
    _integer(change.get("attemptSequence"), "Change.attemptSequence")
    _integer(change.get("stateVersion"), "Change.stateVersion", minimum=1)
    state = change.get("state")
    if state not in CHANGE_STATES:
        raise LifecycleModelError(f"invalid Change state: {state!r}")
    integration = change.get("integrationStatus")
    if integration not in INTEGRATION_STATUSES:
        raise LifecycleModelError(f"invalid integrationStatus: {integration!r}")
    if not isinstance(change.get("pendingCommitIntent"), Mapping):
        raise LifecycleModelError("Change.pendingCommitIntent must be a mapping")
    if state in {"COMMITTED", "COMMITTED_HANDOFF", "INTEGRATED"} and not change.get("commitSha"):
        raise LifecycleModelError(f"{state} Change must retain commitSha")


def validate_attempt(attempt: Mapping[str, Any]) -> None:
    """验证 Attempt 完整指纹、结果分类和重 Gate child 计数。"""
    if not isinstance(attempt, Mapping):
        raise LifecycleModelError("Attempt must be a mapping")
    _require_schema(attempt, "Attempt")
    for key in (
        "sessionId",
        "changeId",
        "attemptId",
        "candidateTree",
        "manifestHash",
        "planFingerprint",
        "commandFingerprint",
        "environmentFingerprint",
        "fingerprint",
        "startedAt",
        "receiptPath",
        "artifactPath",
    ):
        _non_empty(attempt.get(key), f"Attempt.{key}")
    _integer(attempt.get("changeEpoch"), "Attempt.changeEpoch", minimum=1)
    _integer(attempt.get("dependentBlockedCount"), "Attempt.dependentBlockedCount")
    _integer(attempt.get("actualHeavyChildCount"), "Attempt.actualHeavyChildCount")
    if not isinstance(attempt.get("heavyChildStarted"), bool):
        raise LifecycleModelError("Attempt.heavyChildStarted must be bool")
    if bool(attempt['actualHeavyChildCount']) != attempt['heavyChildStarted']:
        raise LifecycleModelError("Attempt heavy child count does not match start evidence")
    if not isinstance(attempt.get("independentRootFailures"), list) or any(
        not isinstance(item, Mapping) for item in attempt["independentRootFailures"]
    ):
        raise LifecycleModelError("Attempt.independentRootFailures must contain mappings")
    status = attempt.get("status")
    if status not in ATTEMPT_STATUSES:
        raise LifecycleModelError(f"invalid Attempt status: {status!r}")
    finished_at = _string(attempt.get("finishedAt"), "Attempt.finishedAt")
    if status == "STARTED" and finished_at:
        raise LifecycleModelError("STARTED Attempt cannot have finishedAt")
    if status in FINISHED_ATTEMPT_STATUSES and not finished_at:
        raise LifecycleModelError(f"{status} Attempt requires finishedAt")
    expected = attempt_fingerprint(
        candidate_tree=attempt["candidateTree"],
        manifest_hash=attempt["manifestHash"],
        plan_fingerprint=attempt["planFingerprint"],
        command_fingerprint=attempt["commandFingerprint"],
        environment_fingerprint=attempt["environmentFingerprint"],
    )
    if attempt["fingerprint"] != expected:
        raise LifecycleModelError("Attempt fingerprint does not match its input fields")


def validate_session(session: Mapping[str, Any]) -> None:
    """验证 Session identity、Change 顺序和 currentChangeId 指针。"""
    if not isinstance(session, Mapping):
        raise LifecycleModelError("Session must be a mapping")
    _require_schema(session, "Session")
    for key in (
        "sessionId",
        "client",
        "agentId",
        "repoKey",
        "gitCommonDir",
        "worktreeId",
        "checkoutRoot",
        "checkoutKind",
        "targetBranch",
        "primaryRepoRoot",
        "createdAt",
        "lastSeenAt",
    ):
        _non_empty(session.get(key), f"Session.{key}")
    _string(session.get("branch"), "Session.branch")
    _string(session.get("currentChangeId"), "Session.currentChangeId")
    if not isinstance(session.get("detached"), bool):
        raise LifecycleModelError("Session.detached must be bool")
    epoch = _integer(session.get("changeEpoch"), "Session.changeEpoch")
    _integer(session.get("auditSequence"), "Session.auditSequence")
    _integer(session.get("attemptJournalSequence"), "Session.attemptJournalSequence")
    changes = session.get("changes")
    if not isinstance(changes, list):
        raise LifecycleModelError("Session.changes must be a list")
    identifiers: set[str] = set()
    previous_epoch = 0
    for change in changes:
        validate_change(change)
        if change["sessionId"] != session["sessionId"]:
            raise LifecycleModelError("Change belongs to a different Session")
        if change["changeId"] in identifiers:
            raise LifecycleModelError(f"duplicate Change id: {change['changeId']}")
        if change["changeEpoch"] != previous_epoch + 1:
            raise LifecycleModelError("Change epochs must be contiguous and monotonic")
        identifiers.add(change["changeId"])
        previous_epoch = change["changeEpoch"]
    if epoch != previous_epoch:
        raise LifecycleModelError("Session.changeEpoch does not match its Change history")
    current = session["currentChangeId"]
    if changes and current != changes[-1]["changeId"]:
        raise LifecycleModelError("currentChangeId must point to the latest Change")
    if not changes and current:
        raise LifecycleModelError("empty Session cannot have currentChangeId")
