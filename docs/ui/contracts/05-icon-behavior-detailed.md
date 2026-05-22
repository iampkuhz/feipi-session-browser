# 05 Icon Behavior Detailed

> 本文档从 `05-button-icon-behavior.md` 提取纯图标规则，并补充 HiFi 与生产环境的完整图标清单及差距分析。

## 全局图标规则（摘自 05-button-icon-behavior.md）

### 图标行为表要求

每个页面必须有一份图标行为表，字段：

```text
icon / location / semantic meaning / decorative-or-action / expected behavior / size class
```

### 图标尺寸分级

| 尺寸类 | 范围 | 典型用途 |
|---|---|---|
| nav icon | 18–20px | 侧边栏导航项前的圆点图标 |
| metric/card icon | 20–24px | 指标卡片、KPI 区域图标 |
| inline action icon | 14–16px | 行内操作、筛选芯片关闭按钮 |

### 常用图标预期行为

- Settings：打开 settings drawer/panel。
- Info icon：打开就地说明 popover。
- More icon：打开轻量 action menu。
- Sort icon：切换升序/降序/无序，显示 ↕→↓ 状态。
- Close/Dismiss icon（×）：关闭弹窗或清除筛选芯片。
- Toggle icon（›/⌄）：展开/折叠可收缩区域。
- Search icon（⌕）：搜索框内装饰性前缀。

---

## HiFi 图标清单

> 扫描范围：`docs/ui/hifi/` 下 28 个 HTML 文件。
> 扫描日期：2026-05-21

### 符号图标总览

HiFi 页面使用的 Unicode 符号共 9 种：

| 符号 | Unicode | 出现文件 | 语义 | 尺寸类 |
|---|---|---|---|---|
| ! | U+0021 | 26/28 文件 | 警告/错误标记（alert、badge、diag） | inline action |
| × | U+00D7 | 10 文件 | 关闭/移除（modal close、chip remove） | inline action |
| › | U+203A | 3 文件 | 展开指示器（toggle collapsed） | inline action |
| ⌄ | U+2304 | 2 文件 | 折叠指示器（toggle expanded） | inline action |
| ↕ | U+2195 | 8 文件 | 排序未激活（sort inactive） | inline action |
| ↓ | U+2193 | 3 文件 | 排序降序（sort descending active） | inline action |
| ⌕ | U+2315 | 2 文件 | 搜索图标（search input prefix） | inline action |
| ✓ | U+2713 | 1 文件 | 成功/通过标记 | inline action |
| ∆ | U+2206 | 3 文件 | 变更/差异标记（alert warn icon） | inline action |
| → | U+2192 | 3 文件 | 导航/跳转指示 | inline action |

### 图标类名清单

| 类名 | 文件 | 用途 |
|---|---|---|
| `.sort-icon` | `sessions_list_hifi_v3_no_hero.html` | 表头排序箭头容器 |
| `.sort-icon.active` | `sessions_list_hifi_v3_no_hero.html` | 当前激活排序列 |
| `.sessions-search__icon` | `sessions_list_hifi_v4_componentized.html` | 搜索框前置 ⌕ 符号 |

### 语义图标分布（按页面区域）

| 页面 | 区域 | 图标 | 含义 |
|---|---|---|---|
| hf_01 (Session Detail) | `.alert.critical .ico` | ! | 严重错误 |
| hf_01 (Session Detail) | `.alert.warn .ico` | ∆ | 警告 |
| hf_01 (Session Detail) | `.trace-row .toggle` | › / ⌄ | 展开/折叠 |
| hf_01 (Session Detail) | `.insp-close` | › | 关闭 inspector 面板 |
| sessions_list_v3 | `.th.sortable .sort-icon` | ↕ / ↓ | 表头排序 |
| sessions_list_v3/v4 | `.sessions-search__icon` | ⌕ | 搜索前缀 |
| v17/v18 session_detail | `.alert` / `.badge-err` | ! | 错误标记（密集使用） |
| v11/v12 session_detail | `.modal-close` | × | 关闭弹窗 |
| v15 session_browser | 多个 modal | × | 关闭弹窗 |
| gallery (hf_00) | `.kpi .v` | ✓ | 状态通过 |

### HiFi 独有图标

以下图标**仅出现在 HiFi**，生产模板中未见：

- `∆` (U+2206) — 用于 alert warn 图标
- `✓` (U+2713) — 用于 KPI 成功标记
- `⌕` (U+2315) — 搜索框装饰（生产模板用 CSS 实现）
- `⌄` (U+2304) — 折叠状态指示

---

## 生产图标清单

> 扫描范围：`src/session_browser/web/templates/` 下 27 个 HTML/Jinja2 模板。
> 扫描日期：2026-05-21

### 符号图标总览

生产模板使用的 Unicode 符号共 12 种：

