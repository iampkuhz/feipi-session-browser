# Spec: Spec Harness Startup

## ADDED Requirements

### Requirement: Startup Contract

The system SHALL enforce a mechanical OpenSpec workflow contract on every Claude Code session start.

#### Scenario: Session start loads startup context

- **GIVEN** a Claude Code session starts in this repository
- **WHEN** the session initializes
- **THEN** `CLAUDE.md` is loaded as the primary context file
- **AND** `CLAUDE.md` references `AGENTS.md` for engineering rules
- **AND** `CLAUDE.md` references the OpenSpec workflow lifecycle (propose -> design -> tasks -> implement -> validate -> archive)
- **AND** the startup context includes a pointer to `.agent/active_change.json` if it exists

#### Scenario: Startup context includes hook configuration

- **GIVEN** `.claude/settings.json` exists
- **WHEN** the session initializes
- **THEN** all configured PreToolUse, PostToolUse, and Stop hooks are registered
- **AND** `HOOK_DRY_RUN` is set to `0` (production mode, not dry-run)

---

### Requirement: /change Command Workflow

The `/change` command SHALL be the single authoritative driver for all OpenSpec change lifecycle operations.

#### Scenario: User initiates a change via /change

- **GIVEN** no active change exists
- **WHEN** the user runs `/change <change-id>`
- **THEN** the command creates `.agent/active_change.json` with the change-id
- **AND** the command loads the change directory under `openspec/changes/<change-id>/`
- **AND** the command presents the proposal, design, and tasks to the agent

#### Scenario: User attempts edit without active change

- **GIVEN** no active change exists (`.agent/active_change.json` missing)
- **WHEN** the agent attempts to Write, Edit, or MultiEdit a product file
- **THEN** the PreToolUse hook blocks the operation
- **AND** returns an error message instructing the user to run `/change` first

#### Scenario: Multiple active changes conflict

- **GIVEN** multiple non-archive directories exist under `openspec/changes/`
- **WHEN** `/change` is invoked without a change-id
- **THEN** the command lists active changes and prompts the user to select one
- **AND** does not proceed until exactly one active change is selected

---

### Requirement: Active Change Sentinel

A local state file `.agent/active_change.json` SHALL track the current working change.

#### Scenario: Active change sentinel creation

- **WHEN** `/change <change-id>` succeeds
- **THEN** `.agent/active_change.json` is created with the following structure:
  ```json
  {
    "change_id": "<change-id>",
    "started_at": "<ISO-8601 timestamp>",
    "status": "active"
  }
  ```

#### Scenario: Active change sentinel validation

- **WHEN** the PreToolUse OpenSpec guard fires
- **THEN** it reads `.agent/active_change.json` to determine the active change-id
- **AND** if the file is missing or invalid, the guard fails with exit code 2

#### Scenario: Active change sentinel cleanup

- **WHEN** the session ends (Stop hook) and all tasks are completed
- **THEN** the Stop hook prompts the user whether to archive the change
- **AND** if confirmed, sets `"status": "archived"` and moves the change directory to `openspec/changes/archive/`

---

### Requirement: PreToolUse Hook Behavior

PreToolUse hooks SHALL gate all file modification operations behind an active OpenSpec change.

#### Scenario: PreToolUse guard blocks write without change

- **GIVEN** `.agent/active_change.json` does not exist
- **WHEN** the agent calls Write, Edit, or MultiEdit
- **THEN** `scripts/agent_hooks/guard_active_openspec_change.py` exits with code 2
- **AND** the operation is blocked

#### Scenario: PreToolUse guard allows write with change

- **GIVEN** `.agent/active_change.json` exists with `"status": "active"`
- **WHEN** the agent calls Write, Edit, or MultiEdit
- **THEN** `guard_active_openspec_change.py` exits with code 0
- **AND** the operation proceeds

#### Scenario: PreToolUse Bash guard blocks destructive commands

- **WHEN** the agent calls Bash with a destructive command (e.g., `rm -rf`, `git reset --hard`, `git push --force`)
- **THEN** `.claude/hooks/pre_tool_guard.sh` blocks the command
- **AND** returns a warning to the user

---

### Requirement: PostToolUse Hook Behavior

PostToolUse hooks SHALL log evidence and perform syntax/validation checks after every file modification.

#### Scenario: PostToolUse evidence logging

- **WHEN** a Write, Edit, or MultiEdit operation completes
- **THEN** `scripts/agent_hooks/log_file_change.py` appends to `.claude/change-log.jsonl`
- **AND** each entry includes: `event`, `ts`, `file_path`, `change_id`, `action`

#### Scenario: PostToolUse syntax checks

- **WHEN** a file modification completes
- **THEN** `.claude/hooks/post_tool_guard.sh` runs syntax checks appropriate to the file type
- **AND** blocks edits to `.claude/settings.local.json`, `.mcp.json`, and other protected files

---

### Requirement: Subagent Inheritance

All subagents SHALL inherit the active change context from the parent session.

#### Scenario: Subagent receives active change context

- **GIVEN** `.agent/active_change.json` exists
- **WHEN** a subagent (openspec-planner, implementer, qa-verifier, ui-architect) is spawned
- **THEN** the subagent's system prompt includes the active change-id
- **AND** the subagent can read the change proposal, design, and tasks

#### Scenario: Subagent validates change association

- **WHEN** a subagent attempts to modify product files
- **THEN** the PreToolUse guard verifies the active change matches the subagent's context
- **AND** blocks the operation if there is a mismatch

---

### Requirement: Evidence Tracking

All file modifications SHALL be tracked with structured evidence linked to the active change.

#### Scenario: Evidence log entry structure

- **WHEN** a file is modified
- **THEN** `.claude/change-log.jsonl` receives a JSONL entry with:
  - `event`: `"pre-edit"` or `"post-edit"`
  - `ts`: ISO-8601 timestamp
  - `file_path`: absolute or repo-relative path
  - `change_id`: the active change-id from `.agent/active_change.json`
  - `action`: `"create"`, `"update"`, or `"delete"`
  - `diff_summary`: short summary of the change (first line of diff)

#### Scenario: Task ledger updates

- **WHEN** a task from `tasks.md` is completed
- **THEN** `.agent/task-ledger.md` is updated to reflect the task status
- **AND** the update includes timestamp and outcome

---

### Requirement: Final Validation Gates

The change SHALL not be considered complete until all validation gates pass.

#### Scenario: Harness structure validation

- **WHEN** final validation runs
- **THEN** `python3 scripts/harness/validate_harness_structure.py` passes

#### Scenario: OpenSpec layout validation

- **WHEN** final validation runs
- **THEN** `python3 scripts/harness/validate_openspec_layout.py` passes

#### Scenario: Unfinished markers check

- **WHEN** final validation runs
- **THEN** `python3 scripts/harness/check_no_unfinished_markers.py` passes

#### Scenario: Task file validation

- **WHEN** final validation runs
- **THEN** `python3 scripts/harness/validate_task_files.py` passes

#### Scenario: Hook self-tests

- **WHEN** final validation runs
- **THEN** `python scripts/agent_hooks/guard_active_openspec_change.py --self-test` passes
- **AND** `python scripts/agent_hooks/stop_validate_change.py --self-test` passes

#### Scenario: Doctor total check

- **WHEN** final validation runs
- **THEN** `python scripts/quality/doctor.py` passes (if available)

#### Scenario: Repo structure validation

- **WHEN** final validation runs
- **THEN** `python scripts/quality/validate_repo_structure.py` passes (if available)
