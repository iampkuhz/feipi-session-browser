# Agents Page Behavior Contract

> 来源: HIFI `pages/agents.html` + `pages/agent-detail.html` + `docs/agents.md` + `docs/agent-detail.md` + 生产模板 `src/session_browser/web/templates/agents.html` + `src/session_browser/web/templates/agent.html`
> 生成时间: 2026-05-21 (Task T020)

## 按钮行为表 (Button Behavior Table)

### Agents List (`/agents`)

| 选择器 | 标签 | 位置 | data-action / href | 预期行为 | 验证点 |
|---|---|---|---|---|---|
| `a.nav-link[data-target="agents"]` / sidebar `a:contains("Agents")` | Agents | 侧边栏导航 | `href="/agents"` (active 状态) | 当前页面标记 active；点击刷新/回到 Agents 列表 | `.active` class 存在于当前行；点击不刷新（已为当前页） |
| `a.nav-link[data-target="dashboard"]` / sidebar `a:contains("Dashboard")` | Dashboard | 侧边栏导航 | `href="/dashboard"` | 跳转到 Dashboard 总览页 | 点击后导航到 `/dashboard` |
| `a.nav-link[data-target="sessions"]` / sidebar `a:contains("Sessions")` | Sessions | 侧边栏导航 | `href="/sessions"` | 跳转到 Sessions 列表页 | 点击后导航到 `/sessions` |
| `a.nav-link[data-target="projects"]` / sidebar `a:contains("Projects")` | Projects | 侧边栏导航 | `href="/projects"` | 跳转到 Projects 列表页 | 点击后导航到 `/projects` |
| `a.nav-link[data-target="glossary"]` / sidebar `a:contains("Token Glossary")` | Token Glossary | 侧边栏导航 | `href="/glossary"` | 跳转到 Token Glossary 页面 | 点击后导航到 `/glossary` |
| `a[data-action="settings"]` / sidebar `.settings-link` | Settings | 侧边栏底部 | `data-action="settings"` | 打开 Settings 抽屉：配置本地数据路径、主题、扫描策略 | 点击后 Settings 抽屉从右侧滑入 |
| `button[data-action="help"]` / `.icon-btn` | 帮助 (emoji: ❔) | Topbar 右侧 | `data-action="help"` | 打开帮助面板：展示 Agents 页面字段说明、排序和快捷键 | 点击后弹出帮助面板 |
| `button[data-action="shell"]` / `.icon-btn` | 终端 (emoji: ⌘/⌨️) | Topbar 右侧 | `data-action="shell"` | 打开本地命令面板：展示重新扫描 session 数据的方法 | 点击后弹出命令面板 |
| `th.sort[data-action="sort"][data-sort="sessions"]` | Sessions ↕ | All Agents 表头 | `data-action="sort" data-sort="sessions"` | 按 session 数排序（首次 desc，再次 asc），刷新表格 | 点击后行顺序改变；`active-sort` class 切换 |
| `th.sort[data-action="sort"][data-sort="projects"]` | Projects ↕ | All Agents 表头 | `data-action="sort" data-sort="projects"` | 按 project 数排序 | 点击后行顺序改变 |
| `th.sort[data-action="sort"][data-sort="tokens"]` | Tokens ↕ | All Agents 表头 | `data-action="sort" data-sort="tokens"` | 按 token 总量排序 | 点击后行顺序改变 |
| `th.sort[data-action="sort"][data-sort="tools"]` | Tool Calls ↕ | All Agents 表头 | `data-action="sort" data-sort="tools"` | 按 tool call 数排序 | 点击后行顺序改变 |
| `th.sort[data-action="sort"][data-sort="failed"]` | Failed ↕ | All Agents 表头 | `data-action="sort" data-sort="failed"` | 按失败数量排序 | 点击后行顺序改变 |
| `th.sort[data-action="sort"][data-sort="last_active"]` | Last Active ↕ | All Agents 表头 | `data-action="sort" data-sort="last_active"` | 按最近活跃时间排序 | 点击后行顺序改变 |
| `tr[data-action="open-agent"]` (整行点击) | Agent 行内容 | All Agents 表体每行 | `data-action="open-agent"` → `href` 或 JS 导航 | 打开对应 Agent detail 页面 | 点击行后导航到 `/agents/{agent_name}` |
| `div.tokenbar` hover (agent 行) | Token breakdown | Tokens 列内 | `aria-hidden="true"`，hover 显示 tooltip | 悬浮显示 Fresh/Cache Read/Cache Write/Output/Total 结构化 tooltip | hover 时出现 tooltip，包含 token 组成百分比 + 总计 |
| `div.progress` hover (agent 行) | Tool call占比条 | Tool Calls 列内 | 装饰性，hover 可显示 agent 在全部 tool calls 中的占比 | 展示该 agent 在总 tool calls 中的占比条 | hover 时显示占比信息 |
| `input.page-input[data-action="page-input"]` | — (页码输入) | Pagination 区域 | `data-action="page-input"` → Enter 触发跳转 | 输入页码后按 Enter 跳转到指定页 | 输入合法页码 + Enter 后 URL page 参数变化 |
| `button[data-action="next-page"]` | next › | Pagination 区域右侧 | `data-action="next-page"` → `href` 指向下一页 | 跳到下一页；尾页时不显示 | 非尾页时可见可点击；尾页时隐藏 |
| `a[data-action="prev-page"]` / `button[data-action="prev-page"]` | prev ‹ | Pagination 区域左侧 | `data-action="prev-page"` → `href` 指向上页 | 跳到上一页；首页时不显示 | 非首页时可见可点击；首页时隐藏 |

