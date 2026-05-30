# Session Detail 页面 — 按钮与图标行为表

> 覆盖 HIFI session-detail-trace / session-detail-metrics / session-detail-payloads 三张页面。
> 共享壳（sidebar + topbar + hero + tabs）合并为一份，各 tab 独有部分分开列出。

---

## 一、Button Behavior Table

### 1. 共享壳按钮（Sidebar / Topbar / Hero / Tabs）

| # | Selector | Label | Location | data-action / href | Expected Behavior | Validation |
|---|---|---|---|---|---|---|
| 1 | `.settings-link` / `[data-action="settings"]` | Settings | Sidebar footer | `data-action="settings"` | 打开 Settings 面板，展示本地数据路径、主题、快捷键与扫描配置。 | Settings 面板可见且内容正确。 |
| 2 | `[data-action="help"]` | Help | Topbar right | `data-action="help"` | 打开帮助浮层或文档。 | 帮助浮层弹出。 |
| 3 | `[data-action="shell"]` | CLI | Topbar right | `data-action="shell"` | 展示 CLI 命令面板或复制 CLI 路径。 | CLI 面板可见。 |
| 4 | `[data-action="copy"]` (hero) | Copy URL | Hero title line, right of URL | `data-action="copy"` | 将完整 session URL 复制到剪贴板。 | Toast 提示 "Copied"。 |
| 5 | `[data-action="jump-round"]` | R8 · 1 failed / R24 · 1 failed / ... | Hero issue row | `data-action="jump-round"` / `href="#round-N"` | 点击后滚动到对应 failed round 并展开。 | 目标 round 在视口内且处于展开状态。 |
| 6 | `a.tab[href="session-detail-trace.html"]` | Trace | Tab bar | href 切换子页面 | 切换到 Trace tab，trace panel 可见。 | Tab 获得 `.active` 类。 |
| 7 | `a.tab[href="session-detail-metrics.html"]` | Metrics | Tab bar | href 切换子页面 | 切换到 Metrics tab，metrics grid + charts 可见。 | Tab 获得 `.active` 类。 |
| 8 | `a.tab[href="session-detail-payloads.html"]` | Payloads | Tab bar | href 切换子页面 | 切换到 Payloads tab，payload workbench 可见。 | Tab 获得 `.active` 类。 |

### 2. Trace Tab 独有按钮

| # | Selector | Label | Location | data-action / href | Expected Behavior | Validation |
|---|---|---|---|---|---|---|
| 9 | `[data-action="filter-status"][data-status="all"]` | All | Trace panel head, seg group | `data-action="filter-status"` | 显示全部 round。 | 所有 round 可见。 |
| 10 | `[data-action="filter-status"][data-status="failed"]` | Failed | Trace panel head, seg group | `data-action="filter-status"` | 仅显示 failed round。 | 仅 failed round 可见。 |
| 11 | `[data-action="toggle-all"][data-state="collapse"]` | Collapse all | Trace panel head | `data-action="toggle-all"` | 收起所有已展开 round。 | 所有 round 处于收起状态。 |
| 12 | `[data-action="toggle-all"][data-state="expand"]` | Expand all | Trace panel head (toggle state) | `data-action="toggle-all"` | 展开所有 round。 | 所有 round 处于展开状态。 |
| 13 | `[data-action="toggle-round"]` (round row chevron) | ⌄ / ⌃ | Each round row, rightmost cell | `data-action="toggle-round"` | 展开/收起对应 round 的详情时间线。 | round 展开后 `.sd-round-detail` 可见且包含 timeline items。 |
| 14 | `[data-action="open-payload"][data-payload-kind="context"]` (user msg) | Open | User message card, action area | `data-action="open-payload"` | 打开 payload modal，展示 user message context。 | Modal 可见，kind = context。 |
| 15 | `[data-action="open-payload"][data-payload-kind="context"]` (LLM call) | Context | LLM call card, action group | `data-action="open-payload"` | 打开 payload modal，展示 request context。 | Modal 可见，kind = context，content 渲染正确。 |
| 16 | `[data-action="open-payload"][data-payload-kind="response"]` | Response | LLM call card, action group | `data-action="open-payload"` | 打开 payload modal，展示 response blocks 和 tool_use。 | Modal 可见，kind = response。 |
| 17 | `[data-action="open-payload"][data-payload-kind="result"]` | Result | Tool row, right side | `data-action="open-payload"` | 打开 payload modal，展示单个 tool result。 | Modal 可见，kind = tool_result。 |
| 18 | `[data-action="toggle-sub-round"]` | SR# chevron | Subagent round summary | `data-action="toggle-sub-round"` | 展开/收起 subagent round 的 LLM call 和 tool steps。 | Sub-round steps 可见/隐藏。 |
| 19 | `[data-action="close-payload"]` | Close | Payload modal head | `data-action="close-payload"` | 关闭 payload modal。 | Modal 消失，焦点返回触发按钮。 |

