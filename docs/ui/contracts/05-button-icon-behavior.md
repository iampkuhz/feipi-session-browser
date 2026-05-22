# 05 Button and Icon Behavior Contract

## 全局按钮行为表要求

每个页面必须有一份按钮行为表，字段：

```text
selector / label / location / data-action-or-href / expected render behavior / validation
```

## 全局图标行为表要求

每个页面必须有一份图标行为表，字段：

```text
icon / location / semantic meaning / decorative-or-action / expected behavior / size class
```

## 常用按钮预期

- Settings：打开 settings drawer/panel。
- Info icon：打开就地说明 popover。
- More icon：打开轻量 action menu。
- Apply：提交当前筛选并刷新列表。
- Clear：清空当前筛选并刷新列表。
- Prev：跳到上一页；首页不渲染。
- Page input：输入页码并确认后跳转。
- Next：跳到下一页；尾页不渲染。
- Context / Response / Result：打开同一个 PayloadModal，切换对应内容。

## 图标尺寸

- nav icon: 18–20px。
- metric/card icon: 20–24px。
- inline action icon: 14–16px。

---

## Current State

> Scanned 2026-05-21 against repo `docs/ui/hifi/` and `src/session_browser/web/templates/`.

### HiFi 按钮总览

| 指标 | 数量 |
|---|---|
| HiFi 页面总数 | 28 个 HTML 文件 |
| 按钮总数（`<button>` + `<a.btn>`） | 240 个 |
| 含 `onclick` 的按钮 | 19 个 |
| 含 `data-action` 的按钮 | 0 个（HiFi 页面不使用 data-action 约定） |

### HiFi 按钮分布（按文件）

> Note: Most hifi files were cleaned up in 2026-05. The table below is a historical snapshot.

| 文件 | 按钮数 |
|---|---|
| `session_detail_hifi_v9_timeline_rounds_refined.html` (deleted) | 19 |
| `session_detail_hifi_v11_interaction_payload_refined.html` (deleted) | 19 |
| `session_browser_hifi_v15/session_detail_result_modal.html` (deleted) | 18 |
| `session_browser_hifi_v15/session_detail_response_modal.html` (deleted) | 18 |
| `session_browser_hifi_v15/session_detail_context_modal.html` (deleted) | 18 |
| `session_browser_hifi_v15/session_detail_trace.html` (deleted) | 17 |
| `hf_01_session_detail_mhtml_ready.html` (deleted) | 15 |
| `prior/session_detail_hifi_v12b_modal_open_state.html` (deleted) | 11 |
| `prior/session_detail_hifi_v12b_clickable_modal.html` (deleted) | 11 |
| `session_detail_hifi_v12c_modal_open_subagent_tool.html` (deleted) | 10 |
| `session_detail_hifi_v12c_modal_open_response.html` (deleted) | 10 |
| `session_detail_hifi_v12c_clickable_response_blocks.html` (deleted) | 10 |
| `hf_05_full_payload_viewer.html` (deleted) | 9 |
| `hf_04_hotspots_view.html` (deleted) | 9 |
| `hf_03_calls_view.html` (deleted) | 9 |
| `sessions_list_hifi_v3_no_hero.html` (deleted) | 8 |
| `session_detail_v17/index.html` (deleted) | 5 |
| `session_browser_hifi_v15/sessions_list.html` (deleted) | 5 |
| `hf_02_sessions_list.html` (deleted) | 5 |
| `dashboard_v16/dashboard.html` (deleted) | 4 |
| `dashboard_v16_tooltip_dots/dashboard.html` (deleted) | 4 |
| `session_detail_v18/index.html` (deleted) | 3 |
| `session_browser_hifi_v15/dashboard.html` (deleted) | 2 |
| `session_browser_hifi_v15/projects_overview.html` (deleted) | 1 |

### 生产环境按钮总览

| 指标 | 数量 |
|---|---|
| 生产模板按钮总数 | 35 个 |
| `<button>` 缺少 `data-action` | 16 个 |
| `<a.btn>` 缺少 `href` | 0 个 |
| 含 `onclick` 的按钮 | 10 个 |

### 生产环境按钮分布（按文件）

| 文件 | 按钮数 |
|---|---|
| `components/viewer.html` | 8 |
| `components/session_detail_timeline_v12.html` | 6 |
| `dashboard.html` | 4 |
| `components/session_detail_timeline.html` | 4 |
| `base.html` | 3 |
| `partials/sessions_grid.html` | 2 |
| `components/sessions_list_components.html` | 2 |
| `projects.html` | 1 |
| `project.html` | 1 |
| `components/ui_primitives.html` | 1 |
| `components/session_detail_payload_v15.html` | 1 |
| `components/data_table.html` | 1 |

### 需要修复的生产按钮

