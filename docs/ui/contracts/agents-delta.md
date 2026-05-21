# Agents List Delta 文档：生产模板 vs HIFI

> 对比源：`src/session_browser/web/templates/agents.html`（生产，基于 base.html）vs `$HOME/Downloads/feipi-session-browser-hifi-integrated-v1/pages/agents.html`（HIFI）
> T125 生成，2026-05-21

---

## 1. 结构差异（Structural）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| S1 | 模板系统 | Jinja2 `{% extends "base.html" %}`，sidebar/topbar/footer 由 base.html 提供 | 独立 HTML，内嵌 `<div class="app">` + sidebar + topbar + footer | structural | 需要迁移 |
| S2 | 指标网格 | 不存在 | `.metric-grid` 含 4 个 `.card.metric`（Active Agents / Sessions / Projects / Total Tokens），各含 icon + label + value + delta | structural | 需要迁移 |
| S3 | 页面标题区 | `.page-header` + `.page-header__top` + `.page-header__desc`（"N 个 Agent，覆盖 N 个模型组合"） | `.page-title` + `h1` + `.subtitle`（"Compare session volume, token usage, tool calls, and failure rate by agent."） | structural | 需要对齐 |
| S4 | 面包屑 | `{% block breadcrumb %}` 模板块，由 base.html 渲染 | `.topbar` 内 `.crumb` 元素（`Agent Run Profiler / Agents`） | structural | base.html 已提供 |
| S5 | 表格列数/结构 | 7 列：Agent / Sessions / Projects / Tokens / Tool Calls / Failed / 最近活跃 | 7 列：Agent / **Provider** / Sessions / Projects / Tokens / Tool Calls / Failed / **Last Active**（HIFI 实际也是 7 列但列序不同，新增 Provider 列） | structural | 需要迁移 |
| S6 | Agent 单元格 | `agent-dot` 圆点 + 纯文本链接（`<a href="/agents/{{ a.agent }}">`） | `.agent-main`（`.agent-avatar` 圆形缩写 + `.title-main` 名称 + `.title-sub` 描述），无 `<a>` 链接 | structural | 需要迁移 |
| S7 | Provider 列 | 不存在 | 新增列：`.badge cc/cx/qd` + `.dot` + Provider 名称（Anthropic / OpenAI / Qoder） | structural | 需要迁移 |
| S8 | Token 单元格 | 纯文本 `{{ a.total_tokens \| format_compact_token }}` | `.token-cell`：`.token-total` + `.tokenbar`（4 段彩色条）+ `.tooltip`（hover breakdown） | structural | 需要迁移 |
| S9 | Tool Calls 单元格 | 纯文本 `{{ a.total_tool_calls \| format_number }}` | `.num` + `.progress`（占比条，`<i style="width:X%">`） | structural | 需要迁移 |
| S10 | Last Active 单元格 | `{{ a.last_active \| relative_time }}` 纯文本 | `.dot` 状态点 + "Xm ago" 文本 | structural | 需要对齐 |
| S11 | 分页 | 无 | `.pagination.unified-pagination`：page-input + "Page X of Y · N-M of N agents" | structural | 需要迁移 |
| S12 | Agent Efficiency 表 | 有独立第二个表格（Agent/Model Efficiency），含 11 列 | 无（HIFI 不包含 efficiency 表） | structural | 生产独有 |
| S13 | Toast 容器 | 无 | HIFI 通过 JS 动态创建 `.copy-note` 元素 | structural | 需要迁移 |
| S14 | 数据属性 | 无行级 data-action | 行级 `data-action="open-agent"`，表头 `data-action="sort"` `data-sort="*"` | structural | 需要迁移 |
| S15 | JS 引用 | 无 agents.js | `<script src="../assets/agents/app.js">` + `common-hifi-rules.js` | structural | 需要迁移 |
| S16 | 空状态 | `.empty-state` 简单文本（"暂无 Agent 数据，请先运行扫描。"） | HIFI CSS 定义了 `.empty-state`（flex 布局 + `.state-icon` + `.state-title`），但 HIFI HTML 中无空状态元素 | structural | 需要对齐 |

---