### 3. Metrics Tab 独有按钮

| # | Selector | Label | Location | data-action / href | Expected Behavior | Validation |
|---|---|---|---|---|---|---|
| 20 | `[data-action="info"]` (metric card) | ℹ️ | Each metric card header (Total Tokens, Fresh Input, Cache Read, Output) | `data-action="info"` | 打开指标说明浮层，解释该指标含义和计算方式。 | Info popover 可见。 |
| 21 | `[data-action="sort"]` (sortable header) | ↕ (column header) | Metrics table headers (Tokens, Tools, etc.) | `data-action="sort"` | 按该列升序/降序/默认排序切换。 | 行顺序变化，sort-mark 指示方向。 |
| 22 | `button[data-action="filter"]` (if present) | Filter | Metrics panel head | `data-action="filter"` | 打开 metric 类型筛选面板。 | Filter panel 可见。 |
| 23 | `button[data-action="export"]` (if present) | Export | Metrics panel head | `data-action="export"` | 导出当前 metrics 表为 CSV/JSON。 | 文件下载触发。 |

### 4. Payloads Tab 独有按钮

| # | Selector | Label | Location | data-action / href | Expected Behavior | Validation |
|---|---|---|---|---|---|---|
| 24 | `[data-action="mode-rendered"]` | Rendered | Payloads panel head | `data-action="mode-rendered"` | 右侧 viewer 显示结构化渲染内容。 | Viewer 渲染模式，按钮 active。 |
| 25 | `[data-action="mode-raw"]` | Raw | Payloads panel head | `data-action="mode-raw"` | 右侧 viewer 显示原始 JSON/文本。 | Viewer 原始模式，按钮 active。 |
| 26 | `[data-action="copy"]` (payloads) | Copy | Payloads panel head | `data-action="copy"` | 复制当前 payload 内容到剪贴板。 | Toast 提示 "Copied"。 |
| 27 | `[data-action="inline-payload"]` | Payload list item (e.g. "R1 · LLM Call #1") | Payloads panel, left list | `data-action="inline-payload"` | 切换右侧 viewer 为选中 payload。 | Viewer 内容更新，列表项获得 `.active`。 |

### 5. Payload Modal 通用按钮

| # | Selector | Label | Location | data-action / href | Expected Behavior | Validation |
|---|---|---|---|---|---|---|
| 28 | `[data-action="close-modal"]` / `[data-action="close-payload"]` | Close | Modal head, right | `data-action="close-modal"` | 关闭 payload modal。 | Modal 消失。 |
| 29 | Modal backdrop click | — | Modal backdrop (outside panel) | 点击背景 | 关闭 payload modal（ESC 键同效）。 | Modal 消失。 |

### 6. 生产模板按钮（session_detail_timeline_v12.html）