| 符号 | Unicode | 出现位置 | 语义 | 尺寸类 |
|---|---|---|---|---|
| ! | U+0021 | base.html, dashboard, sessions, projects, agent, project, error, badge, viewer, sessions_grid | 错误/警告标记 | inline action |
| × | U+00D7 | sessions_list_components.html | 筛选芯片关闭按钮 | inline action |
| → | U+2192 | base.html, project.html | 导航指示 | inline action |
| … | U+2026 | glossary.html | 省略号（文本截断） | — |
| ↑ | U+2191 | ui_primitives.html | 排序升序（active asc） | inline action |
| ↓ | U+2193 | ui_primitives.html | 排序降序（active desc / default） | inline action |
| ↕ | U+2195 | ui_primitives.html | 排序未激活 | inline action |
| ⚠ | U+26A0 | timeline.html | 错误节点图标 | metric/card |
| 🧮 | U+1F9EE | glossary.html L32 | Token Types 指标图标 | metric/card |
| 📐 | U+1F4D0 | glossary.html L40 | Derived Metrics 指标图标 | metric/card |
| 🧩 | U+1F9E9 | glossary.html L48 | Provider Fields 指标图标 | metric/card |
| 🪧 | U+1FAA7 | glossary.html L56 | Round Signals 指标图标 | metric/card |
| 📖 | U+1F4D6 | glossary.html L84 | 空状态图标 | metric/card |
| ℹ️ | U+2139 | glossary.html L34,42,50,58 | 指标说明（info-icon） | inline action |

### 图标类名清单

| 类名 | 文件 | CSS 定义 | 用途 |
|---|---|---|---|
| `.logo-icon` | `base.html` | 30×30px, gradient bg | 侧边栏 Logo 图标 |
| `.nav-dot` | `base.html`, `session.html` | 8×8px, border-radius:999px | 导航项前缀圆点 |
| `.sessions-search__icon` | `sessions.html` | 12px font-size | 搜索框 ⌕ 符号 |
| `.state-panel__icon` | `404.html` | — | 错误页图标容器 |
| `.state-panel__icon--error` | `error.html` | — | 错误页图标变体 |
| `.timeline-node__icon` | `timeline.html` | — | 时序节点图标（动态 class） |
| `{{ icon_cls }}` | `ui_primitives.html` | — | 排序图标（宏参数） |
| `.density-toggle` | `base.html` | — | 密度切换图标 |
| `.sig.err` / `.sig.warn` | `base.html` (round map) | — | 状态信号点 |

### 模板宏图标

| 宏/位置 | 文件 | 逻辑 |
|---|---|---|
| 排序图标 | `components/ui_primitives.html` | `↑` (asc active) / `↓` (desc active) / `↕` (inactive) |
| 节点图标 | `components/timeline.html` | `error` → `⚠️`，其他类型动态映射 |
| 关闭按钮 | `components/sessions_list_components.html` | `×` (aria-label="Remove ... filter") |

---

## Dashboard 页图标行为表（dashboard.html）

> 扫描范围：`src/session_browser/web/templates/dashboard.html`
> 扫描日期：2026-05-22
> 覆盖 T190：确保本页所有图标都有行为说明。

### 图标清单

共 5 种符号，分布在 metric cards 和 chart cards。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | 📁 | U+1F4C1 | L49 `.metric-card__icon` | Projects 指标图标 | 装饰 | 标识 Projects 数量指标 | metric/card |
| 2 | 🧭 | U+1F9ED | L60 `.metric-card__icon` | Sessions 指标图标 | 装饰 | 标识 Sessions 总量指标 | metric/card |
| 3 | 🪙 | U+1FA99 | L71 `.metric-card__icon` | Total Tokens 指标图标 | 装饰 | 标识 Token 总消耗指标 | metric/card |
| 4 | 🚨 | U+1F6A8 | L82 `.metric-card__icon` | Failed Tools 指标图标 | 装饰 | 标识 Failed Tool 数量（红色警告） | metric/card |
| 5 | ℹ️ | U+2139 | L53,64,75,86,100,123,146 `.icon-button--info` | 指标/图表说明 | 动作 — 可点击 | 点击弹出 info popover 浮层，展示计算口径；JS `data-action="info-*"` 处理 | inline action |

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| `.metric-card__icon` | `.metric-card__icon` | `dashboard.css` | `font-size: 28px; line-height: 1` |
| `.icon-button--info` | `.icon-button.icon-button--info` | `dashboard.css` | `font-size: 14px; color: var(--text-subtle); cursor: pointer` |

### JS 行为覆盖

| 图标 | data-action | JS 处理位置（dashboard.js） | 行为 |
|---|---|---|---|
| ℹ️ (metric) | `info-projects` / `info-sessions` / `info-tokens` / `info-failed-tools` | dashboard.js | 点击打开 `#infoPopover` 显示指标口径说明 |
| ℹ️ (chart) | `info-chart-sessions` / `info-chart-tokens` / `info-chart-prompts` | dashboard.js | 点击打开 `#infoPopover` 显示图表口径说明 |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 5 种 | 全部有行为说明 |
| 装饰性图标 | 4 种（📁, 🧭, 🪙, 🚨） | 均有 `aria-hidden="true"` |
| 动作性图标 | 1 种（ℹ️） | 有 `title` 属性 + JS `data-action` 处理 |
| 有 aria-hidden | 所有 `.metric-card__icon` | 符合无障碍要求 |
| 有 title 属性 | 所有 `.icon-button--info` | 悬浮展示原生 tooltip |

---

## Sessions List 页图标行为表（sessions.html）

> 扫描范围：`src/session_browser/web/templates/sessions.html` + `components/sessions_list_components.html`
> 扫描日期：2026-05-22
> 覆盖 T190：确保本页所有图标都有行为说明。

### 图标清单

