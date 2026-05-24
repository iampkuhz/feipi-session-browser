# Shell 状态契约

**版本**: P0 (2026-05-24)
**状态**: 记录 + 后续重构

---

## 当前 Shell 状态

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
| `.app-shell` | `.shell` 的别名/兼容 |
| `.phase1-shell` | Phase1 专用 shell，需要 override body state |
| `.no-inspector` | 标记没有 inspector 栏的页面 |

### Grid 定义位置

`css/shell.css` 中 `grid-template-columns` 在以下区域定义 shell 布局：

- lines 10-80: `.shell` + body state 规则
- lines 82-110: `.app-shell` + body state 规则（aliases）
- lines 210-240: `.phase1-shell` override
- lines 320-360: 媒体查询中 body state override

`style.css` 中的 shell grid 已抽取至 `css/shell.css`（Task 05）。

### 当前 grid 规则（desktop）

```css
/* normal */
.shell                  { grid-template-columns: var(--sidebar) minmax(0, 1fr) var(--inspector); }
.shell.no-inspector     { grid-template-columns: var(--sidebar) minmax(0, 1fr); }

/* hide-left */
body.hide-left .shell                  { grid-template-columns: 0 minmax(0, 1fr) var(--inspector); }
body.hide-left .shell.no-inspector     { grid-template-columns: 0 minmax(0, 1fr); }

/* hide-right */
body.hide-right .shell { grid-template-columns: var(--sidebar) minmax(0, 1fr) 0; }

/* focus */
body.focus .shell       { grid-template-columns: 0 minmax(0, 1fr) 0; }
```

`.app-shell` 有相同规则（lines 296-305）。

---

## 当前风险

### 1. grid-template-columns 多处定义

`style.css` 中有超过 50 处 `grid-template-columns` 定义，分布在：
- shell 层（lines 272-1030, 9323-9339）
- 页面组件层（如 dashboard kpis、session table、project cards 等）
- 媒体查询层

### 2. specificity 竞争

- `.shell` (0,1,0) vs `.app-shell` (0,1,0) — 同级别别名
- `body.hide-left .shell` (0,2,0) vs `body.hide-left .app-shell` (0,2,0) — 同级别
- `.phase1-shell` override 需要更高 specificity
- 媒体查询中的 override 与 desktop 规则存在层叠

### 3. 页面 CSS 可能污染 shell grid

当前 `session-detail.css` 中有一些 `grid-template-columns` 定义属于页面组件级别，
但也有一些可能与 shell 布局产生交互。

---

## 合同目标

### 边界规则

1. **shell grid 只能在 shell 层定义**：`grid-template-columns` 对 `.shell` / `.app-shell` / `.phase1-shell` 的定义只能在 `style.css` 的 shell 层中出现。

2. **page CSS 不得定义 shell grid-template-columns**：`session-detail.css`、`dashboard.css` 等页面 CSS 不得对 `.shell`、`.app-shell`、`.phase1-shell` 设置 `grid-template-columns`。

3. **body 状态类只能控制布局状态，不得控制组件内部样式**：`body.hide-left`、`body.hide-right`、`body.focus` 只能影响 shell grid 的 column visibility，不得影响组件内部样式。

4. **responsive 断点需要完整状态矩阵**：每个断点下需要确认 4 种 body 状态（normal / hide-left / hide-right / focus）的表现。

---

## 后续重构前必须补充

在进行任何 shell 重构之前，必须先建立以下 DOM contract：

### 断点 × 状态矩阵

| 断点 | normal | hide-left | hide-right | focus |
|---|---|---|---|---|
| ≥1440px | ? | ? | ? | ? |
| 1024-1439px | ? | ? | ? | ? |
| 768-1023px | ? | ? | ? | ? |
| ≤767px | ? | ? | ? | ? |

每项需要有：
- 截图验证
- DOM structure contract（`getComputedStyle` 输出 `grid-template-columns` 值）
- `grid-template-areas` 对比（如果使用）

---

## Static Gate: 当前 P0 不检查

P0 阶段暂不实现 shell grid 静态检查，原因：
- 历史 shell grid 定义分散在 style.css 多处
- 需要先确定唯一权威来源后再建立 gate
- 标记为 P2 后续任务
