# /change

End-to-end OpenSpec change driver. Creates a change, plans, implements, validates, and reports.

Arguments: `$ARGUMENTS`

## Phase 0: Intake

Read the user's request from `$ARGUMENTS`. Determine a short `<change-id>` (kebab-case, e.g. `add-search-filter`).

## Phase 1: Inspect

1. Read `CLAUDE.md`, `AGENTS.md`, `openspec/config.yaml`.
2. Read relevant `openspec/specs/` for current truth.
3. Inspect the repository files relevant to the request.

## Phase 2: Propose

1. Create `openspec/changes/<change-id>/` if it does not exist.
2. Write `proposal.md` — Problem, Scope, Non-goals, User impact, Validation strategy.
3. Write `design.md` — Current state, Proposed approach, Risks, Rollback, Validation.
4. Write `tasks.md` — Small, sequential, checkbox tasks with validation for each.
5. Write delta specs under `openspec/changes/<change-id>/specs/` — Requirements and Scenarios.

## Phase 3: Plan

1. Run `python3 scripts/openspec/validate_layout.py`.
2. If validation fails, fix the change docs and re-validate.
3. Confirm the plan is ready. If the user wants changes, adjust before implementing.

## Phase 4: Implement serially

Walk `tasks.md` top to bottom. For each task:

1. Do the work described in the task.
2. Mark the checkbox as done.
3. Add a short validation note.
4. Do NOT skip tasks or reorder them.
5. Do NOT expand scope beyond what the change describes.

## Phase 5: Validate

Run the quality gates:

1. `python3 scripts/openspec/validate_layout.py`
2. `python3 scripts/openspec/validate_schema.py`
3. `python3 scripts/quality/check_no_unfinished_markers.py`
4. `python3 scripts/quality/validate_task_files.py`
5. If product tests exist, run them too.

If any gate fails, fix the issue and re-run.

## Phase 6: Report

Output a summary:

- What changed (files created, modified, deleted).
- Validation results (pass/fail for each gate).
- Remaining risks or follow-ups.
- Do NOT auto-commit. Ask the user before committing.
