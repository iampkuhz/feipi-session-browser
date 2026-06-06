# Projects 页面行为契约

覆盖 **Projects List**（项目列表）和 **Project Detail**（项目详情）两个页面。
数据来源：HIFI 高保真页面 + 生产模板交叉验证。

## 1. 按钮行为表

### Projects List 按钮行为

| # | Selector / Label | Location | data-action / href | Expected Behavior | Validation |
|---|---|---|---|---|---|
| 1 | `a.settings` / "Settings" | Sidebar bottom | `data-action="open-settings"` | 打开 Settings 抽屉，展示数据目录、扫描配置、主题 | HIFI: `data-action="open-settings"`；生产: `data-action="open-settings"` |
| 2 | `button.icon-button[data-action="open-help"]` / "?" | Topbar right | `data-action="open-help"` | 打开帮助说明，展示本页字段含义、排序规则 | HIFI: `data-action="open-help"`；生产: 无对应按钮 |
| 3 | `button.icon-button[data-action="open-shell"]` / "⌨️" | Topbar right | `data-action="open-shell"` | 打开本地命令说明，展示如何重新扫描本地 agent sessions | HIFI: `data-action="open-shell"`；生产: 无对应按钮 |
| 4 | `input.search[data-search="project-name"]` / search input | Filter card | `data-search="project-name"` | 按项目名称实时搜索，过滤表格行 | HIFI: `data-search="project-name"`；生产: `#project-search` + `filterProjects()` |
| 5 | `button[data-action="clear-search"]` / "Clear" | Filter card | `data-action="clear-search"` | 清空项目名搜索，恢复完整项目列表 | HIFI: `data-action="clear-search"`；生产: `onclick="resetProjectFilters()"` |
| 6 | `button[data-action="apply-search"]` / "Apply" | Filter card | `data-action="apply-search"` | 应用项目名搜索，列表只显示名称匹配的项目 | HIFI: `data-action="apply-search"`；生产: 无 Apply 按钮（实时搜索） |
| 7 | `th button.sortable-header[data-action="sort"]` / "Sessions ↕" | Table header | `data-action="sort" data-sort="sessions"` | 按 Sessions 排序：第一次点击从大到小，再次点击反向 | HIFI: `data-action="sort" data-sort="sessions"`；生产: `.sortable` class + JS |
| 8 | `th button.sortable-header[data-action="sort"]` / "Tokens ↕" | Table header | `data-action="sort" data-sort="tokens"` | 按 Tokens 排序：第一次点击从大到小，再次点击反向 | HIFI: `data-action="sort" data-sort="tokens"`；生产: 列存在但不可排序 |
| 9 | `th button.sortable-header[data-action="sort"]` / "Tools ↕" | Table header | `data-action="sort" data-sort="tools"` | 按 Tools 排序：第一次点击从大到小，再次点击反向 | HIFI: `data-action="sort" data-sort="tools"`；生产: 列存在但不可排序 |
| 10 | `th button.sortable-header[data-action="sort"]` / "Last Active ↕" | Table header | `data-action="sort" data-sort="last_active"` | 按 Last Active 排序：第一次点击从近到远，再次点击反向 | HIFI: `data-action="sort" data-sort="last_active"`；生产: `.sortable` class |
| 11 | `tr[data-action="open-project"]` / project row (click) | Table body | `data-action="open-project"` | 点击行打开 Project detail 页面 | HIFI: `data-action="open-project"`；生产: `<a href="/projects/...">` 链接 |
| 12 | `input.page-input[data-action="page-input"]` / page number | Pagination | `data-action="page-input"` | 输入页码后按 Enter，跳转到指定页 | HIFI: `data-action="page-input"`；生产: 无分页组件 |
| 13 | `button[data-action="next-page"]` / "next ›" | Pagination | `data-action="next-page"` | 跳到下一页；当前不是尾页时显示，尾页不渲染 | HIFI: `data-action="next-page"`；生产: 无分页组件 |
| 14 | `button[data-action="clear-search"]` / "Clear Search" | Empty state strip | `data-action="clear-search"` | 清空项目名搜索并重新渲染完整项目列表 | HIFI: 空状态条中的 Clear Search 按钮；生产: 无空状态按钮 |
| 15 | `button.path-copy-btn` / "⧉" (copy path) | Table body, path cell | `onclick="copyProjectPath(this, '...')"` | 复制完整项目路径，并显示 toast | HIFI: 无独立 copy 按钮（Path 是 sub-text）；生产: `onclick="copyProjectPath()"` |
| 16 | `select#project-sort` / Sort dropdown | Filter bar | N/A (select element) | 切换排序字段，触发 `sortProjects()` | HIFI: 无 select（使用 sortable headers）；生产: `<select>` 排序 |

