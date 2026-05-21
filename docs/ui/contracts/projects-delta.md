# Projects List Delta 文档：生产模板 vs HIFI

> 对比源：`src/session_browser/web/templates/projects.html`（生产，基于 base.html）vs `$HOME/Downloads/feipi-session-browser-hifi-integrated-v1/pages/projects.html`（HIFI）
> T097 生成，2026-05-21

---

## 1. 结构差异（Structural）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| S1 | 模板系统 | Jinja2 `{% extends "base.html" %}`，sidebar/topbar/footer 由 base 提供 | 独立 HTML，内嵌 `<div class="app">` + sidebar + topbar + footer | structural | 需要迁移 |
| S2 | 指标网格 | 不存在 | `.metric-grid` 含 4 个 `.card.metric`（Projects / Sessions / Total Tokens / Failed Tools），各含 icon + label + value + delta | structural | 需要迁移 |
| S3 | 筛选栏 | `.card.card--filter-bar` + `.filter-bar`：`<input>` + `<select id="project-sort">` + Reset 按钮 | `.card.filter-card` + `.filter-row`：`<input>` + Clear 按钮 + Apply 按钮，无 sort 下拉 | structural | 需要对齐 |
| S4 | 表头排序控件 | `<select>` 下拉框，5 个 `<option>`（Last Active / Sessions / Tokens / Tools / Failed Tools） | 表头内嵌 `<button class="sortable-header" data-action="sort" data-sort="*">`，含 `.sort-caret` | structural | 需要对齐 |
| S5 | 表格列数 | 8 列：Project / Path / Sessions / Agents / Tokens / Tools / Health / Last Active | 6 列：Project（name+path 合并）/ Agents / Sessions / Tokens / Tools / Last Active | structural | 需要迁移 |
| S6 | Project 单元格 | 项目名是 `<a href="/projects/...">` 链接，路径是独立 `<td>` | 项目名 `.project-name` + 路径 `.project-path` 在同一 `<td>` 内，无链接 | structural | 需要对齐 |
| S7 | 分页 | 无（展示所有行） | `.pagination`：页码输入 + "Page X of N · 1-20 of 128 projects" + next 按钮 | structural | 需要迁移 |
| S8 | 空状态 | `#projects-empty.is-hidden` 或 `.empty-state` 简单文本 | `.state-strip`：图标 + 标题 + 说明 + Clear Search 按钮 | structural | 需要对齐 |
| S9 | Toast 容器 | 无 | `<div class="toast" id="toast">` 在 `</body>` 前 | structural | 需要迁移 |
| S10 | 数据属性 | 行级 `data-name`/`data-path`/`data-last-seen`/`data-total-sessions`/`data-total-tokens`/`data-total-tools`/`data-total-failed` | 行级 `data-action="open-project"`，排序靠 `data-sort` 属性在表头按钮上 | structural | 需要迁移 |

---

## 2. 样式差异（Styling）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| W1 | CSS 引用 | 依赖 base.html 的 `style.css` + `ui-primitives.css` + `legacy-aliases.css` | `../assets/projects/projects-list.css` + `../assets/common-hifi-rules.css` | styling | 需要迁移 |
| W2 | 指标卡片样式 | 无 | `.metric`（`min-height:106px`，`padding:18px`）+ `.metric-icon`（52px 圆角方块，4 色背景）+ `.metric-value`（22px mono）+ `.delta`（含 `.bad` 修饰） | styling | 需要迁移 |
| W3 | 筛选卡片样式 | `.card--filter-bar` + `.filter-bar`（水平排列 input+select+button） | `.filter-card`（`padding:16px`）+ `.input.search`（`min-width:360px`）+ `.button`/`.button.primary` | styling | 需要对齐 |
| W4 | 表格工具栏样式 | `.card-title.flex` 简单文本 | `.table-toolbar`（`height:48px`）+ `.table-title` + `.table-note` | styling | 需要迁移 |
| W5 | Agent badge 样式 | `.badge.badge-claude`/`.badge-codex`/`.badge-qoder` 纯色背景 | `.badge.cc`/`.cx`/`.qd`（柔和背景色）+ `.dot.claude`/`.codex`/`.qoder`（8px 圆点） | styling | 需要对齐 |
| W6 | Token 条样式 | 无（纯文本 `format_compact_token`） | `.tokenbar`（132px 宽，8px 高，4 段彩色条）+ `.tooltip`（hover 显示 breakdown） | styling | 需要迁移 |
| W7 | Tools failed 徽章 | `.badge.badge-error` 红色纯数字 | `.badge.err.tools-failed` 含 "N failed" 文本，红色柔和背景 | styling | 需要对齐 |
| W8 | 可排序表头样式 | 无（`<select>` 控件） | `.sortable-header`（11px bold，hover 变色）+ `.sort-caret` | styling | 需要迁移 |
| W9 | 分页样式 | 无 | `.pagination`（`height:58px`）+ `.page-input` + `.page-status` + `.btn.sm` | styling | 需要迁移 |
| W10 | 空状态样式 | `.empty-state` 简单 div | `.state-strip`（flex 布局，图标 48px 圆角 + 标题 + 说明 + 按钮） | styling | 需要对齐 |

---

