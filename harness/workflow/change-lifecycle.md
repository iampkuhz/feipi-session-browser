# Change Lifecycle

This document describes the full OpenSpec change lifecycle for the feipi-session-browser repository.

## Overview

All non-trivial changes follow this flow:

```
/CHANGE -> PROPOSE -> DESIGN -> TASK FILES -> IMPLEMENT SERIAL -> VALIDATE -> ARCHIVE
```

The single entry point is `/change <requirement or prompt path>`. Do NOT start work by reading `prompts/` directly; always route through `/change`.

## 1. Start a Change

Run `/change <requirement-path>` which:
- Creates `openspec/changes/<change-id>/` with `proposal.md`, `design.md`, `tasks.md`.
- Writes `.agent/active_change.json` to record the active change.
- Updates the change skill reference under `.claude/skills/change/`.

## 2. Propose

The openspec-planner agent writes `proposal.md`:
- One-paragraph summary of what and why.
- Scope boundaries and non-goals.
- Validation approach.

## 3. Design

The openspec-planner writes `design.md`:
- Technical approach and constraints.
- Trade-offs and alternatives considered.
- Implementation boundaries (which files, which subsystems).

## 4. Task Files

The openspec-planner decomposes the change into `tasks.md`:
- Each task is independently verifiable.
- Each task references a validation command.
- Tasks are ordered serially (no parallel execution within a change).

## 5. Implement

The implementer agent executes one task at a time:
- **Preflight**: reads `.agent/active_change.json`, validates active change exists.
- **Scope**: implements exactly the assigned task, no more.
- **Validation**: runs the task's validation command after implementation.
- **Evidence**: all file edits under protected roots are auto-logged to `.agent/task-evidence/<change-id>.jsonl`.

## 6. Validate

The qa-verifier agent checks:
- Active change completeness (proposal, design, tasks).
- Evidence entries match edited files.
- `git diff --stat` scope matches tasks.
- All validation commands pass.
- Product tests pass.
- No generated artifacts in the diff.

Output: PASS / FAIL / BLOCKED with reasons.

## 7. Archive

After validation:
- Merge final behavior into `openspec/specs/`.
- Move `openspec/changes/<change-id>/` to `openspec/changes/archive/`.
- Clear `.agent/active_change.json`.

## Local-Only Changes

OpenSpec changes under `openspec/changes/` are local to the branch. They are not committed to the repository until merged to `openspec/specs/` and archived. The `.gitignore` ensures change artifacts do not leak into commits accidentally.

## Hooks and Enforcement

The lifecycle is enforced by Claude Code hooks wired in `.claude/settings.json`:

| Hook | Script | Purpose |
|------|--------|---------|
| SessionStart/SubagentStart | `inject_session_context.py` | Inject active change status |
| PreToolUse (Write/Edit/MultiEdit) | `guard_active_openspec_change.py` | Block protected edits without active change |
| PostToolUse (Write/Edit/MultiEdit) | `log_change_evidence.py` | Auto-log file edits to evidence |
| Stop/SubagentStop | `stop_validate_change.py` | Block stop if change is incomplete |

See `harness/workflow/hook-enforcement.md` for details.
