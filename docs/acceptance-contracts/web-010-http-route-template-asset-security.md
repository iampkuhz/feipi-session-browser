# WEB-010 HTTP、Route、Template、Asset 与安全契约冻结

## 审计范围

逐 function 审计以下 Python web 模块，冻结 Java Web 行为和安全边界：

- `src/session_browser/web/routes.py` (HTTP handler: 11 page routes + 5 API routes)
- `src/session_browser/web/template_env.py` (Jinja2 environment: 30+ filters)
- `src/session_browser/web/safe_render.py` (XSS 防护: 3 safe filters)
- `src/session_browser/web/mhtml.py` (MHTML export: CSS/JS bundling)
- `src/session_browser/web/view_models.py` (8 TypedDict contracts)
- `src/session_browser/web/presenters/` (4 presenter modules)
- `src/session_browser/web/renderers/` (markdown + llm_blocks)
- `src/session_browser/web/session_detail/` (7 sub-modules)
- `src/session_browser/web/templates/` (29 HTML templates)
- `src/session_browser/web/static/` (52 static assets)

## HTTP Route 清单

### Page Routes (11)

1. R-DASHBOARD: GET / -> dashboard.html (200)
2. R-DASHBOARD-ALT: GET /dashboard -> dashboard.html (200)
3. R-PROJECTS: GET /projects -> projects.html (200)
4. R-PROJECT-DETAIL: GET /projects/{key} -> project.html (200)
5. R-SESSIONS: GET /sessions -> sessions.html (200)
6. R-SESSION-DETAIL: GET /sessions/{agent}/{session_id} -> session.html (200)
7. R-SESSION-MHTML: GET /sessions/{agent}/{session_id}?export=mhtml -> session.html (200)
8. R-GLOSSARY: GET /glossary -> glossary.html (200)
9. R-FAVICON: GET /favicon.ico -> empty (204)
10. R-404: unmatched -> 404.html (404)
11. R-500: error -> error.html (500)

### AJAX Partial (1)

12. R-SESSIONS-AJAX: GET /sessions (X-Requested-With: XMLHttpRequest) -> partials/sessions_ajax_page.html

### JSON API Routes (5)

13. API-PAYLOAD: GET /api/sessions/{agent}/{session_id}/payload/{payload_id} -> JSON
14. API-ATTRIBUTION-MAIN: GET /api/sessions/{source}/{session_id}/attribution/{round}/{call}/{kind} -> JSON
15. API-ATTRIBUTION-SUB: GET /api/sessions/{source}/{session_id}/attribution/subagent/{sa_id}/{call_idx}/{kind} -> JSON
16. API-ROUND: GET /api/sessions/{agent}/{session_id}/round/{round_index} -> JSON (HTML fragment)
17. API-BUCKET-DETAIL: GET /api/sessions/{source}/{session_id}/bucket-detail/{round_index}/{bucket_key} -> JSON

### Static Asset Routes (4 content types)

18. S-CSS: /static/css/** -> text/css
19. S-JS: /static/js/** -> application/javascript
20. S-SVG: /static/images/**.svg -> image/svg+xml
21. S-OTHER: /static/** -> text/plain

## Template 清单

### Layout Templates (8)

- base.html, dashboard.html, projects.html, project.html, sessions.html, session.html, glossary.html, 404.html, error.html

### Component Templates (12)

- badge.html, session_detail_primitives.html, session_detail_timeline.html
- session_detail_timeline/{llm_call, payload, round_table, subagent, summary}.html
- sessions_list_components.html, ui_primitives.html
- ui_primitives/{_badges, _buttons, _cards, _empty_states, _helpers, _tables, _tabs}.html

### Partial Templates (3)

- sessions_ajax_page.html, sessions_grid.html, sessions_table_body.html

## Jinja2 Filter 清单 (30+)

### 格式化 (7): format_number, format_number_short, format_compact_token, format_1d, format_bytes, format_duration, relative_time, local_time
### 路径 (4): truncate_path, display_path, relative_to_repo, shorten_path
### 安全 (5): safe_json_display, safe_html_block, tojson_safe_html, tojson_repo, markdown
### 渲染 (4): render_llm_blocks_html, normalize_llm_content, content_parts, parts_mode_from_raw
### URL (2): urlencode, urldecode
### 工具 (2): strip_line_numbers, renumber_lines
### Dashboard (8): kpi_icon_color, kpi_icon, sum_attribute, db_agent_to_scope, scope_to_agent_url, severity_variant, precision_label, format_coverage

## Static Asset 清单

### CSS (18): tokens, base, shell, states, ui-primitives (10), dashboard, projects, glossary, sessions-list, session-detail (10)
### JS (21): app, arp-storage, view-state, ui_primitives, states, dashboard, projects, data-table, sessions-list, timeline, glossary, payload_viewer, session_detail_timeline, session-detail (11), trace-interactions
### Images (1): favicon.svg

## 安全契约

### XSS 防护 (6)

1. SEC-AUTOESCAPE: Jinja2 autoescape=True
2. SEC-MARKDOWN: html.escape before markdown render
3. SEC-JSON-DISPLAY: json.dumps + html.escape for `<pre>` embedding
4. SEC-HTML-BLOCK: CSS class wrapper for sanitized HTML
5. SEC-TOJSON-SAFE: html.escape for any HTML context
6. SEC-ERROR-REDACT: Regex strip paths/secrets, max 240 chars

### Path Traversal (2)

7. SEC-STATIC-PATH: Java 必须显式验证 resolved path 在 static dir 内
8. SEC-TEMPLATE-PATH: Java 使用 classpath resource loader

### Payload Visibility (3)

9. SEC-PAYLOAD-TRUNCATE: payload API truncate=false
10. SEC-SENSITIVE-MASK: mask_sensitive_keys for bucket-detail
11. SEC-PAYLOAD-ANOMALY: PAYLOAD_VISIBILITY_MISMATCH anomaly

## 校验放置

| 校验 | 位置 | 下游 |
|------|------|------|
| HTTP route 匹配 | Web adapter | use case 接收 typed request |
| URL path 参数 | Web adapter | use case 信任 typed int/string |
| Query params | Web adapter | use case 使用 validated filter |
| Template XSS | Template engine | view model 不拼 HTML |
| Markdown XSS | Rendering boundary | template 信任 rendered HTML |
| Static path | Web adapter | reader 信任 validated path |
| Error 脱敏 | Error response boundary | 500 page 信任 redacted message |
| Session 合法性 | Domain record | Web adapter 信任 typed domain |
| mask_sensitive_keys | Attribution/bucket-detail response | API response 使用 masked text |

## S5 Task 归属

| Task | 覆盖 |
|------|------|
| WEB-020 | HTTP routes, Javalin lifecycle, static path safety |
| WEB-030 | Template filters, view models, Pebble environment |
| WEB-040 | Dashboard/Projects/Sessions pages |
| WEB-050 | Session detail, timeline, rounds |
| WEB-060 | Attribution/Payload/Round/Bucket JSON API |
| WEB-070 | Static/Markdown/MHTML/rendering security |
| WEB-075 | Route/template dedup optimization |
| WEB-080 | DOM/API/XSS/accessibility/performance gate |
