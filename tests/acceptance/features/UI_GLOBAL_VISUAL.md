# 全局视觉契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 全局视觉契约（Shell 布局、多视口矩阵、基础组件、滚动行为、密度/字体） |
| 关联源码 | `src/session_browser/web/static/css/`（shell.css、states.css、全局 CSS）、`src/session_browser/web/static/js/` |
| 关联测试 | `tests/pages/test_macbook_smoke.py`、`test_2560x1440_smoke.py`、`test_error_page.py`、`test_state_pages.py`、`test_scroll_shadow_behavior.py`、`tests/ui/test_ui_density_and_font_size.py`、`test_ui_primitives.py`、`test_hifi_dom_structure.py`、`test_card_sub_spacing.py` |
| 主要风险 | 视口矩阵不全导致特定分辨率下布局崩坏；shell.css 级联冲突 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| UI-VISUAL-001 | P0 | visual | Shell 状态网格宽度断言（Session Detail） | 通过 JS 设置 body class 后测量 `grid-template-columns` | normal: .main>800, sidebar>0; hide-left: sidebar=0, .main>900; hide-right: inspector=0; focus: sidebar+inspector=0, .main>1100 | Playwright | snapshot 更新条件：当 shell.css grid 变更时需更新快照 | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-002 | P0 | visual | Shell 无水平滚动 | 各状态测量 scrollWidth vs viewportWidth | `scrollWidth <= viewportWidth + 2` | Playwright | — | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-003 | P0 | visual | 1440x1100 会话详情外壳布局 | 质量门禁视口测量 | .main>1200, .session-detail-page>1100, .hero>900, 标题在 KPI 上方 | Playwright | snapshot 更新条件：当 shell CSS grid 变更时需更新快照 | `tests/playwright/session-detail-layout.spec.js` |
| UI-VISUAL-004 | P0 | visual | Shell 状态多视口截图基线（normal/hide-right × 1440/1280/1180）| 各状态 × 视口截图 | 截图存入 `tmp/` 目录，结构断言 main 宽度 > 600 | Playwright | snapshot 更新条件：当 shell.css 变更时需更新快照 | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-005 | P0 | visual | Shell 状态截图基线（hide-left/focus × 1440/1280/1180）| 各状态 × 视口截图 | 截图存入 `tmp/` 目录，main 宽度 > 600 | Playwright | snapshot 更新条件：当 shell.css 变更时需更新快照 | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-006 | P0 | visual | Dashboard shell 状态（normal/hide-left） | 在 Dashboard 页面设置 body class 测量 | normal: .main>800, sidebar>0; hide-left: sidebar=0, .main>900, 无水平滚动 | Playwright | — | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-007 | P0 | visual | 404 页多视口截图 + 可见性 | 访问 `/__test-404-not-found__`，各视口截图 | `.state-panel` 可见，标题为 "Page Not Found"，截图通过回归 | Playwright | snapshot 更新条件：当 states.css 变更时需更新快照 | `tests/playwright/ui-contract.spec.ts` |
| UI-VISUAL-008 | P0 | visual | 2560x1440 超宽视口冒烟 | 设置超宽视口访问所有页面 | 所有页面 body 可见，无水平溢出 | pytest | — | `tests/pages/test_2560x1440_smoke.py` |
| UI-VISUAL-009 | P0 | visual | MacBook 视口冒烟（1280x800 / 1440x900） | 各页面在 MacBook 视口加载 | body 可见，title 含页面名，metric-card 存在 | pytest + Playwright | — | `tests/pages/test_macbook_smoke.py`、`tests/playwright/macbook-smoke.spec.js` |
| UI-VISUAL-010 | P1 | visual | 滚动条阴影行为 | 页面内容溢出时检查滚动条阴影 | 滚动条有正确的 box-shadow 效果 | pytest | — | `tests/pages/test_scroll_shadow_behavior.py` |
| UI-VISUAL-011 | P1 | visual | UI 密度和字体大小 | 检查全局 CSS 变量 | `--ui-density` 和字体大小在各组件上一致 | pytest | — | `tests/ui/test_ui_density_and_font_size.py` |
| UI-VISUAL-012 | P1 | visual | UI 基础组件（primitives） | 检查 UI 基础元素渲染 | button/input/badge/tokenbar 等基础组件样式正确 | pytest | — | `tests/ui/test_ui_primitives.py` |
| UI-VISUAL-013 | P1 | visual | HiFi DOM 结构 | 检查高保真测试会话的 DOM 层级 | DOM 结构符合预期层级，无多余嵌套 | pytest | — | `tests/ui/test_hifi_dom_structure.py` |
| UI-VISUAL-014 | P1 | visual | 卡片子元素间距 | 检查 `.card` 子元素间距 | 间距符合设计令牌值 | pytest | — | `tests/ui/test_card_sub_spacing.py` |
| UI-VISUAL-015 | P2 | visual | 状态页（404/empty/loading）模板 | 检查各状态页模板结构 | 各状态页有 `.state-panel`，CSS 共享 states.css | pytest | — | `tests/pages/test_state_pages.py` |
