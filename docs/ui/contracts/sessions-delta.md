# Sessions List — HIFI Delta Contract

> 来源: HIFI `pages/session-list.html` (v3) vs 生产 `src/session_browser/web/templates/sessions.html` + `components/sessions_list_components.html` + `components/ui_primitives.html`
> 生成时间: 2026-05-21 (Task T069)
> 行为参考: `docs/ui/contracts/behavior-sessions.md`

---

## 1. Structural Differences

| # | 区域 | HIFI (参考) | 生产 (当前) | 类别 | 迁移优先级 |
|---|---|---|---|---|---|
| 1 | 模板系统 | 独立 HTML，mock 数据硬编码 | Jinja2 模板，extends base.html，imports 组件宏 | structural | P4 (out of scope) |
| 2 | 表格容器 | `<section class="card table-card">` 包裹 `<div class="table-toolbar">` + `<div class="table-wrap">` + `<table class="data-table">` | `<section class="sessions-table-card">` + `<div class="sessions-table-toolbar">` + `<div class="sessions-table-scroll">` + `<div class="sessions-grid" role="table">` + div-based rows | structural | P1 |
| 3 | 行结构 | 原生 `<tbody>` + `<tr data-action="row">` + `<td>` | `<div class="sessions-row" data-agent/data-model/...>` 每列用 `<div class="sessions-td">` | structural | P1 |
| 4 | 表头 | 原生 `<thead>` + `<tr>` + `<th>`（含 `<button class="sort-button">` 或纯文本 `<th class="static-header">`） | 通过 `sl.table_header()` 宏渲染，`<div class="sessions-th">` + `<button>` / `<span>` | structural | P1 |
| 5 | Page title | `<div class="page-title">` 内含 `<h1>` + `<div class="subtitle">` + `<div class="chips">`（3 个 chip） | 通过 `sl.page_title()` 宏渲染，结构不同但语义等价 | structural | P2 |
| 6 | 空状态 | 独立 `<section class="state-strip">`（含 🔎 图标、Clear Filters 按钮） | `<div class="empty-state">` 内嵌在 sessions-grid 末尾 | structural | P2 |
| 7 | Table toolbar | `<div class="table-toolbar">` 仅含 `<div class="card-title">All Sessions</div>` | `<div class="sessions-table-toolbar">` 含 `.sessions-table-title` + `.sessions-table-sub` 描述文案 | structural | P3 |

## 2. Styling Differences

| # | 区域 | HIFI | 生产 | 类别 | 迁移优先级 |
|---|---|---|---|---|---|
| 8 | CSS 引用 | `<link href="../assets/session-list/session-list.css">` + `common-hifi-rules.css` | `<link rel="stylesheet" href="/static/css/ui-primitives.css">` + `/static/css/sessions-list.css` | styling | P4 (out of scope) |
| 9 | Filter card | `<section class="card filter-card">`，filter-row 内搜索框 + 3 个 select 在同一行，Clear All 和 Apply 按钮同行 | `<section class="sessions-filter-card">`，搜索框在 `.sessions-filter-head` 独占一行 + hint，select 在 `.sessions-control-row`，`__push` 分隔 | styling | P2 |
| 10 | 搜索框 | `<input class="input search" data-search="session-id" placeholder="🔎  Search Session ID...">`（emoji 在 placeholder 中） | `<label class="sessions-search">` 内含 `<span class="sessions-search__icon">` + `<input>`，外加 `<span class="sessions-search-hint">仅支持 Session ID</span>` | styling | P2 |
| 11 | Select 样式 | `<select class="select">` + `<label>` 单独 | `<label class="ui-select">` 包裹 `<span class="ui-select__label">` + `<select class="ui-select__control">` | styling | P3 (组件差异) |
| 12 | Title 单元格 | `<div class="title-main">` + `<div class="title-sub mono">`，sessionId 完整 + · + branch | `<div class="sessions-title"><a href="...">` 标题截断至 80 字符，`<div class="sessions-meta">` 内仅显示 `session_id[:12]` + branch | styling | P1 |
| 13 | Project 单元格 | `<div class="project-cell">` + `<span class="project-name">` + `<span class="project-tooltip">`（hover 显示路径） | `<div class="sessions-project-name"><a href="...">` + `<div class="sessions-project-parent">`（始终可见路径） | styling | P2 |
| 14 | Agent badge | `<span class="badge cc/cx/qd">` | `<span class="sessions-agent-badge sessions-agent-badge--{agent}">` | styling | P1 |
| 15 | Model 单元格 | `<td class="mono">` | `<div class="sessions-td"><span class="sessions-model">` | styling | P3 |
| 16 | Token 单元格 | `<td class="token-cell">` 内含 `<div class="token-total">` + `<div class="tokenbar show">`（首行带 `show` class）+ 内嵌 tooltip | 通过 `ui.token_total()` 宏渲染，结构不同 | styling | P1 |
| 17 | 数字单元格 | `<td class="num mono">` | `<div class="sessions-td sessions-td--num">` | styling | P3 |
| 18 | Updated 列 | `<td class="muted">`（如 "2m ago"） | `<div class="sessions-td sessions-td--num">` + `{{ s.ended_at \| relative_time }}` | styling | P3 |

## 3. Behavioral Differences