## 2. 样式差异（Styling）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| W1 | CSS 引用 | 依赖 base.html 的 `style.css` + `ui-primitives.css` + `legacy-aliases.css` | `../assets/agents/styles.css` + `../assets/common-hifi-rules.css` | styling | 需要迁移 |
| W2 | 指标卡片样式 | 无 | `.metric`（`height:112px`, `padding:18px`）+ `.metric-icon`（52px 圆角方块，4 色背景 purple/green/blue/red）+ `.metric-value`（22px mono）+ `.delta`（含 `.bad` 修饰） | styling | 需要迁移 |
| W3 | 页面标题样式 | `.page-header__title`（base.html 继承样式） | `.page-title h1`（28px, letter-spacing -0.035em）+ `.subtitle`（14px, #475569） | styling | 需要对齐 |
| W4 | Agent 头像样式 | `.agent-dot`（小圆点，3 色） | `.agent-avatar`（34x34 圆角 11px，含缩写 CC/CX/QD，3 色柔和背景） | styling | 需要迁移 |
| W5 | Provider badge 样式 | 无 | `.badge.cc`（#f1edff 背景）/`.badge.cx`（#ecfdf5）/`.badge.qd`（#fff7ed）+ `.dot` 8px 圆点 | styling | 需要迁移 |
| W6 | Token 条样式 | 无 | `.tokenbar`（128px 宽，8px 高，4 段：t-claude/t-codex/t-qoder/t-gray）+ `.tooltip`（hover 显示 breakdown，含具体数值和 total） | styling | 需要迁移 |
| W7 | Tool Calls 进度条 | 无 | `.progress`（92px 宽，7px 高，圆角背景 + `<i>` 占比条） | styling | 需要迁移 |
| W8 | Failed 徽章 | `.highlight-error` class（条件添加） | `.badge.err`（柔和红色背景 #fef2f2，红色文字） | styling | 需要对齐 |
| W9 | 可排序表头样式 | 无 | `.sort`（cursor:pointer，`::after` 显示 `↕`）+ `.active-sort`（brand 色，`::after` 显示 `↓`） | styling | 需要迁移 |
| W10 | 表格工具栏样式 | 无（直接渲染表格） | `.table-toolbar`（height:50px，border-bottom）+ `.table-title`（16px bold） | styling | 需要迁移 |
| W11 | 分页样式 | 无 | `.pagination`（height:56px）+ `.page-input`（56px 宽，居中 mono）+ `.page-status` | styling | 需要迁移 |
| W12 | 表格行样式 | 基础 `<tr>` 无 hover | `tbody tr:hover { background:#fbfcff }` | styling | 需要迁移 |
| W13 | 表格单元格高度 | 默认 | `td { height:60px }` | styling | 需要迁移 |

---

## 3. 行为差异（Behavioral）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| B1 | Agent 行点击 | Agent 名 `<a>` 链接跳转 `/agents/{agent_key}` | 整行 `data-action="open-agent"` 可点击，JS toast 提示 "Navigate to agent detail page" | behavioral | 需要对齐 |
| B2 | 排序交互 | 无客户端排序（数据由服务端排序） | 表头 `data-action="sort"` + `data-sort="sessions|projects|tokens|tools|failed|last_active"`，JS toast 提示（HIFI 当前仅 demo） | behavioral | 需要迁移 |
| B3 | Token hover | 无 | `.tokenbar:hover` 显示 `.tooltip`（token breakdown: Fresh/Cache Read/Cache Write/Output + Total） | behavioral | 需要迁移 |
| B4 | 分页交互 | 无 | `data-action="page-input"` 输入页码 Enter 跳转，`data-action="next-page"` 下一页 | behavioral | 需要迁移 |
| B5 | Toast 通知 | 无 | JS `toast()` 函数，固定右下角 `.copy-note`，1.4s 自动消失 | behavioral | 需要迁移 |
| B6 | 帮助/Shell | base.html 提供 `?` 和 `⌘` 按钮 | HIFI topbar 有 `data-action="help"` 和 `data-action="shell"` 按钮 | behavioral | base.html 已提供 |
| B7 | 设置入口 | base.html 提供 | HIFI sidebar-foot 有 `data-action="settings"` 按钮 | behavioral | base.html 已提供 |
| B8 | Metric info | 无 | 每个 metric label 有 `ⓘ` 按钮（`.info` class），hover 显示计算口径说明 | behavioral | 需要迁移 |
| B9 | Delta 指示 | 无 | 每个 metric 有 delta 文案（如 "↗ 482 vs last 7 days"），含 `.bad` 修饰 | behavioral | 需要迁移 |
| B10 | Efficiency 表交互 | 纯服务端渲染 | 无（HIFI 不包含此表） | behavioral | 生产独有 |

---

