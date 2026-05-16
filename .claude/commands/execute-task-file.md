# /execute-task-file

Execute one task file only.

Arguments: `$ARGUMENTS`

Rules:

- Read the task file.
- Read the linked OpenSpec change.
- Implement the exact scope only.
- Run the validation command in the task file.
- Update the task file with completion evidence.
- Stop after this task.
