# Current Template Map

> Snapshot date: 2026-05-21
> Source: `src/session_browser/web/templates/`
> Route definitions: `src/session_browser/web/routes.py`

## 1. Complete Template File List

### Page Templates (10 files)

| File | Type | Description |
|---|---|---|
| `base.html` | Layout | Root layout — sidebar, topbar, content shell |
| `dashboard.html` | Page | Dashboard / home page |
| `projects.html` | Page | Project list |
| `project.html` | Page | Single project detail |
| `sessions.html` | Page | Session list with filters and pagination |
| `session.html` | Page | Single session detail (largest template) |
| `agents.html` | Page | Agent list with efficiency metrics |
| `agent.html` | Page | Single agent detail |
| `glossary.html` | Page | Token glossary reference |
| `404.html` | Error | 404 not found page |
| `error.html` | Error | Generic error page (500) |

### Components (13 files)

| File | Kind | Description |
|---|---|---|
| `components/badge.html` | Macro library | Badge variants: status, token, agent, tool, anomaly |
| `components/data_table.html` | Macro library | Data table + project_row macro |
| `components/metrics_strip.html` | Macro library | Metrics strip + metric_item |
| `components/page_header.html` | Macro library | Page header macro |
| `components/sessions_list_components.html` | Macro library | Page title, active filters, table header, pagination footer |
| `components/timeline.html` | Macro library | Timeline node, content, container macros |
| `components/token_bar.html` | Macro library | Token bar chart macro |
| `components/ui_primitives.html` | Macro library | Buttons, selects, stat pills, sortable table headers, token total |
| `components/viewer.html` | Macro library | Content viewer + payload viewer macros |

### Session Detail Components (4 files)

| File | Version | Description |
|---|---|---|
| `components/session_detail_primitives.html` | Current | pill, button, metric_cell, token_bar, round_status, timeline_dot, payload_note |
| `components/session_detail_primitives_v12.html` | v12 (legacy) | Extended set with sub_metric_cell, reasoning token_bar, block_pill |
| `components/session_detail_timeline.html` | Current | hero, trace_header, round_summary, llm_call_card, tool_batch, subagent_block, round_detail, trace_round, payload_sources, payload_modal |
| `components/session_detail_timeline_v12.html` | v12 (legacy) | Extended: user_message_card, sub_tool_group in addition to current macros |

### Partials (1 file)

| File | Description |
|---|---|
| `partials/sessions_grid.html` | Sessions grid rows + pagination footer — loaded via AJAX into `sessions-grid-container` |

---

## 2. Template Inheritance Tree

```
base.html (root layout)
├── 404.html
├── agent.html
├── agents.html
├── dashboard.html
├── error.html
├── glossary.html
├── project.html
├── projects.html
├── session.html
└── sessions.html
```

All 10 page templates extend `base.html`. No multi-level inheritance (page templates do not extend other pages).

### Base Template Block Points

`base.html` defines the following blocks for pages to override:

| Block | Purpose |
|---|---|
| `title` | Page title (default: "Agent Run Profiler") |
| `head_extra` | Extra `<head>` content (CSS, meta tags) |
| `script_extra` | Extra scripts before `</head>` |
| `shell_class` | Additional classes on `.shell` div |
| `sidebar_nav` | Sidebar navigation links |
| `sidebar_extra` | Content below sidebar nav (e.g., round map) |
| `breadcrumb` | Topbar breadcrumb navigation |
| `topbar_toggles` | Density toggle button |
| `topbar_actions` | Extra topbar actions |
| `content` | Main page content |
| `legacy_payload_modal` | Payload modal (overridden by session.html) |

---

## 3. Include / Import Dependency Graph

### Page Templates with Imports

| Page Template | Imports From | Macros Used |
|---|---|---|
| `glossary.html` | `components/badge.html` | `badge`, `status_success`, `status_warning`, `status_error`, `status_info`, `status_muted`, `token_input`, `token_cache_read`, `token_cache_write`, `token_output`, `agent_claude`, `agent_codex`, `agent_qoder`, `agent_for`, `tool`, `anomaly` |

