# Design

The harness v2 installation is separated into three concerns:

1. **Specs under `openspec/specs/`** — capture current behavior that was previously only described in context files.
2. **Archive directory** — enable the change lifecycle (changes → archive).
3. **UI hifi references** — place high-fidelity HTML references for UI work.

Existing files (CLAUDE.md, AGENTS.md, .claude/settings.*) are inspected for diffs and preserved if the current repo version is richer. No product code is modified.
