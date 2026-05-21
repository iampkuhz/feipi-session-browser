# Project Detail Delta 文档：生产模板 vs HIFI

> 对比源：`src/session_browser/web/templates/project.html`（生产，基于 base.html）vs `$HOME/Downloads/feipi-session-browser-hifi-integrated-v1/pages/project-detail.html`（HIFI）
> T111 生成，2026-05-21

---

## 1. 结构差异（Structural）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| S1 | 模板系统 | Jinja2 `{% extends "base.html" %}`，sidebar/topbar/footer 由 base.html 提供 | 独立 HTML，内嵌 `<div class="app">` + sidebar + topbar + footer + toast | structural | 需要迁移 |
| S2 | 页面头部容器 | `.page-header` > `.page-header__top` > `.page-header__left`（back 链接 + h1）+ `__actions` + `__desc`（path + copy-btn） | `.page-head` > `.back-btn` + h1 + `.path-row`（path-chip + Copy path 按钮）+ `.subtitle` | structural | 需要对齐 |
| S3 | 项目副标题 | 无 | `.subtitle` 显示 "Performance and cost profiling for agent runs across all models and agents." | structural | 需要迁移 |
| S4 | 指标卡片布局 | `.metrics-grid.metrics-grid--run-summary` 含 4 个 `.metric-card.metric-card--compact`（Sessions / Input-side / Output / Active Period） | `.metric-grid` 含 4 个 `.card.metric`，各含 `.metric-icon` + `.metric-label` + `.metric-value` + `.delta` | structural | 需要迁移 |
| S5 | 指标卡片内容 | 纯值：Sessions（CC/CX/QD badge）、Input-side（Cache R%）、Output（tools + /R）、Active Period（日期范围） | 带 icon（emoji）+ `ⓘ` info 按钮 + delta 行（如 "↗ 482 vs last 7 days"）+ agent-mix（百分比） | structural | 需要迁移 |
| S6 | 表格工具栏 | `.card-title` 纯文本 "Sessions ({{ sessions \| length }})" | `.table-toolbar` > `.card-title` + `ⓘ` + `.card-sub` + `<span class="spacer">` + `<input class="input" data-action="search">` | structural | 需要迁移 |
| S7 | 表格列数与结构 | 13 列：dot / Title / Agent / Model / Messages / Input / Cache R / Cache W / Output / Tools / Failed / Duration / Time | 9 列：Title / Agent / Model / Tokens / Rounds / Tools / Failed / Duration / Updated | structural | 需要迁移 |
| S8 | Token 列展示 | 拆分为 4 列（Input / Cache R / Cache W / Output），每列纯文本 `format_compact_token` | 合并为 1 列 `.token-cell`，含 `.token-total` + `.tokenbar`（4 段色条，hover 显示 breakdown tooltip） | structural | 需要迁移 |
| S9 | Title 单元格 | `<a href="/sessions/...">` 链接 + truncate + tooltip | `.title-main`（纯文本）+ `.title-sub mono`（session ID + branch + copy-session 按钮） | structural | 需要对齐 |
| S10 | 分页 | 无 | `.pagination.unified-pagination`：page-input + "Page X of N · 1-20 of 4.9K sessions" + next 按钮 | structural | 需要迁移 |
| S11 | 空状态 | `.empty-state` 简单文本 "No sessions found for this project." | `.state-strip`：`.state-icon` + `.state-title` + `.muted` 说明 + "View all sessions" 按钮 | structural | 需要对齐 |
| S12 | Topbar | base.html 提供 breadcrumb | `.topbar` > `.crumb`（Agent Run Profiler / Projects / **project-name**）+ `.top-actions`（help/shell 按钮） | structural | base.html 提供 |
| S13 | Toast 容器 | 无（projects.js 动态创建） | `<div class="toast">` 在 `</body>` 前 | structural | 需要迁移 |
| S14 | JS 文件 | `projects.js`（搜索/排序/过滤，projects list 与 detail 共享） | `project-detail.js`（toast 反馈模式，data-action 驱动） | structural | 需要对齐 |

---

