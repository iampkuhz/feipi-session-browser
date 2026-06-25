# Projects 页面 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 项目列表页 + 项目详情页 |
| 关联源码 | `src/session_browser/web/presenters/projects.py`、`src/session_browser/web/templates/projects.html`、`project_detail.html` |
| 关联测试 | `tests/pages/test_projects_page.py`、`test_project_detail_page.py`、`tests/rendering/test_project_detail_table_contract.py`、`test_project_template_contract.py`、`test_projects_template_contract.py`、`tests/web/test_projects_presenter.py`、`tests/playwright/ui-contract.spec.ts` |
| 主要风险 | 项目详情页缺少交互测试；多视口截图基线过时；项目统计聚合不正确 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| UI-PROJECTS-001 | P0 | visual | 项目列表页模板（KPI + 表格 + 筛选） | 访问 `/projects`，检查 DOM | `.page-head` 含 "Projects"，`.metric-grid` 存在，`.data-table` 有项目行 | pytest | snapshot 更新条件：当项目列表布局变更时需更新快照 | 待补充 |
| UI-PROJECTS-002 | P0 | visual | 项目详情页模板（KPI + 会话表） | 访问 `/projects/{key}` | `.page-head` 含项目名，`.metric-grid` 存在，`.data-table` 有会话行 | pytest | snapshot 更新条件：当项目详情布局变更时需更新快照 | `tests/pages/test_project_detail_page.py` |
| UI-PROJECTS-003 | P0 | visual | 项目详情表格契约 | 检查项目详情表格列头 | 列头含 title/agent/model/tokens/rounds 等 | pytest | — | `tests/rendering/test_project_detail_table_contract.py` |
| UI-PROJECTS-004 | P0 | data | Projects Presenter 数据完整 | 调用 `build_projects_view_model` | 返回含 projects 列表、aggregate、pagination，每个项目含 session_count/total_tokens | pytest | — | 待补充 |
| UI-PROJECTS-005 | P0 | visual | 项目页多视口截图（1440x900 / 1280x800 / 1180x800 / 2560x1440）| 各视口访问 `/projects` 截图 | 截图通过视觉回归，maxDiffPixelRatio <= 0.05 | Playwright | snapshot 更新条件：当 UI 布局/设计令牌/颜色变更时需更新快照 | 待补充 |
| UI-PROJECTS-006 | P0 | visual | 项目详情页多视口截图 | 各视口访问 fixture project URL 截图 | 截图通过视觉回归 | Playwright | snapshot 更新条件：当项目详情页布局变更时需更新快照 | 待补充 |
| UI-PROJECTS-007 | P0 | visual | 项目模板契约 | pytest 检查项目模板结构 | 模板正确 extends base，CSS/JS 导入完整 | pytest | — | `tests/rendering/test_project_template_contract.py` |
| UI-PROJECTS-008 | P0 | visual | 项目列表模板契约 | pytest 检查项目列表模板结构 | 模板结构完整，含筛选栏和数据表区域 | pytest | — | `tests/rendering/test_projects_template_contract.py` |
| UI-PROJECTS-009 | P1 | visual | MacBook 视口项目页冒烟 | 设置 1280x800 / 1440x900 视口访问 `/projects` | body 可见，title 含 "Projects"，`.data-table` 可见 | Playwright | — | 待补充 |
| UI-PROJECTS-010 | P2 | interaction | 项目列表筛选/排序（空白待补充） | 待补充 E2E 测试 | 筛选后 URL 变化，排序后行顺序变化 | Playwright | — | 待补充 |
