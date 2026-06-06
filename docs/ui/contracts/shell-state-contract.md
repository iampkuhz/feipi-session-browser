# Shell 状态契约

**版本**: P1 (2026-05-24)
**状态**: 记录

---

## Shell 状态

### 状态类（body 级别）

| 状态 | CSS 类 | 含义 |
|---|---|---|
| normal | (无) | 默认三栏布局：sidebar + main + inspector |
| hide-left | `body.hide-left` | 隐藏左侧 sidebar |
| hide-right | `body.hide-right` | 隐藏右侧 inspector |
| focus | `body.focus` | 只保留 main 内容区 |

### Shell 类组合

| 类 | 作用 |
|---|---|
| `.shell` | 主 grid 容器 |
| `.phase1-shell` | Phase1 专用 shell，需要 override body state |
| `.no-inspector` | 标记没有 inspector 栏的页面 |

### Grid 定义位置

`css/shell.css` 中 `grid-template-columns` 在以下区域定义 shell 布局：
- `.shell` + body state 规则（统一在 body class 切换块中定义）
- `.phase1-shell` override（如有）

### 当前 grid 规则（desktop）

```css
/* normal */
.shell                  { grid-template-columns: var(--sidebar) minmax(0, 1fr) var(--inspector); }
.shell.no-inspector     { grid-template-columns: var(--sidebar) minmax(0, 1fr); }

/* hide-left */
body.hide-left .shell                  { grid-template-columns: minmax(0, 1fr) var(--inspector); }
body.hide-left .shell.no-inspector     { grid-template-columns: minmax(0, 1fr); }

/* hide-right */
body.hide-right .shell { grid-template-columns: var(--sidebar) minmax(0, 1fr); }

/* focus */
body.focus .shell       { grid-template-columns: minmax(0, 1fr); }
```

---

## 合同目标

### 边界规则

1. **shell grid 只能在 shell 层定义**：`grid-template-columns` 对 `.shell` / `.phase1-shell` 的定义只能在 `shell.css` 中出现。

2. **page CSS 不得定义 shell grid-template-columns**：`session-detail.css`、`dashboard.css` 等页面 CSS 不得对 `.shell`、`.phase1-shell` 设置 `grid-template-columns`。

3. **body 状态类只能控制布局状态，不得控制组件内部样式**：`body.hide-left`、`body.hide-right`、`body.focus` 只能影响 shell grid 的 column visibility，不得影响组件内部样式。

4. **responsive 断点需要完整状态矩阵**：每个断点下需要确认 4 种 body 状态（normal / hide-left / hide-right / focus）的表现。
