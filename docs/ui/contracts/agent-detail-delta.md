# Agent Detail Delta 文档：生产模板 vs HIFI

> 对比源：`src/session_browser/web/templates/agent.html`（生产，基于 base.html）vs `$HOME/Downloads/feipi-session-browser-hifi-integrated-v1/pages/agent-detail.html`（HIFI）
> T139 生成，2026-05-21

---

## 1. 结构差异（Structural）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| S1 | 模板系统 | Jinja2 `{% extends "base.html" %}`，sidebar/topbar/footer 由 base.html 提供 | 独立 HTML，内嵌 `<div class="app">` + sidebar + topbar + footer | structural | 需要迁移 |
| S2 | 页面头部结构 | `.page-header` + `.page-header__top` + `.page-header__left` + `.page-header__back` + `.page-header__title` + `.page-header__desc` | `.header` + `.header-left` + `.btn.back-btn`（`data-action="back"`）+ `.agent-title-wrap` + `.agent-title` + `.agent-subtitle` | structural | 需要迁移 |
| S3 | 返回按钮 | `<a href="/agents" class="page-header__back">` 纯箭头文本 | `<a class="btn back-btn" data-action="back">` 带 title 属性 | structural | 需要迁移 |
| S4 | Agent 标识 | `.agent-dot {{ 'claude' \| 'qoder' \| 'codex' }}` + 文本标题 | `.agent-title` 含 `🤖` emoji + 大写标题 + `.agent-subtitle` 描述文本 | structural | 需要迁移 |
| S5 | 指标展示 | `<table class="data-table data-table--compact">` 7 行 × 3 列（指标/数值/说明），含中文说明 | `.metric-grid` 含 6 个 `.card.metric-card`，每个含 `.metric-icon` + `.metric-label` + `.metric-value` + `.info-icon` | structural | 需要迁移 |
| S6 | 指标卡片数量 | 7 项（Sessions, Projects, Input-side Tokens, Cache Reuse, Output Tokens, Tool Calls, Failed Tools） | 6 项（Sessions, Projects, Input-side Tokens, Output Tokens, Cache Reuse, Failed Tools），**无 Tool Calls** | structural | 需要对齐 |
| S7 | Model Breakdown 结构 | `.page-header` 作为 section 标题，下方直接 `.table-wrap` > `.data-table` | `.card.section` + `.section-head`（`.section-title` + `.section-sub` + `.insight`）+ `.table-wrap` > `.data-table` | structural | 需要迁移 |
| S8 | Model Breakdown 列数 | 9 列：Model / Sessions / Input / Cache R / Cache W / Output / Tools / Failed / Avg Duration | 7 列：Model / Sessions / **Tokens（合并）** / Cache Reuse / Tools / Failed / Avg Duration | structural | 需要迁移 |
| S9 | Token 列结构 | 纯文本：Input / Cache R / Cache W / Output 分 4 列 | `.token-col.token-cell`：`.token-total` + `.tokenbar`（4 段彩色条）+ `.tooltip`（hover breakdown） | structural | 需要迁移 |
| S10 | Sessions 结构 | `.page-header` 作为 section 标题，含 `.badge.badge-claude` 等，下方直接 `.table-wrap` | `.card.section` + `.section-head`（`.section-title` + `.section-sub` + `.info-icon` + search input） | structural | 需要迁移 |
| S11 | Sessions 列数 | 12 列：Title / Project / Model / Messages / Input / Cache R / Cache W / Output / Tools / Failed / Duration / Time | 9 列：Title / Project / Model / **Tokens（合并）** / **Rounds** / Tools / Failed / Duration / Updated | structural | 需要迁移 |
| S12 | Sessions 搜索 | 无 | `.input` 搜索框在 `.section-head` 中，placeholder="Search by Session ID or title..." | structural | 需要迁移 |
| S13 | Sessions 分页 | 无（所有行一次渲染） | `.pagination.unified-pagination`：页码输入 + "Page X of N" + next 按钮 | structural | 需要迁移 |
| S14 | 表头排序 | 无（所有列均不可排序） | 所有指标列 `.sortable`，含 `data-action="sort"` + `data-sort-key` + `.sort-mark` | structural | 需要迁移 |
| S15 | 空状态 | `<div class="empty-state">该 Agent 暂无 Session。</div>` 简单文本 | HIFI 未展示空状态，但有 `.state-strip` 模式（参考其他页面） | structural | 需要对齐 |
| S16 | data-action 属性 | 无 | 行级 `data-action="open-session"`，表头 `data-action="sort"`，按钮 `data-action="back"`/`"page-input"`/`"next-page"`/`"metric-info"`/`"help"`/`"shell"` | structural | 需要迁移 |
| S17 | ui_primitives 使用 | 无 import，空状态用简单 div | HIFI 不涉及（独立 HTML），但生产端应使用 ui_primitives 宏 | structural | 需要对齐 |
| S18 | Model Breakdown 条件渲染 | `{% if models \| length > 1 %}` 条件包裹 | HIFI 始终显示（静态数据） | structural | 生产合理 |
| S19 | colgroup 定义 | 无 | Model Breakdown 和 Sessions 表均有 `<colgroup>` 定义列宽 | structural | 需要对齐 |
| S20 | Section insight | 无 | Model Breakdown 有 `.insight` 行（如 "Most active model: claude-3-7-sonnet"） | structural | 需要迁移 |

