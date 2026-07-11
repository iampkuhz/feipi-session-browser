# Agent Runtime

`feipi-session-browser` now has one hook/runtime authority.

## Authoritative files

| Responsibility | Authority |
|---|---|
| Machine policy | `harness/agent-runtime.manifest.yaml` |
| User/maintenance docs | `docs/agent-runtime.md` |
| Run record + authorization library | `scripts/harness/primary_session.py` |
| Runtime CLI/finalize/recovery/cleanup | `scripts/harness/sessionctl.py` |
| Thin launcher | `scripts/agent-session` |
| Stop production entry | `scripts/harness/stop_entry.py` |
| Stop helper functions | `scripts/harness/stop_helpers.py` |
| Changed-file truth | assigned worktree Git `base...HEAD + dirty + untracked` |
| Quality target/gate mapping | `scripts/quality/quality_targets.py` |
| Shared shell hook helpers | `scripts/harness/hook-common.sh` |

Platform directories only keep thin wrappers under `.claude/hooks/`, `.codex/hooks/`, and `.qoder/hooks/`. Wrappers set strict shell options, parse stdin once when Stop needs root resolution, set `FEIPI_AGENT_CLIENT`, and `exec` the shared Python entry.

## Managed run model

Writable work requires a `runId` record stored under `<git-common-dir>/feipi-agent-runtime/runs/`. A run record includes `client`, `taskId`, `sessionId`, `worktreeId`, `worktreeRoot`, `branch`, `targetBranch`, `primaryRepoRoot`, `baseCommit`, `headCommit`, `changeId`, `mode`, `status`, path scopes, writer lease, hook activation, and process metadata.

Daily legacy write authorization is removed. `sessionctl recover-legacy` may read old marker/worktree data once and write a new run record; it does not continue the old runtime.

## Commands

```bash
./scripts/agent-session create --client codex --task-id task-a --change-id converge-agent-hook-runtime --base-ref main_java --allowed-path scripts
./scripts/agent-session start --run-id <run-id> --print-command
./scripts/agent-session bind-session --run-id <run-id> --session-id <real-session> --client codex --cwd <worktree>
./scripts/agent-session stop --run-id <run-id>
./scripts/agent-session finalize --run-id <run-id>
./scripts/agent-session recover-legacy --client codex --session <old-session> --target main_java --change-id <change> --worktree-root <old-worktree>
./scripts/agent-session cleanup --run-id <run-id>              # dry-run by default
./scripts/agent-session cleanup --run-id <run-id> --execute
```

`start` can also create a run in one command when `--run-id` is omitted and `--client --task-id --change-id` are supplied.

## State machine

Normal states:

```text
CREATED -> STARTING -> RUNNING -> VALIDATING -> VALIDATED -> COMMITTED -> INTEGRATING -> INTEGRATED -> CLEANED
```

Exception states: `BLOCKED`, `HANDOFF_REQUIRED`, `FAILED`.

Stop can only validate a run (`VALIDATED`). A target branch contains the changes only after `finalize` reaches `INTEGRATED`.

## Stop and changed files

`stop_entry.py` resolves the assigned worktree from the run record and computes changed files from Git:

```bash
git diff --name-only <baseCommit>...HEAD
git diff --name-only
git ls-files --others --exclude-standard
```

`changed-files.jsonl` remains audit evidence only. It cannot make a run read-only. Read-only PASS requires `HEAD == baseCommit`, clean worktree, no untracked files, and no attribution gap.

Persistent Stop failures are circuit-broken by identical `HEAD + dirtyHash + failureFingerprint`: the second identical Stop reuses the failure without rerunning heavy gates; after the limit it writes a final `BLOCKED` summary so the client can stop looping.

## Quality gates and artifacts

Required tier uses `applicable_gates_for_target(target, changed_files)`. Full tier uses `required_gates_for_target(target)`. Artifacts record triggered gates, not-triggered gates, changed files, base/head/dirty hash, gate config version, environment fingerprint, and cache key. PASS cache reuse requires the same target, gate inputs, base, HEAD, dirty hash, gate version, and environment fingerprint.

Java record component Javadoc validation is the Java Gradle task:

```bash
./gradlew :java:tests:quality-gates:verifyJavaRecordComponentJavadocs
```

## Finalize and handoff

`finalize` takes an integration lock, requires a clean primary checkout, checks target/branch/base/head, requires fresh validated artifacts, and integrates by `ff-only`. If target advanced without conflicts, it rebases only the agent private branch, reruns Stop, then fast-forwards. Dirty primary, conflicts, or stale artifacts produce `HANDOFF_REQUIRED` and leave the target unchanged.

Handoff summaries include committed `base...HEAD` files, commit list, ahead/behind, dirty/untracked files, required gate status, merge risk, and a single finalize command.

## Cleanup

Cleanup is dry-run by default. It blocks on active recorded process, dirty worktree, unintegrated commits, or current-process CWD. Branch deletion requires `INTEGRATED` plus explicit `--delete-branch`.