## 4. 数据绑定差异

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 |
|---|---|---|---|---|
| D1 | Agent 列表 | `{% for a in agents %}` Jinja2 循环，动态渲染所有 agent | 静态 3 行示例（Claude Code / Codex / Qoder） | data |
| D2 | 指标值 | 无独立 metric 区域 | 静态值：Active Agents 3 / Sessions 4,892 / Projects 128 / Total Tokens 1,247.5M | data |
| D3 | Token 值 | `{{ a.total_tokens \| format_compact_token }}` 纯文本 | `.token-total` + `.tokenbar`（4 段 inline style width%）+ `.tooltip`（hover breakdown 含具体数值） | data |
| D4 | Tool Calls | `{{ a.total_tool_calls \| format_number }}` 绝对数字 | `.num` 绝对值 + `.progress`（占比条，inline style width%） | data |
| D5 | Provider 信息 | 无 | 静态 Provider 名称（Anthropic / OpenAI / Qoder）+ badge | data |
| D6 | Agent 描述 | 无（仅名称） | `.title-sub` 描述文本（如 "Local Claude Code sessions"） | data |
| D7 | Last Active 格式 | `{{ a.last_active \| relative_time }}` Jinja2 过滤器 | 静态文本（"2m ago" / "15m ago" / "1h ago"）+ `.dot` 状态点 | data |
| D8 | Failed 格式 | `{{ a.total_failed_tools }}` + `.highlight-error` 条件 | `.badge.err` + 纯数字 | data |
| D9 | 顶部统计 | `{{ agents \| length }}` + `{{ efficiency \| length }}` | 无（由 metric-grid 替代） | data |
| D10 | Efficiency 数据 | `{% for e in efficiency %}` 11 列动态数据（model/avg_duration/p95/cache_reuse_ratio 等） | 无 | data |
| D11 | 排序数据源 | 无客户端 data-sort 属性 | 表头 `data-sort="sessions|projects|tokens|tools|failed|last_active"` | data |
| D12 | 分页数据 | 无（全量展示） | 静态 "Page 1 of 1 · 1-3 of 3 agents" | data |

---

## 5. 迁移优先级

| 优先级 | 项目 | 涉及差异 | 原因 |
|---|---|---|---|
| 高 | 指标网格（S2/W2/B8/B9/D2） | 视觉首屏区域，HIFI 核心新增 | 缺少即偏离 HIFI 设计 |
| 高 | Token 条迁移（S8/W6/B3/D3） | 纯文本 → 可视化条 + hover tooltip | HIFI 独有核心可视化 |
| 高 | Agent 头像升级（S6/W4/D6） | 小圆点 → 圆形缩写头像 + 描述文本 | 视觉辨识度核心差异 |
| 高 | Provider 列新增（S7/W5/D5） | 新增 Provider 列（badge + dot + 名称） | HIFI 结构新增列 |
| 高 | 表头排序对齐（S14/W9/B2/D11） | 无 → 可点击表头排序 | HIFI 标准排序方式 |
| 高 | Tool Calls 进度条（S9/W7/D4） | 纯文本 → 数字 + 占比条 | 视觉增强 |
| 中 | Failed 徽章样式对齐（W8/D8） | `.highlight-error` → `.badge.err` | 视觉一致性 |
| 中 | Last Active 状态点对齐（S10/D7） | 纯文本 → dot + 文本 | 视觉一致性 |
| 中 | Toast 通知（S13/B5） | 新增反馈机制 | 辅助交互 |
| 中 | 分页（S11/W11/B4/D12） | 新增分页能力 | 数据量大时需要 |
| 中 | 表格工具栏（W10） | 新增 `.table-toolbar` + `.table-title` | 结构对齐 |
| 中 | 页面标题区对齐（S3/W3） | `.page-header` → `.page-title` + `.subtitle` | 视觉一致性 |
| 低 | 空状态样式对齐（S16） | 简单文本 → flex 布局（CSS 已定义但 HTML 未使用） | 次要视觉优化 |
| 低 | 表格行 hover（W12/W13） | 无 → hover 高亮 + 固定 td height | 次要交互增强 |
| 保留 | Agent Efficiency 表（S12/B10/D10） | 生产独有第二个表，HIFI 无 | 需评估是否保留或迁移到独立页面 |

---

## 6. 差异统计

| 分类 | 数量 |
|---|---|
| 结构差异（Structural） | 16 |
| 样式差异（Styling） | 13 |
| 行为差异（Behavioral） | 10 |
| 数据绑定差异（Data） | 12 |
| **总计** | **51** |
| 需要迁移的 P0/P1 任务 | 6（指标网格、Token 条、Agent 头像、Provider 列、表头排序、Tool Calls 进度条） |
| 需要迁移的 P2 任务 | 6（Failed 徽章、Last Active、Toast、分页、表格工具栏、页面标题） |
| 需要迁移的 P3 任务 | 2（空状态、表格行 hover） |
| 需评估保留项 | 1（Agent Efficiency 表，HIFI 中不存在） |
