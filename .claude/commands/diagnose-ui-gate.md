# diagnose-ui-gate

You are diagnosing a failed deterministic UI quality gate.

## Rules

- Do NOT modify files unless the user explicitly asks you to fix.
- Do NOT replace deterministic gates with subjective judgement.
- Do NOT treat screenshots as sufficient; read JSON metrics first.
- This is an on-demand diagnostic command, NOT a stop hook gate.

## Input

- Optional argument: change id.
- If no argument, read `ACTIVE_CHANGE_ID` env or `.agent/active-change`.
- Read `.agent/quality/<change-id>/quality-gate-summary.json`.
- Read each failed gate artifact referenced in `blockingFailures` / `artifacts`.

## Procedure

1. **Read the quality gate summary** at `.agent/quality/<change-id>/quality-gate-summary.json`.
   - Identify which gates failed (staticCssContract, templateContract, browserLayout, pytest).
   - Read `blockingFailures` for failure codes and messages.

2. **Read the specific gate result JSON** referenced in artifacts.
   - For `staticCssContract`: read `check_session_detail_static.py` output.
   - For `browserLayout`: read `session-detail-layout-result.json` for computed metrics.

3. **Map failure codes to root causes**:
   - `MISSING_PHASE1_HIDE_LEFT_OVERRIDE` → cascade conflict in CSS specificity.
   - `MISSING_PHASE1_MAIN_GRID_COLUMN` → .main lacks grid-column: 1 / -1.
   - `HERO_MAIN_STILL_TWO_COLUMN` → hero layout still uses two columns.
   - `HERO_TITLE_UNSAFE_ANYWHERE_WRAP` → title uses overflow-wrap: anywhere.
   - `SHELL_ZERO_COLUMN` → body.hide-left overrides phase1-shell, .main in 0px column.
   - `MAIN_WIDTH_TOO_SMALL` → computed width below 1200px threshold.
   - `TITLE_OVERLAPS_KPIS` → title and KPIs DOM order or CSS positioning issue.
   - `HORIZONTAL_SCROLL` → content wider than viewport.

4. **Inspect the smallest relevant source files**:
   - CSS: `src/session_browser/web/static/style.css`
   - Templates: `src/session_browser/web/templates/base.html`, `session.html`
   - Focus on the selectors mentioned in `nextInspection`.

5. **Propose minimal fix**:
   - Identify the exact CSS rule or template change needed.
   - Explain why this is the minimal change (don't refactor).
   - State whether this is deterministic or inference-based.

6. **Provide exact validation command**:
   - `python3 scripts/quality/run_quality_gate.py --target session-detail`
   - Or the specific gate: `python3 scripts/quality/check_session_detail_static.py`

## Output format

```
Observed failure(s):
- [gate]: [failure code] - [message]

Likely root cause:
- [explanation]

Files to inspect:
- [file path] — [what to look for]

Minimal fix plan:
1. [specific change]
2. [specific change]

Validation command:
python3 scripts/quality/run_quality_gate.py --target session-detail

Deterministic vs inference: [state which parts are deterministic and which are LLM inference]
```
