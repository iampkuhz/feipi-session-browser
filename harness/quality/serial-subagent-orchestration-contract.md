# Serial Subagent Orchestration Contract

## Mandatory mode

All tasks in this package must run as foreground subagents, one at a time.

```text
no background
no parallel
no nested subagents
one task per subagent
wait for completion before next task
```

## Main orchestrator

The main agent may only:

```text
copy seed overlay files
create OpenSpec scaffolding
launch serial foreground subagents
collect final reports
run final aggregate validation
```

The main agent must not perform large implementation edits directly.

## Per task

Each subagent receives:

```text
repo path
package path
task file path
allowed files/scope
validation commands
```

Do not pass the whole conversation history to subagents. Pass only the task file and minimal previous summary if necessary.

## Failure

If a task fails:

```text
stop sequence
run one repair subagent for the same task
pass failure output and git diff summary
continue only after repair passes
```
