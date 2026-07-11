# Qoder Hook Bindings

## Required Lifecycle Bindings

| Lifecycle | Matcher | Command | Required | Unsupported reason |
|---|---|---|---:|---|
| SessionStart | session start | `.qoder/hooks/session-start.sh` | yes | n/a |
| PreToolUse | Bash | `.qoder/hooks/pre_tool_guard.sh` | yes | n/a |
| PreToolUse | Write/Edit/MultiEdit/NotebookEdit | `.qoder/hooks/pre_write_guard.sh` | yes | n/a |
| PostToolUse | Bash | `.qoder/hooks/post_bash_guard.sh` | yes | n/a |
| PostToolUse | Write/Edit/MultiEdit/NotebookEdit | `.qoder/hooks/post_tool_guard.sh` | yes | n/a |
| PostToolUseFailure | any failed tool | `.qoder/hooks/tool_failure.sh` | yes | n/a |
| Stop | main/subagent stop | `.qoder/hooks/stop_check.sh` | yes | n/a |
| StopFailure | failed stop/check cleanup | `.qoder/hooks/stop_failure.sh` | yes | n/a |
| SessionEnd | session end | `.qoder/hooks/session_end.sh` | yes | n/a |
| WorktreeCreate | native worktree lifecycle | not bound | no | Qoder native WorktreeCreate lifecycle is not present in the repository-supported hook schema; launcher/sessionctl worktree binding is the fallback. |
| WorktreeRemove | native worktree lifecycle | not bound | no | Qoder native WorktreeRemove lifecycle is not present in the repository-supported hook schema; sessionctl cleanup is the fallback. |

Schema basis: `.qoder/settings.json` follows the hook shape already used by committed `.claude/settings.json` and `.codex/hooks.json` (`hooks`, `matcher`, `type`, `command`). A local Qoder CLI/schema was not available in this worktree; therefore only events represented in repository conventions are treated as bound, and native worktree lifecycle events remain unsupported with fail-closed fallback.

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

- WorktreeCreate is unsupported until Qoder exposes a compatible native lifecycle in this repository hook schema; `sessionctl create/start/bind-session` remains the fallback.
- WorktreeRemove is unsupported until Qoder exposes a compatible native lifecycle in this repository hook schema; `sessionctl cleanup` remains the fallback.
- Unsupported native lifecycle entries must stay unbound in `.qoder/settings.json` and documented with manifest reasons rather than guessed fields.

## Required Payload Fields

- Identity fields: `session_id` or `sessionId`, and `agent_id` or `agentId`.
- Run binding fields: launcher-provided `FEIPI_RUN_ID`, optional `run_id` or `runId`, and current `cwd` or `workingDirectory`.
- Tool input fields: `tool_input` or `toolInput`, including `command` for Bash.
- Candidate path fields: `file_path`, `path`, or `notebook_path` for write-like tools.

## Fail-Closed Rules

- SessionStart must call `sessionctl bind-session` when `FEIPI_RUN_ID` and a session id are present; otherwise it writes a `read-only-unbound` marker and must not make Qoder writable-ready.
- Missing session id with mutation or protected write must block or enter explicit legacy fail-closed mode.
- Missing candidate path for Write/Edit/MultiEdit/NotebookEdit must not silently pass.
- Dirty protected workspace without current-session evidence must block Stop rather than report read-only PASS.
- Main-session mutations outside the assigned git worktree must block before tool execution.

## Local Verification

- Run `python3 -m json.tool .qoder/settings.json .qoder/settings.local.example.json` after editing Qoder settings.
- Run `bash -n .qoder/hooks/*.sh` after editing Qoder wrappers.
- Run `python3 scripts/quality/check_agent_hook_parity.py` and `python3 scripts/quality/check_qoder_runtime_parity.py` after editing Qoder hook bindings.
- Run `python3 scripts/quality/check_agent_runtime_manifest.py` after manifest edits.
