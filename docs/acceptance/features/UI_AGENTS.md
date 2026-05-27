# Agents 页面 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | Agent 列表页 + Agent 详情页 |
| 关联源码 | `src/session_browser/web/presenters/agents.py`、`src/session_browser/web/templates/agents.html`、`agent_detail.html` |
| 关联测试 | `tests/pages/test_agents_list_page.py`、`test_agents_page.py`、`test_agent_detail.py`、`tests/playwright/ui-contract.spec.ts`、`tests/playwright/macbook-smoke.spec.js` |
| 主要风险 | Agent 详情页无 E2E 交互测试；agent 列表统计与索引不一致 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| UI-AGENTS-001 | P0 | visual | Agent 列表页模板（表格 + 筛选 + KPI） | 访问 `/agents`，检查 DOM | `.page-head` 含 "Agents"，`.metric-grid` 存在，`#agents-table.data-table` 可见 | pytest | snapshot 更新条件：当 Agent 列表布局变更时需更新快照 | `tests/pages/test_agents_list_page.py` |
| UI-AGENTS-002 | P0 | visual | Agent 详情页模板（KPI + 会话列表 + tab） | 访问 `/agents/claude_code` | `.header` 存在，`.metric-grid` 可见，`.data-table` 有会话行 | pytest | snapshot 更新条件：当 Agent 详情布局变更时需更新快照 | `tests/pages/test_agent_detail.py` |
| UI-AGENTS-003 | P0 | visual | Agent 列表页多视口截图 | 各视口访问 `/agents` 截图 | 截图通过视觉回归，maxDiffPixelRatio <= 0.05 | Playwright | snapshot 更新条件：当 UI 布局/设计令牌/颜色变更时需更新快照 | `tests/playwright/ui-contract.spec.ts` |
| UI-AGENTS-004 | P0 | visual | Agent 详情页多视口截图 | 各视口访问 fixture agent URL 截图 | 截图通过视觉回归 | Playwright | snapshot 更新条件：当 Agent 详情页布局变更时需更新快照 | `tests/playwright/ui-contract.spec.ts` |
| UI-AGENTS-005 | P0 | visual | MacBook 视口 Agent 页冒烟 | 设置视口访问 `/agents` | body 可见，title 含 "Agents"，`.data-table` 可见 | Playwright | — | `tests/playwright/macbook-smoke.spec.js` |
| UI-AGENTS-006 | P0 | visual | Agent 页面整体结构 | pytest 检查模板渲染 | 模板结构完整，CSS/JS 导入正确 | pytest | — | `tests/pages/test_agents_page.py` |
| UI-AGENTS-007 | P2 | interaction | Agent 列表筛选/排序（空白待补充） | 待补充 E2E 测试 | 筛选后 URL 变化，排序后行顺序变化 | Playwright | — | 待补充 |
| UI-AGENTS-008 | P2 | interaction | Agent 详情交互（空白待补充） | 待补充 E2E 测试 | Agent 详情 tab 切换、会话行点击 | Playwright | — | 待补充 |
