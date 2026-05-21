# 02 Component Contracts

## Shared primitives 必须覆盖

- AppShell
- SidebarNav
- TopbarBreadcrumb
- Button
- IconButton
- Badge / Pill
- MetricCard
- MetricGrid
- TokenBar
- Tooltip
- Popover
- DataTable
- FilterBar
- Pagination
- PayloadModal
- EmptyState
- ErrorState
- SectionCard

## Button

字段：

```text
size: sm / md
variant: primary / secondary / ghost / danger
state: normal / hover / active / disabled
behavior: data-action 或 href
```

Button 内部图标和文字必须 `inline-flex; align-items:center`。

## Pagination

统一结构：

```text
[prev] [page input] [next]
```

- 首页：不渲染 prev。
- 尾页：不渲染 next。
- 页码输入框确认后跳到指定页。

## TokenBar

- Segment：fresh / cache-read / cache-write / output。
- Hover tooltip：显示各 segment 数值与百分比。
- Total 可以出现在 tooltip，不一定出现在图面。
- token 数字统一短格式。

## DataTable

- Header 与 cell 对齐同列一致。
- Cell 必须 padding。
- 数字列可右对齐；文本列左对齐；但表头与单元格必须一致。
- sortable header 必须有明确 affordance；非 sortable 不显示 sort icon。

## HiFi 交叉验证补充（2026-05-21）

以下来自 HIFI_ROOT (`$HOME/Downloads/feipi-session-browser-hifi-integrated-v1/pages/`) 10 个页面的实际观察，
用于补充合同未明确但应约束的细节。

### Button — HiFi 实际使用的 class 变体

| HiFi class | 对应合同 variant | 备注 |
|---|---|---|
| `btn` | secondary (默认) | 无变体后缀时为次按钮 |
| `btn primary` | primary | 主操作按钮 |
| `btn sm` / `btn small` | size=sm | 小尺寸（两种写法等价） |
| `btn btn-sm` / `btn btn-sm btn-primary` | size=sm + primary | session-detail 页面的 payload 操作按钮 |
| `btn back-btn` | secondary + 语义 | 返回按钮，可单独或与 btn 组合 |
| `btn chip-x` | secondary + 语义 | 删除 chip 的按钮 |
| `icon-btn` | IconButton | 纯图标按钮，始终 `data-action` |

**补充约束**：
- `icon-btn` 是独立于 Button 的 IconButton 原始组件。
- `scope-switch__btn` 和 `scope-switch__btn is-active` 是 Dashboard 特有的范围切换按钮组。
- 按钮图标使用 emoji（`span.emoji` 或 `span.ui-icon`），非 SVG。

### Badge — HiFi 实际使用的 class 变体

| HiFi class | 语义 |
|---|---|
| `badge badge-err` / `badge err` | 错误/失败 |
| `badge badge-warn` / `badge warn` | 警告 |
| `badge badge-info` / `badge info` | 信息 |
| `badge badge-manual` / `badge manual` | 手动输入标记 |
| `badge badge-model` | 模型名称标记 |
| `badge ok` | 成功/正常 |
| `badge err tools-failed` | 工具失败专用（带修饰符） |
| `badge cc` / `badge cx` / `badge qd` | Agent 来源标记（Claude/Codex/Qoder） |

### MetricCard / MetricGrid — HiFi 结构

MetricCard 有两种形态：

**形态 A（session-detail metrics 页）**：
```html
<div class="metric-card">
  <h3><span class="ui-icon">🧮</span>Total Tokens</h3>
  <div class="big">34.3M</div>
  <div class="panel-sub">input + output + cache writes</div>
</div>
```

**形态 B（agent-detail 等页）**：
```html
<article class="card metric-card">
  <div class="metric-icon blue"><span class="emoji">🧾</span></div>
  <div class="metric-body">
    <div class="metric-label">Sessions</div>
    <div class="metric-value">4,892</div>
  </div>
</article>
```

**补充约束**：
- 图标颜色类：`metric-icon blue|green|orange|purple|red` 共 5 种语义色。
- 数值类可带 `mono` 修饰符（`metric-value mono`）。
- MetricGrid 统一使用 `class="metric-grid"` 包裹。
- 内联 token 指标使用 `metric-stack` + `metric-token`（非 MetricCard）。