| # | Selector | Label | Location | data-action / href | Expected Behavior | Validation |
|---|---|---|---|---|---|---|
| 30 | `[data-action="filter-status"][data-status="all"]` | All | Trace head, seg group | `data-action="filter-status"` | 显示全部 round。 | 所有 round 可见。 |
| 31 | `[data-action="filter-status"][data-status="failed"]` | Failed | Trace head, seg group | `data-action="filter-status"` | 仅显示 failed round。 | 仅 failed round 可见。 |
| 32 | `[data-action="toggle-all"]` | Collapse all / Expand all | Trace head | `data-action="toggle-all"` | 切换所有 round 展开/收起状态。 | 所有 round 状态翻转。 |
| 33 | `[data-action="toggle-round"]` | Round chevron | Each round summary button | `data-action="toggle-round"` | 展开/收起 round 详情。 | Round detail visible/hidden。 |
| 34 | `[data-action="open-payload"]` (Context) | Context | LLM call card action group | `data-action="open-payload"` + `data-payload-kind="context"` | 打开 payload modal 展示 context。 | Modal 可见，payload-body 渲染 context。 |
| 35 | `[data-action="open-payload"]` (Response) | Response | LLM call card action group | `data-action="open-payload"` + `data-payload-kind="response"` | 打开 payload modal 展示 response。 | Modal 可见，payload-body 渲染 response。 |
| 36 | `[data-action="open-payload"]` (Result) | Result | Tool row | `data-action="open-payload"` | 打开 payload modal 展示 tool result。 | Modal 可见，payload-body 渲染 result。 |
| 37 | `[data-action="close-payload"]` | Close | Payload modal head | `data-action="close-payload"` | 关闭 payload modal。 | Modal 消失。 |
| 38 | `[data-action="jump-round"]` | Issue links (R8 · 1 failed, ...) | Hero issue strip | `data-action="jump-round"` + `href="#round-N"` | 滚动到并高亮对应 failed round。 | Target round in viewport。 |

---

## 二、Icon Behavior Table

### 1. 全局图标（Sidebar / Topbar / Hero）

| # | Icon | Location | Semantic Meaning | Decorative or Action | Expected Behavior | Size Class |
|---|---|---|---|---|---|---|
| 1 | `⌁` (brand mark) | Sidebar brand | 品牌标识 | Decorative | 无交互，仅视觉。 | `--hifi-icon-nav` (18px) |
| 2 | `📊` | Sidebar nav — Dashboard | Dashboard 入口 | Action | 点击导航到 Dashboard。 | `--hifi-icon-nav` (18px) |
| 3 | `💬` | Sidebar nav — Sessions | 会话列表入口 | Action | 点击导航到 Sessions。 | `--hifi-icon-nav` (18px) |
| 4 | `📁` | Sidebar nav — Projects | 项目列表入口 | Action | 点击导航到 Projects。 | `--hifi-icon-nav` (18px) |
| 5 | `🤖` | Sidebar nav — Agents | Agents 列表入口 | Action | 点击导航到 Agents。 | `--hifi-icon-nav` (18px) |
| 6 | `📘` | Sidebar nav — Token Glossary | Token 术语表入口 | Action | 点击导航到 Token Glossary。 | `--hifi-icon-nav` (18px) |
| 7 | `⚙️` | Sidebar footer — Settings | 设置入口 | Action | 打开 Settings 面板。 | `--hifi-icon-nav` (18px) |
| 8 | `›` | Sidebar footer — Settings | 设置入口辅助箭头 | Decorative | 跟随 settings-link 点击。 | `--hifi-icon-inline` (16px) |
| 9 | `❔` | Topbar — Help | 帮助入口 | Action | 打开帮助浮层。 | `--hifi-icon-nav` (18px) |
| 10 | `⌘` | Topbar — CLI | 命令行入口 | Action | 打开 CLI 面板。 | `--hifi-icon-nav` (18px) |
| 11 | `📋` | Hero — Copy URL | 复制 URL | Action | 点击后复制 session URL 到剪贴板。 | `--hifi-icon-nav` (18px) |
| 12 | `⚠️` | Hero issue strip — Issues | 问题警告标识 | Decorative | 跟随 issue row，不可单独点击。 | `--hifi-icon-inline` (16px) |

### 2. Trace Tab 图标

