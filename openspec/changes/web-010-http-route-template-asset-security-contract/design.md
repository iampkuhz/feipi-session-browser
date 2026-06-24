# Design: HTTP、Route、Template、Asset 与安全契约清单

## 1. 概述

本 design 冻结 S5 stage 中 Java Web 模块必须实现的全部 HTTP、路由、模板、静态资源和安全契约。审计覆盖以下 Python 模块：

- `src/session_browser/web/routes.py` (HTTP handler, 11 page routes + 5 API routes)
- `src/session_browser/web/template_env.py` (Jinja2 environment, 30+ filters)
- `src/session_browser/web/safe_render.py` (XSS 防护, 3 safe filters)
- `src/session_browser/web/mhtml.py` (MHTML export, CSS/JS bundling)
- `src/session_browser/web/view_models.py` (8 TypedDict contracts)
- `src/session_browser/web/presenters/dashboard.py`
- `src/session_browser/web/presenters/projects.py`
- `src/session_browser/web/presenters/sessions.py`
- `src/session_browser/web/presenters/session_detail.py`
- `src/session_browser/web/renderers/markdown.py`
- `src/session_browser/web/renderers/llm_blocks.py`
- `src/session_browser/web/session_detail/` (7 sub-modules)
- `src/session_browser/web/templates/` (29 HTML templates)
- `src/session_browser/web/static/` (52 static assets: CSS, JS, images)

## 2. HTTP Route 契约

### 2.1 Page Routes

| 契约 ID | Method | Path | Handler | Template | Content-Type | Status |
|---------|--------|------|---------|----------|-------------|--------|
| R-DASHBOARD | GET | `/` | `_serve_dashboard` | `dashboard.html` | `text/html; charset=utf-8` | 200 |
| R-DASHBOARD-ALT | GET | `/dashboard` | `_serve_dashboard` | `dashboard.html` | `text/html; charset=utf-8` | 200 |
| R-PROJECTS | GET | `/projects` | `_serve_projects` | `projects.html` | `text/html; charset=utf-8` | 200 |
| R-PROJECT-DETAIL | GET | `/projects/{key}` | `_serve_project` | `project.html` | `text/html; charset=utf-8` | 200 |
| R-SESSIONS | GET | `/sessions` | `_serve_all_sessions` | `sessions.html` | `text/html; charset=utf-8` | 200 |
| R-SESSION-DETAIL | GET | `/sessions/{agent}/{session_id}` | `_serve_session` | `session.html` | `text/html; charset=utf-8` | 200 |
| R-SESSION-MHTML | GET | `/sessions/{agent}/{session_id}?export=mhtml` | `_serve_session` | `session.html` | `text/html; charset=utf-8` | 200 |
| R-GLOSSARY | GET | `/glossary` | `_serve_glossary` | `glossary.html` | `text/html; charset=utf-8` | 200 |
| R-FAVICON | GET | `/favicon.ico` | `_send_empty` | - | - | 204 |
| R-404 | GET | `*` (unmatched) | `_send_404` | `404.html` | `text/html; charset=utf-8` | 404 |
| R-500 | GET | `*` (error) | `_send_500` | `error.html` | `text/html; charset=utf-8` | 500 |

### 2.2 AJAX Partial Routes

| 契约 ID | Method | Path | Condition | Template | Content-Type |
|---------|--------|------|-----------|----------|-------------|
| R-SESSIONS-AJAX | GET | `/sessions` | `X-Requested-With: XMLHttpRequest` | `partials/sessions_ajax_page.html` | `text/html; charset=utf-8` |

### 2.3 JSON API Routes