### TokenBar — HiFi 实际 class 映射

| 合同 segment | HiFi class（页面级 bar） | HiFi class（DataTable 内嵌） |
|---|---|---|
| fresh | `fresh` | `t-fresh` |
| cache-read | `read` | `t-read` |
| cache-write | `write` | `t-write` |
| output | `out` | `t-out` |

**补充约束**：
- DataTable 单元格内的 TokenBar 使用 `t-` 前缀以区别于独立 TokenBar。
- Tooltip 结构：`.tooltip > .tip-title + .tip-row* + .tip-sep? + .tip-row (Total)`。
- 独立 TokenBar 可带 `show` 修饰符（`tokenbar show`）。
- TokenBar 段颜色通过 CSS 类名（非 style 背景色）区分。

### DataTable — HiFi 补充观察

- 统一使用 `<table class="data-table">`。
- 使用 `<colgroup>` 定义列宽（如 `col-token-md`、`col-num`、`col-duration`）。
- 排序表头：`class="sortable" data-action="sort" data-sort-key="..."` + `<span class="sort-mark">↕</span>`。
- 非排序表头无 `sortable` 类，不显示 `sort-mark`。
- 数字列统一加 `class="col-num"`，内容用 `class="mono"`。
- 行可带语义类：`class="round-row failed"`、`class="round-row manual"`。

### Pagination — HiFi 验证

完整结构（非首页）：
```html
<div class="pagination unified-pagination">
  <span class="page-status">Page</span>
  <input class="page-input mono" data-action="page-input" value="1"/>
  <span class="page-status">of 245 · 1–20 of 4.9K sessions</span>
  <span class="spacer"></span>
  <button class="btn sm" data-action="next-page">next ›</button>
</div>
```

单页情况（agents.html，of 1）：只渲染 `page-status` + `page-input`，不渲染 prev/next。
验证结果：合同描述的 prev/input/next 模式与 HiFi 一致。

### PayloadModal — HiFi 结构

```html
<div class="modal-backdrop" data-modal="">
  <div class="modal">
    <div class="modal-head">
      <span class="badge badge-info" data-modal-kind="">RESPONSE</span>
      <div><b data-modal-title="">...</b><div class="panel-sub">...</div></div>
      <span class="spacer"></span>
      <button class="btn" data-action="close-modal">...</button>
    </div>
    <div class="modal-body">
      <div data-modal-meta=""></div>
      <main data-modal-content=""></main>
    </div>
  </div>
</div>
```

**补充约束**：
- 模态框由 `.modal-backdrop`（遮罩）+ `.modal`（内容框）组成。
- 头部使用 `data-modal-kind`、`data-modal-title` 数据属性。
- 内容由 `data-modal-meta` 和 `data-modal-content` 占位。
- Toast 通知使用独立 `.toast` 元素（`data-toast=""`），不属于 Modal。

### SectionCard — HiFi 结构

```html
<section class="card section">
  <div class="section-head">
    <div class="section-title">...</div>
    <div class="section-sub">...</div>
    <span class="spacer"></span>
    <span class="insight">...</span>
  </div>
  <div class="table-wrap">...</div>
</section>
```

变体：`card section-card full-width`（全宽表格卡片）。

### EmptyState / ErrorState — HiFi 观察

EmptyState 使用 `.state-strip` 容器：
```html
<section class="state-strip">
  <div class="state-icon">🔎</div>
  <div>
    <div class="state-title">No matching sessions</div>
    <div class="muted">Try adjusting your filters or search terms.</div>
  </div>
</section>
```

ErrorState 未在 HiFi pages 中独立出现（通过 EmptyState 和 inline badges 替代）。

### AppShell — HiFi 验证

两种根容器：
- `<div class="app">` — 部分页面使用
- `<div class="app-shell">` — session-detail 系列页面使用

两者内部结构一致：`.sidebar` + `.main`（含 `.topbar` + `.content`）+ 可选 `.footer`。