### Project Detail 按钮行为

| # | Selector / Label | Location | data-action / href | Expected Behavior | Validation |
|---|---|---|---|---|---|
| 1 | `a.back-btn` / "⬅️" | Page header | `href="#"` (back navigation) | 返回 Projects list 页面 | HIFI: `<a class="back-btn" href="#">`；生产: `<a href="/projects">` |
| 2 | `button.btn[data-action="copy-path"]` / "Copy path" | Page header, path row | `data-action="copy-path"` | 复制项目完整路径，并显示 toast | HIFI: `data-action="copy-path"`；生产: `onclick="copyProjectPath()"` |
| 3 | `button.info-icon[data-action="info"]` / "ⓘ" (Sessions metric) | Metric card | `data-action="info"` | 展示 Sessions 计数方式的说明 popover | HIFI: `data-action="info"`；生产: `data-tooltip` 属性 |
| 4 | `button.info-icon[data-action="info"]` / "ⓘ" (Input-side metric) | Metric card | `data-action="info"` | 展示 Input-side Token 公式的说明 popover | HIFI: `data-action="info"`；生产: `data-tooltip` 属性 |
| 5 | `button.info-icon[data-action="info"]` / "ⓘ" (Output metric) | Metric card | `data-action="info"` | 展示 Output Token 定义的说明 popover | HIFI: `data-action="info"`；生产: `data-tooltip` 属性 |
| 6 | `button.info-icon[data-action="info"]` / "ⓘ" (Active Period metric) | Metric card | `data-action="info"` | 展示日期范围来源的说明 popover | HIFI: `data-action="info"`；生产: `data-tooltip` 属性 |
| 7 | `button.info-icon[data-action="info"]` / "ⓘ" (Sessions table title) | Table toolbar | `data-action="info"` | 展示表格显示本 Project 下 Sessions 的说明 | HIFI: `data-action="info"`；生产: 无对应按钮 |
| 8 | `input[data-action="search"]` / search input | Table toolbar | `data-action="search"` | 按标题或 Session ID 搜索，过滤表格行 | HIFI: `data-action="search"`；生产: 无搜索输入 |
| 9 | `th[data-action="sort"]` / "Tokens ↕" (sortable) | Table header | `data-action="sort"` | 按 Tokens 排序（sorted-desc 默认降序） | HIFI: `data-action="sort"`；生产: 列存在但不可排序 |
| 10 | `th[data-action="sort"]` / "Rounds" (sortable) | Table header | `data-action="sort"` | 按 Rounds 排序 | HIFI: `data-action="sort"`；生产: 无 Rounds 列 |
| 11 | `th[data-action="sort"]` / "Tools" (sortable) | Table header | `data-action="sort"` | 按 Tools 排序 | HIFI: `data-action="sort"`；生产: 列存在但不可排序 |
| 12 | `th[data-action="sort"]` / "Failed" (sortable) | Table header | `data-action="sort"` | 按 Failed 排序 | HIFI: `data-action="sort"`；生产: 列存在但不可排序 |
| 13 | `th[data-action="sort"]` / "Duration" (sortable) | Table header | `data-action="sort"` | 按 Duration 排序 | HIFI: `data-action="sort"`；生产: 列存在但不可排序 |
| 14 | `th[data-action="sort"]` / "Updated" (sortable) | Table header | `data-action="sort"` | 按 Updated 排序 | HIFI: `data-action="sort"`；生产: 列存在但不可排序 |
| 15 | `tr[data-action="open-session"]` / session row (click) | Table body | `data-action="open-session"` | 点击行打开对应 Session detail 页面 | HIFI: `data-action="open-session"`；生产: `<a href="/sessions/...">` 链接 |
| 16 | `button.btn[data-action="copy-session"]` / "📋" | Table body, session row | `data-action="copy-session"` | 复制 Session ID，并显示 toast | HIFI: `data-action="copy-session"`；生产: 无对应按钮 |
| 17 | `input.page-input[data-action="page-input"]` / page number | Pagination | `data-action="page-input"` | 输入页码后按 Enter，跳转到指定页 | HIFI: `data-action="page-input"`；生产: 无分页组件 |
| 18 | `button[data-action="next-page"]` / "next ›" | Pagination | `data-action="next-page"` | 跳到下一页；尾页不显示 | HIFI: `data-action="next-page"`；生产: 无分页组件 |
| 19 | `button[data-action="view-all"]` / "View all sessions" | Empty state strip | `data-action="view-all"` | 查看所有 Sessions（跳转到全局 Sessions 页面） | HIFI: 空状态条中的 View all 按钮；生产: 无对应按钮 |
| 20 | `a.settings[data-action="settings"]` / "Settings" | Sidebar bottom | `data-action="settings"` | 打开 Settings 面板 | HIFI: `data-action="settings"`；生产: `data-action="open-settings"` |
| 21 | `button.icon-btn[data-action="help"]` / "?" | Topbar | `data-action="help"` | 打开帮助说明 | HIFI: `data-action="help"`；生产: 无对应按钮 |
| 22 | `button.icon-btn[data-action="shell"]` / "💻" | Topbar | `data-action="shell"` | 打开本地 CLI/open-folder 操作 | HIFI: `data-action="shell"`；生产: 无对应按钮 |

