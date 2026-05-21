# 05 Icon Behavior Detailed

> 本文档从 `05-button-icon-behavior.md` 提取纯图标规则，并补充 HiFi 与生产环境的完整图标清单及差距分析。

## 全局图标规则（摘自 05-button-icon-behavior.md）

### 图标行为表要求

每个页面必须有一份图标行为表，字段：

```text
icon / location / semantic meaning / decorative-or-action / expected behavior / size class
```

### 图标尺寸分级

| 尺寸类 | 范围 | 典型用途 |
|---|---|---|
| nav icon | 18–20px | 侧边栏导航项前的圆点图标 |
| metric/card icon | 20–24px | 指标卡片、KPI 区域图标 |
| inline action icon | 14–16px | 行内操作、筛选芯片关闭按钮 |

### 常用图标预期行为

- Settings：打开 settings drawer/panel。
- Info icon：打开就地说明 popover。
- More icon：打开轻量 action menu。
- Sort icon：切换升序/降序/无序，显示 ↕→↓ 状态。
- Close/Dismiss icon（×）：关闭弹窗或清除筛选芯片。
- Toggle icon（›/⌄）：展开/折叠可收缩区域。
- Search icon（⌕）：搜索框内装饰性前缀。

---

## HiFi 图标清单

> 扫描范围：`docs/ui/hifi/` 下 28 个 HTML 文件。
> 扫描日期：2026-05-21

### 符号图标总览

HiFi 页面使用的 Unicode 符号共 9 种：

| 符号 | Unicode | 出现文件 | 语义 | 尺寸类 |
|---|---|---|---|---|
| ! | U+0021 | 26/28 文件 | 警告/错误标记（alert、badge、diag） | inline action |
| × | U+00D7 | 10 文件 | 关闭/移除（modal close、chip remove） | inline action |
| › | U+203A | 3 文件 | 展开指示器（toggle collapsed） | inline action |
| ⌄ | U+2304 | 2 文件 | 折叠指示器（toggle expanded） | inline action |
| ↕ | U+2195 | 8 文件 | 排序未激活（sort inactive） | inline action |
| ↓ | U+2193 | 3 文件 | 排序降序（sort descending active） | inline action |
| ⌕ | U+2315 | 2 文件 | 搜索图标（search input prefix） | inline action |
| ✓ | U+2713 | 1 文件 | 成功/通过标记 | inline action |
| ∆ | U+2206 | 3 文件 | 变更/差异标记（alert warn icon） | inline action |
| → | U+2192 | 3 文件 | 导航/跳转指示 | inline action |

### 图标类名清单

| 类名 | 文件 | 用途 |
|---|---|---|
| `.sort-icon` | `sessions_list_hifi_v3_no_hero.html` | 表头排序箭头容器 |
| `.sort-icon.active` | `sessions_list_hifi_v3_no_hero.html` | 当前激活排序列 |
| `.sessions-search__icon` | `sessions_list_hifi_v4_componentized.html` | 搜索框前置 ⌕ 符号 |

### 语义图标分布（按页面区域）

| 页面 | 区域 | 图标 | 含义 |
|---|---|---|---|
| hf_01 (Session Detail) | `.alert.critical .ico` | ! | 严重错误 |
| hf_01 (Session Detail) | `.alert.warn .ico` | ∆ | 警告 |
| hf_01 (Session Detail) | `.trace-row .toggle` | › / ⌄ | 展开/折叠 |
| hf_01 (Session Detail) | `.insp-close` | › | 关闭 inspector 面板 |
| sessions_list_v3 | `.th.sortable .sort-icon` | ↕ / ↓ | 表头排序 |
| sessions_list_v3/v4 | `.sessions-search__icon` | ⌕ | 搜索前缀 |
| v17/v18 session_detail | `.alert` / `.badge-err` | ! | 错误标记（密集使用） |
| v11/v12 session_detail | `.modal-close` | × | 关闭弹窗 |
| v15 session_browser | 多个 modal | × | 关闭弹窗 |
| gallery (hf_00) | `.kpi .v` | ✓ | 状态通过 |

### HiFi 独有图标

以下图标**仅出现在 HiFi**，生产模板中未见：

- `∆` (U+2206) — 用于 alert warn 图标
- `✓` (U+2713) — 用于 KPI 成功标记
- `⌕` (U+2315) — 搜索框装饰（生产模板用 CSS 实现）
- `⌄` (U+2304) — 折叠状态指示

---

## 生产图标清单

> 扫描范围：`src/session_browser/web/templates/` 下 27 个 HTML/Jinja2 模板。
> 扫描日期：2026-05-21

### 符号图标总览

生产模板使用的 Unicode 符号共 6 种：

| 符号 | Unicode | 出现位置 | 语义 | 尺寸类 |
|---|---|---|---|---|
| ! | U+0021 | base.html, dashboard, sessions, projects, agent, project, error, badge, viewer, sessions_grid | 错误/警告标记 | inline action |
| × | U+00D7 | sessions_list_components.html | 筛选芯片关闭按钮 | inline action |
| → | U+2192 | base.html, project.html | 导航指示 | inline action |
| … | U+2026 | glossary.html | 省略号（文本截断） | — |
| ↑ | U+2191 | ui_primitives.html | 排序升序（active asc） | inline action |
| ↓ | U+2193 | ui_primitives.html | 排序降序（active desc / default） | inline action |
| ↕ | U+2195 | ui_primitives.html | 排序未激活 | inline action |
| ⚠ | U+26A0 | timeline.html | 错误节点图标 | metric/card |