---

## 2. 样式差异（Styling）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| W1 | CSS 引用 | 依赖 base.html 的 `style.css` + `ui-primitives.css` + `legacy-aliases.css` | `agent-detail.css` + `common-hifi-rules.css` | styling | 需要迁移 |
| W2 | 指标网格样式 | 无（紧凑表格） | `.metric-grid`（CSS grid）+ `.metric-card`（`min-height`，`padding`）+ `.metric-icon`（52px 圆角方块，4 色背景：green/purple/blue/red） | styling | 需要迁移 |
| W3 | 指标标签样式 | 无 | `.metric-label` 含 `.info-icon`（`ⓘ` 按钮，hover 可点击） | styling | 需要迁移 |
| W4 | 指标值样式 | 无 | `.metric-value`（22px mono 字体，大字展示） | styling | 需要迁移 |
| W5 | 页面头部样式 | `.page-header`（旧结构，多 div 嵌套） | `.header`（简化结构）+ `.agent-title`（大字 + emoji）+ `.agent-subtitle`（灰色描述文本） | styling | 需要迁移 |
| W6 | Section 卡片样式 | 无（`.page-header` + 裸 table） | `.card.section`（完整卡片容器，圆角 + 阴影/边框） | styling | 需要迁移 |
| W7 | Section 头部样式 | `.page-header__title` 简单文本 | `.section-head`（flex 布局）+ `.section-title` + `.section-sub`（灰色小字）+ `.insight`（💡 图标 + 文本） | styling | 需要迁移 |
| W8 | Badge 样式 | `.badge.badge-claude`/`.badge-qoder`/`.badge-codex` 纯色背景 | HIFI Sessions 区域无 badge，agent title 用 emoji + 大写文本 | styling | 生产独有 |
| W9 | Failed badge 样式 | `.badge.badge-error` 红色背景 + 纯数字 | `.badge.err` 柔和红色背景 + 纯数字 | styling | 需要对齐 |
| W10 | Zero 值样式 | `<span class="muted-zero">0</span>` | `<span class="mono">0</span>` 无特殊 muted 样式 | styling | 需要对齐 |
| W11 | Token 条样式 | 无（纯文本 `format_compact_token`） | `.tokenbar`（8px 高，4 段：`.t-fresh`/`.t-read`/`.t-write`/`.t-out`）+ `.tooltip`（hover 显示 breakdown 面板） | styling | 需要迁移 |
| W12 | Token 总数样式 | 无 | `.token-total` 显示在 tokenbar 上方 | styling | 需要迁移 |
| W13 | 可排序表头样式 | 无 | `.sortable` + `.sort-mark`（`↕` 符号） | styling | 需要迁移 |
| W14 | 分页样式 | 无 | `.pagination.unified-pagination`（`height:58px`）+ `.page-input` + `.page-status` + `.btn.sm` | styling | 需要迁移 |
| W15 | 搜索框样式 | 无 | `.input` 在 `.section-head` 中，右对齐 | styling | 需要迁移 |
| W16 | 空状态样式 | `.empty-state` 简单 div 文本 | HIFI 未展示，参考其他页面用 `.state-strip`（flex 布局 + 图标 + 按钮） | styling | 需要对齐 |
| W17 | Session 标题样式 | 纯 `<a>` 链接文本 | `.title-main`（主标题）+ `.title-sub.mono`（session ID + branch） | styling | 需要迁移 |
| W18 | Session 项目单元格 | `<a href="/projects/...">` 链接 + `data-tooltip` | `.project-cell` + `.path-tooltip`（hover 显示路径） | styling | 需要迁移 |
| W19 | 表格列宽控制 | 无 | `<colgroup>` + `.col-model-name`/`.col-sessions`/`.col-token-md`/`.col-cache`/`.col-tools`/`.col-failed`/`.col-avg`/`.col-title`/`.col-project`/`.col-model`/`.col-token`/`.col-num-sm`/`.col-duration`/`.col-updated` | styling | 需要对齐 |
| W20 | Model 单元格截断 | `class="mono" class="cell-truncate"`（重复 class 属性，HTML 无效）+ `{{ model[:60] }}` 硬截断 | `.mono` 纯文本，无截断 | styling | 需要对齐 |