- **16 个 `<button>` 缺少 `data-action`**：主要集中在 `viewer.html`（8 个）、`dashboard.html`（4 个）、`ui_primitives.html`（1 个模板宏）、`data_table.html`（1 个）、`project.html`（1 个）、`projects.html`（1 个）。
- **10 个 `onclick` 违规**：`viewer.html`（4 个 inline onclick）、`dashboard.html`（4 个）、`project.html`（1 个）、`projects.html`（1 个）。这些违反了合同要求的 `data-action` 驱动行为模式。

### 合同合规性评估

| 合同要求 | HiFi 状态 | 生产状态 |
|---|---|---|
| 每个页面有按钮行为表 | 无（需补充） | 无（需补充） |
| 每个页面有图标行为表 | 无（需补充） | 无（需补充） |
| 按钮使用 data-action 或 href | HiFi 使用 onclick | 16/35 缺少 data-action |
| 按钮无 inline onclick | 19/240 有 onclick | 10/35 有 onclick |
| 图标尺寸分级 | 未见显式尺寸 class | 未见显式尺寸 class |

---

## Agent Detail 页面按钮行为表 (agent.html)

> Scanned 2026-05-21 against `src/session_browser/web/templates/agent.html` (324 lines).
> 该页面所有按钮/交互元素均有 data-action 或 href，无 inline onclick，无 inline style 于按钮。

### 按钮行为表

| selector / label | location | data-action-or-href | expected render behavior | validation |
|---|---|---|---|---|
| `a.btn.back-btn` (←) | header left | `data-action="back"` + `href="/agents"` | 返回 Agents 列表页 | JS agents.js L369+ |
| `button.btn.sm` (prev) | pagination bar | `data-action="prev-page"` | 跳到上一页；首页不渲染 | JS agents.js L348+ |
| `button.btn.sm` (next) | pagination bar | `data-action="next-page"` | 跳到下一页；尾页不渲染 | JS agents.js L336+ |
| `input.page-input` | pagination bar | `data-action="page-input"` | 输入页码后 Enter 跳转 | JS agents.js L322+ |
| `tr[data-action="open-session"]` | sessions table body | `data-action="open-session"` + `data-href="/sessions/..."` | 点击行打开会话详情 | JS agents.js L381+ |
| `a` (session title link) | sessions table td | `href="/sessions/{agent}/{session_id}"` | 直接导航到会话 | native link |
| `a` (project link) | sessions table td | `href="/projects/{project_key}"` | 直接导航到项目 | native link |
| `ui.button` macro (error state) | error section | `data-action="refresh"` | 刷新当前页面 | via ui_primitives macro |
| `ui.button` macro (empty state) | empty section | `data-action="back"` + `href="/agents"` | 返回 Agents 列表 | via ui_primitives macro |
| `a` (breadcrumb Dashboard) | breadcrumb | `href="/dashboard"` | 导航到 Dashboard | native link |
| `a` (breadcrumb Agents) | breadcrumb | `href="/agents"` | 导航到 Agents 列表 | native link |
| `th.sortable` (Model table) | model breakdown header | `data-action="sort"` + `data-sort-key` | 点击排序 | JS agents.js L44+ |
| `th.sortable` (Sessions table) | sessions header | `data-action="sort"` + `data-sort-key` | 点击排序 | JS agents.js L44+ |

### 图标行为表

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| `span.emoji` (robot) | header title | Agent 标识 | decorative | 无交互 | ~20px |
| `span.emoji` (metrics) | 6 metric cards | 各指标图标 | decorative | 无交互 | 20-24px |
| `span.info-icon` (ⓘ) × 8 | metric cards + section titles | 指标说明 | action | 点击打开 tooltip/popover 显示定义 | inline action 14-16px |
| `span.sort-mark` (↕) | th.sortable | 排序指示 | decorative | 随排序状态切换 | inline |
| `span.badge.err` | sessions table failed col | 失败计数 | decorative | 无交互 | inline |

### 合规结论

| 合同要求 | agent.html 状态 |
|---|---|
| 每个按钮有 data-action 或 href | 全部覆盖（15/15） |
| 无 inline onclick | 合规（0 个） |
| 无 inline style 于按钮 | 合规（inline style 仅用于 tokenbar 布局） |
| 按钮行为表已记录 | 已补充 |
| 图标行为表已记录 | 已补充 |

---

## Glossary 页面按钮行为分析 (glossary.html)

> Scanned 2026-05-22 against `src/session_browser/web/templates/glossary.html` (466 lines)
> and HIFI `token-glossary.html` (183 lines).

### 生产环境结论：不适用

**生产环境 glossary.html 不含任何 `<button>` 或 `<a class="btn">` 元素。**
该页面为纯静态内容——数据表格、搜索输入框、badge 宏和 `.info-icon` 提示图标。
因此按钮行为覆盖对本页面不适用。

扫描结果：
- `<button>` 元素：0 个
- `<a class="btn">` 元素：0 个
- `onclick` 属性：0 个
- `data-action` 属性仅出现在 `th.sortable` 表头单元格上（6 处），这些是表格排序交互，不是按钮