共 6 种符号，分布在 search/filter、table headers、active filters、empty states。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | ⌕ | U+2315 | L54 `.sessions-search__icon` | 搜索图标 | 装饰 | 搜索框前置视觉标记 | inline action |
| 2 | × | U+00D7 | `sessions_list_components.html` filter chip | 移除筛选 | 动作 — 可点击 | 点击移除对应筛选芯片；链接到 remove URL | inline action |
| 3 | ⇅ | U+21C5 | L119,127,134,141,148 `.sort-icon` | 排序未激活（默认） | 动作 — 跟随表头点击 | Server-side：点击 `<a>` 跳转到带 `?sort=` 参数的 URL | inline action |
| 4 | ↑ | U+2191 | `.sort-icon` (sort_dir == asc) | 排序升序（激活） | 动作 | 当前列按升序排列 | inline action |
| 5 | ↓ | U+2193 | `.sort-icon` (sort_dir == desc) | 排序降序（激活） | 动作 | 当前列按降序排列 | inline action |
| 6 | ℹ️ | U+2139 | L121 `.info-icon`（Tokens 列旁） | Token breakdown 说明 | 装饰 | 原生 `title` 悬浮提示："悬浮 token bar 查看 Fresh/Cache Read/Cache Write/Output breakdown" | inline action |
| 7 | 🔎 | U+1F50E | L211 `ui.empty_state(icon='🔎')` | 搜索无结果空状态 | 装饰 | 有活跃筛选但无匹配结果时展示 | metric/card |
| 8 | 📭 | U+1F4EC | L216 `ui.empty_state(icon='📭')` | 无数据空状态 | 装饰 | 无任何 session 数据时展示 | metric/card |

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| `.sessions-search__icon` | `.sessions-search__icon` | `sessions-list.css` | `font-size: 12px; margin-right: 4px` |
| `.sort-icon` | `.sort-button .sort-icon` | `sessions-list.css` | `font-size: 14px; color: var(--text-subtle)` |
| `.info-icon` | `.info-icon` | `sessions-list.css` | `font-size: 14px; cursor: help` |

### JS 行为覆盖

| 图标 | 事件 | JS 处理位置 | 行为 |
|---|---|---|---|
| × (chip remove) | `click` | 服务端：`<a href="?remove_filter=...">` | 导航到移除筛选后的 URL |
| ⇅/↑/↓ (sort) | `click` | Server-side `<a>` 导航 | 跳转到排序 URL |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 8 种 | 全部有行为说明 |
| 装饰性图标 | 3 种（⌕, ℹ️, 📭, 🔎） | 均有 `aria-hidden="true"` 或 `title` |
| 动作性图标 | 3 种（×, ⇅/↑/↓） | Server-side URL 导航 |
| 有 aria-hidden | `.sessions-search__icon`、`.sort-icon` | 符合无障碍要求 |
| 有 title 属性 | `.sort-button`、`.info-icon` | 悬浮展示原生 tooltip |

---

## Session Detail 页图标行为表（session.html + components）

> 扫描范围：`src/session_browser/web/templates/session.html` + `components/session_detail_timeline.html` + `components/session_detail_primitives.html`
> 扫描日期：2026-05-22
> 覆盖 T190：确保本页所有图标都有行为说明。

### 图标清单

共 11 种符号，分布在 hero 区域、tab 导航、trace 表格、空状态、payload modal。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | 🔌 | U+1F50C | L50 `ui.error_state(icon='🔌')` | 数据加载失败 | 装饰 | 配合 "Session data unavailable" 错误信息展示 | metric/card |
| 2 | 📭 | U+1F4EC | L80 `ui.empty_state(icon='📭')` | 无 Round 数据空状态 | 装饰 | 配合 "No rounds indexed" 信息和 "Run Scan" 按钮 | metric/card |
| 3 | 🧭 | U+1F9ED | L62 `.sd-tab-icon` | Trace tab 图标 | 装饰 | 标识 Trace 视图 tab | inline action |
| 4 | 📊 | U+1F4CA | L65 `.sd-tab-icon` | Metrics tab 图标 | 装饰 | 标识 Metrics 视图 tab | inline action |
| 5 | 📦 | U+1F4E6 | L68 `.sd-tab-icon` | Payloads tab 图标 | 装饰 | 标识 Payloads 视图 tab | inline action |
| 6 | 📋 | U+1F4CB | L21 `.sd-icon-btn-label` | 复制 Session URL | 动作 — 可点击 | 点击复制当前 session URL 到剪贴板；`data-action="copy-session-url"` | inline action |
| 7 | ⌄ | U+2304 | L139 `.round-toggle-btn` | 折叠指示（默认） | 动作 — 可点击 | 点击展开 trace round 详情；`data-action="toggle-round"` | inline action |
| 8 | ⌃ | U+2303 | L139 `.round-toggle-btn` (is_open) | 展开指示 | 动作 — 可点击 | 点击折叠 trace round 详情；`data-action="toggle-round"` | inline action |
| 9 | ✍️ | U+270D | L132 `.badge-manual` / L59 `.sd-summary-icon` | Manual Input 标记 | 装饰 | 标识手动输入 round | inline action |
| 10 | ✅ | U+2705 | L54 `.sd-summary-icon` | 成功状态 | 装饰 | 标识 "Completed" 状态 | inline action |
| 11 | 🛠️ | U+1F6F0 | L64 `.sd-summary-icon` | Subagent 标记 | 装饰 | 标识 Subagent 运行 | inline action |
| 12 | 💾 | U+1F4BE | L69 `.sd-summary-icon` | Cache Write 标记 | 装饰 | 标识 Cache Write 百分比 | inline action |
| 13 | 📦 | U+1F4E6 | L380 `.sd-payload-empty-state__icon` | 无 Payload 空状态 | 装饰 | Payload modal 未选择时展示 | metric/card |
| 14 | × | U+00D7 | L365 `.sd-modal-close` / `payload-modal__close` | 关闭弹窗 | 动作 — 可点击 | 关闭 payload modal；`data-action="close-payload"` / `data-action="close-modal"` | inline action |

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| `.sd-tab-icon` | `.sd-tab .sd-tab-icon` | `session-detail.css` | `font-size: 16px` |
| `.sd-icon-btn` | `.sd-icon-btn` | `session-detail.css` | 按钮容器，`background: none; border: none; cursor: pointer` |
| `.round-toggle-btn` | `.round-toggle-btn span` | `session-detail.css` | `font-size: 14px` |
| `.sd-summary-icon` | `.sd-summary-item .sd-summary-icon` | `session-detail.css` | `font-size: 18px` |