### Agent Detail (`/agents/{agent}`)

| 选择器 | 标签 | 位置 | data-action / href | 预期行为 | 验证点 |
|---|---|---|---|---|---|
| `a.btn.back-btn[data-action="back"]` | ← (Back) | 页面 header 左侧 | `data-action="back"` → `href="/agents"` | 返回 Agents list 页面 | 点击后导航到 `/agents` |
| `button[data-action="help"]` / `.icon-btn` | 帮助 (emoji: ❔) | Topbar 右侧 | `data-action="help"` | 打开帮助面板：展示 Agent Detail 页面字段说明 | 点击后弹出帮助面板 |
| `button[data-action="shell"]` / `.icon-btn` | 终端 (emoji: ⌨️) | Topbar 右侧 | `data-action="shell"` | 打开本地命令面板 | 点击后弹出命令面板 |
| `span.info-icon[data-action="info"]` / `.info-icon` | ⓘ (指标说明) | 每个 metric card 内 | `data-action="info"` 或 `title` tooltip | 打开指标说明浮层，展示计算口径 | 点击/悬浮后显示指标解释 |
| `th.sortable[data-action="sort"][data-sort-key]` (Model Breakdown) | Sessions / Tokens / Cache Reuse / Tools / Failed / Avg Duration ↕ | Model Breakdown 表头 | `data-action="sort" data-sort-key="<key>"` | 按 model 指标排序，刷新表格 | 点击后行顺序改变；`sort-mark` 方向变化 |
| `input.input[aria-label="Search sessions"]` | — (搜索框) | Sessions 区域 header 右侧 | `placeholder="Search by Session ID or title..."` | 按 session ID 或标题过滤 Sessions 表 | 输入后表格实时过滤 |
| `th.sortable[data-action="sort"][data-sort-key]` (Sessions 表) | Model / Tokens / Rounds / Tools / Failed / Duration / Updated ↕ | Sessions 表头 | `data-action="sort" data-sort-key="<key>"` | 按对应字段排序，刷新表格 | 点击后行顺序改变 |
| `tr[data-action="open-session"]` (整行点击) | Session 行内容 | Sessions 表体每行 | `data-action="open-session"` → 导航到 session detail | 打开对应 Session detail 页面 | 点击后导航到 `/sessions/{agent}/{session_id}` |
| `div.tokenbar` hover (session 行) | Token breakdown | Tokens 列内 | hover 显示 tooltip | 悬浮显示 token 组成 breakdown | hover 时出现 tooltip |
| `input.page-input[data-action="page-input"]` | — (页码输入) | Pagination 区域 | `data-action="page-input"` → Enter 触发跳转 | 输入页码后按 Enter 跳转到指定页 | 输入合法页码 + Enter 后跳转 |
| `button[data-action="next-page"]` | next › | Pagination 区域右侧 | `data-action="next-page"` | 跳到下一页；尾页时不显示 | 非尾页时可见可点击 |
| `a.nav-link[data-target="agents"]` / sidebar `a.active:contains("Agents")` | Agents | 侧边栏导航 | `href="/agents"` (active 状态) | 当前页面标记 active；点击跳转到 Agents 列表 | `.active` class 存在 |
| `a.nav-link[data-target="dashboard"]` / sidebar `a:contains("Dashboard")` | Dashboard | 侧边栏导航 | `href="/dashboard"` | 跳转到 Dashboard | 点击后导航到 `/dashboard` |
| `a.nav-link[data-target="sessions"]` / sidebar `a:contains("Sessions")` | Sessions | 侧边栏导航 | `href="/sessions"` | 跳转到 Sessions 列表 | 点击后导航到 `/sessions` |
| `a.nav-link[data-target="projects"]` / sidebar `a:contains("Projects")` | Projects | 侧边栏导航 | `href="/projects"` | 跳转到 Projects 列表 | 点击后导航到 `/projects` |
| `a.nav-link[data-target="glossary"]` / sidebar `a:contains("Token Glossary")` | Token Glossary | 侧边栏导航 | `href="/glossary"` | 跳转到 Token Glossary | 点击后导航到 `/glossary` |
| `a[data-action="settings"]` / sidebar `.sidebar-foot .settings-link` | Settings | 侧边栏底部 | `data-action="settings"` | 打开 Settings 抽屉 | 点击后 Settings 抽屉滑入 |