### HIFI 页面按钮行为表

HIFI 版本在侧边栏和顶栏有 3 个按钮（属于全局 shell，非术语内容本身）：

| selector / label | location | data-action-or-href | expected render behavior | validation |
|---|---|---|---|---|
| `button.settings` (Settings) | sidebar bottom | `data-action="settings"` | 打开 Settings 面板 | 全局 shell |
| `button.icon-button` (help) | topbar right | `data-action="help"` | 打开术语页帮助 | 全局 shell |
| `button.icon-button` (shortcuts) | topbar right | `data-action="shortcuts"` | 打开快捷键说明 | 全局 shell |

### 图标行为表

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| `span.info-icon` (x4) | metric-card labels | 指标说明 | action | 原生 title 提示；JS 预留 click hook（glossary.js L100-108） | inline action 14-16px |
| `span.emoji` (x4) | metric-card icons | 各指标类别 | decorative | 无交互 | 20-24px |

### 合规结论

| 合同要求 | glossary.html 状态 |
|---|---|
| 每个按钮有 data-action 或 href | 不适用（0 个按钮） |
| 无 inline onclick | 合规（0 个） |
| 无 inline style 于按钮 | 合规（无按钮） |
| 按钮行为表已记录 | 不适用，已说明原因 |
| 图标行为表已记录 | 已补充 |

---

## State Pages 按钮行为分析（404.html, error.html）

> Scanned 2026-05-22 against `src/session_browser/web/templates/404.html` (29 lines)
> and `src/session_browser/web/templates/error.html` (32 lines).

### 生产环境结论：不适用（无按钮）

**生产环境 404.html 和 error.html 均不含任何 `<button>` 或 `<a class="btn">` 元素。**
这两个页面为静态状态页——仅包含居中面板（`.state-panel`）、图标、标题、描述和原生导航链接（`<a href>`）。
因此按钮行为覆盖对本页面不适用。

扫描结果：
- `<button>` 元素：0 个
- `<a class="btn">` 元素：0 个
- `onclick` 属性：0 个
- `data-action` 属性：0 个

### 导航链接（`<a href>`）行为表

State Pages 使用原生锚点链接实现页面导航，无需 `data-action` 或 JS 行为绑定。

| selector / label | location | href | expected render behavior | validation |
|---|---|---|---|---|
| `a` (breadcrumb Dashboard) | 404.html breadcrumb | `href="/dashboard"` | 导航到 Dashboard | native link |
| `a.state-panel__link` (← Dashboard) | 404.html nav links | `href="/dashboard"` | 导航到 Dashboard | native link |
| `a.state-panel__link` (Projects) | 404.html nav links | `href="/projects"` | 导航到 Projects | native link |
| `a.state-panel__link` (Sessions) | 404.html nav links | `href="/sessions"` | 导航到 Sessions | native link |
| `a.state-panel__link` (Agents) | 404.html nav links | `href="/agents"` | 导航到 Agents | native link |
| `a` (breadcrumb Dashboard) | error.html breadcrumb | `href="/dashboard"` | 导航到 Dashboard | native link |
| `a.state-panel__link` (← Dashboard) | error.html nav links | `href="/dashboard"` | 导航到 Dashboard | native link |

### 图标行为表

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| `div.state-panel__icon` (404) | 404.html panel top | 404 错误码标识 | decorative | 无交互 | ~48px |
| `div.state-panel__icon--error` (!) | error.html panel top | 通用错误标识 | decorative | 无交互 | ~48px |

### 合规结论

| 合同要求 | state pages 状态 |
|---|---|
| 每个按钮有 data-action 或 href | 不适用（0 个按钮；所有导航链接均有 href） |
| 无 inline onclick | 合规（0 个） |
| 按钮行为表已记录 | 不适用（无按钮），导航链接已记录 |
| 图标行为表已记录 | 已补充 |

---

## Dashboard 页面按钮行为分析 (dashboard.html)

> Scanned 2026-05-22 against behavior contract `docs/ui/contracts/behavior-dashboard.md`.
> 详细行为表见 `behavior-dashboard.md`；以下为摘要。

### 生产环境结论：部分覆盖

生产模板 `dashboard.html` 当前只有 4 个按钮（`range-btn`），使用 `onclick` 而非 `data-action`。
完整 sidebar/topbar 按钮由 `base.html` 提供。HIFI 规范要求 20 个按钮 + 18 个图标。

### 按钮行为表（HIFI 规范摘要）

