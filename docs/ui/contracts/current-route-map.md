# Current Route Map

> Snapshot date: 2026-05-21
> Source: `src/session_browser/web/routes.py` — `SessionBrowserHandler.do_GET()`
> Framework: Python `http.server.BaseHTTPRequestHandler` (no external web framework)

## 1. Blueprint / Module Summary

There is **no blueprint system** — all routes are handled by a single class
`SessionBrowserHandler(BaseHTTPRequestHandler)` in one file.

| Module | Route Prefix | Count |
|---|---|---|
| Dashboard | `/`, `/dashboard` | 1 |
| Projects | `/projects`, `/projects/<key>` | 2 |
| Sessions | `/sessions`, `/sessions/<agent>/<id>` | 2 |
| Agents | `/agents`, `/agents/<agent>` | 2 |
| Glossary | `/glossary` | 1 |
| API | `/api/sessions/...` | 1 |
| Static | `/static/...` | 1 |
| Favicon | `/favicon.ico` | 1 |
| **Total** | | **11** |

## 2. Complete Route Table

| URL Pattern | HTTP Method | Handler Function | Template Rendered | Notes |
|---|---|---|---|---|
| `/` | GET | `_serve_dashboard()` | `dashboard.html` | Also serves `/dashboard` |
| `/favicon.ico` | GET | `_send_empty(204)` | — (no template) | Returns 204 No Content |
| `/projects` | GET | `_serve_projects()` | `projects.html` | Lists all projects (limit 100) |
| `/projects/<project_key>` | GET | `_serve_project(project_key)` | `project.html` | `project_key` is URL-decoded |
| `/sessions` | GET | `_serve_all_sessions()` | `sessions.html` / `partials/sessions_grid.html` | Supports pagination, filters, sort; AJAX partial when `X-Requested-With: XMLHttpRequest` |
| `/sessions/<agent>/<session_id>` | GET | `_serve_session(agent, session_id, export_mhtml)` | `session.html` | `agent` and `session_id` are URL-decoded; `?export=mhtml` triggers MHTML export context |
| `/sessions/<bare_id>` | GET | `_serve_all_sessions()` | `sessions.html` | Fallback: single-segment paths after `/sessions/` redirect to full session list |
| `/agents` | GET | `_serve_agents()` | `agents.html` | Lists all agents with efficiency metrics |
| `/agents/<agent>` | GET | `_serve_agent(agent)` | `agent.html` | `agent` is URL-decoded |
| `/glossary` | GET | `_serve_glossary()` | `glossary.html` | Token glossary reference page |
| `/static/<filename>` | GET | `_serve_static(filename)` | — (static file) | Serves from `web/static/`; content-type: CSS/JS/plain |
| `/api/sessions/<agent>/<session_id>/payload/<payload_id>` | GET | `_serve_api_payload_path(path)` → `_serve_api_payload(...)` | — (JSON API) | Returns full untruncated payload as JSON |
| *(unmatched)* | GET | `_send_404()` | `404.html` | Catch-all 404 |
| *(exception)* | — | `_send_500(error)` | `error.html` | Error handler (500) |

## 3. API Endpoints (JSON)

| URL Pattern | Handler | Response | Status Codes |
|---|---|---|---|
| `/api/sessions/<agent>/<session_id>/payload/<payload_id>` | `_serve_api_payload()` | `{"payload": ...}` full untruncated payload | 200, 404 (not found), 400 (invalid path) |
| `/sessions` (AJAX) | `_serve_all_sessions()` (partial) | HTML fragment from `partials/sessions_grid.html` | 200 (Content-Type: text/html) |

The sessions AJAX endpoint returns **HTML**, not JSON. It is detected by the
`X-Requested-With: XMLHttpRequest` header and renders `partials/sessions_grid.html`
as a partial to replace `#sessions-grid-container` on the sessions page.

## 4. Static File Mount Points

| URL Prefix | Filesystem Path | Content Types |
|---|---|---|
| `/static/` | `src/session_browser/web/static/` | `.css` → `text/css`, `.js` → `application/javascript`, else → `text/plain` |

### Static Files on Disk

**CSS (7 files):**
- `css/dashboard-v16-tooltip-dots.css`
- `css/dashboard-v16.css`
- `css/session-browser-v15.css`
- `css/session-detail-timeline.css`
- `css/session-detail-v18-polish-patch.css`
- `css/sessions-list.css`
- `css/ui-primitives.css`

**JS (9 files):**
- `js/app.js`
- `js/data-table.js`
- `js/keyboard.js`
- `js/payload_viewer.js`
- `js/session_detail_timeline.js`
- `js/timeline.js`
- `js/ui_primitives.js`
- `js/view-state.js`

> Note: `dashboard_v16.js`, `session_browser_ui_v15.js`, `session_detail_response_blocks_v12.js`, `session_detail_timeline_v11.js`, `session_detail_timeline_v17_reference.js` were cleaned up in 2026-05.

**Root:**
- `style.css`

## 5. Cross-Reference with Template Map (T005)

### Templates without Routes (Dead Templates)

| Template File | Type | Status |
|---|---|---|
| `base.html` | Layout | **Not dead** — extended by all 10 page templates via `{% extends %}` |
| `components/*.html` (13 files) | Macro libraries | **Not dead** — imported or used inline by page templates |
| `partials/sessions_grid.html` | AJAX partial | **Active** — served via AJAX on `/sessions` |

**Result: No dead templates.** Every template file is either:
- Directly rendered by a route handler
- Extended by a page template (`base.html`)
- Imported by a page template (`components/badge.html` → `glossary.html`)
- Served as an AJAX partial (`partials/sessions_grid.html`)

### Routes without Templates

| Route | Template | Notes |
|---|---|---|
| `/favicon.ico` | — | Returns 204 No Content (intentional, no template needed) |
| `/static/<file>` | — | Serves static files from disk |
| `/api/sessions/.../payload/...` | — | Returns JSON (API endpoint) |
| `/sessions` (AJAX) | `partials/sessions_grid.html` | HTML fragment, not JSON |

**Result: No orphaned routes.** All non-template routes have clear purpose
(favicon, static files, JSON API).

## 6. Summary

| Metric | Count |
|---|---|
| Total route patterns | 11 (+ catch-all 404) |
| Page templates rendered | 9 unique (`dashboard`, `projects`, `project`, `sessions`, `session`, `agents`, `agent`, `glossary`, `404`, `error`) |
| AJAX partial templates | 1 (`partials/sessions_grid.html`) |
| JSON API endpoints | 1 (`/api/sessions/.../payload/...`) |
| Static file mount points | 1 (`/static/`) |
| Routes without templates | 3 (favicon, static, API — all intentional) |
| Templates without routes | 0 (base.html and components are used via extends/import) |
| Blueprints/Modules | 0 (single handler class) |
| HTTP methods used | GET only |

### Risk Notes

1. **No POST/PUT/DELETE routes** — the entire app is read-only GET. This is
   intentional for a session browser, but means there is no CSRF protection
   surface to worry about.

2. **Fallback ambiguity** — `/sessions/<single_segment>` falls through to
   `_serve_all_sessions()` instead of 404. This is a silent fallback that
   could mask broken links.

3. **AJAX detection** relies on `X-Requested-With: XMLHttpRequest` header,
   which is a convention (not a security boundary). The same URL (`/sessions`)
   returns different content types based on this header.