## 3. 行为差异（Behavioral）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| B1 | 排序交互 | `<select>` 切换值，JS `sortProjects()` 按 dataset 排序 | 点击表头按钮 `data-action="sort"` `data-sort="*"`，触发排序（HIFI 当前仅 toast 提示） | behavioral | 需要对齐 |
| B2 | 搜索交互 | `<input>` on input 即时过滤，`filterProjects()` 同时搜索 name 和 path | `<input>` + Apply/Clear 按钮，`data-action="apply-search"`/`"clear-search"`，仅搜索 project name | behavioral | 需要对齐 |
| B3 | 行点击行为 | 项目名 `<a>` 链接跳转 `/projects/{key}` | 整行 `data-action="open-project"` 可点击 | behavioral | 需要对齐 |
| B4 | 分页 | 无（所有行一次渲染） | 页码输入 `data-action="page-input"` + Enter 跳转，next 按钮 `data-action="next-page"` | behavioral | 需要迁移 |
| B5 | Toast 通知 | 无 | HIFI JS 通过 toast 反馈操作结果（search/sort/page/help/shell/settings/metric-info/open-project） | behavioral | 需要迁移 |
| B6 | Metric info | 无 | 每个 metric 有 `ⓘ` 按钮，`data-action="metric-info"`，触发 toast 显示口径说明 | behavioral | 需要迁移 |
| B7 | 帮助/Shell | base.html 提供 `?` 和 `⌘` 按钮 | HIFI 有 `data-action="open-help"` 和 `data-action="open-shell"` 按钮在 topbar | behavioral | base.html 已提供 |
| B8 | 路径复制 | 有 `<button data-action="copy-project-path" data-clipboard-text="...">` 复制按钮 | 无 | behavioral | 生产独有 |
| B9 | 路径独立列 | 有独立 `<td class="path-cell">`，含 `data-tooltip` 和复制按钮 | 路径内嵌在 project name 下方，无复制按钮 | behavioral | 需要迁移 |
| B10 | Delta 指示 | 无 | 每个 metric 有 `vs last 7 days` delta 文案，含 `.success`/`.bad` 修饰 | behavioral | 需要迁移 |

---

## 4. 数据绑定差异

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 |
|---|---|---|---|---|
| D1 | 项目列表 | `{% for p in projects %}` Jinja2 循环渲染 | 静态 8 行示例数据 | data |
| D2 | Token 值 | `{{ p_total_tokens \| format_compact_token }}` 纯文本 | `.token-value` + `.tokenbar`（4 段 inline style width%）+ `.tooltip`（hover breakdown 含具体数值） | data |
| D3 | 项目计数 | `{{ projects \| length }}`（两处：top label + table title） | 静态 "128 projects" / "Page 1 of 7 · 1-20 of 128 projects" | data |
| D4 | 指标值 | 无独立 metric 区域 | 静态值：Projects 128 / Sessions 4,892 / Total Tokens 1,247.5M / Failed Tools 321 | data |
| D5 | Agent 统计 | `p.claude_sessions` / `p.codex_sessions` / `p.qoder_sessions` 单独过滤 | 静态 badge：cc/cx/qd 数量直接写死 | data |
| D6 | Health 状态 | Jinja2 计算：`p.total_failed_tools > 0` → warning，`> 5` → error | 无独立 Health 列，failed tools 内联显示在 Tools 列中 | data |
| D7 | 排序数据源 | `data-total-sessions`/`data-total-tokens`/`data-total-tools`/`data-total-failed` 行属性 + `data-last-seen` 字符串 | `data-sort` 在表头按钮上，无行级排序数据属性 | data |

---

## 5. 迁移优先级

| 优先级 | 项目 | 涉及差异 | 原因 |
|---|---|---|---|
| 高 | 指标网格（S2/W2/B10/D4） | 视觉首屏区域，HIFI 核心新增 | 缺少即偏离 HIFI 设计 |
| 高 | 筛选栏重构（S3/W3/B2） | 从 select+input 改为 Apply/Clear 按钮模式 | 交互模式根本性变化 |
| 高 | 表头排序对齐（S4/W8/B1） | 从 select 到可点击表头 | HIFI 标准排序方式 |
| 高 | Token 条迁移（W6/D2） | 纯文本 → 可视化条 + hover tooltip | HIFI 独有核心可视化 |
| 中 | 表格列对齐（S5/S6/W5/B3/B9/D6） | 8 列 → 6 列，Health 合并到 Tools | 结构简化但需保留信息 |
| 中 | Agent badge 样式对齐（W5） | 纯色 → 柔和色 + 圆点 | 视觉一致性 |
| 中 | Toast 通知（S9/B5/B6） | 新增反馈机制 | 辅助交互 |
| 中 | 分页（S7/W9/B4） | 新增分页能力 | 数据量大时需要 |
| 低 | 空状态样式对齐（S8/W10） | `.empty-state` → `.state-strip` | 次要视觉优化 |
| 低 | 路径复制按钮（B8/B9） | 生产独有，HIFI 无 | 保留生产功能 |

---

## 6. 差异统计

| 分类 | 数量 |
|---|---|
| 结构差异（Structural） | 10 |
| 样式差异（Styling） | 10 |
| 行为差异（Behavioral） | 10 |
| 数据绑定差异（Data） | 7 |
| **总计** | **37** |
| 需要迁移的 P0/P1 任务 | 4（指标网格、筛选栏、表头排序、Token 条） |
| 需要迁移的 P2 任务 | 3（表格列、Agent badge、Toast） |
| 需要迁移的 P3 任务 | 2（分页、空状态） |