| selector / label | location | data-action-or-href | expected render behavior | validation |
|---|---|---|---|---|
| `button.nav-item[data-action="nav-dashboard"]` | Sidebar nav | `data-action="nav-dashboard"` | 导航到 Dashboard；当前页 `is-active` | `.is-active` 修饰当前页 |
| `button.nav-item[data-action="nav-sessions"]` | Sidebar nav | `data-action="nav-sessions"` | 导航到 Sessions 列表页 | 无特殊状态 |
| `button.nav-item[data-action="nav-projects"]` | Sidebar nav | `data-action="nav-projects"` | 导航到 Projects 列表页 | 无特殊状态 |
| `button.nav-item[data-action="nav-agents"]` | Sidebar nav | `data-action="nav-agents"` | 导航到 Agents 列表页 | 无特殊状态 |
| `button.nav-item[data-action="nav-glossary"]` | Sidebar nav | `data-action="nav-glossary"` | 导航到 Token Glossary 页 | 无特殊状态 |
| `button.nav-item--footer[data-action="open-settings"]` | Sidebar footer | `data-action="open-settings"` | 打开 Settings 抽屉 | `title` 属性含中文说明 |
| `button.scope-switch__btn[data-scope="day"]` | Topbar scope-switch | `data-scope="day"` | 趋势图切换为 Day 粒度（最近 30 天） | 默认 `is-active` |
| `button.scope-switch__btn[data-scope="week"]` | Topbar scope-switch | `data-scope="week"` | 趋势图同步切换为 Week 粒度 | 互斥单选 |
| `button.scope-switch__btn[data-scope="month"]` | Topbar scope-switch | `data-scope="month"` | 趋势图同步切换为 Month 粒度 | 互斥单选 |
| `button.icon-button--info[data-info="projects"]` | Projects metric card | `data-info="projects"` | 打开 info popover | 与 label 同行 |
| `button.icon-button--info[data-info="sessions"]` | Sessions metric card | `data-info="sessions"` | 打开 info popover | 与 label 同行 |
| `button.icon-button--info[data-info="tokens"]` | Total Tokens metric card | `data-info="tokens"` | 打开 info popover | 与 label 同行 |
| `button.icon-button--info[data-info="failed-tools"]` | Failed Tools metric card | `data-info="failed-tools"` | 打开 info popover | 与 label 同行 |
| `button.icon-button--info[data-info="chart-sessions"]` | Session Trend chart | `data-info="chart-sessions"` | 打开图表口径说明 popover | 与 `<h2>` 同行 |
| `button.icon-button--info[data-info="chart-tokens"]` | Token Trend chart | `data-info="chart-tokens"` | 打开图表口径说明 popover | 与 `<h2>` 同行 |
| `button.icon-button--info[data-info="chart-prompts"]` | Prompt Activity chart | `data-info="chart-prompts"` | 打开图表口径说明 popover | 与 `<h2>` 同行 |
| `button.icon-button--ghost[data-action="chart-menu"]` x 3 | Chart cards 右上角 | `data-action="chart-menu"` | 打开 action menu（导出/详情/复制） | `.icon-button--ghost` 透明背景 |
| `button.icon-button[data-action="close-settings"]` | Settings drawer | `data-action="close-settings"` | 关闭 Settings 抽屉 | drawer 右上角 |

### 图标行为表（摘要）

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| `📊` | Sidebar nav | Dashboard 入口图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| `🗂️` | Sidebar nav | Sessions 入口图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| `📁` | Sidebar nav | Projects 入口图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| `🤖` | Sidebar nav | Agents 入口图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| `📘` | Sidebar nav | Token Glossary 入口图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| `⚙️` | Sidebar footer | Settings 入口图标 | decorative | 跟随 Settings 按钮点击 | `--icon-size-nav` (20px) |
| `📁/🧭/🪙/🚨` | 4 个 metric card | 各指标类别标识 | decorative | 无交互 | `--icon-size-metric` (24px) |
| `ℹ️` x 7 | metric card + chart card 标题行 | 指标/图表口径说明入口 | action | 点击打开 info popover | `--icon-size-inline` (16px) |
| `⋯` x 3 | 3 个 chart card 右上角 | 图表更多操作菜单 | action | 点击打开 action menu | `--icon-size-inline` + `.icon-button--ghost` (22px) |
| `✖️` | Settings drawer 头部 | 关闭抽屉 | action | 点击关闭 drawer | `--icon-size-inline` (16px) |
| `.legend-dot--*` x 3 | Chart card legend row | Agent 数据系列色标 | decorative | hover 无特殊行为 | 8-10px circle |

### 合规结论

| 合同要求 | dashboard.html 状态 |
|---|---|
| 每个按钮有 data-action 或 href | HIFI 规范已覆盖（20 项）；生产仅 4 个按钮使用 onclick（不合规） |
| 无 inline onclick | 不合规（生产使用 onclick） |
| 按钮行为表已记录 | 已补充（摘要）；完整表见 `behavior-dashboard.md` |
| 图标行为表已记录 | 已补充（摘要）；完整表见 `behavior-dashboard.md` |

---

## Sessions 页面按钮行为分析 (sessions.html)

> Scanned 2026-05-22 against behavior contract `docs/ui/contracts/behavior-sessions.md`.
> 详细行为表见 `behavior-sessions.md`；以下为摘要。

