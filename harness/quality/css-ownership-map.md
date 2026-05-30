# CSS Ownership Map

> 本文档定义 `src/session_browser/web/static/css/` 下每个文件的职责边界和所有权。任何修改必须遵守本映射，不得越权覆盖他域样式。

---

## 分层架构

```
tokens.css          ← 原始设计令牌（颜色、间距、字体、动效）
    │
base.css            ← 全局重置、HTML/Body 基础、无障碍 focus、reduced-motion
    │
shell.css           ← 应用外壳（CSS Grid 三栏/两栏布局、sidebar、topbar 切换）
    │
ui-primitives.css   ← UI 原子组件（btn、badge、card、modal、tooltip、table…）
    │
┌────────────┬────────────┬────────────┬──────────┬──────────┐
│sessions-   │session-    │dashboard.  │projects. │agents.   │ … 页面级 CSS
│list.css    │detail.css  │css         │css       │css       │
└────────────┴────────────┴────────────┴──────────┴──────────┘
    │
legacy-aliases.css  ← 组件别名层（旧变量映射 + 旧组件样式）
```

**依赖方向**：上 → 下。页面级 CSS 依赖 ui-primitives → shell → base → tokens，反向覆盖一律禁止。

---

## 逐文件所有权

### 1. tokens.css
- **路径**: `css/tokens.css`
- **职责**: 设计令牌 — 所有原始值（primitive tokens）和语义别名（semantic tokens）
- **覆盖变量**:
  - 颜色阶梯：`--gray-50` ~ `--gray-900`
  - 间距：`--space-xs` ~ `--space-3xl`
  - 字体：`--font-sans`、`--mono`、字号比例 `--text-xs` ~ `--text-3xl`
  - 语义颜色：`--bg`、`--surface`、`--text`、`--brand`、`--ok`、`--warn`、`--err` 等
  - 动效：`--motion-duration-*`、`--motion-easing-*`
  - 布局变量：`--sidebar`、`--inspector`、`--topbar`、`--max`
- **边界**: 只声明 `--var` 自定义属性，不含任何选择器规则
- **不得包含**: 选择器、媒体查询、具体组件样式

### 2. base.css
- **路径**: `css/base.css`
- **职责**: 全局重置和基础排版
- **覆盖**:
  - CSS Reset（`*` margin/padding/box-sizing）
  - `html` 字号基准
  - `body` 背景渐变和字体基线
  - `prefers-reduced-motion` 媒体查询降级
  - `:focus-visible` 全局焦点样式
  - 全局链接样式 `a`
- **边界**: 仅针对 HTML 元素选择器、伪类、通配符；不得包含 `.class` 组件样式
- **不得包含**: 任何以 `.` 开头的组件选择器、页面级样式

### 3. shell.css
- **路径**: `css/shell.css`
- **职责**: 应用外壳布局 — CSS Grid 三栏/两栏结构和 body 级状态切换
- **覆盖**:
  - `.shell` 主 Grid 布局（sidebar + content + inspector）
  - `.shell.no-inspector` 两栏变体
  - `body.hide-left`、`body.hide-right` 等状态切换规则
  - `.app-shell` 向后兼容别名
  - sidebar 和 inspector 面板的可见性切换
- **边界**: 只负责页面整体骨架和布局状态，不含页面内容样式
- **不得包含**: 页面内部组件样式、按钮/卡片/列表等 UI 元素

### 4. ui-primitives.css
- **路径**: `css/ui-primitives.css`
- **职责**: 可复用的 UI 原子组件，跨页面共享
- **覆盖组件**:
  - Button（`.btn`、`.ui-btn` 及 `--primary`/`--secondary`/`--sm`/`--md` 变体）
  - IconButton（`.icon-btn`、`.icon-button`）
  - Badge（`.badge` 及颜色变体）
  - MetricCard / MetricGrid（`.metric-card`、`.metric-grid`）
  - Card / SectionCard（`.card`、`.section`、`.section-head`）
  - Tooltip（`.tooltip`）
  - Popover / Menu（`.popover`、`.menu-popover`）
  - DataTable（`.data-table`）
  - FilterBar（`.filter-card`、`.filter-chip`）
  - Pagination（`.pagination`）
  - PayloadModal（`.modal`、`.payload-modal`）
  - Empty/Error State 内联（`.state-strip`）
  - Toast（`.toast`）
  - TokenBar、Page Head（`.page-head` 基础）
- **边界**: 所有组件均为通用、无页面上下文依赖的定义
- **不得包含**: 页面级布局、特定页面（如 session-detail）专属组件

### 5. sessions-list.css
- **路径**: `css/sessions-list.css`
- **职责**: 会话列表页（`sessions.html`）专属样式
- **作用域**: `.sessions-page` 后代选择器
- **覆盖**:
  - 列表页筛选卡片（`.sessions-filter-card`）
  - 列表表格卡片（`.sessions-table-card`）
  - 列表行和单元格样式
  - 列表页特有的分页布局
- **边界**: 仅 `scope: .sessions-page`。不得覆盖 `.session-detail-page` 或全局 `.card`、`.btn`

