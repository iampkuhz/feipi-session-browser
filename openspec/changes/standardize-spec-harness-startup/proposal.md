# Proposal: Standardize Spec Harness Startup

## Problem

Starting Claude Code in this repository does not mechanically enforce the OpenSpec workflow. The current contract — "No feature, refactor, or bugfix implementation without an OpenSpec change" — lives as prose in `CLAUDE.md` and `AGENTS.md` only. There is no mechanism on session start that forces the agent to create, select, or reference an active OpenSpec change before editing product files.

Additionally:
- Multiple active changes coexist (3 found), with no single-active-change enforcement.
- Hooks exist but run in dry-run mode by default (`HOOK_DRY_RUN=1`).
- No `.agent/active_change.json` sentinel tracks the current working change.
- 旧版 evidence logging 曾写入 `.claude/change-log.jsonl`，但该兼容日志缺少足够校验价值；当前链路应使用 `tmp/agent_logs/current/changed-files.jsonl` 与 `task-evidence/<change-id>.jsonl`。
- Subagent definitions contain no reference to the active change context.

## Scope

This change affects harness and workflow files only:
- `openspec/` directory structure and specs
- `.claude/` hooks, commands, agents, and settings
- `.agent/` state files and task ledger
- `scripts/hooks/` and `scripts/agent_hooks/`
- `CLAUDE.md` and `AGENTS.md` startup contracts

Product UI code, templates, and runtime behavior are explicitly out of scope.

## Validation Strategy

1. All hook scripts pass `--self-test`.
2. `guard_active_openspec_change.py` blocks Write/Edit when no active change exists.
3. `create_active_change.py` creates a valid `.agent/active_change.json`.
4. `stop_validate_change.py` verifies change completion state on session end.
5. All quality gates pass:
   - `python3 scripts/harness/validate_harness_structure.py`
   - `python3 scripts/harness/validate_openspec_layout.py`
   - `python3 scripts/harness/check_no_unfinished_markers.py`
   - `python3 scripts/harness/validate_task_files.py`