### JS 行为覆盖

| 图标 | data-action | JS 处理位置（session-detail.js / trace-interactions.js） | 行为 |
|---|---|---|---|
| 📋 | `copy-session-url` | session-detail.js | 复制 URL 到剪贴板 |
| ⌄/⌃ | `toggle-round` | trace-interactions.js | 展开/折叠 round 详情行 |
| × | `close-payload` / `close-modal` | session-detail.js / ui_primitives.js | 关闭 modal |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 14 种 | 全部有行为说明 |
| 装饰性图标 | 9 种（🔌, 📭, 🧭, 📊, 📦×2, ✍️, ✅, 🛠️, 💾） | 均有 `aria-hidden="true"` |
| 动作性图标 | 3 种（📋, ⌄/⌃, ×） | JS 绑定 data-action |
| 有 aria-hidden | 所有 `.sd-tab-icon`、`.sd-summary-icon`、`.sd-icon-btn-label` | 符合无障碍要求 |
| 有 title 属性 | `.sd-icon-btn`、`.round-toggle-btn` | 悬浮展示原生 tooltip |

---

## Projects List 页图标行为表（projects.html）

> 扫描范围：`src/session_browser/web/templates/projects.html`
> 扫描日期：2026-05-22
> 覆盖 T190：确保本页所有图标都有行为说明。

### 图标清单

共 8 种符号，分布在 metric cards、table headers、empty states、agent badges。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | 📁 | U+1F4C1 | L54 `.metric-icon .emoji.lg` | Projects 指标图标 | 装饰 | 标识 Projects 数量指标 | metric/card |
| 2 | 〽️ | U+303D | L68 `.metric-icon .emoji.lg` | Sessions 指标图标 | 装饰 | 标识 Sessions 总量指标 | metric/card |
| 3 | 🪙 | U+1FA99 | L82 `.metric-icon .emoji.lg` | Total Tokens 指标图标 | 装饰 | 标识 Token 总消耗指标 | metric/card |
| 4 | ⚠️ | U+26A0 | L96 `.metric-icon .emoji.lg` | Failed Tools 指标图标 | 装饰 | 标识 Failed Tool 数量（红色变体条件） | metric/card |
| 5 | ⓘ | U+24D8 | L60,73,87,101 `.icon-button--info` | 指标说明 | 动作 — 可点击 | 点击弹出 metric info tooltip；`data-action="metric-info"` | inline action |
| 6 | ↕ | U+2195 | L142,148,154,160 `.sort-caret` | 排序未激活（默认） | 动作 — 可点击 | 点击表头按钮触发客户端排序；`data-action="sort"` | inline action |
| 7 | 📁 | U+1F4C1 | L263 `#projects-empty .state-icon .emoji.lg` | 搜索无结果空状态 | 装饰 | 筛选无匹配项目时展示 | metric/card |
| 8 | 📁 | U+1F4C1 | L275 `ui.empty_state(icon='📁')` | 无数据空状态 | 装饰 | 无项目数据时展示 | metric/card |

### 补充：SVG 复制图标

| 元素 | 出现位置 | 语义 | 预期行为 |
|---|---|---|---|
| SVG copy icon | L206 `.path-copy-btn` | 复制项目路径 | 动作 — 可点击；`data-action="copy-project-path"` |

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| `.metric-icon .emoji.lg` | `.metric-icon .emoji.lg` | `projects.css` | `font-size: 24px`（由 `.emoji.lg` 控制） |
| `.icon-button--info` | `.icon-button.icon-button--info` | `projects.css` | `font-size: 14px; cursor: pointer` |
| `.sort-caret` | `.sortable-header .sort-caret` | `projects.css` | `font-size: 14px` |

### JS 行为覆盖

| 图标 | data-action | JS 处理位置（projects.js） | 行为 |
|---|---|---|---|
| ⓘ | `metric-info` | projects.js | 点击显示指标口径说明 toast |
| ↕ | `sort` | projects.js | 客户端排序，切换 ↕→↓→↕ 状态 |
| SVG copy | `copy-project-path` | projects.js | 复制项目路径到剪贴板 |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 8 种（含 1 种 SVG） | 全部有行为说明 |
| 装饰性图标 | 5 种（📁×3, 〽️, 🪙, ⚠️） | 均有 `aria-hidden="true"` |
| 动作性图标 | 3 种（ⓘ, ↕, SVG copy） | JS 绑定 data-action |
| 有 aria-hidden | 所有 `.emoji`、`.dot`、SVG `aria-hidden="true"` | 符合无障碍要求 |
| 有 title 属性 | `.icon-button--info`、`.sortable-header` | 悬浮展示原生 tooltip |

