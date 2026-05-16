# Task File Lifecycle

Task files live under:

```text
tasks/changes/<change-id>/<NN>-<short-name>.md
```

A task file is executable only when it has:

- Goal
- Scope
- Files to inspect
- Files likely to change
- Required changes
- Validation command
- Acceptance criteria
- Manual QA checklist

Tasks should be small enough to finish and validate in one Claude Code run.