---

## 3. 行为差异（Behavioral）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| B1 | 表头排序 | 无（所有列均不可排序） | 点击 `.sortable` 表头按钮触发排序，`data-action="sort"` + `data-sort-key` | behavioral | 需要迁移 |
| B2 | 搜索交互 | 无 | 搜索框即时过滤 sessions（按 Session ID 或 title） | behavioral | 需要迁移 |
| B3 | 行点击行为 | Title 和项目是 `<a>` 链接分别跳转 | 整行 `data-action="open-session"` 可点击 | behavioral | 需要对齐 |
| B4 | 分页交互 | 无（所有行一次渲染） | 页码输入 `data-action="page-input"` + Enter 跳转，next 按钮 `data-action="next-page"` | behavioral | 需要迁移 |
| B5 | Metric info 按钮 | 无 | 每个 metric label 旁有 `ⓘ` 按钮，点击显示口径说明 toast | behavioral | 需要迁移 |
| B6 | Section info 按钮 | 无 | Model Breakdown 和 Sessions 标题旁有 `.info-icon`，hover 显示说明 | behavioral | 需要迁移 |
| B7 | 返回按钮行为 | `<a href="/agents">` 直接跳转 | `data-action="back"` 按钮，JS 可能触发 history.back() | behavioral | 需要对齐 |
| B8 | Toast 通知 | 无 | JS 通过 toast 反馈操作结果（sort/search/page/help/metric-info/open-session） | behavioral | 需要迁移 |
| B9 | Token tooltip | 无 | hover `.tokenbar` 显示 `.tooltip` 面板：Token Breakdown（Fresh/Cache Read/Cache Write/Output 明细 + 百分比） | behavioral | 需要迁移 |
| B10 | 路径 hover | `data-tooltip` 显示完整 project_key | `.path-tooltip` hover 显示项目路径（如 `~/dev/arp`） | behavioral | 需要对齐 |
| B11 | 帮助/Shell | base.html 提供 `?` 和 `⌘` 按钮 | HIFI topbar 有 `data-action="open-help"` 和 `data-action="open-shell"` | behavioral | base.html 已提供 |
| B12 | Section insight | 无 | Model Breakdown 显示 `.insight`（如 "Most active model: xxx"） | behavioral | 需要迁移 |

---