---

## Project Detail 页图标行为表（project.html）

> 扫描范围：`src/session_browser/web/templates/project.html`
> 扫描日期：2026-05-22
> 覆盖 T190：确保本页所有图标都有行为说明。

### 图标清单

共 8 种符号，分布在 page header、metric cards、table toolbar、table rows、empty state。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | ⬅️ | U+2B05 | L38 `.back-btn .emoji` | 返回上一页 | 动作 — 可点击 | 点击导航到 `/projects` 列表页 | inline action |
| 2 | 📋 | U+1F4CB | L45 `.btn.small .emoji` / L141 `.btn.small .emoji` | 复制 | 动作 — 可点击 | 上方复制项目路径（`data-action="copy-path"`）；行内复制 session ID（`data-action="copy-session"`） | inline action |
| 3 | 📈 | U+1F4C8 | L56 `.metric-icon .emoji` | Sessions 指标图标 | 装饰 | 标识 Sessions 计数指标 | metric/card |
| 4 | 📥 | U+1F4E5 | L70 `.metric-icon .emoji` | Input-side Tokens 指标图标 | 装饰 | 标识 Input-side Tokens 指标 | metric/card |
| 5 | 📤 | U+1F4E4 | L80 `.metric-icon .emoji` | Output Tokens 指标图标 | 装饰 | 标识 Output Tokens 指标 | metric/card |
| 6 | 📅 | U+1F4C5 | L90 `.metric-icon .emoji` | Active Period 指标图标 | 装饰 | 标识活跃周期指标 | metric/card |
| 7 | ⓘ | U+24D8 | L59,73,83,93,112 `.info-icon` | 指标/区域说明 | 动作 — 可点击 | 点击弹出 info tooltip 显示口径说明；`data-action="info"` | inline action |
| 8 | 🔌 | U+1F50C | L26 `ui.error_state(icon='🔌')` | 数据加载失败 | 装饰 | 配合错误信息展示 | metric/card |
| 9 | 📁 | U+1F4C1 | L203 `ui.empty_state(icon='📁')` | 无 Session 空状态 | 装饰 | 项目下无 session 时展示 | metric/card |
| 10 | → | U+2192 | L96（日期范围中） | 日期范围指示 | 装饰 | 展示 "开始日期 → 结束日期" 语义 | inline action |
| 11 | › | U+203A | L195 `.pagination .btn.sm` (next ›) | 下一页指示 | 动作 — 可点击 | 分页导航到下一页 | inline action |

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| `.emoji` (metric) | `.metric-icon .emoji` | `projects.css` | `font-size: 24px` |
| `.emoji` (back-btn) | `.back-btn .emoji` | `projects.css` | `font-size: 18px` |
| `.info-icon` | `.info-icon` | `projects.css` | `font-size: 14px; cursor: help` |

### JS 行为覆盖

| 图标 | data-action | JS 处理位置（projects.js） | 行为 |
|---|---|---|---|
| ⬅️ | 链接 `href="/projects"` | 原生导航 | 点击跳转到 projects 列表 |
| 📋 (path) | `copy-path` | projects.js | 复制项目路径到剪贴板 |
| 📋 (session) | `copy-session` | projects.js | 复制 session ID 到剪贴板 |
| ⓘ | `info` | projects.js | 点击显示 info tooltip |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 11 种 | 全部有行为说明 |
| 装饰性图标 | 6 种（📈, 📥, 📤, 📅, 🔌, 📁, →） | 均有 `aria-hidden="true"` |
| 动作性图标 | 4 种（⬅️, 📋×2, ⓘ, ›） | JS 绑定或链接导航 |
| 有 aria-hidden | 所有 `.emoji` | 符合无障碍要求 |
| 有 title 属性 | `.back-btn`、`.info-icon`、`.btn.small` | 悬浮展示原生 tooltip |

---

## Agents List 页图标行为表（agents.html）

> 扫描范围：`src/session_browser/web/templates/agents.html`
> 扫描日期：2026-05-22
> 覆盖 T190：确保本页所有图标都有行为说明。

### 图标清单

