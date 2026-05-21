# Session Detail Delta 文档：生产模板 vs HIFI

> 对比源：`src/session_browser/web/templates/session.html` + `components/session_detail_timeline.html` + `components/session_detail_primitives.html`（生产）vs `$HOME/Downloads/feipi-session-browser-hifi-integrated-v1/pages/session-detail-trace.html` + `session-detail-metrics.html` + `session-detail-payloads.html`（HIFI）
> T083 生成，2026-05-21

---

## 1. 结构差异（Structural）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| S1 | 模板系统 | Jinja2 `{% extends "base.html" %}`，sidebar/topbar/footer 由 base 提供 | 独立 HTML，内嵌 `<div class="app-shell">` + sidebar + topbar + footer | structural | 需要迁移 |
| S2 | Tab 导航 | 无 tab 链接；仅侧边栏显示 "Sessions" | 3 个 tab 链接（Trace / Metrics / Payloads）在内容区域，使用 `<a class="tab">` 链接到不同 HTML 文件 | structural | 需要迁移 |
| S3 | Hero 区域 | 使用 `sdt.hero()` 宏，参数化传入 | 扁平 `<section class="session-hero card">`，含 `.hero-left`（agent-pill + hero-url + copy + hero-meta + issue-row）+ `.hero-kpis` + `.summary-strip` | structural | 需要迁移 |
| S4 | Trace 表格 | 使用 `sdt.trace_round()` 宏循环生成，基于 `.timeline-node` 嵌套结构 | `<table class="trace-table">` 带 `<colgroup>`，每 round 两行（round-row + expanded-row） | structural | 需要迁移 |
| S5 | Panel header | `sdt.trace_header()` 生成标题 + expand-all/collapse-all + status filter | `<div class="panel-head">` + `.head-actions`（seg toggle + expand-all + collapse-all） | structural | 需要对齐 |
| S6 | Metrics tab | 不存在（仅 trace tab 实现） | 独立页面 `session-detail-metrics.html`，含 metric grid cards + token breakdown table | structural | 需要迁移 |
| S7 | Payloads tab | 不存在（payload 通过 modal 查看） | 独立页面 `session-detail-payloads.html`，含 payload 列表表格 | structural | 需要迁移 |
| S8 | Modal 结构 | `<dialog id="payload-modal">` 在 base.html 中，通过 block 覆盖 | `<div class="modal-backdrop" data-modal>` + `.modal` + `.modal-head` + `.modal-body`，带 data-modal-kind/title/meta/content 属性 | structural | 需要对齐 |
| S9 | Toast | 无 | `<div class="toast" data-toast>` 在页面底部 | structural | 需要迁移 |
| S10 | 隐藏数据 | `<script type="application/json" id="raw-json">` | 无（HIFI 为静态演示） | structural | 生产保留 |

---

## 2. 样式差异（Styling）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| W1 | CSS 引用 | `/static/css/session-detail-timeline.css` | `../assets/session-detail-trace/session-detail.css` + `../assets/common-hifi-rules.css` | styling | 需要迁移 |
| W2 | Shell class | `sd-shell session-detail-page` | `.app-shell`（HIFI 自带完整 shell） | styling | base.html 提供 |
| W3 | Hero 样式 | `sdt.hero()` 宏输出自定义类名 | `.session-hero.card` + `.hero-left` + `.hero-title-line` + `.hero-meta` + `.hero-kpis` + `.kpi` + `.summary-strip` + `.summary-item` | styling | 需要迁移 |
| W4 | Tab 样式 | 无 | `.tab` + `.tab.active`（tab 导航条样式） | styling | 需要迁移 |
| W5 | Trace panel | `.sd-trace-panel` + `.sd-trace-list` + `.timeline-node` 嵌套 | `.panel` + `.panel-head` + `.head-actions` + `.seg` + `table.trace-table` | styling | 需要迁移 |
| W6 | Round row | `.timeline-node` + `.timeline-node__header` + `.timeline-node__body` | `tr.round-row` / `tr.expanded-row` 表格行 | styling | 需要迁移 |
| W7 | Modal | `<dialog>` 原生元素 + `.payload-modal__*` 类 | `.modal-backdrop` + `.modal` + `.modal-head` + `.modal-body` | styling | 需要迁移 |
| W8 | Agent pill | 无 | `.agent-pill`（显示 Claude/Qoder/Codex 标识） | styling | 需要迁移 |
| W9 | Issue links | 无 | `.issue-row` + `.chip-issue` + `.chip-fail`（带 data-action="jump-round"） | styling | 需要迁移 |
| W10 | Token bar | `.timeline-node__token-bar` + 4 段 div | `.tokenbar` + 4 段 span（fresh/read/write/out） | styling | 需要对齐 |

