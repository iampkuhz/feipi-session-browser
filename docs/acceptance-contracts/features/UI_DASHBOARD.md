# Dashboard 页面 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | Dashboard 页面（概览统计、趋势图、模型/Agent 分布） |
| 关联源码 | `src/session_browser/web/presenters/dashboard.py`、`src/session_browser/web/templates/dashboard.html` |
| 关联测试 | `tests/pages/test_dashboard.py`、`test_dashboard_page.py`、`tests/web/test_dashboard_presenter.py`、`tests/ui/test_dashboard_tooltip_contract.py`、`tests/playwright/macbook-smoke.spec.js`、`tests/playwright/ui-contract.spec.ts` |
| 主要风险 | metric-card 数值与索引不一致；趋势图数据为空；多视口布局错乱 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| UI-DASHBOARD-001 | P0 | visual | Dashboard 页面基础结构渲染 | 访问 `/dashboard`，检查 DOM | `.page-head` 含 "Dashboard" 标题，`.metric-grid` 存在，`.chart-card` 至少 3 个 | pytest | snapshot 更新条件：当 UI 布局/设计令牌/颜色变更时需更新快照 | 待补充 |
| UI-DASHBOARD-002 | P0 | visual | metric-card 数量为 4 | 检查 `.metric-card` 元素数量 | 恰好 4 个 metric-card（sessions/projects/tokens/agents） | Playwright | snapshot 更新条件：当 metric-card 布局变更时需更新快照 | 待补充 |
| UI-DASHBOARD-003 | P0 | visual | 范围切换控件存在 | 检查 `.scope-switch` 元素 | `.scope-switch` 可见，含 "7 days"/"30 days" 等选项 | Playwright | — | 待补充 |
| UI-DASHBOARD-004 | P0 | data | Dashboard 统计数据结构完整 | 调用 `build_dashboard_view_model` | 返回 dict 含 stats/trend_data/model_distribution/agent_distribution，stats 含 total_sessions/total_tokens 等 | pytest | — | 待补充 |
| UI-DASHBOARD-005 | P1 | visual | Dashboard 多视口截图（1440x900 / 1280x800 / 1180x800 / 2560x1440） | 各视口访问 `/dashboard` 截图 | 截图通过视觉回归比对，maxDiffPixelRatio <= 0.05 | Playwright | snapshot 更新条件：当 UI 布局/设计令牌/颜色变更时需更新快照 | 待补充 |
| UI-DASHBOARD-006 | P1 | visual | Dashboard 提示框契约 | 检查 tooltip 渲染结构 | tooltip 元素存在，含正确的 data-tooltip 属性 | pytest | — | 待补充 |
| UI-DASHBOARD-007 | P1 | visual | 1440x900 MacBook 视口 Dashboard 冒烟 | 设置视口 1440x900 访问 `/dashboard` | body 可见，title 含 "Dashboard"，metric-card 有 4 个 | Playwright | snapshot 更新条件：当 MacBook 视口布局变更时需更新快照 | 待补充 |
| UI-DASHBOARD-008 | P1 | visual | Dashboard 模板结构检查 | 检查模板 extends、active_page、CSS/JS 导入 | 模板正确 extends base，active_page="dashboard"，CSS/JS 路径有效 | pytest | — | 待补充 |
