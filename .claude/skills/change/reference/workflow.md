# OpenSpec Change Workflow — 7 Phases

This document describes the canonical 7-phase workflow for driving an OpenSpec change. It is referenced by the `change` skill and provides detailed guidance for each phase.

## Overview

```
Phase 0: Intake  →  Phase 1: Create  →  Phase 2: Inspect  →  Phase 3: Propose
                                                                          ↓
Phase 7: Report  ←  Phase 6: Validate  ←  Phase 5: Implement  ←  Phase 4: Plan
```

Each phase has entry criteria, steps, and exit criteria. Do not skip phases.

---

## Phase 0: Intake

**Entry:** User provides a request (free-form text or file path).

**Steps:**

1. Parse the request. If a file path is provided, read it for content.
2. Derive a `<change-id>` in kebab-case.
3. Check `openspec/changes/` for existing matching change.
4. Read `CLAUDE.md` and `openspec/config.yaml` for constraints.

**Exit:** A clear `<change-id>` and understanding of project constraints.

---

## Phase 1: Create

**Entry:** Valid `<change-id>` from Intake.

**Steps:**

1. Create `openspec/changes/<change-id>/` directory if it does not exist.
2. Write `.agent/active_change.json` to register the active change:
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
   See `.agent/SCHEMA.md` for the full field specification.

**Exit:** Change directory exists and `.agent/active_change.json` is written.

---

## Phase 2: Inspect

**Entry:** Active change is registered.

**Steps:**

1. Read `CLAUDE.md`, `AGENTS.md` for repository constraints.
2. Read relevant specs under `openspec/specs/` for current behavior.
3. Inspect source files, tests, and configs relevant to the change.
4. Run `python3 scripts/harness/validate_openspec_layout.py` to confirm structure.

**Exit:** Clear understanding of current state and relevant files.

---

## Phase 3: Propose

**Entry:** Inspection complete.

**Steps:**

1. Write `proposal.md` — Problem, Scope, Non-goals, User impact, Validation strategy.
2. Write `design.md` — Current state, Proposed approach, Risks, Rollback, Validation.
3. Write `tasks.md` — Granular, sequential tasks with validation steps.
4. Write delta specs under `openspec/changes/<change-id>/specs/`.

**Exit:** All proposal documents and spec deltas are written.

---

## Phase 4: Plan (Validate Plan)

**Entry:** Proposal and spec deltas are written.

**Steps:**

1. Run `python3 scripts/openspec/validate_layout.py`
2. Run `python3 scripts/openspec/validate_schema.py`
3. Run `python3 scripts/harness/validate_harness_structure.py`
4. Fix any validation failures.
5. Present the plan to the user for approval.

**Exit:** All validators pass and user approves the plan.

---

## Phase 5: Implement (Serial)

**Entry:** Plan is approved.

**Steps:**

1. Walk `openspec/changes/<change-id>/tasks.md` top to bottom.
2. For each task:
   - Do the work.
   - Mark the checkbox as done (`- [x]`).
   - Add a validation note.
3. Do NOT skip or reorder tasks.
4. Do NOT expand scope beyond what the change describes.
5. For large tasks, delegate to subagents with explicit scope (see `subagent-contract.md`).

**Exit:** All tasks are complete and marked done.

---

## Phase 6: Validate

**Entry:** All implementation tasks are done.

**Steps:**

1. Run `python3 scripts/openspec/validate_layout.py`
2. Run `python3 scripts/openspec/validate_schema.py`
3. Run `python3 scripts/openspec/validate_active_change.py --change-id <change-id>`
4. Run `python3 scripts/harness/validate_harness_structure.py`
5. Run `python3 scripts/harness/check_no_unfinished_markers.py`
6. Run `python3 scripts/harness/validate_task_files.py`
7. Run product tests if they exist.
8. Fix any failures and re-run until all gates pass.

**Exit:** All quality gates pass.

---

## Phase 7: Report

**Entry:** All quality gates pass.

**Steps:**

1. Summarize what changed (files created, modified, deleted).
2. Report validation results (pass/fail per gate).
3. Note remaining risks or follow-ups.
4. Ask the user before committing.

**Exit:** User has the report and decides on commit.

---

## Post-Change: Archive

After the change is committed and approved:

1. Merge spec deltas from `openspec/changes/<change-id>/specs/` into `openspec/specs/`.
2. Move the change directory to `openspec/changes/archive/<change-id>/`.
3. Remove `.agent/active_change.json` or update it if another change is active.

This is governed by `openspec/config.yaml` under `final_specs_update_rule`.
