# CSS 所有权与分层治理

> 版本: 1.0 | 创建: 2026-05-22 | 维护者: feipi-session-browser 团队

## 一、4 层 CSS 架构

```
Layer 1 — 设计令牌 + Shell 骨架（全局）
  style.css

Layer 2 — 共享原子组件（全局）
  css/ui-primitives.css

Layer 3 — 旧版别名（向后兼容）
  css/legacy-aliases.css

Layer 4 — 页面特定 CSS（按页面加载）
  css/dashboard.css
  css/sessions-list.css
  css/session-detail.css
  css/projects.css
  css/agents.css
  css/glossary.css
  css/states.css
```

加载顺序（base.html）：
```
1. style.css              → Layer 1（令牌 + Shell）
2. ui-primitives.css      → Layer 2（原子组件）
3. legacy-aliases.css     → Layer 3（别名）
4. {% block head_extra %} → Layer 4（页面特定）
```

---

## 二、各层职责

### Layer 1: `style.css`

**必须包含**:
- `:root { }` 中的 CSS 变量（primitive、semantic、component 令牌）
- Shell 布局骨架：`.shell`、`.app-shell`、`.main`、`.main-panel`
- Shell 区域：`.sidebar`、`.topbar`、`.content`、`.footer`、`.breadcrumb`
- Body class 切换规则（`.hide-left`、`.hide-right`、`.focus`）
- Session detail shell 别名：`.sd-shell`、`.sd-content`

**禁止**:
- 页面特定组件样式（图表、表格行、token cell、project cell 等）
- 按钮、徽章、tooltip 等共享组件样式
- 图表样式、legend、chart-group 等

### Layer 2: `css/ui-primitives.css`

**必须包含**:
- 可复用 UI 原子组件：`.btn`、`.badge`、`.tooltip`、`.popover`、`.toast`
- 共享布局组件：`.metric-card`、`.metric-grid`、`.data-table`、`.tokenbar`
- 分页：`.pagination`
- 图标按钮：`.icon-button`

**禁止**:
- Shell 布局（sidebar、topbar、content、footer）
- CSS 变量定义（仅可引用 style.css 中的变量，可新增组件 token）
- 页面特定样式

### Layer 3: `css/legacy-aliases.css`

**必须包含**:
- 旧 class → 新 class 的映射（如 `.sd-agent-pill` → `.agent` badge）
- Additive 补充：link hover 颜色、badge variant 颜色、text utility

**铁律 — 禁止定义以下选择器的任何属性**:
```
.shell, .app-shell, .sidebar, .topbar, .content, .footer,
.breadcrumb, .topbar-breadcrumb, .topbar-actions, .main-panel,
.main, .sd-shell, .sd-content
```

**禁止**:
- 布局属性（display、grid-template、padding、height、width、margin）on shell selectors
- 新的页面特定样式
- 新的共享组件样式

### Layer 4: 页面 CSS

**必须包含**:
- 仅页面独有的组件样式
- 页面头部布局（`.page-head`、scope switch 等）
- 页面特有的表格变体、图表样式

**禁止**:
- Shell 选择器（见 Layer 3 铁律列表）
- CSS 变量定义
- 共享组件的基础样式（只能在已有组件上做 layout override，如 grid columns）

---

## 三、选择器所有权矩阵

| 选择器模式 | 归属文件 | 其他文件能否定义 |
|---|---|---|
| `:root { --* }` | style.css | ui-primitives.css 可新增组件 token |
| `.shell`, `.app-shell` | style.css | ❌ |
| `.sidebar` | style.css | ❌ |
| `.topbar` | style.css | ❌ |
| `.content` | style.css | ❌ |
| `.footer` | style.css | ❌ |
| `.breadcrumb`, `.topbar-breadcrumb` | style.css | Layer 3 可做 additive 补充（color、font-weight） |
| `.main-panel`, `.main` | style.css | ❌ |
| `.sd-shell`, `.sd-content` | style.css | ❌ |
| `.btn`, `.badge`, `.tooltip`, `.popover`, `.toast` | ui-primitives.css | ❌ |
| `.metric-card`, `.metric-grid` | ui-primitives.css | 页面 CSS 可做 layout override（如 grid columns） |
| `.data-table` | ui-primitives.css | 页面 CSS 可做 cell 变体 |
| `.sd-*` 别名 | legacy-aliases.css | — |
| `.page-head`, `.chart-card` | dashboard.css | — |
| `.sessions-page`, `.token-cell` | sessions-list.css | — |
| `.sd-hero`, `.trace-table` | session-detail.css | — |
| `.project-cell`, `.hero-metrics` | projects.css | — |
| `.agent-cell`, `.efficiency` | agents.css | — |
| `.glossary-table` | glossary.css | — |
| `.state-panel` | states.css | — |

---

## 四、文件命名规则

### 禁止创建的命名模式
- `*-v\d+.css`（如 dashboard-v16.css）
- `*-patch.css`（如 session-patch.css）
- `*-fix.css`
- `*-overlay.css`
- `*-reference.css`

### 正确命名
- 页面 CSS：`css/<page-name>.css`
- 共享组件：`css/<component>.css`（归入 ui-primitives.css）
- 别名：`css/legacy-aliases.css`（仅此一个）

---

## 五、自动化检查

运行 `python3 scripts/validate_css_ownership.py` 检查以下违规：

| 检查项 | 说明 |
|---|---|
| shell_selector_violation | Layer 3/4 文件中出现 shell 选择器 |
| forbidden_filename | 匹配禁止的文件名模式 |
| style_bloat | style.css 中出现页面特定选择器 |
| duplicate_selector | 同一选择器在多个非允许文件中定义 |

---

## 六、已废弃文件

| 文件 | 状态 | 说明 |
|---|---|---|
| `css/session-detail-timeline.css` | 待合并 | 内容与 session-detail.css 重复，应合并后停止引用 |
