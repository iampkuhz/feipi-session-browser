# Qoder Hook Bindings

## Required Lifecycle Bindings

| Lifecycle | Matcher | Command | Required | Unsupported reason |
|---|---|---|---:|---|
| PreToolUse | Bash | `.qoder/hooks/pre_tool_guard.sh` | yes | n/a |
| PreToolUse | Write/Edit/MultiEdit/NotebookEdit | `.qoder/hooks/pre_write_guard.sh` | yes | n/a |
| PostToolUse | Bash | `.qoder/hooks/post_bash_guard.sh` | yes | n/a |
| PostToolUse | Write/Edit/MultiEdit/NotebookEdit | `.qoder/hooks/post_tool_guard.sh` | yes | n/a |
| Stop | main/subagent stop | `.qoder/hooks/stop_check.sh` | yes | n/a |
| SessionStart | session start | not bound | no | Qoder hook lifecycle is not available in this repository runtime contract |
| SubagentStart | subagent start | not bound | no | Qoder hook lifecycle is not available in this repository runtime contract |
| ToolFailure | tool failure | not bound | no | Qoder hook lifecycle is not available in this repository runtime contract |
| ConfigChange | config change | not bound | no | Qoder hook lifecycle is not available in this repository runtime contract |

## PreToolUse Bash

- Bind Bash command attempts to `.qoder/hooks/pre_tool_guard.sh`.
- Provide command, session identity, agent identity, and working directory fields when Qoder supports them.
- Fail closed when a protected mutation command lacks usable runtime identity or active change evidence.
- For main sessions, create or require the assigned git worktree before mutating Bash runs.

## PreToolUse Write/Edit/MultiEdit/NotebookEdit

- Bind write-like tools to `.qoder/hooks/pre_write_guard.sh` before file mutation.
- Provide candidate path fields such as `file_path`, `path`, or `notebook_path`.
- Fail closed when the candidate path is missing for write-like tools or the path targets a protected root without a valid active change.
- For main sessions, create or require the assigned git worktree before Write/Edit/MultiEdit proceeds.

## PostToolUse Bash

- Bind completed Bash commands to `.qoder/hooks/post_bash_guard.sh`.
- Include command, exit status when available, and mutation attribution evidence.
- Record attribution gaps when pre/post snapshots are missing instead of silently passing.

## PostToolUse Write/Edit/MultiEdit/NotebookEdit

- Bind completed write-like tools to `.qoder/hooks/post_tool_guard.sh`.
- Include final written paths and tool result metadata when available.
- Record evidence for changed protected paths so Stop can evaluate current-session mutations.

## Stop

- Bind Qoder stop events to `.qoder/hooks/stop_check.sh`.
- Stop must evaluate required quality gates for current-session protected changes.
- Stop must not treat missing changed-file evidence as PASS when the workspace is dirty.
- Stop must block required gates when an assigned main-session worktree exists but the stop hook runs from another checkout with changes.

## Unsupported Lifecycles

- SessionStart is unsupported until Qoder exposes a compatible lifecycle in this repository.
- SubagentStart is unsupported until Qoder exposes a compatible lifecycle in this repository.
- ToolFailure and ConfigChange are unsupported until Qoder exposes compatible lifecycle payloads.

## Required Payload Fields

- Identity fields: `session_id` or `sessionId`, and `agent_id` or `agentId`.
- Tool input fields: `tool_input` or `toolInput`, including `command` for Bash.
- Candidate path fields: `file_path`, `path`, or `notebook_path` for write-like tools.

## Fail-Closed Rules

- Missing session id with mutation or protected write must block or enter explicit legacy fail-closed mode.
- Missing candidate path for Write/Edit/MultiEdit/NotebookEdit must not silently pass.
- Dirty protected workspace without current-session evidence must block Stop rather than report read-only PASS.
- Main-session mutations outside the assigned git worktree must block before tool execution.

## Local Verification

- Run `ACTIVE_CHANGE_ID=enable-parallel-main-agent-worktrees python scripts/quality/check_agent_runtime_worktree.py` after editing worktree isolation behavior.
- Run `ACTIVE_CHANGE_ID=harden-agent-runtime-full-v3 python scripts/quality/check_qoder_runtime_parity.py` after editing Qoder runtime files.
- Run `ACTIVE_CHANGE_ID=harden-agent-runtime-full-v3 python scripts/quality/check_agent_runtime_manifest.py` after manifest edits.
- Run `ACTIVE_CHANGE_ID=harden-agent-runtime-full-v3 python scripts/quality/check_skill_registry.py` after skill alias edits.
