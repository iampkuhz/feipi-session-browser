# /openspec-apply

Apply an existing OpenSpec change by executing `tasks.md` sequentially.

Arguments: `$ARGUMENTS`

Rules:

- Read `proposal.md`, `design.md`, `tasks.md`, and delta specs first.
- Execute only the next incomplete task unless explicitly asked otherwise.
- Mark completed tasks in `tasks.md`.
- Run the task-specific validation before moving to the next task.
- Do not broaden scope beyond the change.
