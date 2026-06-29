# Sessions List 页面 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 会话列表页（筛选、排序、分页、数据表） |
| 关联源码 | `java/web/src/main/java/com/feipi/session/browser/web/page/SessionsListPage.java`、`java/web/src/main/resources/templates/sessions_list.html` |
| 关联测试 | `tests/sessions_list/test_sessions_list.py`、`test_sessions_list_contract.py`、`test_sessions_list_interactions.py`、`test_sessions_list_query_state.py`、`test_sessions_pagination.py`、`tests/playwright/sessions-list.spec.js` |
| 主要风险 | 分页双跳（next 跳过 page 2）、筛选 URL 不更新、tokenbar 渲染异常 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| UI-SESSIONS-001 | P0 | visual | 会话列表页模板完整检查（extends/active_page/UI primitives/CSS/JS） | pytest 检查模板结构 | 模板正确 extends base，active_page="sessions"，UI primitives/CSS/JS 导入完整，无 inline onclick | pytest | — | `tests/sessions_list/test_sessions_list.py` |
| UI-SESSIONS-002 | P0 | visual | 数据表格列头完整性 | 访问 `/sessions`，检查 `th` 元素 | 至少 8 个列头，含 title/project/agent/model/tokens/rounds/tools/duration/updated | Playwright | snapshot 更新条件：当列头增减/排序按钮样式变更时需更新快照 | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-003 | P0 | visual | token 条包含四段 | 检查 `.tokenbar` 内 `.tokenbar-seg` 数量 | `.tokenbar-seg` 数量为 4（input/output/cached-in/cached-out） | Playwright | snapshot 更新条件：当 tokenbar CSS 变更时需更新快照 | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-004 | P0 | visual | agent 徽章渲染（cc/cx/qd 类） | 检查 `.badge` 元素 class | badge class 匹配 `/(cc|cx|qd)/` | Playwright | snapshot 更新条件：当 badge 样式变更时需更新快照 | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-005 | P0 | interaction | 排序按钮可点击且 URL 变化 | 点击 `.sort-button[data-sort-key="tokens"]` | URL 包含 `sort=tokens`，按钮数 >= 4 | Playwright | — | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-006 | P0 | interaction | 筛选表单提交并改变 URL | 在 `#session-search` 填入关键词点击应用 | URL 包含 `q=<关键词>` | Playwright | — | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-007 | P0 | interaction | next 一次到 page 2（回归测试 S-09） | 从 `/sessions?page=1` 点击 next | URL 变为 `page=2`（非 page=3），page-input 值为 2，prev 按钮启用 | Playwright | — | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-008 | P0 | visual | 会话行 data 属性契约 | 检查 `tr[data-action="row"]` | 行含 `data-agent`、`data-model`、`data-session-id` 属性 | Playwright | — | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-009 | P0 | visual | 会话列表契约（模板结构 + CSS/JS + 筛选栏 + 数据表 + tokenbar + 分页 + 空状态） | pytest 检查模板渲染 | 模板结构完整，筛选栏/数据表/tokenbar/分页/空状态区域均存在 | pytest | — | 待补充 |
| UI-SESSIONS-011 | P1 | interaction | 会话列表 AJAX 部分渲染 | 触发筛选/分页 AJAX 请求 | 返回 HTML 片段渲染正确，无完整页面刷新 | pytest | — | `java/web/src/test/java/com/feipi/session/browser/web/api/SessionApiHandlerTest.java` |
| UI-SESSIONS-012 | P1 | interaction | 分页边界条件（page size / 页码输入 / prev 禁用） | 测试最后一页的 next 禁用、第一页的 prev 禁用 | next/prev 按钮在边界时正确禁用，页码输入框限制在有效范围 | pytest | — | 待补充 |
| UI-SESSIONS-013 | P1 | visual | 列表标题截断 | 检查长标题在列表中的截断行为 | 标题超过最大长度时被截断，不破坏布局 | pytest | — | 待补充 |
| UI-SESSIONS-014 | P1 | interaction | 查询状态管理 | 验证筛选/排序/分页状态同步 | query params 与当前筛选/排序/分页状态一致 | pytest | — | 待补充 |
| UI-SESSIONS-015 | P1 | visual | 1440x900 截图基线 | 设置视口截图 | 截图通过视觉回归 | Playwright | snapshot 更新条件：当列表页整体布局变更时需更新快照 | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-016 | P1 | visual | token 单元格契约 | 检查 token 单元格渲染 | 单元格含 tokenbar 组件，数值格式化正确 | pytest | — | `tests/rendering/test_sessions_token_cell_contract.py` |
| UI-SESSIONS-017 | P2 | visual | 空数据态渲染 | 在无 session 数据时访问列表页 | 显示空状态提示，无数据表报错 | pytest | — | `tests/sessions_list/test_sessions_list.py`（空状态检查） |