| 契约 ID | Method | Path | Handler | Content-Type | Status Codes |
|---------|--------|------|---------|-------------|-------------|
| API-PAYLOAD | GET | `/api/sessions/{agent}/{session_id}/payload/{payload_id}` | `_serve_api_payload` | `application/json; charset=utf-8` | 200, 400, 404 |
| API-ATTRIBUTION-MAIN | GET | `/api/sessions/{source}/{session_id}/attribution/{round}/{call}/{kind}` | `_serve_api_attribution_main` | `application/json; charset=utf-8` | 200, 400, 404, 500 |
| API-ATTRIBUTION-SUB | GET | `/api/sessions/{source}/{session_id}/attribution/subagent/{sa_id}/{call_idx}/{kind}` | `_serve_api_attribution_subagent` | `application/json; charset=utf-8` | 200, 400, 404, 500 |
| API-ROUND | GET | `/api/sessions/{agent}/{session_id}/round/{round_index}` | `_serve_api_round` | `application/json; charset=utf-8` | 200, 400, 404 |
| API-BUCKET-DETAIL | GET | `/api/sessions/{source}/{session_id}/bucket-detail/{round_index}/{bucket_key}` | `_serve_api_bucket_detail` | `application/json; charset=utf-8` | 200, 400, 404 |

### 2.4 Static Asset Routes

| 契约 ID | Method | Path Pattern | Content-Type |
|---------|--------|-------------|-------------|
| S-CSS | GET | `/static/css/**` | `text/css` |
| S-JS | GET | `/static/js/**` | `application/javascript` |
| S-SVG | GET | `/static/images/**.svg` | `image/svg+xml` |
| S-OTHER | GET | `/static/**` | `text/plain` |

## 3. Template 契约

### 3.1 Template Hierarchy

```
base.html (master layout, nav, <head>)
  |-- dashboard.html
  |-- projects.html
  |-- project.html
  |-- sessions.html
  |-- session.html
  |-- glossary.html
  |-- 404.html
  |-- error.html
```

### 3.2 Component Templates (Jinja2 macros)

| Template | 用途 | 消费者 |
|----------|------|--------|
| `components/badge.html` | Badge UI 组件 | all pages |
| `components/session_detail_primitives.html` | Session detail 基础组件 | session.html |
| `components/session_detail_timeline.html` | Timeline macro (llm_call, subagent, round_table, payload, summary) | session.html, round API |
| `components/sessions_list_components.html` | Sessions list 组件 | sessions.html |
| `components/ui_primitives.html` | UI 基础组件入口 | all pages |
| `components/ui_primitives/_badges.html` | Badge 组件 | all pages |
| `components/ui_primitives/_buttons.html` | Button 组件 | all pages |
| `components/ui_primitives/_cards.html` | Card 组件 | dashboard, project |
| `components/ui_primitives/_empty_states.html` | Empty state 组件 | all list pages |
| `components/ui_primitives/_helpers.html` | Helper macros | all pages |
| `components/ui_primitives/_tables.html` | Table 组件 | all list pages |
| `components/ui_primitives/_tabs.html` | Tab 组件 | dashboard, session |

### 3.3 Partial Templates

| Template | 用途 | 触发条件 |
|----------|------|----------|
| `partials/sessions_ajax_page.html` | AJAX 分页局部渲染 | `X-Requested-With: XMLHttpRequest` |
| `partials/sessions_grid.html` | Sessions 网格视图 | sessions.html |
| `partials/sessions_table_body.html` | Sessions 表格 tbody | sessions.html, ajax |

### 3.4 Template-ViewModel 绑定

| Template | ViewModel | 消费 presenter |
|----------|-----------|---------------|
| `dashboard.html` | `DashboardViewModel` | `build_dashboard_view_model` |
| `projects.html` | `ProjectsViewModel` | `build_projects_view_model` |
| `project.html` | `ProjectDetailViewModel` | `build_project_detail_view_model` |
| `sessions.html` / `partials/sessions_ajax_page.html` | `SessionsViewModel` | `fetch_sessions_view_model` |
| `session.html` | `SessionDetailViewModel` + rounds + llm_calls + anomalies | `_build_v11_view_model` |

## 4. Jinja2 Filter 契约

### 4.1 格式化 Filters

