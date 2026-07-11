# `sessionctl` worktree lifecycle

`scripts/harness/sessionctl.py` manages local primary-agent run records and Git worktrees without starting real Qoder/Codex network sessions by default.

## Minimal lifecycle

```bash
python3 scripts/harness/sessionctl.py create --client codex --task-id task-a --change-id change-a --base-ref main_java --allowed-path 'docs/a'
python3 scripts/harness/sessionctl.py start --run-id <run-id> --print-command
python3 scripts/harness/sessionctl.py bind-session --run-id <run-id> --session-id <client-session-id> --client codex --cwd <worktree-root>
python3 scripts/harness/sessionctl.py status --run-id <run-id>
python3 scripts/harness/sessionctl.py handoff --run-id <run-id>
python3 scripts/harness/sessionctl.py cleanup --run-id <run-id>          # dry-run by default
```

## Safety contract

- `create` writes records under the shared `FEIPI_AGENT_RUNTIME_ROOT` or `git-common-dir/feipi-agent-runtime` registry with a cross-process lock and atomic JSON replace.
- Writable runs get unique `runId`, `worktreeId`, branch, worktree root, base commit, writer lease, allowed paths, and forbidden paths.
- Same branch, same worktree writer, and overlapping writable scope conflicts are blocked before the run record is committed.
- `start --print-command` only prints safe environment variables and a command template; real clients require `--client-command` or `FEIPI_SESSIONCTL_<CLIENT>_COMMAND`.
- `bind-session` verifies `cwd` realpath, branch, base commit, client, and active session identity before marking hook activation confirmed.
- `cleanup` is dry-run by default, refuses dirty worktrees, does not force remove, and does not delete branches unless explicitly requested.


## Runtime capability

`sessionctl doctor` reports `writable-ready`, `read-only-ready`, `blocked`, or `legacy-single-writer`; required gates must not collapse these states into a generic PASS. Hook activation marker deletion, config hash drift, or duplicate active writer leases are blocking conditions.

## Rollout modes and defaults

`sessionctl create/start` is the only path that creates a `managed-worktree` run. The printed start command always includes `FEIPI_PRIMARY_SESSION_MODE=managed-worktree`, `FEIPI_RUN_ID`, `FEIPI_TASK_ID`, `FEIPI_WORKTREE_ID`, and the shared runtime root; users do not need to remember these variables for the safe default.

Direct Qoder/Codex launches without a bound run are `read-only-unbound`: they may inspect files, but mutating hooks block until `sessionctl bind-session` proves the run id, client session id, worktree root, branch, base commit, writer lease, OpenSpec change id, and hook activation marker.

`legacy-single-writer` is an explicit compatibility mode only (`FEIPI_PRIMARY_SESSION_MODE=legacy-single-writer` or `FEIPI_LEGACY_SINGLE_WRITER=1`). It emits a persistent warning, is not multi-primary writable, and blocks when any active managed writable run exists. `blocked` is used for unsafe states such as hook activation drift, mismatched session/worktree/branch, writer lease conflicts, invalid change id, registry corruption, resource lock timeout, Stop report write failure, or dirty cleanup.

## Handoff contract

`sessionctl handoff` is reporting-only and never commits, pushes, merges, deletes branches, or removes worktrees. Its JSON includes run/task/client/session, worktree/branch/base commit, changed files, OpenSpec change, required target summary, artifact paths, blocking failures, merge/write-scope overlap risk, and manual next steps.

## Rollback dry-run

Safe rollback is intentionally non-destructive:

1. Stop managed runs with `sessionctl stop --run-id <run-id>` or by ending the client session; keep the worktree and branch for review.
2. Run `sessionctl cleanup --run-id <run-id>` first. This is a dry-run and reports actions without deleting anything.
3. Only after manual review, use `--execute`; cleanup still refuses dirty worktrees and does not delete branches unless `--delete-branch` is explicitly supplied.
4. To disable project hooks while keeping direct launches read-only, remove or disable the project hook binding outside the repo policy and do not set legacy writer mode.
5. To return to legacy single-writer, set `FEIPI_PRIMARY_SESSION_MODE=legacy-single-writer` for the one checkout writer after all managed writable runs are stopped or cleaned.
6. Restore a registry backup by copying it back to `FEIPI_AGENT_RUNTIME_ROOT` or `git-common-dir/feipi-agent-runtime`; never recover by deleting user worktree changes.

Legacy `tmp/agent_logs` data remains readable. New managed runs write run-scoped evidence under `tmp/agent_logs/<client>/<session>/runs/<run-id>/...`; no migration or deletion of old logs is performed automatically.
