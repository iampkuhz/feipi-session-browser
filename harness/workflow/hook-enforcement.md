# Hook Enforcement

This document describes the hook architecture that enforces the OpenSpec workflow.

## Overview

Hooks are wired in `.claude/settings.json` and execute at specific lifecycle points. They are the primary enforcement mechanism -- without hooks, the workflow relies only on agent prompt compliance.

## Hook Types

### PreToolUse

Executes BEFORE a tool (Write, Edit, MultiEdit, Bash) runs.

- **Write|Edit|MultiEdit guard** (`guard_active_openspec_change.py`):
  - Checks if the target file is under a protected root.
  - Protected roots: `CLAUDE.md`, `AGENTS.md`, `openspec/`, `.claude/`, `scripts/`, `harness/`, `src/`.
  - If protected, requires `.agent/active_change.json` with a valid `change_id` and matching `openspec/changes/<change-id>/` directory.
  - Exit 0 = ALLOW, Exit 1 = BLOCK.
  - Creation exceptions: writing to `openspec/changes/` or `.agent/active_change.json` is always allowed.

- **Bash guard** (`pre_tool_guard.sh`):
  - General Bash pre-execution check.

### PostToolUse

Executes AFTER a tool completes.

- **Write|Edit|MultiEdit logger** (`log_change_evidence.py`):
  - Logs the edited file path, tool name, timestamp, and change_id.
  - Appends to `.agent/task-evidence/<change-id>.jsonl`.
  - If no active change, logs to `unknown.jsonl`.
  - Always exits 0 (non-blocking).

### Stop / SubagentStop

Executes when the agent session is about to end.

- **Stop check** (`stop_check.sh`):
  - Warns about local-only files in git status.
  - Calls `stop_validate_change.py` for change completeness.

- **Stop validation** (`stop_validate_change.py`):
  - Checks for uncommitted changes in protected roots.
  - If changes exist, validates:
    1. `.agent/active_change.json` exists and has `change_id`.
    2. `openspec/changes/<change-id>/` exists.
    3. Required files present: `proposal.md`, `design.md`, `tasks.md`.
    4. Evidence entries in `.agent/task-evidence/<change-id>.jsonl`.
  - If incomplete, blocks with exit 1.
  - Emergency bypass: `FEIPI_SKIP_STOP_HOOK=1`.

### SessionStart / SubagentStart

Executes when a new session or subagent session begins.

- **Context injector** (`inject_session_context.py`):
  - Prints concise context to stdout.
  - Includes: repo root, active change status, evidence path, protected roots.
  - If no active change, warns that protected edits are blocked until `/change` creates one.
  - Self-test validates with/without active change scenarios.

## Wiring

All hooks are configured in `.claude/settings.json` under the `hooks` key:

```json
{
  "hooks": {
    "SessionStart": [{ "command": "python3 scripts/agent_hooks/inject_session_context.py" }],
    "SubagentStart": [{ "command": "python3 scripts/agent_hooks/inject_session_context.py" }],
    "PreToolUse": [
      { "matcher": "Write|Edit|MultiEdit", "command": "python3 scripts/agent_hooks/guard_active_openspec_change.py" },
      { "matcher": "Bash", "command": ".claude/hooks/pre_tool_guard.sh" }
    ],
    "PostToolUse": [
      { "matcher": "Write|Edit|MultiEdit", "command": "python3 scripts/agent_hooks/log_change_evidence.py" }
    ],
    "Stop": [{ "command": ".claude/hooks/stop_check.sh" }],
    "SubagentStop": [{ "command": "python3 scripts/agent_hooks/stop_validate_change.py" }]
  }
}
```

## Self-Tests

Every hook script supports `--self-test` mode that runs deterministic pass/fail checks in a temporary git repo:

```bash
python3 scripts/agent_hooks/guard_active_openspec_change.py --self-test   # 8/8
python3 scripts/agent_hooks/stop_validate_change.py --self-test           # 8/8
python3 scripts/agent_hooks/inject_session_context.py --self-test         # 10/10
python3 scripts/agent_hooks/log_change_evidence.py --self-test            # 3/3
```

## Failure Modes

| Scenario | Hook | Result |
|----------|------|--------|
| Protected write, no active change | PreToolUse guard | BLOCK (exit 1) |
| Session start, no active change | SessionStart inject | WARN (exit 0, context says NONE) |
| Stop, protected changes, incomplete change | Stop validate | BLOCK (exit 1) |
| Stop, emergency bypass | Stop validate | ALLOW (FEIPI_SKIP_STOP_HOOK=1) |
| PostToolUse, no active change | Evidence logger | LOG to unknown.jsonl (exit 0) |