### 生产环境结论：部分覆盖

生产模板 `sessions.html` + `components/sessions_list_components.html` 包含筛选表单、排序按钮、分页和行点击交互。
HIFI 规范要求 34 个按钮/交互元素 + 16 个图标。

### 按钮行为表（HIFI + 生产 摘要）

| selector / label | location | data-action-or-href | expected render behavior | validation |
|---|---|---|---|---|
| `button[data-action="apply"]` (Apply) | Filter card | `type="submit"` -> POST/GET `/sessions` | 按筛选条件刷新表格，重置到第一页 | URL 含查询参数 |
| `button[data-action="clear"]` / `.js-clear-all` (Clear All) | Filter card | `href="/sessions"` 无参数 | 清空所有筛选条件，恢复默认列表 | URL 无查询参数 |
| `button.chip-x` (filter chip x) | Active filters 区域 | `href` 移除对应 filter | 移除单个筛选条件并刷新 | chip 消失，表格更新 |
| `button.sessions-sort-btn` (Sortable headers) | Table header | `name="sort" value="<key>"` | 切换排序字段和方向 | URL sort/dir 变化 |
| `.sessions-row` (整行点击) | Table body | `data-action="row"` -> JS 导航 | 打开 Session detail 页面 | 跳转到 `/sessions/{agent}/{id}` |
| `input.page-input` (页码输入) | Pagination | `data-action="page-input"` -> Enter 跳转 | 输入页码后跳转 | 合法页码 + Enter |
| `button[data-action="next-page"]` (Next) | Pagination 右侧 | `href` 指向下一页 | 跳到下一页；尾页不显示 | 非尾页可见 |
| `a[href]:contains("Previous")` | Pagination | `href` 指向上页 | 跳到上一页；首页不显示 | 非首页可见 |
| `select.sessions-footer-page-size__select` | Footer 左侧 | `onchange` -> `window.location.href` | 切换每页行数 | URL page_size 变化 |
| `button.nav-button[data-target="sessions"]` | Sidebar nav | `data-action="nav" data-target="sessions"` | 当前页标记 active | `.active` class 存在 |
| `button.nav-button[data-target="dashboard/projects/agents/glossary"]` | Sidebar nav | `data-action="nav" data-target="<page>"` | 跳转到对应页面 | 点击后导航 |
| `button.settings-button[data-action="settings"]` | Sidebar footer | `data-action="settings"` | 打开 Settings 抽屉 | 抽屉从右侧滑入 |
| `button.icon-button[data-action="help"]` | Topbar 右侧 | `data-action="help"` | 打开帮助说明 | 弹出帮助面板 |
| `button.icon-button[data-action="local-command"]` | Topbar 右侧 | `data-action="local-command"` | 打开本地命令说明 | 弹出命令面板 |
| `#session-search` (Session ID 搜索) | Filter card | `name="q"` | 输入 Session ID 搜索 | 点击 Apply 生效 |
| `#filter-agent/model/project` (筛选下拉) | Filter card | `name="agent/model/project"` | 选择后 Apply 过滤 | URL 含对应参数 |
| `a.sessions-title` (标题链接) | Table body | `href="/sessions/{agent}/{id}"` | 打开 Session detail | 直接跳转 |
| `a.link-muted[data-project]` (项目链接) | Table body | `href="/projects/{key}"` | 打开 Project 页面 | 直接跳转 |

### 图标行为表（摘要）

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| `🔎` | Filter card 搜索框内 | 搜索输入提示 | decorative | 输入框可交互 | `sessions-search__icon`: 12px |
| `📈` | 侧边栏顶部 | App logo | decorative | 可点击跳转到首页 | `brand-logo` |
| `📊/📋/📁/🤖/📖` | Sidebar nav 5 行 | 各页面入口图标 | decorative | 跟随导航按钮点击 | `nav-icon` |
| `⚙️` | Sidebar footer | Settings 入口 | decorative | 跟随 Settings 按钮 | `settings-button` 内 |
| `❔/💻` | Topbar 右侧 | 帮助/命令面板入口 | action | 点击弹出面板 | `icon-button` |
| `↕/↑/↓` | Table header 可排序列 | 排序方向图标 | action | 点击切换排序方向 | `sessions-sort-icon`: 18x18px |
| Token bar 彩色段 | Tokens 列内 | Token 组成可视化 | action (hover) | hover 显示 breakdown tooltip | `sessions-token-bar`: 46x7px |
| Agent badge CC/QD/CX | Table body Agent 列 | Agent 类型识别 | decorative | 颜色固定：purple/green/orange | `sessions-agent-badge` |

### 合规结论

| 合同要求 | sessions.html 状态 |
|---|---|
| 每个按钮有 data-action 或 href | HIFI 规范已覆盖（34 项）；生产部分使用 form submit/onclick |
| 无 inline onclick | 部分不合规（部分交互使用 inline handler） |
| 按钮行为表已记录 | 已补充（摘要）；完整表见 `behavior-sessions.md` |
| 图标行为表已记录 | 已补充（摘要）；完整表见 `behavior-sessions.md` |

