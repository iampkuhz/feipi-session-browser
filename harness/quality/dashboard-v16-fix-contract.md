# Dashboard v16 Fix Contract

Scope: dashboard page only.

Required changes:

1. Upgrade hero UI:
   - More polished, compact, centered card.
   - Left: Local badge, Dashboard title, short Chinese description, chips.
   - Right: KPI mini cards for Projects, Agents, Sessions, Errors.
   - Hero must be visually stronger than chart titles.

2. Reduce Session Trend typography:
   - Chart title must be smaller than hero title.
   - Recommended: hero title 18px, chart title 14px.

3. Remove top-right compact/tight mode button:
   - No density/theme toggle on dashboard.

4. Footer must stay at page bottom:
   - Use flex page layout with `main { min-height: 100vh; display:flex; flex-direction:column; }`
   - Content flexes; footer uses `margin-top:auto`.
   - Do not use `position: fixed` unless explicitly required.

5. Session Trend hover:
   - Hover over each day bar shows Claude Code / Codex / Qoder / Total session count.

6. Add Token Trend chart:
   - Same chart style as Session Trend.
   - Per-day stacked bars by agent.
   - Values are token totals per agent per day.
   - Hover shows Claude Code / Codex / Qoder / Total token values.

7. Delete Recent Activity:
   - Dashboard should only show hero + charts.
