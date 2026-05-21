# Sessions Page Behavior Contract

> 来源: HIFI `pages/session-list.html` + `docs/session-list.md` + 生产模板 `src/session_browser/web/templates/sessions.html` + `components/sessions_list_components.html` + `components/ui_primitives.html` + `static/css/sessions-list.css`
> 生成时间: 2026-05-21 (Task T017)

## 按钮行为表 (Button Behavior Table)

| 选择器 | 标签 | 位置 | data-action / href | 预期行为 | 验证点 |
|---|---|---|---|---|---|
| `button[data-action="apply"]` / `#session-filter-form[type="submit"]` | Apply | Filter card 右侧 | `type="submit"` → POST/GET `/sessions` | 按当前 Session ID / Agent / Model / Project 条件刷新表格，重置到第一页 | 点击后 URL 包含 q, agent, model, project 参数；表格数据更新 |
| `button[data-action="clear"]` / `a.js-clear-all` | Clear All | Filter card 右侧（有筛选时可见） | `href` 指向 `/sessions` 无参数 URL | 清空所有筛选条件（q, agent, model, project, sort, dir），恢复默认列表，回到第一页 | 点击后 URL 无查询参数；active filters 区域消失；Clear All 按钮隐藏 |
| `button.chip-x` / `a[aria-label^="Remove"]` × | × (filter chip 移除) | Active filters 区域，每个 chip 右侧 | `href` 指向移除对应 filter 后的 URL | 移除单个筛选条件并刷新表格 | 点击后 URL 去掉对应参数；该 chip 消失；表格更新 |
| `a.sessions-th__sort-btn` / `button[data-sort-key]` | Tokens / Rounds / Tools / Duration / Updated + ↕ | Table header 行，可排序列 | `href` 包含 `sort=<key>&dir=<dir>` 或 `name="sort" value="<key>"` | 切换排序字段和方向（首次 desc，再次 asc），重新渲染表格 | 点击后 URL sort/dir 参数变化；表头箭头方向变化（↑/↓/↕）；行顺序改变 |
| `.sessions-row` (整行点击) | — (行内容) | Table body 每行 | `data-action="row"` → `window.location.href = /sessions/{agent}/{session_id}` | 打开对应 Session detail 页面 | 点击非链接区域后跳转到 `/sessions/{agent}/{session_id}`；点击行内 `<a>` 标签不触发整行跳转 |
| `.sessions-token-bar` hover | — (token bar 段) | Tokens 列内 | `aria-hidden="true"`，hover 显示 tooltip | 悬浮显示 Fresh / Cache Read / Cache Write / Output / Total 结构化 tooltip | hover 时出现 tooltip，包含 4 段百分比 + 总计；tooltip 随鼠标定位 |
| `input.page-input` / `#filter-form` page input | — (页码输入) | Pagination 区域 | `data-action="page-input"` → Enter 触发跳转 | 输入页码后按 Enter 跳转到指定页 | 输入合法页码 + Enter 后 URL page 参数变化；表格更新；非法输入不跳转 |
| `button[data-action="next-page"]` / `a[href]:contains("Next")` | Next / next › | Pagination 区域右侧 | `href` 指向下一页 URL | 跳到下一页；当前页为尾页时不显示 | 非尾页时可见可点击；尾页时隐藏或 disabled |
| `a[href]:contains("Previous")` | Previous | Pagination 区域，Next 左侧 | `href` 指向上页 URL | 跳到上一页；当前页为首页时不显示 | 非首页时可见可点击；首页时 disabled（opacity:0.5; pointer-events:none） |
| `select.sessions-footer-page-size__select` | Rows per page: 20/100/500/All | Footer 左侧 | `onchange` → `window.location.href` | 切换每页行数，立即跳转刷新 | 选择后 URL page_size 参数变化；表格行数变化 |
| `button.nav-button[data-target="sessions"]` | Sessions | 侧边栏导航 | `data-action="nav" data-target="sessions"` | 当前页面标记 active；点击刷新/回到 Sessions 列表 | `.active` class 存在；点击不刷新（已为当前页）或回到第一页 |
| `button.nav-button[data-target="dashboard"]` | Dashboard | 侧边栏导航 | `data-action="nav" data-target="dashboard"` | 跳转到 Dashboard 总览页 | 点击后导航到 `/dashboard` |
| `button.nav-button[data-target="projects"]` | Projects | 侧边栏导航 | `data-action="nav" data-target="projects"` | 跳转到 Projects 页面 | 点击后导航到 `/projects` |
| `button.nav-button[data-target="agents"]` | Agents | 侧边栏导航 | `data-action="nav" data-target="agents"` | 跳转到 Agents 页面 | 点击后导航到 `/agents` |
| `button.nav-button[data-target="glossary"]` | Token Glossary | 侧边栏导航 | `data-action="nav" data-target="glossary"` | 跳转到 Token Glossary 页面 | 点击后导航到 `/glossary` |
| `button.settings-button[data-action="settings"]` | Settings | 侧边栏底部 | `data-action="settings"` | 打开 Settings 抽屉：可配置数据源、扫描路径、显示偏好等 | 点击后 Settings 抽屉从右侧滑入 |
| `button.icon-button[data-action="help"]` | ❔ (帮助) | Topbar 右侧 | `data-action="help"` | 打开帮助说明：解释 Sessions 页面字段、排序、过滤和快捷键 | 点击后弹出帮助面板 |
| `button.icon-button[data-action="local-command"]` | 💻 (命令面板) | Topbar 右侧 | `data-action="local-command"` | 打开本地命令说明：显示如何重新扫描 session 数据 | 点击后弹出命令面板 |
| `a.sessions-title > a` (标题链接) | 会话标题（截断至 80 字符） | Table body 行 Title 列 | `href="/sessions/{agent}/{session_id}"` | 打开 Session detail 页面 | 点击标题链接直接跳转详情 |
| `a.link-muted[data-project]` | 项目名称 | Table body 行 Project 列 | `href="/projects/{project_key}"` | 打开对应 Project 页面 | 点击项目名跳转到项目详情页 |
| `#session-search` / `input[data-search="session-id"]` | — (搜索框) | Filter card 顶部 | `name="q"` placeholder="Search by Session ID..." | 输入 Session ID，仅支持 Session ID 搜索，不支持全文搜索 | 输入后点击 Apply 生效；输入非 ID 格式无匹配时显示空状态 |
| `#filter-agent` / `select[data-filter="agent"]` | Agent: All Agents / Claude Code / Codex / Qoder | Filter card 控制行 | `name="agent"` | 选择 agent 类型，点击 Apply 后过滤 | 选中后 URL 含 agent 参数 |
| `#filter-model` / `select[data-filter="model"]` | Model: All Models / ... | Filter card 控制行 | `name="model"` | 选择模型，点击 Apply 后过滤 | 选中后 URL 含 model 参数 |
| `#filter-project` / `select[data-filter="project"]` | Project: All Projects / ... | Filter card 控制行 | `name="project"` | 选择项目，点击 Apply 后过滤 | 选中后 URL 含 project 参数 |

