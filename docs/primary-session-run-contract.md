# Primary session run contract

`harness/primary-session.manifest.yaml` defines the machine-readable contract for primary agent runs. It is separate from subagent identity: `runId` owns the primary writer lease, `sessionId` identifies the client session, and subagents inherit the parent `runId` while using their own agent id.

Writable primary runs require `git-worktree-required` isolation, at most one active writer per worktree, and confirmed hook activation before entering writable-ready states such as `running` or `validating`. Read-only sessions may share a worktree but cannot write protected paths.

Runtime state is never committed. `scripts/harness/primary_session.py` resolves the shared registry root from `FEIPI_AGENT_RUNTIME_ROOT` first, otherwise from `git rev-parse --git-common-dir` plus `feipi-agent-runtime`, which works for both normal checkouts and linked worktrees.


## Runtime capability

`sessionctl doctor` reports `writable-ready`, `read-only-ready`, `blocked`, or `legacy-single-writer`; required gates must not collapse these states into a generic PASS. Hook activation marker deletion, config hash drift, or duplicate active writer leases are blocking conditions.

## Compatibility contract

The rollout exposes four explicit runtime modes:

- `managed-worktree`: created by `sessionctl`; the only multi-primary writable mode.
- `read-only-unbound`: direct Qoder/Codex launch without a bound run; read/analysis only.
- `legacy-single-writer`: explicit compatibility mode for one checkout writer; warning-only compatibility, not multi-primary.
- `blocked`: fail-closed state for missing hooks, identity/worktree/branch mismatches, writer lease conflicts, invalid change id, registry/resource/Stop failures, or dirty cleanup.

Subagents inherit the parent primary run id and evidence layout; `.codex/agents/*.toml` and `.claude/agents/*.md` do not create primary runs. Legacy `tmp/active_change.json` is only considered for unbound legacy contexts and cannot authorize a bound managed run.