共 5 种符号，分布在 metric cards、table headers、agent cells、empty state。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | 🤖 | U+1F916 | L38 `.metric-icon .emoji` | Active Agents 指标图标 | 装饰 | 标识 Agent 数量指标 | metric/card |
| 2 | 🧾 | U+1F9FE | L48 `.metric-icon .emoji` | Sessions 指标图标 | 装饰 | 标识 Sessions 总量指标 | metric/card |
| 3 | 📁 | U+1F4C1 | L58 `.metric-icon .emoji` | Projects 指标图标 | 装饰 | 标识 Projects 数量指标 | metric/card |
| 4 | 🪙 | U+1FA99 | L74 `.metric-icon .emoji` | Total Tokens 指标图标 | 装饰 | 标识 Token 总消耗指标 | metric/card |
| 5 | ⓘ | U+24D8 | L41,51,61,77 `.info-icon` | 指标说明 | 动作 — 可点击 | 点击弹出 info tooltip 显示计算口径；`data-action="info"` | inline action |
| 6 | ↕ | U+2195 | L100,103,106,109,112,115,118,121,221-251 `.sort-caret` | 排序未激活（默认） | 动作 — 可点击 | 点击表头按钮触发客户端排序；`data-action="sort"` | inline action |
| 7 | 🤖 | U+1F916 | L301 `ui.empty_state(icon='🤖')` | 无 Agent 空状态 | 装饰 | 无 agent 数据时展示 | metric/card |

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| `.emoji` (metric) | `.metric-icon .emoji` | `agents.css` | `font-size: 16px` |
| `.info-icon` | `.info-icon` | `agents.css` | `font-size: 14px; cursor: help` |
| `.sort-caret` | `.sortable-header .sort-caret` | `agents.css` | `font-size: 14px; color: var(--text-subtle)` |
| `.agent-avatar` | `.agent-avatar` | `agents.css` | 34×34px, `border-radius: 11px`（含缩写文本 CC/CX/QD） |
| `.dot` | `.dot.claude/.codex/.qoder` | `agents.css` | 8px 圆点，3 色（brand/green/orange） |

### JS 行为覆盖

| 图标 | data-action | JS 处理位置（agents.js） | 行为 |
|---|---|---|---|
| ⓘ | `info` | agents.js | 点击显示 info tooltip 浮层 |
| ↕ | `sort` | agents.js | 客户端排序，切换排序方向 |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 7 种 | 全部有行为说明 |
| 装饰性图标 | 5 种（🤖×2, 🧾, 📁, 🪙） | 均有 `aria-hidden="true"` |
| 动作性图标 | 2 种（ⓘ, ↕） | JS 绑定 data-action |
| 有 aria-hidden | 所有 `.emoji`、`.dot` | 符合无障碍要求 |
| 有 title 属性 | 所有 `.info-icon`、`.sortable-header` | 悬浮展示原生 tooltip |

---

## Agent Detail 页图标行为表（agent.html）

> 扫描范围：`src/session_browser/web/templates/agent.html`
> 扫描日期：2026-05-21
> 覆盖 T148：确保本页所有图标都有行为说明。

### 图标清单

共 11 种符号，分布在 header、metric cards、section headers、table headers、error/empty states。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | `←` | U+2190 | L34 `.back-btn` | 返回上一页 | 动作 — 可点击 | 点击导航到 `/agents`；JS 拦截 `data-action="back"` 执行 `window.location.href` | inline action |
| 2 | `🤖` | U+1F916 | L38 `.agent-title .emoji` | Agent 身份标识（header） | 装饰 | 跟随 agent title 展示当前 agent 类型（Claude Code/Qoder/Codex） | metric/card |
| 3 | `🧾` | U+1F9FE | L50 `.metric-icon .emoji` | Sessions 指标图标 | 装饰 | 标识 Sessions 总量指标 | metric/card |
| 4 | `📁` | U+1F4C1 | L59 `.metric-icon .emoji` | Projects 指标图标 | 装饰 | 标识 Projects 数量指标 | metric/card |
| 5 | `⬇️` | U+2B07 | L68 `.metric-icon .emoji` | 输入方向（向下=输入） | 装饰 | 标识 Input-side Tokens 指标 | metric/card |
| 6 | `⬆️` | U+2B06 | L77 `.metric-icon .emoji` | 输出方向（向上=输出） | 装饰 | 标识 Output Tokens 指标 | metric/card |
| 7 | `♻️` | U+267B | L86 `.metric-icon .emoji` | 缓存复用 | 装饰 | 标识 Cache Reuse 比率指标 | metric/card |
| 8 | `⚠️` | U+26A0 | L95 `.metric-icon .emoji` | 失败警告 | 装饰 | 标识 Failed Tools 指标（红色 metric-icon） | metric/card |
| 9 | `ⓘ` | U+24D8 | L53,62,71,80,89,98,115,211 `.info-icon` | 指标/区域说明 | 动作 — 可点击 | 点击弹出 info-tooltip 浮层，展示计算口径；JS `data-action="info"` 处理 | inline action |
| 10 | `💡` | U+1F4A1 | L119 `.insight .emoji` | 洞察提示 | 装饰 | 跟随 insight badge 展示 "Most active model" 提示 | inline action |
| 11 | `↕` | U+2195 | L135-141, L236-242 `.sort-mark` | 排序未激活（默认） | 动作 — 跟随表头点击 | 点击 sortable th 后切换为 `↑`（升序）或 `↓`（降序）；JS `updateModelSortIndicators()` 处理 | inline action |

### 补充：通过宏传入的图标

以下图标通过 `ui_primitives.html` 宏渲染，不在 agent.html 中直接书写：

| 符号 | Unicode | 宏调用位置 | 语义 | 预期行为 |
|---|---|---|---|---|
| `⚠️` | U+26A0 | L24 `ui.error_state(icon='⚠️')` | 数据加载失败错误标记 | 装饰；配合 "刷新页面" 按钮使用 |
| `🤖` | U+1F916 | L307 `ui.empty_state(icon='🤖')` | 无 Session 数据空状态 | 装饰；配合 "返回 Agents" 按钮使用 |

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| emoji（metric card） | `.emoji` | `agents.css` L98-102 | `font-size: 16px; line-height: 1; display: inline-block` |
| info-icon | `.card.metric .info-icon` | `agents.css` L84-88 | `font-size: 14px; color: var(--text-subtle); cursor: help` |
| sort-mark | `.data-table th.sortable .sort-mark` | `agents.css` L476-480 | `font-size: 10px; color: #667085; margin-left: 6px` |
| insight emoji | `.insight .emoji` | `agents.css` L421-432（`.insight` 容器） | `display: inline-flex; align-items: center; gap: 7px` |
| back-btn arrow | `.back-btn`（内含 `←`） | `agents.css` L329-332 | `width: 36px; height: 36px`（按钮尺寸） |