## 2. 图标行为表

### Projects List 图标行为

| # | Icon | Location | Semantic Meaning | Decorative or Action | Expected Behavior | Size Class |
|---|---|---|---|---|---|---|
| 1 | 📊 | Sidebar nav | Dashboard — 数据分析总览 | Action (nav link) | 点击跳转到 Dashboard 页面 | `emoji` — nav icon (18–20px) |
| 2 | 🗓️ | Sidebar nav | Sessions — 会话运行记录 | Action (nav link) | 点击跳转到 Sessions 列表页 | `emoji` — nav icon (18–20px) |
| 3 | 📁 | Sidebar nav (active) | Projects — 本地项目/工作区 | Action (nav link, current) | 当前页面，高亮状态，点击刷新本页 | `emoji` — nav icon (18–20px) |
| 4 | 🤖 | Sidebar nav | Agents — agent provider 统计 | Action (nav link) | 点击跳转到 Agents 统计页 | `emoji` — nav icon (18–20px) |
| 5 | 📖 | Sidebar nav | Token Glossary — 指标说明 | Action (nav link) | 点击跳转到 Token Glossary 页 | `emoji` — nav icon (18–20px) |
| 6 | ⚙️ | Sidebar bottom | Settings — 全局设置 | Action (link) | 打开 Settings 抽屉 | `icon--nav` — nav icon (18–20px) |
| 7 | ⓘ | Metric card "Projects" | Info — 指标说明 | Action (button) | 点击展示项目数量计数方式的 popover | `icon-button--info` — inline (13–14px) |
| 8 | ⓘ | Metric card "Sessions" | Info — 指标说明 | Action (button) | 点击展示 session 总数的 popover | `icon-button--info` — inline (13–14px) |
| 9 | ⓘ | Metric card "Total Tokens" | Info — 指标说明 | Action (button) | 点击展示 token 消耗合计的 popover | `icon-button--info` — inline (13–14px) |
| 10 | ⓘ | Metric card "Failed Tools" | Info — 指标说明 | Action (button) | 点击展示 failed tool call 数量的 popover | `icon-button--info` — inline (13–14px) |
| 11 | 📁 | Metric card "Projects" | Projects — 项目数量标识 | Decorative (metric icon) | 静态展示，无交互 | `emoji lg` — metric icon (20–24px, container: 22px) |
| 12 | 〽️ | Metric card "Sessions" | Sessions — 运行记录标识 | Decorative (metric icon) | 静态展示，无交互 | `emoji lg` — metric icon (20–24px, container: 22px) |
| 13 | 🪙 | Metric card "Total Tokens" | Tokens — token 消耗标识 | Decorative (metric icon) | 静态展示，无交互 | `emoji lg` — metric icon (20–24px, container: 22px) |
| 14 | ⚠️ | Metric card "Failed Tools" | Warning — 失败标识 | Decorative (metric icon) | 静态展示，无交互 | `emoji lg` — metric icon (20–24px, container: 22px) |
| 15 | ↕ | Sortable column header | Sortable — 可排序列 | Action (follows header click) | 跟随表头点击切换排序方向 | `sort-caret` — inline (14–16px) |
| 16 | 📋 (SVG) | Path copy button | Copy — 复制项目路径 | Action (button) | 点击复制项目完整路径，显示 toast | `path-copy-btn` — inline (14px SVG, container: 22px) |
| 17 | 📁 | Empty state strip | Empty — 无匹配项目 | Decorative (state icon) | 静态展示 | `emoji lg` — state icon (24–32px, container: 24px) |
| 18 | 🔴/🟣/🟢 (`.dot.claude/.dot.codex/.dot.qoder`) | Agent badges | Agent provider 标识 | Decorative | 颜色标识：CC=purple, CX=green, QD=orange | `dot` — inline (8–10px) |
| 19 | Token bar segments (`.t-fresh/.t-read/.t-write/.t-out`) | Tokens column | Token 组成分段 | Decorative + Action (hover) | 悬浮时展示 token breakdown tooltip | `tokenbar` — inline (bar height ~8px) |
| 20 | ? | Topbar help button | Help — 帮助说明 | Action (button) | 点击打开帮助面板 | `icon-btn` — inline (16px, container: 32px) |
| 21 | ⌘ | Topbar shell button | Terminal — 本地 CLI | Action (button) | 点击打开本地扫描命令说明 | `icon-btn` — inline (16px, container: 32px) |

