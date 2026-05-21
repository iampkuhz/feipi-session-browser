# UI Import Snapshot

> Generated: 2026-05-21
> Task: T004 — Snapshot current UI imports
> Working directory: `/Users/zhehan/Documents/tools/llm/feipi-session-browser`

---

## 1. CSS Files on Disk

| # | File | Size |
|---|------|------|
| 1 | `static/css/dashboard-v16-tooltip-dots.css` | on disk |
| 2 | `static/css/dashboard-v16.css` | on disk |
| 3 | `static/css/session-browser-v15.css` | on disk |
| 4 | `static/css/session-detail-timeline.css` | on disk |
| 5 | `static/css/session-detail-v18-polish-patch.css` | on disk |
| 6 | `static/css/sessions-list.css` | on disk |
| 7 | `static/css/ui-primitives.css` | on disk |
| 8 | `static/style.css` (legacy root) | 243 KB |

## 2. JS Files on Disk

| # | File |
|---|------|
| 1 | `static/js/app.js` |
| 2 | `static/js/dashboard_v16.js` |
| 3 | `static/js/data-table.js` |
| 4 | `static/js/keyboard.js` |
| 5 | `static/js/payload_viewer.js` |
| 6 | `static/js/session_browser_ui_v15.js` |
| 7 | `static/js/session_detail_response_blocks_v12.js` |
| 8 | `static/js/session_detail_timeline_v11.js` |
| 9 | `static/js/session_detail_timeline.js` |
| 10 | `static/js/timeline.js` |
| 11 | `static/js/ui_primitives.js` |
| 12 | `static/js/view-state.js` |

## 3. CSS Imports in Templates

| Template | CSS File Imported |
|----------|------------------|
| `base.html:9` | `/static/style.css` |
| `base.html:10` | `/static/css/session-browser-v15.css` |
| `dashboard.html:11` | `/static/css/dashboard-v16.css` |
| `sessions.html:19` | `/static/css/ui-primitives.css` |
| `sessions.html:20` | `/static/css/sessions-list.css` |
| `session.html:30` | `/static/css/session-detail-timeline.css` |

## 4. JS Imports in Templates

| Template | JS File Imported |
|----------|-----------------|
| `base.html:124` | `/static/js/view-state.js` |
| `base.html:125` | `/static/js/payload_viewer.js` |
| `base.html:126` | `/static/js/app.js` |
| `base.html:127` | `/static/js/data-table.js` |
| `base.html:128` | `/static/js/timeline.js` |
| `base.html:129` | `/static/js/keyboard.js` |
| `base.html:130` | `/static/js/session_browser_ui_v15.js` |
| `session.html:34` | `/static/js/session_detail_timeline.js` |
| `sessions.html:178` | `/static/js/ui_primitives.js` |

## 5. Import Statements in JS Files

No ES module `import` or `require()` statements found in any JS files under `static/js/`. All scripts are loaded via `<script>` tags in templates and share the global scope.

## 6. Coverage Summary

### CSS Coverage

| File | Imported? | By |
|------|-----------|-----|
| `style.css` | Yes | `base.html` |
| `session-browser-v15.css` | Yes | `base.html` |
| `dashboard-v16.css` | Yes | `dashboard.html` |
| `ui-primitives.css` | Yes | `sessions.html` |
| `sessions-list.css` | Yes | `sessions.html` |
| `session-detail-timeline.css` | Yes | `session.html` |
| `dashboard-v16-tooltip-dots.css` | **NO** | — |
| `session-detail-v18-polish-patch.css` | **NO** | — |

### JS Coverage

| File | Imported? | By |
|------|-----------|-----|
| `app.js` | Yes | `base.html` |
| `data-table.js` | Yes | `base.html` |
| `keyboard.js` | Yes | `base.html` |
| `payload_viewer.js` | Yes | `base.html` |
| `timeline.js` | Yes | `base.html` |
| `view-state.js` | Yes | `base.html` |
| `session_browser_ui_v15.js` | Yes | `base.html` |
| `session_detail_timeline.js` | Yes | `session.html` |
| `ui_primitives.js` | Yes | `sessions.html` |

## 7. Orphaned Files

### CSS Orphans (on disk, never imported)
1. `dashboard-v16-tooltip-dots.css` — zero references anywhere in templates or JS
2. `session-detail-v18-polish-patch.css` — zero references anywhere in templates or JS

### JS Orphans (on disk, never imported)
- None. All orphaned JS files were cleaned up in 2026-05.

### Imported but Missing (404 risk)
- None. All imported files exist on disk.

## 8. Notes

- `dashboard.html` has inline JS that references `dashboard-tooltip` class (lines 102, 112) but does not import `dashboard-v16-tooltip-dots.css`.
- All JS files use global scope (no ES modules); loaded via classic `<script>` tags.
- `base.html` is the primary layout template and imports the largest set of shared assets.