### JS 行为覆盖

| 图标 | data-action | JS 处理位置（agents.js） | 行为 |
|---|---|---|---|
| `←` | `back` | L369-376 | 拦截点击，执行 `window.location.href` 导航 |
| `ⓘ` | `info` | L247-305 | 点击创建 `info-tooltip` 浮层，4 秒自动消失 |
| `↕` | 跟随 `th.sortable` `sort` | L396-466 | 切换排序方向，更新 `.sort-mark` 文本 |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 11 种 + 2 种宏传入 | 全部有行为说明 |
| 装饰性图标 | 8 种（🤖×2, 🧾, 📁, ⬇️, ⬆️, ♻️, ⚠️, 💡） | CSS 定义尺寸和行为 |
| 动作性图标 | 3 种（←, ⓘ, ↕） | JS 绑定 data-action |
| 有 aria-hidden | 所有 `<span class="emoji" aria-hidden="true">` | 符合无障碍要求 |
| 有 title 属性 | 所有 `.info-icon` | 悬浮展示原生 tooltip |

---

## Glossary 页图标行为表（glossary.html）

> 扫描范围：`src/session_browser/web/templates/glossary.html`（466 行）
> 扫描日期：2026-05-22
> 覆盖 T162：确保本页所有图标都有行为说明。

### 图标清单

共 6 种符号，分布在 metric cards 和 empty state。Anomaly badges 和 signal badges 均为纯文本，不使用 emoji 图标。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | 🧮 | U+1F9EE | L32 `.metric-icon.purple .emoji` | Token Types 指标图标 | 装饰 | 标识 Token 分类数量指标 | metric/card |
| 2 | 📐 | U+1F4D0 | L40 `.metric-icon.green .emoji` | Derived Metrics 指标图标 | 装饰 | 标识派生指标数量指标 | metric/card |
| 3 | 🧩 | U+1F9E9 | L48 `.metric-icon.orange .emoji` | Provider Fields 指标图标 | 装饰 | 标识 Provider 字段映射数量指标 | metric/card |
| 4 | 🪧 | U+1FAA7 | L56 `.metric-icon.blue .emoji` | Round Signals 指标图标 | 装饰 | 标识 Round 信号数量指标 | metric/card |
| 5 | ℹ️ | U+2139 | L34, L42, L50, L58 `.info-icon` | 指标说明 | 动作 — 可点击 | 原生 `title` 提示；JS `glossary.js` 预留 click hook（L100-108） | inline action |
| 6 | 📖 | U+1F4D6 | L84 `.state-icon`（empty state） | 空状态图标 | 装饰 | 搜索无结果时展示，JS 控制 `.is-hidden` 切换 | metric/card |

### 补充说明

- **Anomaly badges**（L129-131）：通过 `{{ anomaly() }}` 宏渲染，纯文本（"Long Duration"、"Cache Creation"），不使用 emoji。
- **Signal badges**（L427-456）：纯文本（"failed tool"、"llm error" 等），不使用 emoji。
- **Badge 区**（L98-131）：所有 badge 通过 `components/badge.html` 宏渲染，纯文本 + CSS 样式，不使用 emoji 图标。
- **Token badge**（L148）：`<span class="token-badge">` 纯文本标签，不使用 emoji。

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| `.metric-icon .emoji` | `.metric-icon .emoji` | `glossary.css` | 跟随 `.metric-icon` 容器尺寸，emoji 本身无额外 font-size |
| `.info-icon` | `.card.metric .info-icon` | `glossary.css` | `font-size` 继承，`cursor: help`（原生 title tooltip） |
| `.state-icon` | `.state-icon` | `glossary.css` | 空状态图标容器，font-size 由上下文决定 |

### JS 行为覆盖

| 图标 | 事件 | JS 处理位置（glossary.js） | 行为 |
|---|---|---|---|
| `.info-icon` | `click` | 预留 hook | 点击弹出 info-tooltip 浮层（预留，依赖原生 title 作为回退） |
| `.state-icon` | 无 | 无 | 纯装饰，无 JS 交互 |
| `.metric-icon .emoji` | 无 | 无 | 纯装饰，无 JS 交互 |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 6 种 | 全部有行为说明 |
| 装饰性图标 | 5 种（🧮, 📐, 🧩, 🪧, 📖） | 均有 `aria-hidden="true"` |
| 动作性图标 | 1 种（ℹ️） | 有 `title` 属性 + JS 预留 hook |
| 有 aria-hidden | 所有 `.emoji` 和 `.state-icon` | 符合无障碍要求 |
| 有 title 属性 | 所有 `.info-icon` | 悬浮展示原生 tooltip |

---

## State Pages 图标行为表（404.html, error.html）

> 扫描范围：`src/session_browser/web/templates/404.html`, `error.html`
> 扫描日期：2026-05-22
> 覆盖 T176：确保状态页面所有图标都有行为说明。

### 图标清单

