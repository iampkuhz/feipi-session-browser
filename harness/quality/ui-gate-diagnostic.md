# UI Gate Diagnostic Boundary

## Overview

The quality gate system has two tiers:

| Tier | Type | Trigger | Examples |
|---|---|---|---|
| **Deterministic gates** | Automated scripts | Stop hook, quality runner | static CSS check, template contract pytest, browser layout gate |
| **On-demand LLM diagnostic** | Manual trigger | User invokes `/diagnose-ui-gate` | root cause analysis, fix suggestion |

## Deterministic Gates

These run automatically and can block the stop hook:

- `scripts/quality/check_session_detail_static.py` — static CSS/template text checks
- `scripts/quality/run_session_detail_layout_gate.py` — Playwright computed layout metrics
- `tests/test_session_detail_layout_contract.py` — template structure pytest
- `scripts/quality/run_quality_gate.py` — unified runner that orchestrates all gates

**Properties:**
- No LLM inference required.
- Output is structured JSON.
- Results written to `.agent/quality/<change-id>/`.
- Stop hook reads these artifacts to enforce gates.

## On-Demand LLM Diagnostic

Triggered by `/diagnose-ui-gate` command.

**Properties:**
- Manual trigger only — never called by stop hook.
- Reads deterministic gate output JSON, then uses LLM reasoning to interpret failures.
- Can suggest fixes but does NOT modify files unless user explicitly asks.
- Cannot override or伪造 deterministic gate results.

**Allowed to infer:**
- Complex CSS cascade root cause.
- Difference between failure screenshot and layout intent.
- Trade-offs between multiple fix approaches.
- Which files are most likely relevant.

**NOT allowed to伪造:**
- `quality-gate-summary.json` PASS status.
- Browser computed metrics.
- Screenshot artifacts.
- Stop hook evidence.

## Forbidden

- Stop hook MUST NOT call LLM diagnostic commands.
- Stop hook MUST NOT start subagents, call Claude, Codex, or Qoder.
- Stop hook MUST NOT run browser tests directly.
- LLM diagnostic MUST NOT replace deterministic gates with subjective judgement.

## Diagnostic Command

Location: `.claude/commands/diagnose-ui-gate.md`

Usage:
```
/diagnose-ui-gate           # uses current active change
/diagnose-ui-gate fix-xyz   # specific change id
```