## 图标行为表 (Icon Behavior Table)

### Agents List

| 图标 | 位置 | 语义 | 装饰性/可操作性 | 预期行为 | 尺寸/样式类 |
|---|---|---|---|---|---|
| ⌁ (brand logo) | 侧边栏顶部 | 应用图标：代表本地 agent run profiler | 装饰性 | 仅标识，不可点击 | `brand-logo` |
| 📊 (Dashboard nav) | 侧边栏导航 Dashboard 行 | Dashboard 图标：表示总体统计 | 可点击（跟随导航） | 点击跳转到 Dashboard | `nav-emoji` / `emoji`，与文字垂直居中 |
| 🧾 (Sessions nav) | 侧边栏导航 Sessions 行 | Sessions 图标：表示会话记录 | 可点击（跟随导航） | 点击跳转到 Sessions 列表 | `nav-emoji` / `emoji` |
| 📁 (Projects nav) | 侧边栏导航 Projects 行 | Projects 图标：表示项目工作区 | 可点击（跟随导航） | 点击跳转到 Projects | `nav-emoji` / `emoji` |
| 🤖 (Agents nav) | 侧边栏导航 Agents 行 | Agents 图标：当前页面入口 | 可点击（跟随导航） | 当前页标记 active；点击刷新 | `nav-emoji` / `emoji`，`.active` class |
| 📚/📘 (Glossary nav) | 侧边栏导航 Token Glossary 行 | Token Glossary 图标：表示 token 定义说明 | 可点击（跟随导航） | 点击跳转到 Token Glossary | `nav-emoji` / `emoji` |
| ⚙️ (Settings) | 侧边栏底部 Settings 按钮 | Settings 图标：表示设置入口 | 可点击 | 打开 Settings 抽屉 | `settings-link` 内 `<span>` |
| › (chevron) | 侧边栏底部 Settings 按钮右侧 | Chevron 图标：表示进入设置面板 | 装饰性（跟随按钮） | 与 Settings 按钮一起触发 | `settings-link` 右侧 `<span>` |
| ❔ (Help) | Topbar 右侧第一个 icon-btn | 帮助说明图标 | 可点击 | 打开帮助面板 | `icon-btn` |
| ⌘/⌨️ (Shell) | Topbar 右侧第二个 icon-btn | 终端/命令面板图标 | 可点击 | 打开本地命令面板 | `icon-btn` |
| 🤖 (metric icon) | Metric grid Active Agents 卡片 | Agent 种类数图标 | 装饰性 | 标识 Active Agents 指标 | `metric-icon purple` |
| 🧾 (metric icon) | Metric grid Sessions 卡片 | Session 总量图标 | 装饰性 | 标识 Sessions 指标 | `metric-icon green` |
| 📁 (metric icon) | Metric grid Projects 卡片 | Project 数量图标 | 装饰性 | 标识 Projects 指标 | `metric-icon blue` |
| 🪙 (metric icon) | Metric grid Total Tokens 卡片 | Token 总量图标 | 装饰性 | 标识 Total Tokens 指标 | `metric-icon red` |
| ⓘ (info) | 每个 metric card 指标名称后 | Info 图标：指标说明 | 可点击 | 点击后展示计算口径浮层 | `info` / `info-icon` |
| ↕ (sort mark) | 表头可排序列标题右侧 | 排序方向：↕ 可排序/↓ 降序/↑ 升序 | 可点击（跟随表头） | 点击切换排序方向 | `sort-mark` |
| CC/QD/CX (agent avatar) | Agent 行首 | Agent 缩写头像：CC=Claude Code, CX=Codex, QD=Qoder | 装饰性（行点击进入详情） | 颜色固定：CC purple、CX green、QD orange | `agent-avatar cc/cx/qd` |
| 颜色点 (badge dot) | Provider 单元格 agent badge 内 | Agent 类型颜色标识 | 装饰性 | 颜色与全局一致：purple/green/orange | `dot claude/codex/qoder` |
| TokenBar 彩色段 | Tokens 列内 | Token 组成可视化 | hover 可交互 | hover 显示 breakdown tooltip | `tokenbar` + `t-claude/t-codex/t-qoder/t-gray` |
| 占比条 (progress bar) | Tool Calls 列内 | Tool call 占比可视化 | 装饰性/hover 可交互 | 展示该 agent 在全部 tool calls 中的占比 | `progress` + `<i>` width 百分比 |
| ⚠️ (error dot) | Last Active 列前（失败行） | 失败状态标识 | 装饰性 | 红色/橙色点标识最近活跃异常 | `dot err` 或 `dot codex` 正常为绿色 |