## 图标行为表 (Icon Behavior Table)

| 图标 | 位置 | 语义 | 装饰性/可操作性 | 预期行为 | 尺寸/样式类 |
|---|---|---|---|---|---|
| 🔎 (search) | Filter card 搜索框内 | 搜索输入提示 | 不可点击，输入框可交互 | 与输入框一起组成 Session ID 搜索入口 | `sessions-search__icon`: font-size: 12px, color: text-3 |
| 📈 (logo) | 侧边栏顶部 | App logo：表示本地 agent session profiler | 装饰性 | 点击可跳转到首页/Dashboard | `brand-logo` |
| 📊 (dashboard nav) | 侧边栏导航 Dashboard 行 | Dashboard 图标：表示总体统计 | 可点击（跟随导航按钮） | 点击跳转到 Dashboard | `nav-icon`，与文字垂直居中 |
| 📋 (sessions nav) | 侧边栏导航 Sessions 行 | Sessions 图标：表示会话记录 | 可点击（跟随导航按钮） | 当前页标记 active；点击刷新列表 | `nav-icon`，与文字垂直居中 |
| 📁 (projects nav) | 侧边栏导航 Projects 行 | Projects 图标：表示项目工作区 | 可点击（跟随导航按钮） | 点击跳转到 Projects | `nav-icon`，与文字垂直居中 |
| 🤖 (agents nav) | 侧边栏导航 Agents 行 | Agents 图标：表示 Claude Code / Codex / Qoder 等 agent | 可点击（跟随导航按钮） | 点击跳转到 Agents | `nav-icon`，与文字垂直居中 |
| 📖 (glossary nav) | 侧边栏导航 Token Glossary 行 | Token Glossary 图标：表示 token 定义说明 | 可点击（跟随导航按钮） | 点击跳转到 Token Glossary | `nav-icon`，与文字垂直居中 |
| ⚙️ (settings) | 侧边栏底部 Settings 按钮 | Settings 图标：表示设置 | 可点击 | 打开 Settings 抽屉 | `settings-button` 内 `<span>` |
| ➡️ (settings chevron) | 侧边栏底部 Settings 按钮右侧 | Chevron 图标：表示打开下一级设置面板 | 装饰性（跟随按钮） | 与 Settings 按钮一起触发抽屉 | `settings-button` 内右侧 `<span>` |
| ❔ (help) | Topbar 右侧第一个 icon-button | 帮助说明图标 | 可点击 | 打开帮助说明面板 | `icon-button` |
| 💻 (local command) | Topbar 右侧第二个 icon-button | 本地命令面板图标 | 可点击 | 打开本地命令说明面板 | `icon-button` |
| ↕ / ↑ / ↓ (sort) | Table header 可排序列标题右侧 | 排序方向图标：↕ 可排序/↑ 升序/↓ 降序 | 可点击（跟随表头按钮） | 点击切换排序方向，表头行刷新 | `sessions-sort-icon`: 18x18px, border-radius: 7px, bg: #eff1ff, active: bg brand, color #fff, font-size: 11px |
| ℹ️ (info, Tokens 列) | HIFI 中 Tokens 表头旁 | Info 图标：表示此列有 token breakdown 说明 | 可点击/HFI 中跟随表头 | 悬浮 token bar 查看详情（生产实现为 hover token bar 触发 tooltip） | `info-icon`（HIFI）；生产中通过 token bar hover 实现 |
| Token bar 彩色段 | Tokens 列内，数字右侧 | Token 组成可视化：blue=Fresh, amber=Cache, green=Output | hover 可交互 | hover 显示 tooltip：Fresh/Cache_Read/Cache_Write/Output/Total | `sessions-token-bar`: 46x7px, border-radius: 999px；段: `__fresh`, `__cache`, `__out` |
| Agent badge CC/QD/CX | Table body Agent 列 | Agent 类型识别：CC=Claude Code, QD=Qoder, CX=Codex | 通常不可点击，行点击进入详情 | 颜色固定：CC purple、QD orange、CX green | `sessions-agent-badge`: height: 23px, border-radius: 999px；`--claude_code` purple, `--codex` green, `--qoder` orange |
| 🔎 (empty state) | 空状态条（无匹配 session 时） | 空状态图标：表示当前筛选没有匹配 session | 装饰性 | 配合 "No matching sessions" 文案展示 | `state-icon` |