## 2. 样式差异（Styling）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| W1 | CSS 引用 | 依赖 base.html 全局 CSS + `projects.css`（含 `.page-head`、`.metric-grid`、`.tokenbar` 等全局规则） | `../assets/project-detail/project-detail.css` + `../assets/common-hifi-rules.css` | styling | 需要迁移 |
| W2 | 页面头部类名 | `.page-header`（生产自定义） | `.page-head`（HIFI 标准 pattern） | styling | 需要对齐 |
| W3 | 返回按钮 | `.page-header__back`（`<a>` 链接，仅 `&larr;` 文本） | `.back-btn`（42px 方块，1px border，emoji ⬅️） | styling | 需要对齐 |
| W4 | 路径展示 | `.mono` > `.path-text.truncate` + `.path-copy-btn`（小方块 ⧉） | `.path-chip.mono`（30px 高 pill，1px border）+ `.btn.small`（📋 Copy path 文本按钮） | styling | 需要对齐 |
| W5 | 指标网格间距 | `.metrics-grid`（自定义 grid） | `.metric-grid`（`grid-template-columns: repeat(4, minmax(0, 1fr))`，`gap: 16px`） | styling | 需要对齐 |
| W6 | 指标卡片内部 | `.metric-label` + `.metric-value` + `.metric-sub` | `.metric-icon`（52px 方块，4 色背景）+ `.metric-label`（含 `ⓘ`）+ `.metric-value`（21px mono）+ `.delta` + `.agent-mix` | styling | 需要迁移 |
| W7 | Agent badge | `.badge.badge-claude/codex/qoder`（纯色背景） | `.badge.cc/cx/qd`（柔和背景色）+ `.dot.claude/codex/qoder`（8px 圆点） | styling | 需要对齐 |
| W8 | Token 条 | 无（纯文本跨 4 列） | `.tokenbar`（132px 宽，8px 高，4 段 `t-fresh/t-read/t-write/t-out`）+ `.tooltip`（hover breakdown） | styling | 需要迁移 |
| W9 | 可排序表头 | 无（表头 `<th>` 无 sortable 类） | `.sortable` 类 + `::after` 伪元素显示 `↕`/`↓` 排序指示器 | styling | 需要迁移 |
| W10 | 数字列对齐 | `class="numeric mono text-xs"` | `class="num mono"` | styling | 需要对齐 |
| W11 | 失败行样式 | `class="row--failed"` | 无特殊行样式，failed 通过 badge 展示 | styling | 生产独有 |
| W12 | Failed 徽章 | `.badge.badge-error`（红色纯数字）+ `.muted-zero`（灰色 0） | `.badge.err`（"1 failed" 文本，红色柔和背景）/ `.muted`（"—"） | styling | 需要对齐 |
| W13 | 空状态样式 | `.empty-state` 简单 div | `.state-strip`（flex，48px 圆角图标 + 标题 + 说明 + 按钮） | styling | 需要对齐 |
| W14 | 分页样式 | 无 | `.unified-pagination`（58px 高，`.page-input` + `.page-status` + `.btn.sm`） | styling | 需要迁移 |

---

## 3. 行为差异（Behavioral）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| B1 | 表格排序 | 无（表头不可点击） | `.sortable` 表头 `data-action="sort"` 可点击，当前 sorted-desc 状态 | behavioral | 需要迁移 |
| B2 | 表格搜索 | 无 | `<input data-action="search">` 即时搜索 title/session ID | behavioral | 需要迁移 |
| B3 | 分页交互 | 无（所有行一次渲染） | `.page-input` + Enter 跳转，`data-action="next-page"` 按钮 | behavioral | 需要迁移 |
| B4 | 行点击行为 | Title `<a>` 链接跳转 `/sessions/{agent}/{id}` | 整行 `data-action="open-session"` 可点击（HIFI JS toast 提示） | behavioral | 需要对齐 |
| B5 | 复制 session | 无 | `.btn.small` `data-action="copy-session"` 在 `.title-sub` 内 | behavioral | 需要迁移 |
| B6 | Metric info | 无 | 每个 metric 有 `ⓘ` 按钮 `data-action="info"`，触发 toast 显示口径说明 | behavioral | 需要迁移 |
| B7 | Token tooltip | 无（纯文本无 hover 详情） | `.tokenbar:hover .tooltip` 显示 breakdown（Input-side/Cache Read/Cache Write/Output 及百分比） | behavioral | 需要迁移 |
| B8 | Delta 指示 | 无 | 每个 metric 有 `vs last 7 days` delta 文案 | behavioral | 需要迁移 |
| B9 | 帮助/Shell | base.html 提供 | HIFI topbar 有 `data-action="help"` 和 `data-action="shell"` | behavioral | base.html 已提供 |
| B10 | 路径复制 | `.path-copy-btn` `data-action="copy-project-path"` `data-clipboard-text` | `.btn.small` `data-action="copy-path"` 带 📋 图标 + "Copy path" 文本 | behavioral | 生产已有，样式需对齐 |
| B11 | Toast 反馈 | projects.js 动态创建 toast | 页面内置 `.toast` 容器，JS toast 函数 | behavioral | 需要对齐 |

---

