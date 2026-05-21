# Dashboard Delta 文档：生产模板 vs HIFI

> 对比源：`src/session_browser/web/templates/dashboard.html`（生产 v16）vs `$HOME/Downloads/feipi-session-browser-hifi-integrated-v1/pages/dashboard.html`（HIFI）
> T055 生成，2026-05-21

---

## 1. 结构差异（Structural）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| S1 | 模板系统 | Jinja2 `{% extends "base.html" %}`，sidebar/topbar 由 base 提供 | 独立 HTML，内嵌 `<div class="app-shell">` + sidebar + topbar | structural | 需要迁移 |
| S2 | Hero 区域 | 存在 `.hero` 区域，包含 `.hero-title`/`.hero-kpis`/`.hero-chips` | 无 hero 区域；使用 `.page-head` 替代（`<h1>Dashboard</h1>` + `<p>`） | structural | 需要迁移 |
| S3 | 指标网格 | 无独立 metric-card 结构；指标值内嵌在 hero-kpis 中 | 独立的 `.metric-grid` 含 4 个 `.metric-card`（Projects / Sessions / Total Tokens / Failed Tools） | structural | 需要迁移 |
| S4 | Chart 数量 | 2 张图表：Session Trend + Token Trend | 3 张图表：Session Trend + Token Trend + **Prompt Activity Trend** | structural | 需要迁移 |
| S5 | Chart 卡片结构 | `<section class="chart-card">`，内部 `.chart-head` 含 title + range-tabs | `<article class="chart-card" data-chart-card="*">`，内部 `.chart-card__head` 含 title + info-btn + ghost-menu-btn；legend 在 head 下方 | structural | 需要迁移 |
| S6 | Scope switch | 每张图各自独立的 `.range-tabs`（30d/7d），inline onclick | 全局唯一的 `.scope-switch`（Day/Week/Month），位于 `.page-head`，所有图表共享 | structural | 需要迁移 |
| S7 | Overlay 容器 | 无 tooltip/popover/menu/toast/drawer 容器 | 存在 `#chartTooltip`、`#infoPopover`、`#menuPopover`、`#toast`、`#settingsDrawer` | structural | 需要迁移 |
| S8 | 页脚 | 由 base.html 提供 | `<footer class="footer">Agent Run Profiler · Read-only · Local</footer>` | structural | 需要迁移 |

---

## 2. 样式差异（Styling）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| W1 | CSS 引用 | `/static/css/dashboard-v16.css`（Jinja URL） | `../assets/dashboard/dashboard.css` + `../assets/common-hifi-rules.css` | styling | 需要迁移 |
| W2 | Hero vs page-head | `.hero`（含 v16 hero 特有样式） | `.page-head`（更紧凑的标题区域） | styling | 需要迁移 |
| W3 | Metric card 样式 | 无 | 完整的 `.metric-card` 组件：`.metric-card__icon`、`.metric-card__body`、`.metric-card__label-row`、`.metric-card__label`、`.metric-card__value`、`.metric-card__sub`（含 `.success`/`.danger` 修饰） | styling | 需要迁移 |
| W4 | Chart card 样式 | `.chart-card` + `.chart-head` + `.range-tabs` + `.range-btn` | `.chart-card` + `.chart-card__head` + `.chart-card__title-row` + `.chart-card__subtitle` + `.legend-row` + `.chart-wrap` + `.y-axis` + `.stacked-chart` | styling | 需要迁移 |
| W5 | Scope switch 样式 | 无 | `.scope-switch` + `.scope-switch__btn` + `.is-active` | styling | 需要迁移 |
| W6 | Info button 样式 | 无 | `.icon-button` + `.icon-button--info`（16px info 图标按钮） | styling | 需要迁移 |
| W7 | Ghost button 样式 | 无 | `.icon-button` + `.icon-button--ghost`（透明背景 ⋯ 按钮） | styling | 需要迁移 |
| W8 | Overlay 样式 | 无 | `.tooltip`、`.popover`、`.menu-popover`、`.toast`、`.drawer` + `.drawer__panel` + `.drawer__head` + `.drawer__body` | styling | 需要迁移 |
| W9 | Legend 样式 | `.legend` + `.legend-item` + `.dot` | `.legend-row` + `.legend-item` + `.legend-dot`（`.legend-dot--claude`/`--codex`/`--qoder`） | styling | 需要迁移 |
| W10 | Breadcrumb 样式 | base.html 提供 | `.breadcrumb` 在 `.topbar` 内 | styling | 需要迁移 |

