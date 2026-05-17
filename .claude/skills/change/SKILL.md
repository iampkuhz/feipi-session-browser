---
name: change
disable-model-invocation: true
description: End-to-end OpenSpec change driver. Creates a change, plans, implements, validates, and reports. Use `/change` for all feature work, bug fixes, and refactors.
---

# change — End-to-end OpenSpec Change Driver

This skill drives the full lifecycle of an OpenSpec change: intake, inspect, propose, plan, implement, validate, and report. It is the canonical entrypoint for all feature work, bug fixes, and refactors in this repository.

## Policy

- **prompts/ files are input, not workflow authority.** Prompt files under `harness/prompts/` or `prompts/` provide reusable scaffolding. They do not drive the workflow. Always use this skill as the entrypoint.
- **Protected file edits require an active OpenSpec change.** The PreToolUse hook (`scripts/hooks/guard_openspec_change.py`) blocks Write/Edit/MultiEdit on protected files when no active change directory exists under `openspec/changes/` (excluding `archive`).
- **Do not auto-commit.** Report results and wait for user confirmation before committing.

## Phases

### Phase 0: Intake

1. Parse the user's request. If it is a file path, read the file for the request content. Otherwise treat it as a free-form description.
2. Derive a short `<change-id>` in kebab-case (e.g. `add-search-filter`). Check `openspec/changes/` — if a matching change already exists, reuse it.
3. Read `CLAUDE.md` and `openspec/config.yaml` for project constraints and workflow settings.

### Phase 1: Create

1. Create `openspec/changes/<change-id>/` if it does not exist.
2. Write `.agent/active_change.json` with:
   ```json
   {
     "change_id": "<change-id>",
     "change_path": "openspec/changes/<change-id>/",
     "started_at": "<ISO 8601 timestamp>",
     "source_request": "<original user request or prompt file path>",
     "protected_roots": ["openspec/", "harness/", ".claude/", "CLAUDE.md"],
     "required_gates": ["scripts/openspec/validate_layout.py", ...]
   }
   ```
3. This file is how subagents inherit the active change context. All subagent work must reference `.agent/active_change.json`. See `reference/subagent-contract.md` for details. See `.agent/SCHEMA.md` for the full field specification.

### Phase 2: Inspect

1. Read `CLAUDE.md`, `AGENTS.md` for repository constraints.
2. Read relevant `openspec/specs/` for current behavior truth.
3. Inspect repository files relevant to the request (source, tests, configs).
4. Run `python3 scripts/harness/validate_openspec_layout.py` to confirm repo structure is sound.

### Phase 3: Propose

1. Write `proposal.md` under `openspec/changes/<change-id>/` — Problem, Scope, Non-goals, User impact, Validation strategy. Use `templates/proposal.md` as a starting point.
2. Write `design.md` under `openspec/changes/<change-id>/` — Current state, Proposed approach, Risks, Rollback, Validation. Use `templates/design.md` as a starting point.
3. Write `tasks.md` under `openspec/changes/<change-id>/` — Small, sequential, checkbox tasks with validation for each. Use `templates/tasks.md` as a starting point.
4. Write delta specs under `openspec/changes/<change-id>/specs/` — Requirements and Scenarios in the format expected by `openspec/validate_schema.py`. Use `templates/spec.md` as a starting point.

### Phase 4: Plan (Validate Plan)

1. Run `python3 scripts/openspec/validate_layout.py`
2. Run `python3 scripts/openspec/validate_schema.py`
3. Run `python3 scripts/harness/validate_harness_structure.py`
4. If any validator fails, fix the change docs and re-validate.
5. Confirm the plan is ready. If the user wants adjustments, revise before implementing.

### Phase 5: Implement (Serial)

Walk `openspec/changes/<change-id>/tasks.md` top to bottom. For each task:

1. Do the work described in the task.
2. Mark the checkbox as done (`- [x]`).
3. Add a short validation note below the task.
4. **Do NOT skip tasks or reorder them.**
5. **Do NOT expand scope beyond what the change describes.**
6. For large or bounded tasks, delegate to project subagents with explicit scope boundaries. Subagents must read `.agent/active_change.json` for context. See `reference/subagent-contract.md`.

### Phase 6: Validate

Run all quality gates:

1. `python3 scripts/openspec/validate_layout.py`
2. `python3 scripts/openspec/validate_schema.py`
3. `python3 scripts/openspec/validate_active_change.py --change-id <change-id>`
4. `python3 scripts/harness/validate_harness_structure.py`
5. `python3 scripts/harness/check_no_unfinished_markers.py`
6. `python3 scripts/harness/validate_task_files.py`
7. If product tests exist, run them too (e.g. `./scripts/session-browser.sh test`).

If any gate fails, fix the issue and re-run all gates until they pass.

### Phase 7: Report

Output a summary:

- What changed (files created, modified, deleted).
- Validation results (pass/fail for each gate).
- Remaining risks or follow-ups.
- **Do NOT auto-commit.** Ask the user before committing.

## Hook Enforcement

The repository enforces OpenSpec change presence via hooks defined in `.claude/settings.json`:

- **PreToolUse (Write|Edit|MultiEdit):** `scripts/hooks/guard_openspec_change.py` — blocks protected file edits when no active change directory exists under `openspec/changes/`.
- **PostToolUse (Write|Edit|MultiEdit):** `.claude/hooks/post_tool_guard.sh` — syntax checks for edited shell and JSON files.
- **PreToolUse (Bash):** `.claude/hooks/pre_tool_guard.sh` — blocks destructive shell commands.
- **Stop:** `.claude/hooks/stop_check.sh` — warns about uncommitted local-only files and generated artifacts.

These hooks are the enforcement layer. The skill orchestrates the workflow; the hooks prevent policy violations.

## Reference

- Full 7-phase workflow: `reference/workflow.md`
- Subagent inheritance contract: `reference/subagent-contract.md`
- Templates: `templates/` directory