### Agent Detail

| 图标 | 位置 | 语义 | 装饰性/可操作性 | 预期行为 | 尺寸/样式类 |
|---|---|---|---|---|---|
| ⌁ (brand logo) | 侧边栏顶部 | 应用图标 | 装饰性 | 仅标识 | `brand-logo` / `icon-emoji` |
| 📊 (Dashboard nav) | 侧边栏导航 | Dashboard 图标 | 可点击（跟随导航） | 跳转到 Dashboard | `nav-emoji` |
| 🧾 (Sessions nav) | 侧边栏导航 | Sessions 图标 | 可点击（跟随导航） | 跳转到 Sessions | `nav-emoji` |
| 📁 (Projects nav) | 侧边栏导航 | Projects 图标 | 可点击（跟随导航） | 跳转到 Projects | `nav-emoji` |
| 🤖 (Agents nav) | 侧边栏导航 | Agents 图标（当前 active） | 可点击（跟随导航） | 当前页标记 active | `nav-emoji`，`.active` |
| 📘 (Glossary nav) | 侧边栏导航 | Token Glossary 图标 | 可点击（跟随导航） | 跳转到 Glossary | `nav-emoji` |
| ⚙️ (Settings) | 侧边栏底部 | Settings 图标 | 可点击 | 打开 Settings 抽屉 | `settings-link` 内 |
| › (chevron) | Settings 按钮右侧 | 进入设置面板指示 | 装饰性 | 跟随 Settings 按钮 | `settings-link` 右侧 |
| ❔ (Help) | Topbar 右侧 | 帮助说明图标 | 可点击 | 打开帮助面板 | `icon-btn` |
| ⌨️ (Shell) | Topbar 右侧 | 终端图标 | 可点击 | 打开命令面板 | `icon-btn` |
| ← (Back) | Header 左侧 | 返回按钮 | 可点击 | 返回 Agents list | `back-btn` |
| 🤖 (header) | Header agent title 前 | 当前 agent 标识 | 识别 | 标识当前 agent 类型 | `icon-emoji` |
| 🧾 (metric) | Sessions metric card | Session 总量图标 | 装饰性 | 标识 Sessions 指标 | `metric-icon green` |
| 📁 (metric) | Projects metric card | Project 数量图标 | 装饰性 | 标识 Projects 指标 | `metric-icon purple` |
| ⬇️ (metric) | Input-side Tokens metric card | 输入 token 方向（向下=输入） | 装饰性 | 标识 Input-side Tokens 指标 | `metric-icon blue` |
| ⬆️ (metric) | Output Tokens metric card | 输出 token 方向（向上=输出） | 装饰性 | 标识 Output Tokens 指标 | `metric-icon purple` |
| ♻️ (metric) | Cache Reuse metric card | 缓存复用图标 | 装饰性 | 标识 Cache Reuse 指标 | `metric-icon blue` |
| ⚠️ (metric) | Failed Tools metric card | 失败警告图标 | 装饰性 | 标识 Failed Tools 指标 | `metric-icon red` |
| ⓘ (info) | 每个 metric card 指标名称后 | 指标说明 | 可点击 | 展示计算口径浮层 | `info-icon` |
| 💡 (insight) | Model Breakdown section header 右侧 | Insight 提示 | 不可点击 | 展示洞察信息（如 "Most active model: claude-3-7-sonnet"） | `insight` 内 `icon-emoji` |
| ↕ (sort mark) | 可排序表头右侧 | 排序方向 | 可点击（跟随表头） | 点击切换排序方向 | `sort-mark` |
| TokenBar 彩色段 | Token 列内 | Token 组成可视化 | hover 可交互 | hover 显示 breakdown tooltip | `tokenbar` + `t-fresh/t-read/t-write/t-out` |
| CC/QD/CX (agent avatar) | HIFI agent-avatar | Agent 缩写头像 | 装饰性 | 颜色固定 | `agent-avatar cc/cx/qd` |

