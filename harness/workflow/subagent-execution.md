# Subagent Execution

This document describes how subagents operate within the OpenSpec workflow.

## Subagent Model

Subagents in this repo are defined under `.claude/agents/`. Each agent has:
- `name`: Unique identifier.
- `description`: When to use.
- `tools`: Allowed Claude Code tools.
- `model`: `inherit` means use the same model as the main session.

## Default Agents

Three agents form the core OpenSpec workflow:

### openspec-planner

- **Purpose**: Design OpenSpec changes (proposal, design, tasks, spec deltas).
- **Scope**: `openspec/changes/`, `.agent/active_change.json`, `openspec/specs/`.
- **Prohibited**: Product source files, CLAUDE.md, AGENTS.md, code implementation.
- **Active change**: Creates and records active change via `/change` or `create_active_change.py`.

### implementer

- **Purpose**: Execute exactly one task from a change's `tasks.md`.
- **Preflight**: Must verify `.agent/active_change.json` exists and is valid.
- **Scope**: Only the files required for the assigned task.
- **Evidence**: Auto-logged by PostToolUse hook to `.agent/task-evidence/<change-id>.jsonl`.
- **Prohibited**: Scope expansion, skipping validation, modifying OpenSpec artifacts.

### qa-verifier

- **Purpose**: Final verification gate before session stop.
- **Checks**: Active change completeness, evidence entries, diff scope, validation gates, generated artifacts.
- **Output**: PASS / FAIL / BLOCKED with structured reasons.
- **Tools**: Read-only analysis (Read, Grep, Glob, LS, Bash).

## Specialty Agents

Specialty agents live under `.claude/agents/specialty/` and are used for domain-specific work (UI, MHTML export, migration). They are not part of the default OpenSpec loop.

## Context Inheritance

Every subagent receives the session context injected by `inject_session_context.py`:
- Repo root path.
- Active change ID and status.
- Evidence path and entry count.
- Protected roots and workflow default.

This ensures subagents cannot operate without knowledge of the current OpenSpec state.

## Guard Enforcement

The `guard_active_openspec_change.py` PreToolUse hook runs before every Write/Edit/MultiEdit to protected roots. If no active change exists, the edit is blocked. This applies to subagents equally.

## Evidence Tracking

The `log_change_evidence.py` PostToolUse hook logs every protected file edit. Evidence is written to `.agent/task-evidence/<change-id>.jsonl`. The qa-verifier reads this file to confirm all edits are accounted for.

## Stop Validation

When a subagent finishes, `stop_validate_change.py` checks:
- If protected changes exist, the active change must be complete.
- Required files (proposal.md, design.md, tasks.md) must be present.
- Evidence entries must exist.
- If incomplete, the stop is blocked (exit 1).

Emergency bypass: `FEIPI_SKIP_STOP_HOOK=1`.