| 契约 ID | Filter Name | 输入 | 输出 | 消费 template |
|---------|-------------|------|------|---------------|
| TF-FORMAT-NUM | `format_number` / `format_number_short` | int/float/None | compact string (1.5K, 2.3M) | dashboard, sessions |
| TF-FORMAT-TOKEN | `format_compact_token` | int/float/None | compact token string | session detail |
| TF-FORMAT-1D | `format_1d` | float/None | `X.X` string | session detail |
| TF-FORMAT-BYTES | `format_bytes` | int/float/None | `X B`/`KB`/`MB`/`GB` | session detail |
| TF-FORMAT-DURATION | `format_duration` | seconds (float) | `Xh Ymin` / `Xmin Ys` / `Xs` | session detail |
| TF-RELATIVE-TIME | `relative_time` | ISO8601 string | `Xd ago`/`Xh ago`/`Xm ago` | dashboard, sessions |
| TF-LOCAL-TIME | `local_time` | ISO8601 UTC string | `YYYY-MM-DD HH:MM:SS` local | session detail |

### 4.2 Path Filters

| 契约 ID | Filter Name | 输入 | 输出 | 消费 template |
|---------|-------------|------|------|---------------|
| TF-TRUNCATE-PATH | `truncate_path` | path string | truncated path (40 char limit) | session detail |
| TF-DISPLAY-PATH | `display_path` | path string | `~`-prefixed display path | session detail |
| TF-RELATIVE-REPO | `relative_to_repo` | path string | repo-relative path | session detail |
| TF-SHORTEN-PATH | `shorten_path` | path string | repo-relative -> ~ -> truncate | session detail |

### 4.3 安全/渲染 Filters

| 契约 ID | Filter Name | 输入 | 输出 | 消费 template |
|---------|-------------|------|------|---------------|
| TF-SAFE-JSON | `safe_json_display` | object | HTML-escaped JSON | session detail `<pre>` |
| TF-SAFE-HTML | `safe_html_block` | (html, class) | `<div class="...">...</div>` | markdown output |
| TF-TOJSON-SAFE | `tojson_safe_html` | object | HTML-escaped JSON | `<pre><code>` |
| TF-TOJSON-REPO | `tojson_repo` | object | relative-path JSON, HTML-escaped | session detail |
| TF-MARKDOWN | `markdown` | text | sanitized HTML | session detail |
| TF-RENDER-LLM | `render_llm_blocks_html` | content | HTML cards | session detail |

### 4.4 URL/Utility Filters

| 契约 ID | Filter Name | 输入 | 输出 |
|---------|-------------|------|------|
| TF-URLENCODE | `urlencode` | string | URL-encoded string |
| TF-URLDECODE | `urldecode` | string | URL-decoded string |
| TF-STRIP-LINES | `strip_line_numbers` | text | text without line number gutter |
| TF-RENUMBER | `renumber_lines` | text | text with renumbered gutter |
| TF-NORMALIZE-LLM | `normalize_llm_content` | text | normalized content blocks |
| TF-CONTENT-PARTS | `content_parts` | content | ContentPart blocks |
| TF-PARTS-MODE | `parts_mode_from_raw` | raw string | viewer-compatible dicts |

### 4.5 Dashboard-specific Filters

| 契约 ID | Filter Name | 输入 | 输出 |
|---------|-------------|------|------|
| TF-KPI-ICON-COLOR | `kpi_icon_color` | 1-based index | color class name |
| TF-KPI-ICON | `kpi_icon` | 1-based index | emoji glyph |
| TF-SUM-ATTRIBUTE | `sum_attribute` | (seq, attr) | sum of attribute |
| TF-DB-AGENT-SCOPE | `db_agent_to_scope` | DB agent value | URL scope param |
| TF-SCOPE-AGENT-URL | `scope_to_agent_url` | URL scope | agent path segment |
| TF-SEVERITY-VARIANT | `severity_variant` | severity label | badge variant class |
| TF-PRECISION-LABEL | `precision_label` | precision key | display label |
| TF-FORMAT-COVERAGE | `format_coverage` | ratio 0-1 | percentage string |

