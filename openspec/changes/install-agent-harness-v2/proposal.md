# Proposal

## Why

Install seed v2 harness into the current repository, completing the OpenSpec-first workflow setup with specs, archive directory, UI hifi references, and a formal change record.

## What changes

- Add `openspec/specs/` for current-behavior specs (agent-harness, claude-code-harness, mhtml-export, session-detail-ui).
- Add `openspec/changes/archive/.gitkeep` for completed change storage.
- Add `docs/ui/hifi/README.md` and extract hifi reference HTML set.
- Create this OpenSpec change record.

## Out of scope

- Product UI implementation changes.
- Overwriting existing CLAUDE.md, AGENTS.md, or .claude/settings.* — these are already richer in the current repo.