| # | Icon | Location | Semantic Meaning | Decorative or Action | Expected Behavior | Size Class |
|---|---|---|---|---|---|---|
| 13 | `🧭` | Tab — Trace | Trace 子页面标识 | Action (tab) | 点击切换到 Trace 页面。 | `--hifi-icon-nav` (18px) |
| 14 | `✅` | Summary strip — Status | 成功状态标识 | Decorative | 跟随 status 文本展示。 | `--hifi-icon-inline` (16px) |
| 15 | `✍️` | Summary strip — Manual input | 手动输入标识 | Decorative | 跟随 manual input 计数。 | `--hifi-icon-inline` (16px) |
| 16 | `🧰` | Summary strip — Subagents | Subagent 标识 | Decorative | 跟随 subagent 计数。 | `--hifi-icon-inline` (16px) |
| 17 | `💾` | Summary strip — Cache write | 缓存写入标识 | Decorative | 跟随 cache write 百分比。 | `--hifi-icon-inline` (16px) |
| 18 | `⌃` / `⌄` | Round row chevron | 展开/收起指示器 | Action | 点击展开/收起 round，图标翻转。 | `--hifi-icon-inline` (16px) |
| 19 | `✍️` | Timeline — User message step | 用户消息步骤 | Decorative | 标识 user message step 类型。 | `--hifi-icon-inline` (16px) |
| 20 | `🧠` | Timeline — LLM call step | LLM 调用步骤 | Decorative | 标识 LLM call step 类型。 | `--hifi-icon-inline` (16px) |
| 21 | `🧭` | LLM call step — Context button | Context payload 入口 | Action (button) | 跟随 Context 按钮，打开 payload modal。 | `--hifi-icon-inline` (16px) |
| 22 | `📝` | LLM call step — Response button | Response payload 入口 | Action (button) | 跟随 Response 按钮，打开 payload modal。 | `--hifi-icon-inline` (16px) |
| 23 | `🧰` | Timeline — Tool batch step | 工具批量调用步骤 | Decorative | 标识 tool batch step 类型。 | `--hifi-icon-inline` (16px) |
| 24 | `📦` | Tool row — Result button | Result payload 入口 | Action (button) | 跟随 Result 按钮，打开 payload modal。 | `--hifi-icon-inline` (16px) |
| 25 | `▶` | Subagent round chevron | Sub-round 展开指示器 | Action | 点击展开/收起 sub-round 步骤。 | `--hifi-icon-inline` (16px) |

### 3. Metrics Tab 图标

| # | Icon | Location | Semantic Meaning | Decorative or Action | Expected Behavior | Size Class |
|---|---|---|---|---|---|---|
| 26 | `📊` | Tab — Metrics | Metrics 子页面标识 | Action (tab) | 点击切换到 Metrics 页面。 | `--hifi-icon-nav` (18px) |
| 27 | `🧮` | Metric card — Total Tokens | 总 tokens 标识 | Decorative | 跟随 metric card 标题。 | `--hifi-icon-metric` (22px) |
| 28 | `✍️` | Metric card — Fresh Input | 新鲜输入标识 | Decorative | 跟随 metric card 标题。 | `--hifi-icon-metric` (22px) |
| 29 | `💾` | Metric card — Cache Read | 缓存读取标识 | Decorative | 跟随 metric card 标题。 | `--hifi-icon-metric` (22px) |
| 30 | `📤` | Metric card — Output | 输出标识 | Decorative | 跟随 metric card 标题。 | `--hifi-icon-metric` (22px) |
| 31 | `ℹ️` | Metric card — Info button | 指标说明入口 | Action | 点击打开指标说明浮层。 | `--hifi-icon-inline` (16px) |
| 32 | `↕` | Sortable column header | 可排序标识 | Decorative (follows header click) | 跟随表头点击切换排序方向。 | `--hifi-icon-inline` (16px) |

### 4. Payloads Tab 图标

| # | Icon | Location | Semantic Meaning | Decorative or Action | Expected Behavior | Size Class |
|---|---|---|---|---|---|---|
| 33 | `📦` | Tab — Payloads | Payloads 子页面标识 | Action (tab) | 点击切换到 Payloads 页面。 | `--hifi-icon-nav` (18px) |
| 34 | `👁️` | Rendered mode button | 渲染模式入口 | Action | 切换到 Rendered 模式。 | `--hifi-icon-inline` (16px) |
| 35 | `🧾` | Raw mode button | 原始模式入口 | Action | 切换到 Raw 模式。 | `--hifi-icon-inline` (16px) |
| 36 | `📋` | Copy payload button | 复制 payload | Action | 复制当前 payload 内容。 | `--hifi-icon-inline` (16px) |