---

## Session Detail 页面按钮行为分析 (session.html)

> Scanned 2026-05-22 against behavior contract `docs/ui/contracts/behavior-session-detail.md`.
> 详细行为表见 `behavior-session-detail.md`；以下为摘要。

### 生产环境结论：部分覆盖

生产模板仅实现 Trace tab；Metrics 和 Payloads tab 未实现。
HIFI 规范要求 29 个按钮（去重后）+ 30 个图标。生产 v12 timeline 基本合规。

### 按钮行为表（HIFI + 生产 摘要）

| selector / label | location | data-action-or-href | expected render behavior | validation |
|---|---|---|---|---|
| `[data-action="settings"]` (Settings) | Sidebar footer | `data-action="settings"` | 打开 Settings 面板 | Settings 面板可见 |
| `[data-action="help"]` (Help) | Topbar right | `data-action="help"` | 打开帮助浮层 | 浮层弹出 |
| `[data-action="shell"]` (CLI) | Topbar right | `data-action="shell"` | 展示 CLI 命令面板 | CLI 面板可见 |
| `[data-action="copy"]` (hero, Copy URL) | Hero title line | `data-action="copy"` | 复制 session URL 到剪贴板 | Toast 提示 "Copied" |
| `[data-action="jump-round"]` (Issue links) | Hero issue row | `data-action="jump-round"` + `href="#round-N"` | 滚动到并展开对应 failed round | 目标 round 在视口内 |
| `a.tab` (Trace/Metrics/Payloads) | Tab bar | href 切换子页面 | 切换到对应 tab | Tab 获得 `.active` 类 |
| `[data-action="filter-status"][data-status="all/failed"]` | Trace panel head | `data-action="filter-status"` | 切换显示全部/仅 failed round | round 可见性变化 |
| `[data-action="toggle-all"]` (Expand/Collapse all) | Trace panel head | `data-action="toggle-all"` | 展开/收起所有 round | 所有 round 状态翻转 |
| `[data-action="toggle-round"]` (Round chevron) | Each round row | `data-action="toggle-round"` | 展开/收起 round 详情 | `.sd-round-detail` 可见/隐藏 |
| `[data-action="open-payload"][data-payload-kind="context/response/result"]` | LLM call / Tool row | `data-action="open-payload"` | 打开 payload modal 展示对应内容 | Modal 可见，kind 正确 |
| `[data-action="close-payload"]` | Payload modal head | `data-action="close-payload"` | 关闭 payload modal | Modal 消失 |
| `[data-action="mode-rendered/raw"]` | Payloads panel head | `data-action="mode-rendered/raw"` | 切换 viewer 渲染/原始模式 | Viewer 模式变化 |
| `[data-action="info"]` (metric card info) | Metric card header | `data-action="info"` | 打开指标说明浮层 | Info popover 可见 |
| `[data-action="sort"]` (sortable header) | Metrics table headers | `data-action="sort"` | 切换排序方向 | 行顺序变化 |
| Modal backdrop click | Modal backdrop | 点击背景 | 关闭 modal（ESC 同效） | Modal 消失 |

### 图标行为表（摘要）

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| `⌁` (brand) | Sidebar brand | 品牌标识 | decorative | 无交互 | `--hifi-icon-nav` (18px) |
| `📊/💬/📁/🤖/📘` | Sidebar nav | 各页面入口 | action | 点击导航 | `--hifi-icon-nav` (18px) |
| `⚙️/›` | Sidebar footer | Settings 入口/指示器 | action/decorative | 跟随 Settings 按钮 | `--hifi-icon-nav` / `--hifi-icon-inline` |
| `❔/⌘` | Topbar | 帮助/CLI 入口 | action | 点击弹出面板 | `--hifi-icon-nav` (18px) |
| `⌃/⌄` | Round row chevron | 展开/收起指示器 | action | 点击翻转图标 | `--hifi-icon-inline` (16px) |
| `✍️/🧠/🧰/📦` | Timeline steps | 各步骤类型标识 | decorative | 标识 step 类型 | `--hifi-icon-inline` (16px) |
| `🧮/✍️/💾/📤` | Metric card icons | 各指标标识 | decorative | 无交互 | `--hifi-icon-metric` (22px) |
| `ℹ️` | Metric card info button | 指标说明入口 | action | 点击打开说明浮层 | `--hifi-icon-inline` (16px) |
| CSS dots (.sd-timeline-dot--*) | Timeline nodes | 各节点类型标识 | decorative | 无独立点击 | 12px (CSS) |

### 合规结论