| # | 交互 | HIFI | 生产 | 类别 | 迁移优先级 |
|---|---|---|---|---|---|
| 19 | 排序按钮 | `<button class="sort-button" data-action="sort" data-sort="tokens|rounds|tools|duration|updated">` | `<button class="sessions-sort-btn" name="sort" value="...">`（通过 form 提交 + sort_urls） | behavioral | P1 |
| 20 | Token bar 交互 | `<div class="tokenbar show">` 首行默认展开，hover 显示内嵌 tooltip（含 Fresh/Cache Read/Cache Write/Output breakdown） | 通过 `ui.token_total()` 宏渲染，hover tooltip 行为由 JS 控制 | behavioral | P1 |
| 21 | Active filters | `<div class="active-filters">` 内显示 filter-chip（含 × 移除按钮） | 通过 `sl.active_filters()` 宏渲染，结构类似 | behavioral | P3 |
| 22 | 行点击导航 | `<tr data-action="row">` — 由通用 data-action 委派处理 | 内联 `<script>` 在 sessions.html 末尾，`grid.addEventListener('click', ...)` 读取 `.sessions-row` 的 dataset | behavioral | P2 |
| 23 | 排序方向图标 | `<span class="sort-icon">⇅</span>` 在 sort-button 文本后 | `<span class="sessions-sort-icon">` 在按钮内，通过 CSS 伪元素或 class 切换 | behavioral | P3 |
| 24 | Pagination | `<div class="pagination unified-pagination">` 内含 `input.page-input` + `span.page-status` + `button[data-action="next-page"]` | 通过 `sl.footer()` 宏渲染，结构不同（有 page-size selector） | behavioral | P2 |
| 25 | 静态列提示 | `<th class="static-header" title="...">`（tooltip 说明不提供排序） | 静态列通过宏渲染，无 title 提示 | behavioral | P3 |
| 26 | Token info icon | `<span class="info-icon" title="...">ℹ️</span>` 在 Tokens 表头旁 | 生产无此图标，token breakdown 仅在 hover token bar 时显示 | behavioral | P3 |

## 4. Data Differences

| # | 数据项 | HIFI | 生产 | 类别 | 迁移优先级 |
|---|---|---|---|---|---|
| 27 | Session ID 显示 | 完整 ID（如 `sess_01JWVXZ2Y4X3G7P9Q8M1N2D3`） | 截断至前 12 字符（如 `sess_01JWVX`） | data | P2 |
| 28 | Agent filter 值 | `<option>Claude Code</option>`（显示文本即值） | `<option value="claude_code">Claude Code</option>`（value 为内部 key） | data | P3 (架构差异) |
| 29 | Model filter 值 | 硬编码 3 个 mock 选项 | Jinja2 循环 `for m in model_list`，动态渲染 | data | P4 (out of scope) |
| 30 | Token 分解 | 首行 tokenbar 带 `show` class，内嵌 breakdown tooltip（4 段 % + Total） | 通过 `ui.token_total()` 宏，tooltip 由 JS 动态渲染 | data | P2 |
| 31 | Page size | 无 page-size 选择器（固定 20 行/页） | `<select class="sessions-footer-page-size__select">` 可选 20/100/500/All | data | P3 |
| 32 | Showing 文案 | `Page 1 of 245 · 1–20 of 4.9K sessions` | `Showing {start}–{end} of {total} matching sessions`（filter 区域） | data | P3 |

## 5. 已在生产中实现（无需迁移）

| # | 功能 | 说明 |
|---|---|---|
| 33 | 侧边栏导航 | 5 个 nav 项 (Dashboard/Sessions/Projects/Agents/Token Glossary) 已在 base.html 实现 |
| 34 | Topbar 结构 | breadcrumb + top-actions (help, local-command) 已在 base.html 实现 |
| 35 | Footer 文案 | `Agent Run Profiler · Read-only · Local` 已在 base.html 实现 |
| 36 | 行点击跳转 | sessions.html 内联 JS 实现 row click → `/sessions/{agent}/{session_id}` |
| 37 | Token formatter | `format_compact_token` filter 已注册，与 HIFI 显示等价 |

## 6. 不在本次迁移范围

| # | 项目 | 说明 |
|---|---|---|
| 38 | HIFI standalone assets | `assets/session-list/session-list.css` / `.js` 不在生产路径，CSS 整合归入 page CSS 迁移 |
| 39 | Emoji 图标系统 | HIFI 使用 emoji 作为 nav/icon，生产也已迁移至 emoji |
| 40 | Settings 抽屉后端 | 前端按钮已就绪，后端配置存储不在前端迁移范围 |

## 7. 迁移优先级汇总

| 优先级 | 数量 | 说明 |
|---|---|---|
| P0 | 0 | 无阻塞性问题 |
| P1 | 8 | #2, #3, #4, #12, #14, #16, #19, #20 — 核心结构差异（table vs div grid, badge, sort, token） |
| P2 | 7 | #5, #6, #9, #10, #13, #22, #24 — 体验改进（page-title, 空状态, filter 布局, 行导航, 分页） |
| P3 | 9 | #7, #11, #15, #17, #18, #23, #25, #26, #31 — 样式/行为微调 |
| P4 | 4 | #1, #8, #29, #38 — 模板系统/CSS 资产/out of scope |