### Project Detail 图标行为

| # | Icon | Location | Semantic Meaning | Decorative or Action | Expected Behavior | Size Class |
|---|---|---|---|---|---|---|
| 1 | ⌁ | Sidebar brand | App logo — 品牌标识 | Decorative | 静态展示 | `brand-logo` — brand icon (24–28px) |
| 2 | 📊 | Sidebar nav | Dashboard — 数据分析总览 | Action (nav link) | 点击跳转到 Dashboard 页面 | `emoji` — nav icon (18–20px) |
| 3 | 🗓️ | Sidebar nav | Sessions — 会话运行记录 | Action (nav link) | 点击跳转到 Sessions 列表页 | `emoji` — nav icon (18–20px) |
| 4 | 📁 | Sidebar nav (active) | Projects — 本地项目/工作区 | Action (nav link, current) | 当前页面，高亮状态 | `emoji` — nav icon (18–20px) |
| 5 | 🤖 | Sidebar nav | Agents — agent provider 统计 | Action (nav link) | 点击跳转到 Agents 统计页 | `emoji` — nav icon (18–20px) |
| 6 | 📖 | Sidebar nav | Token Glossary — 指标说明 | Action (nav link) | 点击跳转到 Token Glossary 页 | `emoji` — nav icon (18–20px) |
| 7 | ⚙️ | Sidebar bottom | Settings — 全局设置 | Action (link) | 打开 Settings 面板 | `emoji` — nav icon (18–20px) |
| 8 | › | Sidebar bottom (after Settings) | Chevron — 展开指示器 | Decorative | 视觉指示，无独立行为 | text — inline (14–16px) |
| 9 | ⬅️ | Page header back button | Back — 返回列表 | Action (link) | 点击返回 Projects list | `emoji` — inline (16–18px) |
| 10 | 📋 | Copy path button | Copy — 复制路径 | Action (button) | 点击复制项目完整路径，显示 toast | `emoji` — inline (14–16px) |
| 11 | 📈 | Metric card "Sessions" | Sessions trend — 趋势标识 | Decorative (metric icon) | 静态展示 | `metric-icon purple` — metric icon (20–24px) |
| 12 | ⓘ | Metric card "Sessions" info | Info — Sessions 计数说明 | Action (button) | 点击展示 Sessions 计数方式 popover | `info-icon` — inline (14–16px) |
| 13 | 📥 | Metric card "Input-side Tokens" | Input — 输入侧 token 标识 | Decorative (metric icon) | 静态展示 | `metric-icon green` — metric icon (20–24px) |
| 14 | ⓘ | Metric card "Input-side" info | Info — Input-side 公式说明 | Action (button) | 点击展示 Input-side token 公式 popover | `info-icon` — inline (14–16px) |
| 15 | 📤 | Metric card "Output Tokens" | Output — 输出侧 token 标识 | Decorative (metric icon) | 静态展示 | `metric-icon blue` — metric icon (20–24px) |
| 16 | ⓘ | Metric card "Output" info | Info — Output 定义说明 | Action (button) | 点击展示 Output token 定义 popover | `info-icon` — inline (14–16px) |
| 17 | 📅 | Metric card "Active Period" | Calendar — 活跃周期标识 | Decorative (metric icon) | 静态展示 | `metric-icon purple` — metric icon (20–24px) |
| 18 | ⓘ | Metric card "Active Period" info | Info — 日期范围说明 | Action (button) | 点击展示日期范围来源 popover | `info-icon` — inline (14–16px) |
| 19 | ⓘ | Sessions table title info | Info — 表格说明 | Action (button) | 点击展示表格内容说明 popover | `info-icon` — inline (14–16px) |
| 20 | 🔎 | Search input prefix | Search — 搜索提示 | Decorative (input prefix) | 输入框交互 | `emoji` — inline (14–16px) |
| 21 | ↕ | Sortable column header | Sortable — 可排序列 | Action (follows header click) | 跟随表头点击切换排序方向 | `sortable` — inline (14–16px) |
| 22 | 📋 | Copy session ID button | Copy — 复制 Session ID | Action (button) | 点击复制 Session ID，显示 toast | `emoji` — inline (14–16px) |
| 23 | 📁 | Empty state strip | Empty — 无 Sessions | Decorative (state icon) | 静态展示 | `emoji` — state icon (24–32px) |
| 24 | 🔴/🟣/🟢 (`.dot.claude/.dot.codex/.dot.qoder`) | Agent badges | Agent provider 标识 | Decorative | 颜色标识：CC=purple, CX=green, QD=orange | `dot` — inline (8–10px) |
| 25 | Token bar segments (`.t-fresh/.t-read/.t-write/.t-out`) | Tokens column | Token 组成分段 | Decorative + Action (hover) | 悬浮时展示 token breakdown tooltip | `tokenbar` — inline (bar height ~8px) |
| 26 | ❔ | Topbar help button | Help — 帮助说明 | Action (button) | 点击打开帮助面板 | `emoji` — inline (16–18px) |
| 27 | 💻 | Topbar shell button | Terminal — 本地 CLI | Action (button) | 点击打开本地 CLI 操作面板 | `emoji` — inline (16–18px) |

