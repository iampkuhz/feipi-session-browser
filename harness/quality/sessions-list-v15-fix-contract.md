# Sessions List v15 Fix Contract

Scope: sessions list page only.

Known issues:
1. Wide-screen layout is left-biased. Sessions list must be centered like dashboard/session-detail pages.
2. Header KPI `tokens` shows `0 tokens` while row tokens are non-zero.
3. `ROUNDS` sorting does not sort the data; the `ROUNDS` header is clipped.
4. Agent badges are all purple. Agent colors must be globally consistent:
   - Claude Code: purple
   - Codex: green
   - Qoder: orange
5. Remove Refresh button.
6. Footer must support page size selector:
   - default 20
   - selectable 100, 500, All
   - control placed at bottom-left.