### 5. Payload Modal 图标

| # | Icon | Location | Semantic Meaning | Decorative or Action | Expected Behavior | Size Class |
|---|---|---|---|---|---|---|
| 37 | `✖️` | Modal close button | 关闭 modal | Action | 关闭 payload modal。 | `--hifi-icon-inline` (16px) |

### 6. 生产模板图标（session_detail_timeline_v12.html + primitives_v12.html）

| # | Icon | Location | Semantic Meaning | Decorative or Action | Expected Behavior | Size Class |
|---|---|---|---|---|---|---|
| 38 | `.sd-timeline-dot--user` (CSS dot) | Timeline — user message | 用户消息节点 | Decorative | 时间线节点标识，无独立点击。 | 12px (CSS) |
| 39 | `.sd-timeline-dot--llm` (CSS dot) | Timeline — LLM call | LLM 调用节点 | Decorative | 时间线节点标识。 | 12px (CSS) |
| 40 | `.sd-timeline-dot--tool` (CSS dot) | Timeline — tool batch | 工具调用节点 | Decorative | 时间线节点标识。 | 12px (CSS) |
| 41 | `.sd-timeline-dot--sub` (CSS dot) | Timeline — subagent | Subagent 节点 | Decorative | 时间线节点标识。 | 12px (CSS) |

---

## 三、统计

### HIFI Session Detail 按钮总数

| 区域 | 数量 |
|---|---|
| 共享壳（Sidebar/Topbar/Hero/Tabs） | 8 |
| Trace Tab 独有 | 11 |
| Metrics Tab 独有 | 4 |
| Payloads Tab 独有 | 4 |
| Payload Modal 通用 | 2 |
| **总计（去重后）** | **29** |

### HIFI Session Detail 图标总数

| 类别 | 数量 |
|---|---|
| 全局（Sidebar/Topbar/Hero） | 12 |
| Trace Tab | 13 |
| Metrics Tab | 7 |
| Payloads Tab | 4 |
| Payload Modal | 1 |
| **总计（去重后，跨 tab 复用计一次）** | **~30** |

### 图标尺寸分层

| Size Tier | CSS Variable | Value | 适用图标 |
|---|---|---|---|
| Nav icon | `--hifi-icon-nav` | 18px | Sidebar nav, tab, settings, topbar, brand |
| Inline action | `--hifi-icon-inline` | 16px | Buttons, chevrons, badges, status, tool rows |
| Metric icon | `--hifi-icon-metric` | 22px | Metric card headers |

---

## 四、生产 vs HIFI 差距备注

| 项目 | HIFI 状态 | 生产状态 | 差距 |
|---|---|---|---|
| data-action 覆盖 | 全部按钮有 data-action | 大部分按钮有 data-action（timeline 合规） | 部分遗留模板缺失 |
| Tab 导航 | 3 tab（Trace/Metrics/Payloads） | 仅 Trace tab 实现 | Metrics/Payloads tab 未实现 |
| Hero 结构 | agent-pill + URL + copy + chips + issue-row + KPIs + summary-strip | agent-pill + title + chips + KPIs + issue-strip | 基本对齐，URL copy 缺失 |
| Round 展开 | 单按钮 toggle-round + chevron 翻转 | 单按钮 toggle-round + chevron 翻转 | 已对齐 |
| Payload 按钮 | Context/Response/Result 均有 data-payload-kind | Context/Response 有 kind, Result 无 kind | 需统一 Result kind |
| 图标尺寸分层 | CSS 变量 3 层 | 无显式分层，依赖全局 `.ui-icon` | 需补充 CSS |
| Metrics tab | 完整 metric grid + sortable tables | 未实现 | 待实现 |
| Payloads tab | 完整 payload workbench | 未实现 | 待实现 |
| Subagent 展开 | toggle-sub-round + 内嵌 LLM/tool steps | 已实现 subagent 展开 | 基本对齐 |