All other page templates (`dashboard.html`, `projects.html`, `project.html`, `sessions.html`, `session.html`, `agent.html`, `agents.html`, `404.html`, `error.html`) do **not** use `{% include %}` or `{% from ... import %}`. They rely on inline template code or client-side rendering.

### Partial Templates

| Partial | Consumption Method |
|---|---|
| `partials/sessions_grid.html` | Loaded via AJAX (`/api/sessions/...`), replaced into `#sessions-grid-container` on the sessions page |

### Component Self-References (Documentation Pattern)

Several component files contain a self-referencing `{% from %}` at the top for standalone testing/documentation purposes:

| Component File | Self-Reference |
|---|---|
| `components/badge.html` | `{% from "components/badge.html" import badge %}` |
| `components/data_table.html` | `{% from "components/data_table.html" import data_table %}` |
| `components/metrics_strip.html` | `{% from "components/metrics_strip.html" import metrics_strip, metric_item %}` |
| `components/page_header.html` | `{% from "components/page_header.html" import page_header %}` |
| `components/timeline.html` | `{% from "components/timeline.html" import timeline_node, timeline_node_content %}` |

These are documentation/standalone-test annotations, not cross-file dependencies.

---

## 4. Macro Inventory

### components/badge.html

| Macro | Parameters | Description |
|---|---|---|
| `badge` | label, variant, value, extra_class, tooltip | Core badge renderer |
| `status_success` | label | Green status badge |
| `status_warning` | label | Yellow status badge |
| `status_error` | label | Red status badge |
| `status_info` | label | Blue info badge |
| `status_muted` | label | Gray muted badge |
| `token_input` | label | Fresh input token badge |
| `token_cache_read` | label | Cache read token badge |
| `token_cache_write` | label | Cache write token badge |
| `token_output` | label | Output token badge |
| `token_reasoning` | label | Reasoning token badge |
| `agent_claude` | label | Claude Code agent badge |
| `agent_codex` | label | Codex agent badge |
| `agent_qoder` | label | Qoder agent badge |
| `agent_for` | name, label | Generic agent badge by name |
| `tool` | name | Tool name badge |
| `anomaly` | label, level | Anomaly level badge |

### components/data_table.html

| Macro | Parameters | Description |
|---|---|---|
| `data_table` | id, columns, extra_classes, wrapper_id, empty_message, selectable, sort_key, sort_dir | Generic data table |
| `project_row` | p | Single project row rendering |

### components/metrics_strip.html

| Macro | Parameters | Description |
|---|---|---|
| `metric_item` | label, value, status, mono, tooltip | Single metric display item |
| `metrics_strip` | items=None | Horizontal metrics strip container |

### components/page_header.html

| Macro | Parameters | Description |
|---|---|---|
| `page_header` | title, description, back_url, actions_html, extra_class, title_tooltip | Standard page header with optional back link and actions |

### components/sessions_list_components.html

| Macro | Parameters | Description |
|---|---|---|
| `page_title` | total_sessions, total_projects, total_tokens | Sessions page title block |
| `active_filters` | session_id, agent, project, model, count_label, remove_urls | Active filter display |
| `table_header` | sort_key, sort_dir, sort_urls | Sortable table header row |
| `footer` | start_label, end_label, total_label, prev_url, next_url, page_size_urls, current_page_size | Pagination footer |

### components/timeline.html

| Macro | Parameters | Description |
|---|---|---|
| `timeline_node_content` | node | Content for a single timeline node |
| `timeline_node` | node | Timeline node wrapper with dot and content |
| `timeline_container` | nodes, id_prefix | Full timeline container |

### components/token_bar.html

| Macro | Parameters | Description |
|---|---|---|
| `token_bar` | fresh, cache_read, cache_write, output, reasoning | Token distribution bar chart |

### components/ui_primitives.html

| Macro | Parameters | Description |
|---|---|---|
| `btn` | label, variant, size, type, href, extra_class | Generic button |
| `select_control` | label, name, options, selected, extra_class | Select dropdown |
| `stat_pill` | value, label | Statistic pill |
| `th_static` | label | Non-sortable table header cell |
| `th_sort` | label, key, sort_key, sort_dir, href | Sortable table header cell |
| `token_total` | total, fresh_pct, cache_pct, output_pct | Token total with bar |

