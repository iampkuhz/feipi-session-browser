# OpenSpec

This repository uses OpenSpec-style spec-driven development.

```text
openspec/
  config.yaml        # workflow settings and policy configuration
  specs/             # current source of truth (git-tracked)
  schemas/           # validation schemas (git-tracked)
  templates/         # reusable templates (git-tracked)
  changes/           # local working state for proposed changes
    archive/         # completed/archived changes
```

Every non-trivial change starts under `openspec/changes/<change-id>/`.

## Policies

- **Tracked vs local**: `specs/`, `schemas/`, `templates/` are git-tracked and represent the approved canonical state. `changes/` is local working state and is not git-tracked by default.
- **Protected edit rule**: Protected directories (`specs/`, `schemas/`, `templates/`) must not be edited directly. An active change directory under `changes/` is required before modifying any protected file.
- **Final specs update**: After a change is approved and archived, its spec deltas are merged into `specs/` and the change directory is removed.

See `openspec/config.yaml` for the full machine-readable configuration.