## 5. Static Asset 契约

### 5.1 CSS Files (18 files)

| 分类 | 文件 | 用途 |
|------|------|------|
| Core | `tokens.css`, `base.css`, `shell.css`, `states.css` | 全局 token 和布局 |
| UI Primitives | `ui-primitives.css`, `ui-primitives/_variables.css`, `_badges.css`, `_buttons.css`, `_empty-states.css`, `_forms.css`, `_metrics.css`, `_modals.css`, `_tables.css`, `_utilities.css` | 可复用 UI 组件 |
| Pages | `dashboard.css`, `projects.css`, `glossary.css`, `sessions-list.css` | 页面特定样式 |
| Session Detail | `session-detail.css`, `session-detail/00-tokens.css` ~ `09-anomalies-signals.css` (9 files) | Session detail 样式 |

### 5.2 JS Files (21 files)

| 分类 | 文件 | 用途 |
|------|------|------|
| Core | `app.js`, `arp-storage.js`, `view-state.js`, `ui_primitives.js`, `states.js` | 全局交互和状态 |
| Dashboard | `dashboard.js` | Dashboard 图表和交互 |
| Projects | `projects.js`, `data-table.js` | Project 列表交互 |
| Sessions | `sessions-list.js`, `timeline.js`, `glossary.js` | Session 列表和 glossary |
| Session Detail | `payload_viewer.js`, `session_detail_timeline.js`, `session-detail/namespace.js`, `init.js`, `dom.js`, `events.js`, `tabs.js`, `filters.js`, `lazy_rounds.js`, `payload.js`, `attribution.js` | Session detail 交互 |
| Utility | `trace-interactions.js` | Trace 交互工具 |

### 5.3 Image Assets

| 文件 | 用途 |
|------|------|
| `images/favicon.svg` | 站点图标 |

### 5.4 MHTML Export 契约

| 契约 ID | 名称 | CSS Load Order | JS Load Order |
|---------|------|----------------|---------------|
| MHTML-CSS | shared CSS bundle | `tokens.css` -> `base.css` -> `shell.css` -> `ui-primitives.css` (含 @import 展开) |
| MHTML-PAGE-CSS | session page CSS | `session-detail.css` (含 @import 展开) |
| MHTML-JS | shared JS bundle | `arp-storage.js` -> `view-state.js` -> `payload_viewer.js` -> `app.js` -> `data-table.js` -> `timeline.js` -> `keyboard.js` |

## 6. 安全契约

### 6.1 XSS 防护

| 契约 ID | 防护点 | 实现 | Trust Boundary |
|---------|--------|------|----------------|
| SEC-AUTOESCAPE | Jinja2 autoescape | `Environment(autoescape=True)` | Template rendering boundary |
| SEC-MARKDOWN | Markdown XSS | `html.escape(text)` before `_md.render()` | Rendering boundary (renderers/markdown.py) |
| SEC-JSON-DISPLAY | JSON in `<pre>` | `json.dumps` + `html.escape` | Template filter boundary |
| SEC-HTML-BLOCK | HTML wrapper | `<div class="safe-html-block">` wrapper | Template filter boundary |
| SEC-TOJSON-SAFE | JSON in any HTML context | `json.dumps` + `html.escape` (escapes `<`, `>`, `&`, `"`, `'`) | Template filter boundary |
| SEC-ERROR-REDACT | Error message redaction | Regex strip: user paths -> `[path]`, secrets -> `[redacted]`, max 240 chars | HTTP error response boundary |

### 6.2 Path Traversal 防护

| 契约 ID | 防护点 | 当前状态 | Java 要求 |
|---------|--------|----------|-----------|
| SEC-STATIC-PATH | `_serve_static` filename | 当前无显式 traversal 检查; 依赖 http.server 行为 | Java 必须显式验证 resolved path 在 static dir 内 |
| SEC-TEMPLATE-PATH | Jinja2 FileSystemLoader | 安全: 限制在 `_TEMPLATE_DIR` 内 | Java 使用 classpath resource loader |