| 合同要求 | session.html 状态 |
|---|---|
| 每个按钮有 data-action 或 href | HIFI 规范已覆盖（29 项）；v12 timeline 基本合规 |
| 无 inline onclick | 合规（v12 timeline 无 inline onclick） |
| 按钮行为表已记录 | 已补充（摘要）；完整表见 `behavior-session-detail.md` |
| 图标行为表已记录 | 已补充（摘要）；完整表见 `behavior-session-detail.md` |

---

## Projects 页面按钮行为分析 (projects.html + project.html)

> Scanned 2026-05-22 against behavior contract `docs/ui/contracts/behavior-projects.md`.
> 详细行为表见 `behavior-projects.md`；以下为摘要。

### Projects List 生产环境结论：部分覆盖

生产模板 `projects.html` 只有 1 个按钮，使用 `onclick` 实现排序和重置。
HIFI 规范要求 16 个按钮（Projects List）+ 21 个图标。

### Project Detail 生产环境结论：部分覆盖

生产模板 `project.html` 只有 1 个按钮（copy-path）。
HIFI 规范要求 22 个按钮（Project Detail）+ 27 个图标。

### 按钮行为表摘要（Projects List + Project Detail）

| selector / label | location | data-action-or-href | expected render behavior | validation |
|---|---|---|---|---|
| `a.settings[data-action="open-settings"]` | Sidebar bottom | `data-action="open-settings"` | 打开 Settings 抽屉 | 抽屉滑入 |
| `button.icon-button[data-action="open-help"]` | Topbar right | `data-action="open-help"` | 打开帮助说明 | 帮助面板弹出 |
| `button.icon-button[data-action="open-shell"]` | Topbar right | `data-action="open-shell"` | 打开本地命令说明 | 命令面板弹出 |
| `input.search[data-search="project-name"]` | Filter card | `data-search="project-name"` | 按项目名实时搜索 | 表格行实时过滤 |
| `button[data-action="clear-search"]` (Clear) | Filter card | `data-action="clear-search"` | 清空搜索 | 恢复完整列表 |
| `button[data-action="apply-search"]` (Apply) | Filter card | `data-action="apply-search"` | 应用搜索 | 仅匹配行可见 |
| `button.sortable-header[data-action="sort"]` x 4 | Table header | `data-action="sort" data-sort="*"` | 按列排序（降->升->默认） | 行顺序变化 |
| `tr[data-action="open-project"]` (行点击) | Table body | `data-action="open-project"` | 打开 Project detail 页面 | 跳转到 `/projects/...` |
| `input.page-input[data-action="page-input"]` | Pagination | `data-action="page-input"` -> Enter | 输入页码跳转 | URL page 参数变化 |
| `button[data-action="next-page"]` (next) | Pagination | `data-action="next-page"` | 跳到下一页 | 非尾页可见 |
| `button.path-copy-btn` (Copy path) | Table body path cell | `onclick="copyProjectPath()"` | 复制项目路径并 toast | 生产使用 onclick |
| `a.back-btn` (Back) | Project detail header | `href="/projects"` | 返回 Projects list | 点击导航 |
| `button.btn[data-action="copy-path"]` | Project detail header | `data-action="copy-path"` | 复制项目路径 | Toast 提示 |
| `button.info-icon[data-action="info"]` x 4 | Metric cards | `data-action="info"` | 展示指标说明 popover | popover 可见 |
| `input[data-action="search"]` (session search) | Project detail toolbar | `data-action="search"` | 按标题/ID 搜索 sessions | 表格实时过滤 |
| `tr[data-action="open-session"]` (行点击) | Project detail table | `data-action="open-session"` | 打开 Session detail | 跳转到 `/sessions/...` |
| `button.btn[data-action="copy-session"]` | Session row | `data-action="copy-session"` | 复制 Session ID | Toast 提示 |
| `button[data-action="view-all"]` (Empty state) | Empty state strip | `data-action="view-all"` | 查看所有 Sessions | 跳转到 Sessions 页 |

### 图标行为表摘要

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| `📊/🗓️/📁/🤖/📖` | Sidebar nav | 各页面入口图标 | action | 跟随导航链接 | `emoji` -- nav icon (18-20px) |
| `⚙️/›` | Sidebar footer | Settings 入口/指示器 | action/decorative | 跟随 Settings 按钮 | `icon--nav` (18-20px) |
| `ℹ️` x 4 | Metric cards | 指标说明 | action | 点击展示 popover | `icon-button--info` -- inline (13-14px) |
| `📁/🗜️/🪙/⚠️` | Metric cards | 各指标类别 | decorative | 无交互 | `emoji lg` -- metric icon (20-24px) |
| `↕` | Sortable column header | 可排序列标识 | action | 跟随表头点击 | `sort-caret` -- inline (14-16px) |
| `🔴/🟣/🟢` (.dot) | Agent badges | Agent provider 标识 | decorative | 颜色标识 | `dot` -- inline (8-10px) |
| Token bar segments | Tokens column | Token 组成分段 | decorative + action (hover) | hover 展示 breakdown tooltip | `tokenbar` -- bar height ~8px |

