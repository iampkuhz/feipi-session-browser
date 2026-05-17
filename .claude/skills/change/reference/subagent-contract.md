# Subagent Contract — Active Change Inheritance

This document defines how subagents inherit and work within an active OpenSpec change.

## How Subagents Inherit the Active Change

When a parent agent (the `change` skill driver) delegates work to a subagent, the subagent MUST read `.agent/active_change.json` to determine the current active change context.

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

The `change_id` field is the key that links all subagent work back to the parent change. The `change_path` field tells subagents where to find tasks and specs. See `.agent/SCHEMA.md` for the full field specification.

## What Subagents Must Do

### 1. Read the Active Change

Before doing any work, the subagent MUST:

```
Read .agent/active_change.json
```

If the file does not exist, the subagent MUST NOT proceed with implementation edits. It should report an error: "No active OpenSpec change found. Run `/change` to create one before delegating work."

### 2. Work Within the Change Scope

The subagent MUST:

- Only modify files relevant to the active change identified in `.agent/active_change.json`.
- Reference the change ID in any commits, validation notes, or reports.
- NOT expand scope beyond what the parent change describes.
- NOT create a new change directory. The parent change owns the scope.

### 3. Update Task Status

If the subagent is assigned a specific task from `openspec/changes/<change-id>/tasks.md`, it MUST:

- Mark the task checkbox as done (`- [x]`) when complete.
- Add a short validation note below the task.
- Report evidence (command output, file counts, etc.) — not just "done".

### 4. Respect Hook Enforcement

Subagents operate under the same hook constraints as the parent:

- **PreToolUse (Write|Edit|MultiEdit):** `scripts/hooks/guard_openspec_change.py` checks for an active change directory. The subagent's work is valid because the parent already created the change directory. The `.agent/active_change.json` file is the subagent's context anchor, but the hook checks for the directory under `openspec/changes/`.
- **PostToolUse (Write|Edit|MultiEdit):** `.claude/hooks/post_tool_guard.sh` runs syntax checks.
- **PreToolUse (Bash):** `.claude/hooks/pre_tool_guard.sh` blocks destructive commands.
- **Stop:** `.claude/hooks/stop_check.sh` warns about uncommitted files.

### 5. Do NOT Touch Active Change Registration

The subagent MUST NOT:

- Modify `.agent/active_change.json` (the parent manages this).
- Create a new change directory under `openspec/changes/`.
- Move or archive the change (that is a parent-level action).

## Delegation Pattern

The parent agent should delegate with this pattern:

1. Ensure `.agent/active_change.json` exists and is current.
2. Assign the subagent a specific task from `openspec/changes/<change-id>/tasks.md`.
3. Communicate the scope boundaries clearly.
4. After the subagent completes, verify the work and task checkbox.
5. Continue to the next task or phase.

## Example Subagent Prompt

> You are working on active change: `<change-id>`.
> Read `.agent/active_change.json` for context.
> Complete the following task from `openspec/changes/<change-id>/tasks.md`:
>
> - Task: <task description>
> - Scope: <specific files/functions>
> - Out of scope: <explicitly excluded>
>
> When done, mark the task checkbox as done and add a validation note.

## Validation Evidence

Subagents must provide concrete evidence, not claims:

- Run the relevant validation command and show output.
- Show file diff or key lines changed.
- Report test results with pass/fail counts.