### 6.3 CSP / Security Headers

| 契约 ID | Header | 当前状态 | Java 要求 |
|---------|--------|----------|-----------|
| SEC-CSP | Content-Security-Policy | 当前未设置 | 评估是否需要; 本地 server 风险低 |
| SEC-X-FRAME | X-Frame-Options | 当前未设置 | 评估是否需要 |
| SEC-CACHE | Cache-Control (static) | 当前未设置 | Java 应设置 static asset cache headers |

### 6.4 Payload Visibility

| 契约 ID | 场景 | 行为 |
|---------|------|------|
| SEC-PAYLOAD-TRUNCATE | payload API `truncate=false` | 返回完整 payload, 不截断 |
| SEC-SENSITIVE-MASK | bucket-detail `current_user_message` / `local_instruction_context` | `mask_sensitive_keys()` 脱敏 |
| SEC-PAYLOAD-ANOMALY | Session 有 input tokens 但无 request/response | 触发 `PAYLOAD_VISIBILITY_MISMATCH` anomaly |

## 7. Python Symbol 归属

### 7.1 Migrate 到 Java Web

| Symbol | 来源文件 | 目标 Java Task |
|--------|----------|---------------|
| `SessionBrowserHandler` | routes.py | WEB-020 (Javalin lifecycle) |
| `SessionBrowserServer` | routes.py | WEB-020 |
| `create_server` | routes.py | WEB-020 |
| `AttributionRequest` | routes.py | WEB-060 (attribution API) |
| `env` (Jinja2 Environment) | template_env.py | WEB-030 (Pebble environment) |
| `safe_json_display`, `safe_html_block`, `tojson_safe_html` | safe_render.py | WEB-070 (rendering security) |
| `render_markdown` | renderers/markdown.py | WEB-070 |
| `normalize_llm_content`, `render_llm_blocks_html` | renderers/llm_blocks.py | WEB-030 |
| `get_context`, `get_css`, `get_js`, `get_page_css` | mhtml.py | WEB-070 |
| `build_dashboard_view_model` | presenters/dashboard.py | WEB-040 |
| `build_projects_view_model`, `build_project_detail_view_model` | presenters/projects.py | WEB-040 |
| `fetch_sessions_view_model`, `parse_sessions_query_params`, `compute_pagination` | presenters/sessions.py | WEB-040 |
| `build_rounds`, `build_llm_calls`, `assign_interactions_to_rounds` | presenters/session_detail.py | WEB-050 |
| `_build_v11_view_model` | session_detail/view_model.py | WEB-050 |
| `compute_round_signals`, `compute_bar_scale` | session_detail/anomalies.py | WEB-050 |
| `build_round_preview`, `compact_preview_text` | session_detail/preview.py | WEB-050 |
| All 8 TypedDict view models | view_models.py | WEB-030 (presentation models) |

### 7.2 DO_NOT_MIGRATE (Python-only / 不迁移)

| Symbol | 原因 |
|--------|------|
| `_get_repo_root` (module-level) | 使用 subprocess 调用 git; Java 使用 process builder 或 JGit |
| `_SESSION_REPO_ROOT` (module global) | Python module state; Java 使用 request-scoped context |
| `BaseHTTPRequestHandler` | Python stdlib; Java 使用 Javalin |
| `ThreadingHTTPServer` | Python stdlib; Java 使用 Javalin/Jetty |
| `log_message`, `log_error` overrides | Python logging bridge; Java 使用 SLF4J |
| `_TEMPLATE_DIR` / `_STATIC_DIR` path constants | Python filesystem; Java 使用 classpath resources |
| `_REPO_ROOT` module-level cache | Python module init; Java 使用 application-scoped config |

## 8. Validation Placement

