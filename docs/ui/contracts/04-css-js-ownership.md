# 04 CSS / JS 所有权契约

## 规范 CSS

```text
src/session_browser/web/static/style.css                 # legacy dead code (not loaded; primitives migrated)
src/session_browser/web/static/css/ui-primitives.css      # shared primitives (canonical: .btn, .badge, .tabs, .pagination, .toast, .popover, .tooltip, .data-table, .empty-state, .breadcrumb)
src/session_browser/web/static/css/dashboard.css          # dashboard only
src/session_browser/web/static/css/sessions-list.css      # sessions list only
src/session_browser/web/static/css/session-detail.css     # session detail only
src/session_browser/web/static/css/projects.css           # projects list/detail only
src/session_browser/web/static/css/agents.css             # agents list/detail only
src/session_browser/web/static/css/glossary.css           # glossary only
src/session_browser/web/static/css/states.css             # 404/error/empty only
```

## 规范 JS

```text
src/session_browser/web/static/js/ui_primitives.js
src/session_browser/web/static/js/dashboard.js
src/session_browser/web/static/js/sessions-list.js
src/session_browser/web/static/js/session-detail.js
src/session_browser/web/static/js/projects.js
src/session_browser/web/static/js/agents.js
src/session_browser/web/static/js/glossary.js
src/session_browser/web/static/js/states.js
```

## 禁止新增

- `*-v17.css`
- `*-v18.css`
- `*-patch.css`
- `*-fix.css`
- `*-overlay.css`
- `session_browser_ui_vXX.js`

旧文件只能迁移、清理、停止引用，不能继续扩展。

---

## 当前状态

> Appended: 2026-05-21
> Task: T011 — Install CSS/JS Ownership Contract
> Source: `$HOME/Downloads/feipi-session-browser-ui-contract-taskpack/contracts/04-css-js-ownership.md`
> Cross-reference: `docs/ui/contracts/current-imports.md` (T004)

### CSS：磁盘文件 vs 规范

| # | File on disk | Status | Imported by |
|---|---|---|---|
| 1 | `style.css` (root, 243KB) | Canonical target — EXISTS, needs瘦身 | `base.html` |
| 2 | `css/ui-primitives.css` | Canonical target — EXISTS | `sessions.html` |
| 3 | `css/sessions-list.css` | Canonical target — EXISTS | `sessions.html` |
| 4 | `css/dashboard.css` | Canonical target — MISSING | — |
| 5 | `css/session-detail.css` | Canonical target — MISSING | — |
| 6 | `css/projects.css` | Canonical target — EXISTS | `projects.html` |
| 7 | `css/agents.css` | Canonical target — MISSING | — |
| 8 | `css/glossary.css` | Canonical target — MISSING | — |
| 9 | `css/states.css` | Canonical target — MISSING | — |

**Versioned/legacy CSS to clean up later (5 files):**

| File | Status | Notes |
|---|---|---|
| `dashboard-v16-tooltip-dots.css` | Orphaned (not imported) | Safe to remove |
| `dashboard-v16.css` | Imported by `dashboard.html` | Replace with `dashboard.css` |
| `session-browser-v15.css` | Imported by `base.html` | Replace with canonical files |
| `session-detail-timeline.css` | Imported by `session.html` | Migrate into `session-detail.css` |
| `session-detail-v18-polish-patch.css` | Orphaned (not imported) | Safe to remove |

### JS：磁盘文件 vs 规范

| # | Canonical file | Status | Notes |
|---|---|---|---|
| 1 | `js/ui_primitives.js` | EXISTS | — |
| 2 | `js/dashboard.js` | MISSING | Needs creation |
| 3 | `js/sessions-list.js` | MISSING | Needs creation |
| 4 | `js/session-detail.js` | MISSING | Needs creation |
| 5 | `js/projects.js` | EXISTS | Projects page search, sort, filter persistence |
| 6 | `js/agents.js` | MISSING | Needs creation |
| 7 | `js/glossary.js` | MISSING | Needs creation |
| 8 | `js/states.js` | EXISTS | 404/error pages — purely static, IIFE stub (T169) |

**Existing non-canonical JS (currently imported, not in contract list — 7 files):**

| File | Imported by | Notes |
|---|---|---|
| `app.js` | `base.html` | Global shell, not page-specific |
| `data-table.js` | `base.html` | Shared utility |
| `keyboard.js` | `base.html` | Shared utility |
| `payload_viewer.js` | `base.html` | Shared utility |
| `timeline.js` | `base.html` | Shared utility |
| `view-state.js` | `base.html` | Shared utility |
| `session_detail_timeline.js` | `session.html` | Page-specific, not in canonical list |

**Versioned/legacy JS cleaned up (2026-05):**

| File | Status | Notes |
|---|---|---|
| `session_browser_ui_v15.js` | Cleaned | Removed |
| `dashboard_v16.js` | Cleaned | Orphan removed |
| `session_detail_response_blocks_v12.js` | Cleaned | Orphan removed |
| `session_detail_timeline_v11.js` | Cleaned | Orphan removed |
| `session_detail_timeline_v17_reference.js` | Cleaned | Orphan removed |

### 汇总

| Metric | Count |
|---|---|
| Canonical CSS targets already exist | 4/9 (`style.css`, `ui-primitives.css`, `sessions-list.css`, `projects.css`) |
| Canonical CSS targets need creation | 5/9 |
| Versioned/legacy CSS files for later cleanup | 5 |
| CSS orphans (on disk, never imported) | 2 |
| Canonical JS targets already exist | 3/8 (`ui_primitives.js`, `projects.js`, `states.js`) |
| Canonical JS targets need creation | 5/8 |
| Non-canonical JS currently imported | 7 (may need reclassification) |
| Versioned/legacy JS files cleaned up | 5 |
| JS orphans (on disk, never imported) | 0 (cleaned) |

### 备注

- `style.css` at 243KB is far too large for "tokens + shell only" — will need significant瘦身 during migration.
- The contract's canonical JS list has no `app.js`/`data-table.js`/etc. These 7 shared utilities may either need to be absorbed into page-specific files or added to the canonical list as shared modules.
- `session_detail_timeline.js` is imported by `session.html` but is not in the canonical list; its functionality should migrate to `session-detail.js`.