### 6. session-detail.css
- **路径**: `css/session-detail.css`
- **职责**: 会话详情页（`session-detail.html`）专属样式
- **作用域**: `.session-detail-page` / `.sd-shell` 后代选择器
- **覆盖**:
  - 详情页布局壳（`.sd-shell`、`.sd-content`）
  - 时间线组件（`.sd-timeline`、`.sd-timeline-dot--*`）
  - 详情页按钮/药片变体（`.sd-btn--*`、`.sd-pill--*`）
  - 消息流、工具调用、代码块渲染
  - 详情页特有的表格和指标展示
- **边界**: 仅 `scope: .session-detail-page`。不得覆盖 `.sessions-page` 或全局 `.card`、`.btn`、`.pill`、`.tabs`

### 7. dashboard.css
- **路径**: `css/dashboard.css`
- **职责**: Dashboard 页（`/dashboard`）专属样式
- **依赖**: ui-primitives.css（token 变量、button、tooltip、metric-card 等）
- **覆盖**:
  - 页面头部（`.page-head` 在 dashboard 上下文中的扩展）
  - Dashboard 特有的指标卡片布局
  - Dashboard 导航和快捷入口
- **边界**: 仅 dashboard 页面。不得重复 ui-primitives.css 中已有的组件定义

### 8. projects.css
- **路径**: `css/projects.css`
- **职责**: Projects 页（`projects.html`）专属样式
- **覆盖**:
  - 项目列表和详情视图
  - 表格工具栏、可排序表头
  - Token 栏、Agent 徽标
  - 项目/路径合并单元格
- **边界**: 仅 projects 页面。不得覆盖全局 `.card`、`.btn`、`.pill`、`.tabs`

### 9. agents.css
- **路径**: `css/agents.css`
- **职责**: Agents 页（`agents.html`）专属样式
- **覆盖**:
  - Agent 列表视图
  - Agent 详情视图
  - Agent 特有的指标和状态展示
- **边界**: 仅 agents 页面。不得覆盖全局 `.card`、`.btn`、`.pill`、`.tabs`、sessions-list 样式

### 10. glossary.css
- **路径**: `css/glossary.css`
- **职责**: Glossary 页（`glossary.html`）专属样式
- **覆盖**:
  - Glossary 页面头部
  - 词条列表和分类
- **边界**: 仅 glossary 页面。`.card`、`.data-table`、`.badge` 等已在 ui-primitives.css 中定义，不得重复

### 11. states.css
- **路径**: `css/states.css`
- **职责**: 状态页（404、500/error）专属样式
- **覆盖**:
  - `.state-panel` — 独立状态/错误页容器
- **边界**: 仅 404.html 和 error.html 模板。与 ui-primitives.css 中的 `.state-strip`（内联空状态）为不同组件，但共享同一设计令牌系统

### 12. legacy-aliases.css
- **路径**: `css/legacy-aliases.css`
- **职责**: 向后兼容别名层 — 将旧变量名映射到新变量名，保证迁移期间不破坏现有样式
- **覆盖**:
  - 旧版 `--ui-*` 变量 → 新版 token 变量映射
  - 旧版选择器别名（如 `.app-shell` → `.shell`）
  - 历史遗留的 versioned 文件名兼容
- **边界**: 只声明别名映射（`--old: var(--new)`），不含新样式逻辑
- **目标**: 最终清理后删除本文件

---

## 门禁规则

| 规则 | 说明 |
|---|---|
| **依赖方向** | 页面 CSS → ui-primitives → shell → base → tokens，禁止反向 |
| **不得重复定义** | ui-primitives 中已有的组件（`.btn`、`.card`、`.badge` 等）不得在页面 CSS 中重写 |
| **作用域限定** | 页面 CSS 必须使用页面级前缀选择器（如 `.sessions-page .card`）限定作用域 |
| **硬编码颜色禁止** | 页面 CSS 必须使用 token 变量，不得写 `#5b5ce2` 等硬编码颜色 |
| **legacy-aliases 仅兼容** | 不得在 legacy-aliases 中添加新样式逻辑，仅做变量/选择器映射 |

---

## 文件清单

| 文件 | 层级 | 行数 | 所有权域 |
|---|---|---|---|
| `tokens.css` | L0 令牌 | ~200 | 设计令牌（颜色、间距、字体、动效、布局变量） |
| `base.css` | L1 基础 | ~55 | 全局重置、HTML/Body 基线、focus、reduced-motion |
| `shell.css` | L2 外壳 | ~270 | 应用外壳 Grid 布局、body 状态切换 |
| `ui-primitives.css` | L3 原子组件 | ~2500 | 通用 UI 组件（btn、card、badge、table、modal…） |
| `sessions-list.css` | L4 页面 | ~700 | 会话列表页 |
| `session-detail.css` | L4 页面 | ~2300 | 会话详情页 |
| `dashboard.css` | L4 页面 | ~400 | Dashboard 页 |
| `projects.css` | L4 页面 | ~400 | Projects 页 |
| `agents.css` | L4 页面 | ~350 | Agents 页 |
| `glossary.css` | L4 页面 | ~200 | Glossary 页 |
| `states.css` | L4 页面 | ~90 | 状态页（404、error） |
| `legacy-aliases.css` | L5 兼容 | ~1000 | 向后兼容别名映射 |

---

*最后更新：2026/05/24*
