# Serial Subagent Runbook

Use subagents for bounded work, not uncontrolled parallelism.

Recommended sequence:

1. `repo-mapper` inspects current state.
2. `openspec-planner` creates or reviews change plan.
3. `task-slicer` creates task files.
4. `implementer` executes one task at a time.
5. `qa-verifier` validates each completed task.

The main agent should not busy-wait. It should delegate a bounded task and only continue after a completed report is returned.