## 4. 数据绑定差异

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 |
|---|---|---|---|---|
| D1 | 项目名 | `{{ project.project_name }}`（Jinja2） | 静态值 "Agent Run Profiler" | data |
| D2 | 项目路径 | `{{ project.project_key | relative_to_repo | truncate_path }}` + `data-tooltip="{{ project.project_key }}"` | 静态 `~/dev/arp/Agent-Run-Profiler` | data |
| D3 | 指标值 | `{{ project.total_sessions }}` / `{{ p_input_side | format_compact_token }}` / `{{ project.total_output_tokens | format_compact_token }}` | 静态值：Sessions 4.9K / Input-side 1.1B / Output 167.6M | data |
| D4 | Agent 分布 | `{{ project.claude_sessions }}` / `{{ project.codex_sessions }}` / `{{ project.qoder_sessions }}` 绝对值 | 静态百分比：CC 46.0% / QD 31.0% / CX 23.0% | data |
| D5 | Delta 数据 | 无 | 静态 delta 文案：如 "↗ 482 vs last 7 days" | data |
| D6 | Session 行 | `{% for s in sessions %}` 循环 | 静态 6 行示例 | data |
| D7 | Token 格式化 | `{{ s.input_tokens | format_compact_token }}` 等 4 列独立 | `.token-total` 总和 + `.tokenbar` 4 段 inline style width% + hover tooltip 含具体数值 | data |
| D8 | 计算字段 | Jinja2 模板内计算：`p_input_side` / `p_cache_reuse` / `p_tools_per_round` | 静态值，无模板计算 | data |
| D9 | Active Period | `{{ project.first_seen[:10] }} → {{ project.last_seen | relative_time }}` | 静态 "May 9 – May 22" + "Last 14 days" | data |
| D10 | 计数 | `sessions | length`（两处） | 静态 "4.9K sessions" + "Page 1 of 245" | data |
| D11 | 行数据属性 | 无行级 `data-*` 属性（除 `data-tooltip`） | 行级 `data-action="open-session"` | data |

---

## 5. 迁移优先级

| 优先级 | 项目 | 涉及差异 | 原因 |
|---|---|---|---|
| 高 | 指标网格重构（S4/S5/W5/W6/B6/B8/D3/D4/D5） | 视觉首屏区域，HIFI 含 icon + info + delta + agent-mix 核心功能 | 缺少即偏离 HIFI 设计 |
| 高 | Token 列合并 + TokenBar（S7/S8/W8/B7/D7） | 13 列 → 9 列，4 列纯文本 → 1 列可视化条 + hover tooltip | HIFI 独有核心可视化 |
| 高 | 表格工具栏搜索（S6/B2） | 新增 search input，即时过滤 title/session ID | 基础交互能力 |
| 高 | Title 单元格重构（S9/B5） | `<a>` 链接 → `.title-main` + `.title-sub`（ID + branch + copy-session） | 信息结构变化 |
| 中 | 表头排序（B1/W9） | 新增 sortable 表头能力 | HIFI 标准排序方式 |
| 中 | 分页（S10/B3/W14/D10） | 新增分页交互 | 数据量大时需要 |
| 中 | Agent badge 样式对齐（W7） | 纯色 → 柔和色 + 圆点 | 视觉一致性 |
| 中 | Toast 容器（S13/B11） | 页面内置 toast vs 动态创建 | 辅助交互 |
| 中 | Failed 徽章（W12） | 纯数字 → "N failed" 文本 + 柔和背景 | 信息表达更清晰 |
| 低 | 页面头部对齐（S2/W2/W3/W4/B10） | `.page-header` → `.page-head`，back-btn / path-chip / subtitle | 视觉优化，结构微调 |
| 低 | 空状态样式（S11/W13） | `.empty-state` → `.state-strip` + button | 次要视觉优化 |
| 低 | 行点击行为（B4） | `<a>` 链接 vs `data-action="open-session"` 整行可点 | 交互体验优化 |
| 低 | 项目副标题（S3） | 新增 `.subtitle` 描述文案 | 信息增强 |

---

## 6. 差异统计

| 分类 | 数量 |
|---|---|
| 结构差异（Structural） | 14 |
| 样式差异（Styling） | 14 |
| 行为差异（Behavioral） | 11 |
| 数据绑定差异（Data） | 11 |
| **总计** | **50** |
| 需要迁移的 P0/P1 任务 | 4（指标网格、TokenBar、搜索、Title 重构） |
| 需要迁移的 P2 任务 | 5（排序、分页、Agent badge、Toast、Failed 徽章） |
| 需要迁移的 P3 任务 | 4（页面头部、空状态、行点击、副标题） |
