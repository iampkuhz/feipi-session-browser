# Repository Context

## Overview

feipi-session-browser is a local session browser for indexing and analyzing Claude Code, Codex, Qoder, and other local agent session history. It emphasizes traceability, payload visibility, UI diagnosis, and offline export.

## Tech Stack

- **Backend**: Python 3 (Flask-based web server)
- **Frontend**: HTML templates + CSS + vanilla JavaScript
- **Testing**: Playwright (E2E), pytest (unit)
- **Data**: JSONL session history files

## Directory Structure

| Path | Purpose |
|------|---------|
| `src/session_browser/` | Application source (server, templates, static assets) |
| `tests/` | Unit tests, Playwright E2E tests, fixture data |
| `scripts/` | Build, test, harness, and quality scripts |
| `scripts/agent_hooks/` | Claude Code lifecycle hooks (PreToolUse, PostToolUse, Stop, etc.) |
| `scripts/quality/` | Repo structure and health validators |
| `scripts/harness/` | Harness validation and doctor scripts |
| `.claude/` | Project-level Claude Code config, hooks, skills, commands, agents |
| `.agent/` | Local agent state (active change, evidence, task ledger) -- not committed |
| `openspec/` | OpenSpec specs, changes, config, and schema |
| `harness/` | Agent workflow documentation, context packs, templates |
| `docs/` | Development norms and UI specifications |
| `prompts/` | Input prompt packs -- NOT authoritative; route through `/change` |

## OpenSpec Workflow

All non-trivial changes go through `/change <requirement-path>`:

1. Creates `openspec/changes/<change-id>/` with proposal, design, tasks.
2. Records `.agent/active_change.json`.
3. Protected file edits require active change (enforced by PreToolUse hooks).
4. Edits auto-logged to `.agent/task-evidence/<change-id>.jsonl`.
5. QA verifier validates before stop.
6. Stop hook blocks if change is incomplete.

See `harness/workflow/change-lifecycle.md` and `harness/workflow/hook-enforcement.md`.

## Default Agents

| Agent | Purpose |
|-------|---------|
| openspec-planner | Design OpenSpec changes (proposal, design, tasks, spec deltas) |
| implementer | Execute one bounded task from tasks.md |
| qa-verifier | Final verification gate (workflow + technical correctness) |

Specialty agents under `.claude/agents/specialty/` are for domain-specific work.

## Local-Only State

The following are intentionally `.gitignore`'d:
- `.agent/` -- agent state (active change, evidence, task results)
- `openspec/changes/*` -- local change proposals (except `.gitkeep`)
- `reports/` -- non-baseline report output
- `test-results/`, `playwright-report/` -- test runner output

## Quality Gates

Run `bash scripts/harness/doctor.sh` for full health check.

Individual validators:
```bash
python3 scripts/harness/validate_harness_structure.py
python3 scripts/harness/validate_openspec_layout.py
python3 scripts/harness/check_no_unfinished_markers.py
python3 scripts/harness/validate_task_files.py
python3 scripts/quality/validate_repo_structure.py
```