## 4. 数据绑定差异

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 |
|---|---|---|---|---|
| D1 | Session 列表 | `{% for s in sessions %}` Jinja2 循环渲染 | 静态 8 行示例数据 | data |
| D2 | Model 列表 | `{% for model in models %}` 通过 sessions 去重动态收集 | 静态 4 行示例数据 | data |
| D3 | Token 值 | `{{ s.input_tokens \| format_compact_token }}` 等纯文本，分 4 列展示 | `.token-total` + `.tokenbar`（4 段 inline style width%）+ `.tooltip`（hover breakdown 含具体数值） | data |
| D4 | 指标值 | `{{ agent_info.session_count \| format_number }}` 等动态计算 | 静态值：Sessions 4,892 / Projects 128 / Input-side Tokens 1,247.5M / Output Tokens 156.6M / Cache Reuse 67.2% / Failed Tools 321 | data |
| D5 | 计算逻辑 | Jinja2 模板内计算 `a_input_side`、`a_cache_reuse`、`a_tools_per_round` | HIFI 不涉及（静态展示） | data |
| D6 | Model 聚合 | `{% set ms = sessions \| selectattr("model", "equalto", model) \| list %}` 模板内过滤聚合 | HIFI 不涉及（静态数据） | data |
| D7 | Agent 名称 | 三元表达式：`{{ 'Claude Code' if current_agent == 'claude_code' else 'Qoder' if current_agent == 'qoder' else 'Codex' }}` | 静态 "CLAUDE CODE" 大写 | data |
| D8 | 面包屑 | `{% block breadcrumb %}` 三段式：Dashboard / Agents / 当前 Agent | `.crumb`：Agent Run Profiler / Agents / **Claude Code** | data |
| D9 | 排序数据源 | 无排序功能 | 表头 `data-sort-key`：`model_sessions`/`model_tokens`/`cache_reuse`/`model_tools`/`model_failed`/`avg_duration`/`model`/`tokens`/`rounds`/`tools`/`failed`/`duration`/`updated` | data |
| D10 | 分页状态 | 无 | 静态 "Page 1 of 245 · 1–20 of 4.9K sessions" | data |
| D11 | 模型名截断 | `{{ model[:60] }}` 硬截断 + `data-tooltip="{{ model }}"` | 无截断，完整显示 | data |
| D12 | Session 标题截断 | `{{ s.title[:70] or 'Untitled' }}` 硬截断 | `.title-main` 完整标题 + `.title-sub.mono` 显示 session ID + branch | data |
| D13 | Duration 格式 | `{{ s.duration_seconds \| format_duration }}` | 静态显示如 "12m 47s"、"2m ago" | data |
| D14 | 相对时间 | `{{ s.ended_at \| relative_time }}` | 静态显示如 "2m ago"、"15m ago"、"1h ago" | data |

---

## 5. 生产中缺失的 HIFI 功能

1. **指标网格（Metric Grid）** — 6 个 `.metric-card` 卡片，含 icon + label + value + info 按钮，取代紧凑表格
2. **Token 可视化条（Tokenbar）** — Model Breakdown 和 Sessions 表的 Token 列使用彩色条 + hover tooltip 展示明细
3. **Sessions 搜索** — 搜索框支持按 Session ID 或 title 即时过滤
4. **Sessions 分页** — `.unified-pagination` 支持页码跳转
5. **表头排序** — 所有指标列可点击排序，含 `data-sort-key` 和 `.sort-mark`
6. **Section 卡片包装** — `.card.section` + `.section-head` 替代旧 `.page-header`
7. **Info 按钮** — metric label、section title 旁的 `ⓘ` 按钮，提供口径说明
8. **Section insight** — Model Breakdown 的 `.insight` 行展示洞察信息
9. **Session 标题双行结构** — `.title-main` + `.title-sub.mono`（session ID + branch）
10. **Project cell 结构** — `.project-cell` + `.path-tooltip` 替代独立链接
11. **colgroup 列宽定义** — 精确控制每列宽度
12. **data-action 属性体系** — 统一的交互属性标记

---

## 6. 生产独有功能

