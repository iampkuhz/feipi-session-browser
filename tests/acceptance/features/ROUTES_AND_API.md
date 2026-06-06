# 路由与 API 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | HTTP 路由与 API 端点 |
| 关联源码 | `src/session_browser/web/routes.py`、`src/session_browser/web/template_env.py` |
| 关联测试 | `tests/session_detail/test_session_detail_route.py`、`test_session_detail_api.py`、`tests/rendering/test_safe_render.py`、`tests/rendering/test_template_render.py`、`tests/web/test_template_env.py` |
| 主要风险 | 路由返回 500 导致页面不可用；模板 XSS 漏洞；API 端点字段缺失 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| ROUTE-API-001 | P0 | data | 会话详情路由冒烟（200、trace-panel、metrics、无 500） | 访问 `/sessions/claude_code/<session_id>` | HTTP 200，页面含 `.trace-panel` 和 metrics 区域，无 500 错误 | pytest | — | `tests/session_detail/test_session_detail_route.py` |
| ROUTE-API-002 | P0 | data | Payload API 返回 JSON（字段完整、404 处理、不截断） | 访问 payload API 端点 | 返回 JSON 含 raw_payload/size/tool_name 等字段，不存在的 payload 返回 404 | pytest | — | `tests/session_detail/test_session_detail_api.py` |
| ROUTE-API-003 | P0 | data | Jinja2 安全渲染（XSS 防护） | 在模板中渲染含 `<script>` 标签的用户输入 | 输出被转义为 `&lt;script&gt;`，不执行 JS | pytest | — | `tests/rendering/test_safe_render.py` |
| ROUTE-API-004 | P0 | data | 模板环境配置（自定义 filter 注册） | 检查 template_env 中注册的 filter | `_relative_to_repo`、`_truncate_path`、`_format_compact_token` 等 filter 可用 | pytest | — | `tests/web/test_template_env.py` |
| ROUTE-API-005 | P1 | data | Dashboard 路由返回有效 HTML | 访问 `/dashboard` | HTTP 200，页面含 `.metric-grid` 和 `.chart-card` | pytest | — | `src/session_browser/web/routes.py` |
| ROUTE-API-006 | P1 | data | Sessions 列表路由返回有效 HTML | 访问 `/sessions` | HTTP 200，页面含 `.data-table` 和筛选栏 | pytest | — | `src/session_browser/web/routes.py` |
| ROUTE-API-007 | P1 | data | Projects 路由返回有效 HTML | 访问 `/projects` 和 `/projects/{key}` | HTTP 200，页面含项目列表或详情 | pytest | — | `src/session_browser/web/routes.py` |
| ROUTE-API-008 | P1 | data | Agents 路由返回有效 HTML | 访问 `/agents` 和 `/agents/{name}` | HTTP 200，页面含 Agent 列表或详情 | pytest | — | `src/session_browser/web/routes.py` |
| ROUTE-API-009 | P1 | data | Glossary 路由返回有效 HTML | 访问 `/glossary` | HTTP 200，页面含术语表 | pytest | — | `src/session_browser/web/routes.py` |
| ROUTE-API-010 | P1 | data | 404 路由返回状态页 | 访问未映射路径 `/__test-404-not-found__` | HTTP 404（或 200 + 状态页模板），含 `.state-panel` | Playwright | snapshot 更新条件：当 states.css 样式/布局变更时需更新快照 | `tests/playwright/ui-contract.spec.ts` |
| ROUTE-API-011 | P1 | data | Presenter + Route 集成测试 | 通过路由访问各页面，验证 presenter 数据渲染到模板 | 页面上显示的数值与 presenter 返回的 view_model 一致 | pytest | — | `tests/web/test_presenter_route_integration.py` |
| ROUTE-API-012 | P2 | data | Sessions AJAX 部分渲染端点 | 发送 AJAX 请求到 sessions 部分渲染 API | 返回 HTML 片段含会话行，不包含完整页面模板 | pytest | — | `tests/web/test_sessions_ajax_partial.py` |
| ACCEPTANCE-001 | P2 | data | CLI 命令执行与超时处理 | 运行 `_run_command` 并测试正常和超时场景 | 返回码正确，超时后清理进程组 | pytest | — | `tests/misc/test_cli.py` |
