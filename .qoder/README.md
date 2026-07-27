# Qoder Entry

`.qoder/` is the first-class Qoder entry for this repository. It is maintained in parallel with `.claude/` and `.codex/` and provides:

- policy entry: `.qoder/AGENTS.md`
- specialist descriptors: `.qoder/agents/*.md`
- shared skill aliases: `.qoder/skills/*`
- default agent selection: `.qoder/settings.json`

Qoder operators should start from `.qoder/AGENTS.md`, then select a specialist from `.qoder/agents/*` by its role and usage description. Shared skill bodies remain under `skills/authoring/`; `.qoder/skills` only exposes aliases without copying long skill content.
