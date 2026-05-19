# /openspec-propose

Create a new OpenSpec change. Do not implement code.

Arguments: `$ARGUMENTS`

Steps:

1. Inspect `openspec/specs/` and relevant repository files.
2. Create `openspec/changes/<change-id>/proposal.md`.
3. Create `design.md` if there are UI, architecture, data model, or export changes.
4. Create `tasks.md` with small, verifiable tasks.
5. Create delta specs under `openspec/changes/<change-id>/specs/`.
6. Run `python3 scripts/harness/validate_openspec_layout.py`.
7. Report the created files and validation result.
