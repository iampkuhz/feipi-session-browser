# Design: Standardize Spec Harness Startup

## Current State (from Audit 00-01)

The audit at `.agent/audit/00-01-startup-audit.md` identified the following gaps:

| Area | Current | Required | Gap | Fix Task |
|------|---------|----------|-----|----------|
| Startup contract | Prose in CLAUDE.md only | Mechanical enforcement on session start | No SessionStart hook; no auto-prompt injection | 03-06 |
| Pre-write guard | `guard_openspec_change.py` fires on Write/Edit | Must block all file modifications without change | Bypassable via Bash (sed -i, cp, python); no change association | 03-03 |
| Change uniqueness | 3 active changes coexist | One active change at a time | No single-active-change enforcement | 03-02, 03-07 |
| Post-write evidence | change-log.jsonl (ts + event only) | Must log file, change-id, action | No structured evidence; no change association | 03-04 |
| Session-end check | stop_check.sh warns about local files | Should verify change completion state | No active-change cleanup check | 03-05 |
| Subagent context | Agent files minimal, no change refs | Subagents must know active change | No active_change injection in any agent | 04-01, 03-06 |
| Dry-run mode | HOOK_DRY_RUN=1 default in common.sh | Production hooks should not be dry-run | post_tool_guard.sh and stop_check.sh downgrade blocks | 03-07 |
| Change tracking | No `.agent/active_change.json` | Local state file for current change | Missing mechanism entirely | 03-01, 03-02 |
| gitignore | `/openspec/changes/` is ignored | Changes should be tracked (at least proposal/design) | Change artifacts cannot be shared via git | 05-02 |
| Command landscape | 7 commands + `/change` | Single authoritative change driver | Redundant commands create confusion | 02-03, 02-05, 05-03 |
| .agent/task-ledger | Static template with 4 baseline tasks | Dynamic task tracking | Not updated by hooks; no automation linkage | 03-01 |

## Proposed Approach

This change standardizes the entire spec harness startup lifecycle through 6 phases:

1. **Config & Schema (01-xx)**: Fix `config.yaml`, add schemas and validators, ensure the openspec structure is valid.
2. **Startup Contract (02-xx)**: Converge `CLAUDE.md` and `AGENTS.md` into a single authoritative contract. Create the `/change` command as the sole change driver. Isolate legacy slash commands. Add `.claude/skills/change`.
3. **Hooks & Evidence (03-xx)**: Define `.agent` local transaction state. Implement `create_active_change.py` for the active sentinel. Implement PreToolUse write gate, PostToolUse evidence logger, Stop/SubagentStop completion gate, and SessionStart/SubagentStart context injection. Configure `.claude/settings.json` hooks with dry-run disabled.
4. **Subagents (04-xx)**: Converge subagents to a minimal closed loop (openspec-planner, implementer, qa-verifier). Strengthen each with active change context and proper task execution protocols.
5. **Validation & Policy (05-xx)**: Implement repo structure validator. Update `.gitignore` for local process policy. Define prompts as inputs (not authoritative entry points). Add hook negative tests.
6. **Final Gates (06-xx)**: Refactor harness docs into a long-term manual. Implement doctor total check. Execute change dry-run validation. Final cleanup and report.

## 29 Task Phases

See `tasks.md` for the complete task list. Tasks map to the phases above as follows:

- Phase 1 (Config & Schema): Tasks 01-01, 01-02, 01-03
- Phase 2 (Startup Contract): Tasks 02-01 through 02-05
- Phase 3 (Hooks & Evidence): Tasks 03-01 through 03-07
- Phase 4 (Subagents): Tasks 04-01 through 04-04
- Phase 5 (Validation & Policy): Tasks 05-01 through 05-04
- Phase 6 (Final Gates): Tasks 06-01 through 06-04