## 3. 统计数据

| 指标 | Projects List | Project Detail | 合计 |
|---|---|---|---|
| 按钮/交互元素数 | 16 | 22 | 38 |
| 含 `data-action` 的按钮 (HIFI) | 8 | 16 | 24 |
| 含 `onclick` 的按钮 (生产) | 2 | 1 | 3 |
| 图标数 | 21 | 27 | 48 |
| 可点击图标 | 11 | 14 | 25 |
| 装饰性图标 | 10 | 13 | 23 |

## 4. 生产 vs HIFI 差异分析

| 差异项 | HIFI 状态 | 生产状态 | 风险 |
|---|---|---|---|
| 排序实现 | 可点击表头 + `data-action="sort"` + `data-sort` | `select` 下拉 + `onclick="sortProjects()"` | 中：交互模式不一致 |
| 分页组件 | `unified-pagination` (page-input + next) | 无分页 | 高：生产缺少分页 |
| 项目路径 copy | 无独立按钮（路径为 sub-text） | `onclick="copyProjectPath()"` + SVG 图标 | 低：功能一致，实现不同 |
| Session ID copy | `data-action="copy-session"` + emoji 📋 | 无对应功能 | 中：生产缺少此功能 |
| Token 展示 | TokenBar + 缩写 (72.3M) + breakdown tooltip | 原始整数 + `format_number` 过滤器 | 中：视觉不一致 |
| Info popover | `data-action="info"` 按钮 + popover | `data-tooltip` 属性 | 低：功能等效 |
| Search 模式 | 输入 + Apply/Clear 按钮 | 实时搜索 + Reset 按钮 | 低：交互模式不同但功能等效 |
| 列定义 | Sessions/Agents/Tokens/Tools/Last Active | Project/Path/Sessions/Agents/Tokens/Tools/Health/Last Active | 中：列数不同，HIFI 合并了 Path 到 Project 列 |
| Topbar 按钮 | Help + Shell (emoji) | 无 topbar 按钮区域 | 低：生产在 base.html 中实现 |
| Empty state | `.state-strip` + "View all sessions" 按钮 | `.empty-state` 纯文本 | 低：视觉风格不同 |
| Agent 徽章 | `badge cc/cx/qd` + 彩色 dot | `badge badge-claude/codex/qoder` | 低：class 命名不同，视觉一致 |
