# Qoder Agent Rules

## Scope

- Applies to Qoder main agents and Qoder-launched subagents working in this repository.
- Defines the Qoder runtime entry in parallel with `.claude/` and `.codex/`.

## Startup Rules

- Read `.qoder/AGENTS.md` before planning or editing repository files.
- Read the task source and explicitly listed context files before reading optional references.
- Confirm `ACTIVE_CHANGE_ID` when protected paths, hooks, skills, harness, scripts, or tests are in scope.

## Delegation Rules

- Use `.qoder/agents/*` descriptions to choose the narrowest specialist for scoped work.
- Provide a complete handoff with `Goal`, `Task id`, `Task source`, `Allowed files/directories`, `Forbidden files/directories`, `Required context files`, `Expected output`, `Validation command`, and `Failure policy`.
- Assign a unique `agent_id` or equivalent instance id to each subagent instance.
- Do not delegate broad repository exploration, OpenSpec planning, or QA-only verification to an implementation specialist.

## Runtime Identity Rules

- Preserve distinct `client`, `session_id`, and `agent_id` values when invoking hooks or quality gates.
- Keep Qoder runtime evidence separate from Claude and Codex evidence, even for the same session id.
- Main aggregation of subagent evidence is limited to the same `client/session_id`; never merge evidence from another client or session.
- Parallel editing subagents must have non-overlapping write scopes.
- Treat missing runtime identity on mutation or protected writes as fail-closed, not read-only PASS.

## Protected Path Rules

- Treat `.qoder/`, `.claude/`, `.codex/`, `.agents/`, `skills/`, `harness/`, `scripts/`, `openspec/`, `src/session_browser/`, `tests/`, `AGENTS.md`, and `CLAUDE.md` as protected roots.
- Require a valid active OpenSpec change before modifying protected paths unless the task explicitly authorizes the scoped change.
- Modify only allowed paths and never copy task packs, real session data, secrets, tokens, caches, or personal local config into the repository.

## Validation Rules

- Run the validation command specified by the task exactly when provided.
- Treat failed, skipped, unavailable, excluded, or not-run required gates as non-PASS.
- Before final reporting, verify changed Qoder runtime files against `python3 scripts/gates/cli.py run --mode incremental --gate agentConfigurationPolicy` when available.

## Forbidden Actions

- Do not read `~/.claude`, `~/.codex`, or `~/.qoder` original session data.
- Do not modify `.env`, `.env.*`, `.mcp.json`, local settings, generated caches, or real runtime output outside the task scope.
- Do not add skip markers, delete required gates, bypass hook guards, or describe skipped checks as passing.

## Final Report Rules

- Return `PASS`, `FAIL`, or `BLOCKED` with concise evidence for each required validation.
- Subagent output must include `Status`, `Changed files`, `Validation`, `Effect checks`, and `Risks`; subagent `FAIL` or `BLOCKED` must not let main silently skip validation.
- List changed files and risks without pasting long logs or sensitive content.
- If blocked by missing paths, environment, or out-of-scope requirements, report the blocker instead of guessing or widening scope.