## 生产 vs HIFI 差异分析

| 项目 | HIFI 规范 | 生产现状 | 风险等级 |
|---|---|---|---|
| Metric grid 布局 | 6 卡片等宽 grid (agent-detail: Sessions/Projects/Input-side/Output/Cache Reuse/Failed Tools) | 3 列 `data-table--compact` 文档表格（指标/数值/说明） | 高 — 需改造为 metric grid |
| Agent List metric cards | 4 个汇总卡片 (Active Agents/Sessions/Projects/Total Tokens) | 无汇总 metric grid | 中 — HIFI 新增 |
| Token 展示 | 缩写格式 (723.3M) + TokenBar 分解 | 纯数字 `format_number`，无 TokenBar | 中 |
| 排序实现 | `data-action="sort"` + `data-sort`/`data-sort-key` + `sort-mark` | 无排序按钮（agents.html 表头无交互；agent.html 无排序） | 高 — 需新增 |
| 分页 | `unified-pagination` (page-input + prev/next 条件显示) | 无分页（agents.html/agent.html 均无分页组件） | 中 — 数据量小时可接受 |
| Agent detail header | `back-btn` + agent title + subtitle | `back-btn` + agent title + desc 行 | 低 — 结构类似 |
| Model Breakdown tooltip | TokenBar 带 breakdown tooltip | 无 TokenBar，纯数字列 | 中 |
| Sessions 表搜索 | `input` search 框在 section header 内 | 无搜索框 | 中 |
| Insight badge | 💡 insight 提示在 Model Breakdown header | 无 insight 区域 | 低 — 可选增强 |
| Agent avatar | `agent-avatar cc/cx/qd` 圆形头像 | `agent-dot` 小圆点 | 低 — 视觉差异 |

## 统计数据

- **按钮行为表**: 41 项 (Agents List 20 + Agent Detail 21)
- **图标行为表**: 44 项 (Agents List 21 + Agent Detail 23)
- **HIFI 页面**: `agents.html` (agent list) + `agent-detail.html` (agent detail)
- **生产模板**: `agents.html` (list) + `agent.html` (detail)