---

## 3. 行为差异（Behavioral）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| B1 | 图表时间粒度 | 30d / 7d 两张图各自切换 | Day（30天）/ Week（12周）/ Month（12月），全局同步切换所有 3 张图 | behavioral | 需要迁移 |
| B2 | 图表渲染方式 | 内联 JS 构建 HTML 柱状图（`bar-stack` + CSS height 百分比） | HIFI JS 使用同一套 chart 组件，X 轴统一（需迁移后验证） | behavioral | 需要迁移 |
| B3 | Total 数据展示 | Tooltip 中显示 Total 行 | HIFI 要求 Total **仅**在 hover tooltip 中出现，不可作为灰色柱段渲染 | behavioral | 已实现（生产 tooltip 已有 Total） |
| B4 | Info popover | 无 | 点击 metric card 或 chart card 的 ℹ️ 按钮 → 打开 `#infoPopover` 显示口径说明 | behavioral | 需要迁移 |
| B5 | Chart menu | 无 | 点击 ⋯ → 打开 `#menuPopover`（导出预览、打开详情、复制链接） | behavioral | 需要迁移 |
| B6 | Settings drawer | 无 | 点击 Settings → 打开 `#settingsDrawer` | behavioral | 需要迁移 |
| B7 | Toast 通知 | 无 | 存在 `#toast` 容器（行为待 JS 实现） | behavioral | 需要迁移 |
| B8 | 数据属性 | 使用 `onclick`（内联事件处理） | 使用 `data-action`、`data-scope`、`data-info`、`data-chart` 等属性（事件委托） | behavioral | 需要迁移 |
| B9 | 导航交互 | base.html 提供 | `data-action="nav-*"` 按钮，当前页 `.is-active` | behavioral | 由 base.html 提供，Dashboard 模板不涉及 |
| B10 | 图表 subtitle | 硬编码 `(sessions per day by agent)` | `<p data-subtitle="sessions">` 属性，JS 可动态更新 | behavioral | 需要迁移 |

---

## 4. 数据差异（Data）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| D1 | 数据源 | Jinja2 模板变量：`{{ stats.* }}`、`{{ trend }}`、`{{ agent_dist }}` | 静态 mock 数据（128 projects、4892 sessions、1247.5M tokens、321 failed tools） | data | 需要迁移 |
| D2 | Prompt Activity 数据 | 无此图表，无相关数据 | 需要新增 prompt activity 趋势数据（用户主动输入次数 by agent） | data | 需要迁移 |
| D3 | Token 格式化 | `formatTokens` 函数：B/M/K，`toFixed(1)` | HIFI 要求 `M` 缩写，保留 1 位小数（`1.7M`） | data | 部分已实现（生产已有 formatTokens） |
| D4 | Metric sub 文案 | 无 | 每个 metric card 有 `vs last 7 days` 对比文案，含 `.success`/`.danger` 修饰 | data | 需要迁移 |
| D5 | 图表 tooltip 数据 | Session tooltip：`claude_count`/`codex_count`/`qoder_count`/`total_count` | 相同结构 + Total 仅 tooltip 中出现 | data | 部分已实现 |

---

## 5. 已实现差异

| # | 差异点 | 说明 |
|---|---|---|
| I1 | Total 在 tooltip 中出现 | 生产模板 `buildSessionTooltip` 和 `buildTokenTooltip` 都已包含 Total 行 |
| I2 | Token 缩写格式化 | 生产模板 `formatTokens` 已支持 B/M/K 缩写，`toFixed(1)` 保留 1 位小数 |
| I3 | 3 个 agent legend | 生产模板 legend 已包含 Claude Code / Codex / Qoder |
| I4 | 多图表共享时间范围 | 生产模板 `updateChart` 调用 `renderTokenChart` 实现两图同步，需扩展到 3 图 |

---

## 6. 超出范围差异