### 图标类名清单

| 类名 | 文件 | CSS 定义 | 用途 |
|---|---|---|---|
| `.logo-icon` | `base.html` | 30×30px, gradient bg | 侧边栏 Logo 图标 |
| `.nav-dot` | `base.html`, `session.html` | 8×8px, border-radius:999px | 导航项前缀圆点 |
| `.sessions-search__icon` | `sessions.html` | 12px font-size | 搜索框 ⌕ 符号 |
| `.state-panel__icon` | `404.html` | — | 错误页图标容器 |
| `.state-panel__icon--error` | `error.html` | — | 错误页图标变体 |
| `.timeline-node__icon` | `timeline.html` | — | 时序节点图标（动态 class） |
| `{{ icon_cls }}` | `ui_primitives.html` | — | 排序图标（宏参数） |
| `.density-toggle` | `base.html` | — | 密度切换图标 |
| `.sig.err` / `.sig.warn` | `base.html` (round map) | — | 状态信号点 |

### 模板宏图标

| 宏/位置 | 文件 | 逻辑 |
|---|---|---|
| 排序图标 | `components/ui_primitives.html` | `↑` (asc active) / `↓` (desc active) / `↕` (inactive) |
| 节点图标 | `components/timeline.html` | `error` → `⚠️`，其他类型动态映射 |
| 关闭按钮 | `components/sessions_list_components.html` | `×` (aria-label="Remove ... filter") |

---

## 差距分析

### HiFi 有 / 生产无

| 图标 | HiFi 用途 | 生产状态 | 风险 |
|---|---|---|---|
| `∆` (U+2206) | alert warn 图标 | 生产无此符号，用 `⚠` 替代 | 低 — 语义等价 |
| `✓` (U+2713) | KPI 成功标记 | 生产无此符号，用 CSS badge 替代 | 低 |
| `⌄` (U+2304) | 折叠指示 | 生产无此符号，展开/折叠用 JS 控制 | 低 |
| `›` (U+203A) | 展开指示器 + inspector close | 生产无此符号 | 中 — inspector 关闭按钮缺失视觉一致性 |

### 生产有 / HiFi 无

| 图标 | 生产用途 | HiFi 状态 | 风险 |
|---|---|---|---|
| `⚠` (U+26A0) | timeline 错误节点 | HiFi 用 `!` | 低 — 语义等价 |
| `…` (U+2026) | glossary 省略号 | HiFi 未覆盖 glossary 页 | 低 |
| `↑` (U+2191) | 排序升序 | HiFi 只有 ↕/↓ | 中 — 升序状态 HiFi 未展示 |
| `.logo-icon` | 30×30px 渐变 logo | HiFi 用 `.logo-mark` (文字) | 低 |
| `.nav-dot` | 8px 导航圆点 | HiFi 也有 `.nav-dot` | 无 — 一致 |
| `.density-toggle` | 密度切换 | HiFi 未覆盖此功能 | 低 — HiFi 无此 UI |
| `.sig` | round map 状态信号 | HiFi 有 `.sig` | 无 — 一致 |

### CSS 尺寸规则差距

| 规则 | 合同要求 | HiFi 实现 | 生产实现 |
|---|---|---|---|
| nav icon 18–20px | 合同 | 无显式尺寸 class | `.nav-dot`: 8×8px（圆点，非图标） |
| metric/card icon 20–24px | 合同 | 无显式尺寸 class | 无统一定义 |
| inline action 14–16px | 合同 | 无显式尺寸 class | `.sessions-search__icon`: 12px |

**结论**：当前 HiFi 和生产环境均**未实现合同要求的图标尺寸分级**。符号图标依靠 Unicode 字符自身尺寸，无显式 font-size 或 class 控制。需后续在 CSS 中补充。

### 覆盖率总结

| 维度 | HiFi | 生产 | 一致性 |
|---|---|---|---|
| 符号图标种类 | 9 种 | 7 种 | 6 种重叠 |
| 图标类名数量 | 2 个 | 9 个 | 1 个重叠（`.sessions-search__icon`） |
| 有语义图标 | !, ∆, ×, ↕, ↓, ⌕, ✓, ›, ⌄, → | !, ×, →, …, ↑, ↓, ↕, ⚠ | — |
| 尺寸分级实现 | 无 | 部分（search__icon=12px, nav-dot=8px, logo-icon=30px） | 不一致 |
| 图标行为表 | 无（需补充） | 无（需补充） | 待办 |

### 已知风险

1. **图标尺寸分级未实现** — 合同定义了三级尺寸，但 CSS 中无对应规则。
2. **升序图标 ↥ 缺失于 HiFi** — HiFi 只展示 ↕ 和 ↓，未覆盖升序激活态。
3. **alert 图标不一致** — HiFi 用 `!`/`∆`，生产用 `!`/`⚠`。
4. **每个页面缺少图标行为表** — 合同要求但未在 HiFi 或生产中落实。
