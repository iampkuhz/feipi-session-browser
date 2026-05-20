# Dashboard v16 Tooltip Dots Contract

Scope: dashboard page only.

This is an incremental refinement on `dashboard_v16_fix_prompt_pack`.

Required behavior:

1. Session Trend bar hover must render a structured tooltip.
2. Token Trend bar hover must render a structured tooltip.
3. Tooltip must contain one row for each agent and one total row:
   - Claude Code
   - Codex
   - Qoder
   - Total
4. Each agent row must have a small colored dot before the label:
   - Claude Code: purple
   - Codex: green
   - Qoder: orange
   - Total: neutral gray
5. Values must come from the same backend chart data used to render the bars.
6. Do not use a plain `title` attribute or a single unstructured data-tip string for the final implementation.
7. Keep the existing chart visual style; only refine tooltip internals.