共 2 种符号，均为装饰性大尺寸指示符，分布在 `.state-panel` 容器中。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | `404` | 纯文本数字 | 404.html L19 `.state-panel__icon` | 页面未找到状态标识 | 装饰 | 纯视觉标识，无交互；配合下方 "Page Not Found" 标题传达语义 | state icon (48px) |
| 2 | `!` | U+0021 | error.html L19 `.state-panel__icon--error` | 错误/异常状态标识 | 装饰 | 纯视觉标识，红色变体；配合下方 "Something Went Wrong" 标题传达语义 | state icon (48px) |

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| `.state-panel__icon` | `.state-panel__icon` | `states.css` L35-41 | `font-size: 48px; font-weight: 700; color: var(--text-subtle); line-height: 1` |
| `.state-panel__icon--error` | `.state-panel__icon--error` | `states.css` L44-46 | `color: var(--err)`（红色变体） |
| 移动端响应 | `.state-panel__icon` @media | `states.css` L124-126 | `font-size: 40px`（<768px） |

### JS 行为覆盖

| 图标 | 事件 | JS 处理位置（states.js） | 行为 |
|---|---|---|---|
| `.state-panel__icon` (404) | 无 | 无 | 纯装饰，无 JS 交互 |
| `.state-panel__icon--error` (!) | 无 | 无 | 纯装饰，无 JS 交互 |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 2 种 | 全部有行为说明 |
| 装饰性图标 | 2 种（404, !） | 均有 `aria-hidden="true"` |
| 动作性图标 | 0 种 | 不适用（纯静态页面） |
| 有 aria-hidden | 所有 `.state-panel__icon` | 符合无障碍要求 |
| 有 title 属性 | 无 | 不适用 — 装饰性图标无需 title |

---

## 差距分析

### HiFi 有 / 生产无

| 图标 | HiFi 用途 | 生产状态 | 风险 |
|---|---|---|---|
| `∆` (U+2206) | alert warn 图标 | 生产无此符号，用 `⚠` 替代 | 低 — 语义等价 |
| `✓` (U+2713) | KPI 成功标记 | 生产无此符号，用 CSS badge 替代 | 低 |
| `⌄` (U+2304) | 折叠指示 | 生产无此符号，展开/折叠用 JS 控制 | 低 |
| `›` (U+203A) | 展开指示器 + inspector close | 生产无此符号 | 中 — inspector 关闭按钮缺失视觉一致性 |

### 生产有 / HiFi 无

| 图标 | 生产用途 | HiFi 状态 | 风险 |
|---|---|---|---|
| `⚠` (U+26A0) | timeline 错误节点 | HiFi 用 `!` | 低 — 语义等价 |
| `…` (U+2026) | glossary 省略号 | HiFi 未覆盖 glossary 页 | 低 |
| `↑` (U+2191) | 排序升序 | HiFi 只有 ↕/↓ | 中 — 升序状态 HiFi 未展示 |
| `.logo-icon` | 30×30px 渐变 logo | HiFi 用 `.logo-mark` (文字) | 低 |
| `.nav-dot` | 8px 导航圆点 | HiFi 也有 `.nav-dot` | 无 — 一致 |
| `.density-toggle` | 密度切换 | HiFi 未覆盖此功能 | 低 — HiFi 无此 UI |
| `.sig` | round map 状态信号 | HiFi 有 `.sig` | 无 — 一致 |

### CSS 尺寸规则差距

| 规则 | 合同要求 | HiFi 实现 | 生产实现 |
|---|---|---|---|
| nav icon 18–20px | 合同 | 无显式尺寸 class | `.nav-dot`: 8×8px（圆点，非图标） |
| metric/card icon 20–24px | 合同 | 无显式尺寸 class | 无统一定义 |
| inline action 14–16px | 合同 | 无显式尺寸 class | `.sessions-search__icon`: 12px |

**结论**：当前 HiFi 和生产环境均**未实现合同要求的图标尺寸分级**。符号图标依靠 Unicode 字符自身尺寸，无显式 font-size 或 class 控制。需后续在 CSS 中补充。

### 覆盖率总结

| 维度 | HiFi | 生产 | 一致性 |
|---|---|---|---|
| 符号图标种类 | 9 种 | 7 种 | 6 种重叠 |
| 图标类名数量 | 2 个 | 9 个 | 1 个重叠（`.sessions-search__icon`） |
| 有语义图标 | !, ∆, ×, ↕, ↓, ⌕, ✓, ›, ⌄, → | !, ×, →, …, ↑, ↓, ↕, ⚠ | — |
| 尺寸分级实现 | 无 | 部分（search__icon=12px, nav-dot=8px, logo-icon=30px） | 不一致 |
| 图标行为表 | 无 | **已覆盖全部 9 页**（Dashboard / Sessions / Session Detail / Projects / Project Detail / Agents / Agent Detail / Glossary / State Pages） | 已落实 |

### 已知风险

1. **图标尺寸分级未实现** — 合同定义了三级尺寸，但 CSS 中无对应规则。
2. **升序图标 ↥ 缺失于 HiFi** — HiFi 只展示 ↕ 和 ↓，未覆盖升序激活态。
3. **alert 图标不一致** — HiFi 用 `!`/`∆`，生产用 `!`/`⚠`。
4. ~~每个页面缺少图标行为表~~ — **已解决（T190）**：所有 9 个页面均已有图标行为表。