1. **Tool Calls 指标** — 生产模板单独展示 "Tool Calls" 指标（总调用数 + 轮数），HIFI 仅展示 Failed Tools
2. **BreadCrumb 三段式** — Dashboard / Agents / Current Agent，HIFI 仅 "Agent Run Profiler / Agents / Claude Code"
3. **Agent Dot 标识** — `.agent-dot.claude`/`.qoder`/`.codex` 圆点指示器
4. **Agent Badge** — Sessions 表头的 `.badge.badge-claude`/`.badge-qoder`/`.badge-codex`
5. **模型条件渲染** — 仅当 `models | length > 1` 时显示 Model Breakdown
6. **Project 超链接** — 项目名直接链接到 `/projects/{key}`
7. **指标中文说明列** — 紧凑表格的第三列展示每个指标的中文说明
8. **Cache R / Cache W 分离列** — Model Breakdown 和 Sessions 表分别展示 Cache Read 和 Cache Write
9. **Messages 列** — Sessions 表展示 `user_message_count + assistant_message_count`
10. **`muted-zero` 类** — 0 值使用特殊灰色样式
11. **`highlight-error` 类** — Failed Tools > 0 时高亮数值
12. **`row--failed` 类** — 失败 session 行高亮

---

## 7. 迁移优先级

| 优先级 | 项目 | 涉及差异 | 原因 |
|---|---|---|---|
| 高 | 指标网格（S5/S6/W2/W3/W4） | 视觉首屏区域，HIFI 核心设计 | 紧凑表格 → 卡片网格是根本性变化 |
| 高 | Token 条迁移（S9/W11/W12/D3/B9） | 4 列 Token → 1 列可视化条 + tooltip | HIFI 独有核心可视化，信息密度大幅提升 |
| 高 | 表头排序（S14/W13/B1/D9） | 无排序 → 全指标可排序 | 交互能力核心缺失 |
| 高 | Section 结构重构（S7/S10/W6/W7） | `.page-header` → `.card.section` + `.section-head` | 整体页面结构变化 |
| 中 | Sessions 搜索（S12/W15/B2） | 无搜索 → 即时搜索框 | 用户体验改进 |
| 中 | Sessions 分页（S13/W14/B4/D10） | 无分页 → 统一分页组件 | 数据量大时需要 |
| 中 | Sessions 标题结构（W17/D12） | 纯链接 → `.title-main` + `.title-sub` | 信息展示更丰富 |
| 中 | Project cell 对齐（W18/B10） | 独立链接 → `.project-cell` + `.path-tooltip` | 视觉一致性 |
| 中 | Info 按钮（B5/B6） | 无 → metric + section 信息按钮 | 辅助交互 |
| 低 | Badge 移除/对齐（W8/S11） | 生产独有 badge，HIFI 无对应 | 评估是否保留 |
| 低 | 空状态样式对齐（S15/W16） | `.empty-state` → `.state-strip` | 次要视觉优化 |
| 低 | colgroup 列宽（W19） | 无 → 精确列宽控制 | 精细排版 |
| 低 | Section insight（W7/S20/B12） | 无 → Model Breakdown 洞察行 | 增值信息 |
| 保留 | 生产独有功能（第 6 节） | Tool Calls 指标、中文说明、Cache 分离列等 | 需评估是否保留或迁移到 HIFI 模式 |

---

## 8. 差异统计

| 分类 | 数量 |
|---|---|
| 结构差异（Structural） | 20 |
| 样式差异（Styling） | 20 |
| 行为差异（Behavioral） | 12 |
| 数据绑定差异（Data） | 14 |
| **总计** | **66** |
| 需要迁移的 P0/P1 任务 | 4（指标网格、Token 条、表头排序、Section 结构） |
| 需要迁移的 P2 任务 | 5（搜索、分页、标题结构、Project cell、Info 按钮） |
| 需要迁移的 P3 任务 | 4（Badge 对齐、空状态、列宽、Insight） |
| 生产独有需评估 | 12 项 |
