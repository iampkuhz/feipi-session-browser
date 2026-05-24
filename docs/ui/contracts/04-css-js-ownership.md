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

### CSS：磁盘文件 vs 规范

所有规范 CSS 目标文件均已存在：

| # | File | Imported by |
|---|---|---|
| 1 | `style.css` (root) | `base.html` |
| 2 | `css/ui-primitives.css` | `sessions.html` |
| 3 | `css/sessions-list.css` | `sessions.html` |
| 4 | `css/dashboard.css` | `dashboard.html` |
| 5 | `css/session-detail.css` | `session.html` |
| 6 | `css/projects.css` | `projects.html` |
| 7 | `css/agents.css` | `agents.html` |
| 8 | `css/glossary.css` | `glossary.html` |
| 9 | `css/states.css` | `states.html` |

### JS：磁盘文件 vs 规范

| # | Canonical file | Status |
|---|---|---|
| 1 | `js/ui_primitives.js` | EXISTS |
| 2 | `js/dashboard.js` | EXISTS |
| 3 | `js/sessions-list.js` | EXISTS |
| 4 | `js/session-detail.js` | EXISTS |
| 5 | `js/projects.js` | EXISTS |
| 6 | `js/agents.js` | EXISTS |
| 7 | `js/glossary.js` | EXISTS |
| 8 | `js/states.js` | EXISTS |

共享工具 JS（非页面专属，由 base.html 加载）：
`app.js`、`data-table.js`、`keyboard.js`、`payload_viewer.js`、`timeline.js`、`view-state.js`。

### 备注

- `style.css` 体积较大，历史规则需要持续迁移到页面 CSS 和 primitives。
