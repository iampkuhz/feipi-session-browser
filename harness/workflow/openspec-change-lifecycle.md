# OpenSpec Change Lifecycle

Every non-trivial repository change follows:

```text
propose -> design -> task files -> implement serially -> validate -> archive
```

## Propose

Create:

```text
openspec/changes/<change-id>/proposal.md
openspec/changes/<change-id>/design.md
openspec/changes/<change-id>/tasks.md
openspec/changes/<change-id>/specs/<capability>/spec.md
```

## Implement

Implementation agents read the change and execute `tasks.md` sequentially. If tasks are too large, create task files under `tasks/changes/<change-id>/`.

## Archive

After validation, merge final behavior into `openspec/specs/` and move the change to `openspec/changes/archive/`.
