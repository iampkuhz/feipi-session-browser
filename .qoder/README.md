# Qoder Runtime Entry

`.qoder/` is the first-class Qoder runtime entry for this repository. It is maintained in parallel with `.claude/` and `.codex/` and provides:

- policy entry: `.qoder/AGENTS.md`
- Session Runtime lifecycle: `docs/agent-runtime.md`
- specialist descriptors: `.qoder/agents/*.md`
- shared skill aliases: `.qoder/skills/*`
- hook wiring: `.qoder/settings.json` 直接调用 `scripts/harness/hook_dispatch.py`

Qoder operators must start by reading `.qoder/AGENTS.md`, then select a specialist from `.qoder/agents/*` by its role and usage description. Shared skill bodies remain under `skills/authoring/`; `.qoder/skills` only exposes aliases so the registry can verify runtime parity without copying long skill content.