### components/viewer.html

| Macro | Parameters | Description |
|---|---|---|
| `viewer` | content, mode, title, id_suffix, max_height | Generic content viewer |
| `payload_viewer` | parts_data, title | Full payload viewer with tabs |

### components/session_detail_primitives.html (Current)

| Macro | Parameters | Description |
|---|---|---|
| `pill` | label, tone, size, extra_class | Pill label |
| `button` | label, action, variant, size, payload_id, extra_class, attrs | Action button |
| `metric_cell` | label, value, tone | Metric value cell |
| `token_bar` | fresh_pct, cache_pct, out_pct | Token bar (inline variant) |
| `round_status` | label, tone | Round status indicator |
| `timeline_dot` | tone | Timeline dot indicator |
| `payload_note` | text, tone | Payload note text |

### components/session_detail_timeline.html (Current)

| Macro | Parameters | Description |
|---|---|---|
| `hero` | summary, metrics, issues | Session hero section |
| `trace_header` | — | Trace view header |
| `round_summary` | row | Round summary card |
| `llm_call_card` | call | LLM call card |
| `tool_batch` | batch | Tool call batch group |
| `subagent_block` | block | Sub-agent execution block |
| `round_detail` | row | Round detail expandable section |
| `trace_round` | row | Trace round renderer |
| `payload_sources` | sources | Payload source references |
| `payload_modal` | — | Payload modal dialog |

---

## 5. Route-to-Template Mapping

| URL Pattern | Route Handler | Template | HTTP Method |
|---|---|---|---|
| `/` or `/dashboard` | `_serve_dashboard()` | `dashboard.html` | GET |
| `/projects` | `_serve_projects()` | `projects.html` | GET |
| `/projects/<project_key>` | `_serve_project(project_key)` | `project.html` | GET |
| `/sessions` | `_serve_sessions()` | `sessions.html` | GET |
| `/sessions/<agent>/<session_id>` | `_serve_session(agent, session_id)` | `session.html` | GET |
| `/agents` | `_serve_agents()` | `agents.html` | GET |
| `/agents/<agent>` | `_serve_agent(agent)` | `agent.html` | GET |
| `/glossary` | `_serve_glossary()` | `glossary.html` | GET |
| `/api/sessions/<...>` | `_serve_api_payload_path(path)` | `partials/sessions_grid.html` (AJAX partial) | GET |
| (unmatched) | `_send_404()` | `404.html` | GET |
| (error handler) | `_send_500(error)` | `error.html` | — |

### Static Assets

| URL Pattern | Handler |
|---|---|
| `/static/*` | `_serve_static(path)` — serves from `static/` directory |

---

## 6. Shared Components / Macros Summary

### Cross-Page Reusable Macros

| Macro Source | Used By Pages | Notes |
|---|---|---|
| `components/badge.html` | `glossary.html` (direct import); other pages use inline badge HTML | Only glossary page formally imports these |
| `components/sessions_list_components.html` | `sessions.html` (inline, not imported) | Macros defined but used inline on sessions page |

### Observations

1. **No formal component imports on most pages**: Most page templates do not `{% include %}` or `{% from %}` components. They either:
   - Use inline template code that duplicates component patterns
   - Rely on `base.html` block inheritance for structure
   - Use client-side JS for dynamic content

2. **Legacy versioned components**: Four session-detail component files carry version suffixes (v12). The "current" (unversioned) versions are `session_detail_primitives.html` and `session_detail_timeline.html`. Legacy v15/v17 component files were cleaned up in 2026-05.

3. **AJAX partial**: `partials/sessions_grid.html` is the only template served as an AJAX partial (not via full page render). It is loaded by the sessions page's client-side JS for pagination/filtering.

4. **Self-contained page templates**: Each page template (except `glossary.html`) is self-contained — it extends `base.html` and defines all its markup inline without importing other templates.

5. **Component macros are defined but underutilized**: Many macros in `components/*.html` are defined and available for import, but most page templates do not import them. The badge component library is the most complete and most formally imported (by `glossary.html`).
