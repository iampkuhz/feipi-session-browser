# Sessions List Delta 文档：生产模板 vs HIFI

> 对比源：`src/session_browser/web/templates/sessions.html`（生产，基于 base.html）vs `$HOME/Downloads/feipi-session-browser-hifi-integrated-v1/pages/session-list.html`（HIFI）
> T167 生成，2026-05-21

---

## 1. 结构差异（Structural）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| S1 | 模板系统 | Jinja2 `{% extends "base.html" %}`，sidebar/topbar/footer 由 base.html 提供 | 独立 HTML，内嵌 `<div class="app">` + sidebar + topbar + footer | structural | 需要迁移 |
| S2 | 页面头部 | `.page-head` + `h1` + `p` + `.sessions-page-stats` + `.ui-stat-pill` × 3 | `.page-title` + `h1` + `.subtitle` + `.chips` + `.chip` × 3 | structural | 需要对齐 |
| S3 | 统计胶囊 | `.ui-stat-pill` 含 `<b>` 数值 + 文本 | `.chip` 含 emoji 图标 + `.mono` 数值 + 文本 | structural | 需要对齐 |
| S4 | 筛选表单 | `<form>` + `<select>` + server-side apply/clear | `.card.filter-card` + `.filter-row` + `<select>` + `data-filter` + Apply/Clear 按钮 | structural | 需要迁移 |
| S5 | 筛选器布局 | 多行 `.sessions-control-row`，含 label + search + selects | 单行 `.filter-row`，search + selects + spacer + buttons | structural | 需要对齐 |
| S6 | Active filters | `sl.active_filters(...)` 宏渲染 | `.active-filters` + `.filter-chip` + `.btn.chip-x` | structural | 需要对齐 |
| S7 | Table card | `.card.table-card` + `.table-toolbar` + `.data-table` | 同左，结构一致 | structural | 已对齐 |
| S8 | 表头结构 | 9 列：Title / Project / Agent / Model / Tokens / Rounds / Tools / Duration / Updated | 同左，但 HIFI 用 `<button>` sort-button，生产用 `<a>` sort-button | structural | 需要对齐 |
| S9 | 排序机制 | Server-side：`<a href="?sort=...">` + `data-sort-key` | Client-side：`<button>` + `data-action="sort"` + `data-sort` | structural | 需要对齐 |
| S10 | Token bar | `.tokenbar` + `.tokenbar-seg fresh/read/write/out` + `--segment-width` | `.tokenbar` + `.tokenbar-seg t-fresh/t-read/t-write/t-output` + `width: pct%` + `.token-tooltip` | structural | 需要对齐 |
| S11 | Token tooltip | 无（仅 tokenbar 段） | `.token-tooltip` 内含 breakdown 面板 | structural | 需要迁移 |
| S12 | 行点击行为 | `data-action="row"` + title 属性 | `data-action="row"` + title 属性 | structural | 已对齐 |
| S13 | 分页 | Server-side：prev/next URL 驱动的 `<button>` + `data-action` | Client-side：`.unified-pagination` + page input + status | structural | 需要对齐 |
| S14 | 空状态 | 表格内 `<td colspan="9">` + `ui.empty_state()` | 独立 `.state-strip` 在 table 下方 | structural | 需要对齐 |
| S15 | data-action 属性 | 部分：sort/row/page-input/prev-page/next-page/apply/clear | 全面：sort/row/page-input/prev-page/next-page/apply/clear/remove-filter/settings/help/local-command/nav | structural | 需要迁移 |
| S16 | 搜索范围 | 仅 Session ID（`data-search="session-id"`） | 仅 Session ID（一致） | structural | 已对齐 |
| S17 | Agent filter | Server-side `<select name="agent">` | Client-side `<select data-filter="agent">` | structural | 需要对齐 |
| S18 | Model filter | Server-side `<select name="model">` 从 `model_list` 渲染 | Client-side `<select data-filter="model">` 静态选项 | structural | 需要对齐 |
| S19 | Project filter | Server-side `<select name="project">` 从 `project_list` 渲染 | Client-side `<select data-filter="project">` 静态选项 | structural | 需要对齐 |

---

## 2. 样式差异（Styling）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| W1 | CSS 引用 | `ui-primitives.css` + `sessions-list.css` | `session-list.css` + `common-hifi-rules.css` | styling | 需要迁移 |
| W2 | Page head 样式 | `.page-head` + `.sessions-page-stats`（flex 布局） | `.page-title` + `.chips` + `.chip`（emoji + mono 值） | styling | 需要对齐 |
| W3 | 筛选卡片 | `.sessions-filter-card`（独立类名） | `.card.filter-card`（统一卡片类） | styling | 需要对齐 |
| W4 | Token bar 段命名 | `.tokenbar-seg fresh/read/write/out` | `.tokenbar-seg t-fresh/t-read/t-write/t-output` | styling | 需要对齐 |
| W5 | Token tooltip | 无 | `.token-tooltip`（绝对定位面板，含 breakdown 行） | styling | 需要迁移 |
| W6 | Sort button | `<a class="sort-button" href="...">` | `<button class="sort-button" data-action="sort">` | styling | 需要对齐 |
| W7 | Active filters | 由 macro 生成的样式 | `.filter-chip` + `.btn.chip-x`（圆角标签 + 移除按钮） | styling | 需要对齐 |
| W8 | Project cell | `.project-cell` + `.project-name` + `.project-tooltip` | 同左结构 | styling | 已对齐 |
| W9 | Badge 样式 | `.badge cc/cx/qd` | `.badge cc/cx/qd` | styling | 已对齐 |

---

## 3. 行为差异（Behavioral）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| B1 | 排序方式 | Server-side：点击 `<a>` 跳转 URL | Client-side：JS 排序 DOM 行 | behavioral | 需要对齐 |
| B2 | 筛选方式 | Server-side：`<form>` submit → URL params | Client-side：Apply 按钮 → JS 过滤 | behavioral | 需要对齐 |
| B3 | 分页方式 | Server-side：prev/next URL | Client-side：JS 分页 + page input | behavioral | 需要对齐 |
| B4 | Token tooltip | 无交互 | Hover tokenbar 显示 breakdown tooltip | behavioral | 需要迁移 |
| B5 | Clear All | Server-side：href 跳转 | Client-side：JS 清空 filter + 重置 | behavioral | 需要对齐 |
| B6 | 行点击 | `data-action="row"` → JS 导航 | `data-action="row"` → JS 导航 | behavioral | 已对齐 |

---

## 4. 可访问性差异（Accessibility）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| A1 | 表格 aria | `role="table"` + `aria-label="Sessions table"` | `aria-label="All sessions table"` | accessibility | 需要对齐 |
| A2 | 筛选 aria | 无 `aria-label` on filter card | `aria-label="Session filters"` on filter card | accessibility | 需要对齐 |
| A3 | Active filters aria | 无 | `aria-label="Active filters"` | accessibility | 需要对齐 |
| A4 | Sort aria-sort | `aria-sort="ascending/descending"` | 无 aria-sort（button 方式） | accessibility | 需要对齐 |
| A5 | Emoji aria-hidden | `aria-hidden="true"` on search icon | `title` 属性描述 emoji | accessibility | 需要对齐 |
| A6 | Empty state aria | `ui.empty_state()` 宏提供 | `.state-strip` + `role="status"` + `aria-live="polite"` | accessibility | 需要对齐 |