## 布局结构说明

### 页面 Grid 列定义

`.sessions-grid` 使用 9 列 CSS Grid：

```
minmax(340px,2fr)  minmax(190px,1fr)  98px  126px  104px  112px  82px  108px  94px
↑ Title            ↑ Project           Agent Model Tokens Rounds Tools Duration Updated
```

### 排序列 vs 静态列

| 静态列（无排序按钮） | 可排序列（有 ↕ 图标 + 点击行为） |
|---|---|
| Title, Project, Agent, Model | Tokens, Rounds, Tools, Duration, Updated |

### Token bar 颜色映射

| 段 | CSS 变量/值 | 含义 |
|---|---|---|
| Fresh | `--token-input-fresh, #2563eb` (blue) | 未缓存输入 token |
| Cache (Read+Write) | `--token-cache-read, #f59e0b` (amber) | 缓存读写 token |
| Output | `--token-output-visible, #059669` (green) | 输出 token |

### Agent badge 颜色映射

| Agent | CSS class | 背景色 | 文字色 | 边框色 |
|---|---|---|---|---|
| Claude Code | `--claude_code` | #f5f3ff | #7c3aed | #ddd6fe |
| Codex | `--codex` | #ecfdf5 | #059669 | #bbf7d0 |
| Qoder | `--qoder` | #fffbeb | #d97706 | #fde68a |