### 合规结论

| 合同要求 | projects.html + project.html 状态 |
|---|---|
| 每个按钮有 data-action 或 href | HIFI 规范已覆盖（38 项合计）；生产部分使用 onclick |
| 无 inline onclick | 不合规（生产 `sortProjects()`、`copyProjectPath()`、`resetProjectFilters()` 使用 onclick） |
| 按钮行为表已记录 | 已补充（摘要）；完整表见 `behavior-projects.md` |
| 图标行为表已记录 | 已补充（摘要）；完整表见 `behavior-projects.md` |

---

## Agents 页面按钮行为分析 (agents.html)

> Scanned 2026-05-22 against behavior contract `docs/ui/contracts/behavior-agents.md`.
> 详细行为表见 `behavior-agents.md`；以下为摘要。

### Agents List 生产环境结论：部分覆盖

生产模板 `agents.html` 无 metric grid、无排序按钮、无分页。
HIFI 规范要求 20 个按钮（Agents List）+ 21 个图标。

### 按钮行为表摘要（Agents List）

| selector / label | location | data-action-or-href | expected render behavior | validation |
|---|---|---|---|---|
| `a.nav-link[data-target="agents/dashboard/sessions/projects/glossary"]` | Sidebar nav | `href="/<page>"` | 跳转到对应页面 | 点击导航 |
| `a[data-action="settings"]` | Sidebar footer | `data-action="settings"` | 打开 Settings 抽屉 | 抽屉滑入 |
| `button[data-action="help"]` | Topbar right | `data-action="help"` | 打开帮助面板 | 面板弹出 |
| `button[data-action="shell"]` | Topbar right | `data-action="shell"` | 打开命令面板 | 面板弹出 |
| `th.sort[data-action="sort"][data-sort="sessions/projects/tokens/tools/failed/last_active"]` | All Agents 表头 | `data-action="sort" data-sort="<key>"` | 按列排序（desc->asc） | 行顺序变化，`active-sort` class |
| `tr[data-action="open-agent"]` (整行点击) | All Agents 表体 | `data-action="open-agent"` | 打开 Agent detail 页面 | 导航到 `/agents/{name}` |
| `div.tokenbar` hover | Tokens 列内 | `aria-hidden="true"`，hover tooltip | 悬浮显示 token breakdown | tooltip 含组成百分比 |
| `input.page-input[data-action="page-input"]` | Pagination | `data-action="page-input"` -> Enter | 输入页码跳转 | URL page 参数变化 |
| `button[data-action="next-page/prev-page"]` | Pagination 两侧 | `data-action="next/prev-page"` | 跳到上/下一页 | 首页/尾页条件隐藏 |
| `div.progress` hover | Tool Calls 列内 | decorative，hover 显示占比 | 展示 agent 在总 tool calls 中的占比 | hover 显示占比信息 |

### Agent Detail 按钮行为摘要

Agent Detail 页面的完整按钮/图标行为表已在本文件上方的 "Agent Detail 页面按钮行为表 (agent.html)" 章节记录。

### 图标行为表摘要（Agents List）

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| `⌁` (brand logo) | 侧边栏顶部 | 应用图标 | decorative | 仅标识，不可点击 | `brand-logo` |
| `📊/🧾/📁/🤖/📚` | Sidebar nav | 各页面入口图标 | action (nav) | 点击跳转到对应页面 | `nav-emoji` / `emoji` |
| `⚙️/›` | Sidebar footer | Settings 入口/指示器 | action/decorative | 跟随 Settings 按钮 | `settings-link` 内 |
| `❔/⌘` | Topbar 右侧 | 帮助/命令面板入口 | action | 点击弹出面板 | `icon-btn` |
| `🤖/🧾/📁/🪙` | Metric card icons | 各指标类别 | decorative | 无交互 | `metric-icon` (4 色背景) |
| `ℹ️` | 每个 metric card | 指标说明 | action | 点击展示计算口径浮层 | `info` / `info-icon` |
| `↕` (sort mark) | 可排序表头右侧 | 排序方向 | action | 点击切换排序方向 | `sort-mark` |
| CC/QD/CX (agent avatar) | Agent 行首 | Agent 缩写头像 | decorative | 颜色固定 | `agent-avatar cc/cx/qd` |
| TokenBar 彩色段 | Tokens 列内 | Token 组成可视化 | action (hover) | hover 显示 breakdown tooltip | `tokenbar` |

### 合规结论

| 合同要求 | agents.html 状态 |
|---|---|
| 每个按钮有 data-action 或 href | HIFI 规范已覆盖（41 项合计）；生产缺少排序/分页/metric grid |
| 无 inline onclick | 合规（生产模板无 inline onclick） |
| 按钮行为表已记录 | 已补充（摘要）；完整表见 `behavior-agents.md` |
| 图标行为表已记录 | 已补充（摘要）；完整表见 `behavior-agents.md` |