| 校验条件 | 唯一主要位置 | 下游行为 |
|----------|-------------|----------|
| HTTP method/route 匹配 | Web adapter (Javalin route handler) | use case 接收 typed request |
| URL path 参数解析 (agent, session_id, round_index) | Web adapter (path param parser) | use case 信任 typed int/string |
| Query string 解析 (page, sort, filter) | Web adapter (query param parser) | use case 使用 validated filter |
| `kind` 合法性 (request/response) | Web adapter | use case 信任 enum |
| `round_index`/`call_index` 正整数 | Web adapter | use case 信任 positive int |
| `bucket_key` 合法性 | Web adapter (allowlist) | use case 使用 validated key |
| Template XSS | Template engine (autoescape + safe filters) | view model 不自行拼 HTML |
| Markdown XSS | Rendering boundary (html.escape before render) | template 信任 rendered HTML |
| Static path traversal | Web adapter (resolved path check) | static reader 信任 validated path |
| Error message 脱敏 | HTTP error response boundary | 500 page 信任 redacted message |
| Session data 合法性 | Domain record compact constructor | Web adapter 信任 typed domain object |
| JSON serialization | Web adapter (Jackson/JSON encoder) | HTTP response 信任 serializer |
| MHTML CSS @import 展开 | MHTML bundler (circular import guard) | template 信任 bundled CSS |
| `mask_sensitive_keys` | Attribution/bucket-detail response boundary | API response 使用 masked text |

## 9. 重复校验审计

| 条件 | 出现位置 | 判断 |
|------|----------|------|
| Session lookup (DB query) | `_serve_session`, `_serve_api_payload`, `_load_session_and_build_rounds`, `_serve_api_bucket_detail` | 不同 route handler, 每个需要独立 DB lookup; 内存缓存减少重复 |
| Session parse (source parser) | 同上 4 处 | 缓存命中后不重复 parse; 缓存未命中时各 route 独立 |
| Round/LLM call 构建 | `_serve_session`, `_load_session_and_build_rounds`, `_serve_api_bucket_detail` | 通过 `_load_session_and_build_rounds` 共享; bucket-detail 对 `current_user_message` 和 `full_messages_array_item` 有独立构建 |
| Qoder short ID 解析 | `_serve_session`, `_serve_api_payload`, `_load_session_and_build_rounds`, `_serve_api_bucket_detail` | 每个 route 独立处理; Java 可提取为共享 use case |
| `mask_sensitive_keys` | `_serve_api_bucket_detail` 中 `current_user_message` 和 `local_instruction_context` | 每个 bucket 独立调用; 合理 |

## 10. S5 Task 归属

| S5 Task | 覆盖契约 |
|---------|----------|
| WEB-020 | R-DASHBOARD ~ R-500, SEC-STATIC-PATH, Javalin lifecycle |
| WEB-030 | TF-* filters, VM-* view models, presentation models, Pebble environment |
| WEB-040 | R-DASHBOARD, R-PROJECTS, R-PROJECT-DETAIL, R-SESSIONS, R-SESSIONS-AJAX, VM-DASHBOARD, VM-SESSIONS, VM-PROJECTS, VM-PROJECT-DETAIL |
| WEB-050 | R-SESSION-DETAIL, R-SESSION-MHTML, VM-SESSION-DETAIL, VM-TRACE-ROW, VM-PAYLOAD |
| WEB-060 | API-PAYLOAD, API-ATTRIBUTION-MAIN, API-ATTRIBUTION-SUB, API-ROUND, API-BUCKET-DETAIL |
| WEB-070 | SEC-AUTOESCAPE ~ SEC-PAYLOAD-ANOMALY, S-CSS ~ S-OTHER, MHTML-*, TF-MARKDOWN, TF-RENDER-LLM |
| WEB-075 | 重复校验消除, route 精简, filter 复用优化 |
| WEB-080 | DOM/API/XSS/accessibility/performance 只读门禁 |