---

## 3. 行为差异（Behavioral）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| B1 | Tab 切换 | 无 tab，仅 trace 视图 | 3 tab（Trace/Metrics/Payloads），点击切换整个页面内容 | behavioral | 需要迁移 |
| B2 | Round expand/collapse | `.timeline-node__header` 点击切换 `.is-expanded` | `tr.round-row` + `tr.expanded-row`，点击 toggle-round 按钮 | behavioral | 结构不同但已实现 |
| B3 | Expand all / Collapse all | `sdt.trace_header()` 提供 | `.head-actions` 中两个按钮，data-action="expand-all"/"collapse-all" | behavioral | 需要对齐 |
| B4 | Status filter | 无 | All / Failed 切换按钮（seg toggle） | behavioral | 需要迁移 |
| B5 | Jump to round | 无 | Issue links 带 `data-action="jump-round"` 和 `href="#round-N"` | behavioral | 需要迁移 |
| B6 | Copy session URL | 无 | `data-action="copy"` 按钮在 hero 区域 | behavioral | 需要迁移 |
| B7 | Payload modal | dialog 元素 + JS 打开 | `.modal-backdrop` + data-modal 属性；通过 data-action="open-payload" 触发 | behavioral | 需要对齐 |
| B8 | Toast 通知 | 无 | `data-toast` 容器 | behavioral | 需要迁移 |
| B9 | 侧边栏 | 标准 6 项导航（dashboard/sessions/projects/agents/glossary） | 仅显示 Sessions + 设置按钮（session detail 上下文精简模式） | behavioral | 需要对齐 |
| B10 | Breadcrumb | 3 级：Agent Run Profiler / Session Detail / ID | 5 级：Agent Run Profiler / Sessions / agent / ID（加粗） | behavioral | 需要对齐 |

---

## 4. 数据绑定差异

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 |
|---|---|---|---|---|
| D1 | Session ID | `{{ session.session_id }}`（Jinja2） | 静态示例值 `e915ce5b` | data |
| D2 | Token 格式化 | `format_compact_token` filter（`1.7M`/`20.0K`） | 静态值（`34.3M`/`59.0K`）| data |
| D3 | Trace rows | `{% for row in trace_rows %}` 循环 | 静态 12 行示例 | data |
| D4 | Hero metrics | `hero_metrics` 参数传入 | 静态 4 KPI（Tokens/Rounds/Tools/Failed）| data |
| D5 | Issue links | `issue_links` 参数传入 | 静态 4 个 failed round 引用 | data |

---

## 5. 迁移优先级

| 优先级 | 项目 | 原因 |
|---|---|---|
| 高 | Tab 导航结构（S2/S6/S7） | Metrics/Payloads tabs 是 HiFi 独有核心功能 |
| 高 | Hero 区域对齐（S3/W3/B6/B10） | 视觉重心区域，影响第一印象 |
| 高 | Trace 表格结构（S4/W6） | 页面主体内容，交互密集 |
| 中 | Modal 结构对齐（S8/W7/B7） | 需要与 data-modal 属性契约一致 |
| 中 | Toast 通知（S9/B8） | 辅助功能，不阻塞核心流程 |
| 低 | 侧边栏精简（B9） | 可选优化，取决于整体 shell 策略 |