| # | 差异点 | 说明 |
|---|---|---|
| O1 | HIFI 独立 CSS/JS 文件 | `dashboard.css`、`dashboard.js`、`common-hifi-rules.css`、`common-hifi-rules.js` 为 HIFI 预览专用，生产环境需整合到现有 CSS/JS 体系 |
| O2 | HIFI 侧边栏结构 | HIFI 的 sidebar 是完整自包含的；生产环境 sidebar 由 `base.html` 提供，Dashboard 模板不需要重复实现 |
| O3 | HIFI footer 文案 | HIFI footer 为 `Agent Run Profiler · Read-only · Local`；生产 footer 由 base.html 控制，文案可能不同 |
| O4 | Settings drawer 内容 | HIFI 仅为 preview，实际内容需在后端实现后接入 |

---

## 7. 迁移计划（按优先级排序）

### Phase 1：结构基础（必须先行）

| 优先级 | 任务 | 涉及文件 | 前置依赖 |
|---|---|---|---|
| P0 | 1. 添加 `.metric-grid` + 4 个 `.metric-card` 结构 | `templates/dashboard.html`、`style.css` 或 `dashboard.css` | 无 |
| P0 | 2. 替换 hero 为 `.page-head` + `.scope-switch` | `templates/dashboard.html` | 无 |
| P0 | 3. 统一 chart card 结构为 HIFI 格式（`.chart-card__head`、`.chart-card__title-row`、`.chart-card__subtitle`） | `templates/dashboard.html` | 无 |

### Phase 2：图表扩展

| 优先级 | 任务 | 涉及文件 | 前置依赖 |
|---|---|---|---|
| P1 | 4. 添加 Prompt Activity Trend 图表 | `templates/dashboard.html`、chart JS | Phase 1 |
| P1 | 5. 重构 scope-switch 为全局 Day/Week/Month | `templates/dashboard.html`、dashboard JS | Phase 1 |
| P1 | 6. 统一 3 张图表共享同一 chart 组件 | dashboard JS | 任务 4、5 |

### Phase 3：交互组件

| 优先级 | 任务 | 涉及文件 | 前置依赖 |
|---|---|---|---|
| P2 | 7. 添加 overlay 容器（tooltip、popover、menu、toast、drawer） | `templates/dashboard.html`、`style.css` | 无 |
| P2 | 8. 实现 info popover 行为（ℹ️ 按钮） | dashboard JS | 任务 7 |
| P2 | 9. 实现 chart menu 行为（⋯ 按钮） | dashboard JS | 任务 7 |
| P2 | 10. 实现 Settings drawer 行为 | dashboard JS、base.html | 任务 7 |

### Phase 4：数据集成

| 优先级 | 任务 | 涉及文件 | 前置依赖 |
|---|---|---|---|
| P3 | 11. 将 Jinja2 数据注入 metric card | `templates/dashboard.html`、后端数据层 | Phase 1 |
| P3 | 12. 实现 Prompt Activity 数据源 | 后端 Python | 任务 4 |
| P3 | 13. 实现 metric sub 对比文案（vs last 7 days） | `templates/dashboard.html`、后端 | Phase 1、任务 11 |

### Phase 5：样式收尾

| 优先级 | 任务 | 涉及文件 | 前置依赖 |
|---|---|---|---|
| P4 | 14. 整合 HIFI CSS 到生产 CSS 体系 | `style.css` 或 `dashboard.css` | Phase 1-3 |
| P4 | 15. 迁移内联 onclick 为 data-action 事件委托 | dashboard JS | Phase 2、3 |

---

## 8. 差异统计

| 分类 | 数量 |
|---|---|
| 结构差异（Structural） | 8 |
| 样式差异（Styling） | 10 |
| 行为差异（Behavioral） | 10 |
| 数据差异（Data） | 5 |
| **总计** | **33** |
| 已实现 | 4 |
| 超出范围 | 4 |
| 需要迁移 | 25 |
| 需要迁移的 P0 任务 | 3 |
| 需要迁移的 P1 任务 | 3 |
| 需要迁移的 P2 任务 | 4 |
| 需要迁移的 P3 任务 | 3 |
| 需要迁移的 P4 任务 | 2 |
