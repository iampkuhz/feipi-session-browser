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

## Agent Detail 页图标行为表（agent.html）

> 扫描范围：`src/session_browser/web/templates/agent.html`
> 扫描日期：2026-05-21
> 覆盖 T148：确保本页所有图标都有行为说明。

### 图标清单

共 11 种符号，分布在 header、metric cards、section headers、table headers、error/empty states。

| # | 符号 | Unicode | 出现位置（模板行号） | 语义 | 装饰或动作 | 预期行为 | 尺寸类 |
|---|---|---|---|---|---|---|---|
| 1 | `←` | U+2190 | L34 `.back-btn` | 返回上一页 | 动作 — 可点击 | 点击导航到 `/agents`；JS 拦截 `data-action="back"` 执行 `window.location.href` | inline action |
| 2 | `🤖` | U+1F916 | L38 `.agent-title .emoji` | Agent 身份标识（header） | 装饰 | 跟随 agent title 展示当前 agent 类型（Claude Code/Qoder/Codex） | metric/card |
| 3 | `🧾` | U+1F9FE | L50 `.metric-icon .emoji` | Sessions 指标图标 | 装饰 | 标识 Sessions 总量指标 | metric/card |
| 4 | `📁` | U+1F4C1 | L59 `.metric-icon .emoji` | Projects 指标图标 | 装饰 | 标识 Projects 数量指标 | metric/card |
| 5 | `⬇️` | U+2B07 | L68 `.metric-icon .emoji` | 输入方向（向下=输入） | 装饰 | 标识 Input-side Tokens 指标 | metric/card |
| 6 | `⬆️` | U+2B06 | L77 `.metric-icon .emoji` | 输出方向（向上=输出） | 装饰 | 标识 Output Tokens 指标 | metric/card |
| 7 | `♻️` | U+267B | L86 `.metric-icon .emoji` | 缓存复用 | 装饰 | 标识 Cache Reuse 比率指标 | metric/card |
| 8 | `⚠️` | U+26A0 | L95 `.metric-icon .emoji` | 失败警告 | 装饰 | 标识 Failed Tools 指标（红色 metric-icon） | metric/card |
| 9 | `ⓘ` | U+24D8 | L53,62,71,80,89,98,115,211 `.info-icon` | 指标/区域说明 | 动作 — 可点击 | 点击弹出 info-tooltip 浮层，展示计算口径；JS `data-action="info"` 处理 | inline action |
| 10 | `💡` | U+1F4A1 | L119 `.insight .emoji` | 洞察提示 | 装饰 | 跟随 insight badge 展示 "Most active model" 提示 | inline action |
| 11 | `↕` | U+2195 | L135-141, L236-242 `.sort-mark` | 排序未激活（默认） | 动作 — 跟随表头点击 | 点击 sortable th 后切换为 `↑`（升序）或 `↓`（降序）；JS `updateModelSortIndicators()` 处理 | inline action |

### 补充：通过宏传入的图标

以下图标通过 `ui_primitives.html` 宏渲染，不在 agent.html 中直接书写：

| 符号 | Unicode | 宏调用位置 | 语义 | 预期行为 |
|---|---|---|---|---|
| `⚠️` | U+26A0 | L24 `ui.error_state(icon='⚠️')` | 数据加载失败错误标记 | 装饰；配合 "刷新页面" 按钮使用 |
| `🤖` | U+1F916 | L307 `ui.empty_state(icon='🤖')` | 无 Session 数据空状态 | 装饰；配合 "返回 Agents" 按钮使用 |

### CSS 规则覆盖

| 图标类 | CSS 选择器 | 文件 | 规则 |
|---|---|---|---|
| emoji（metric card） | `.emoji` | `agents.css` L98-102 | `font-size: 16px; line-height: 1; display: inline-block` |
| info-icon | `.card.metric .info-icon` | `agents.css` L84-88 | `font-size: 14px; color: var(--text-subtle); cursor: help` |
| sort-mark | `.data-table th.sortable .sort-mark` | `agents.css` L476-480 | `font-size: 10px; color: #667085; margin-left: 6px` |
| insight emoji | `.insight .emoji` | `agents.css` L421-432（`.insight` 容器） | `display: inline-flex; align-items: center; gap: 7px` |
| back-btn arrow | `.back-btn`（内含 `←`） | `agents.css` L329-332 | `width: 36px; height: 36px`（按钮尺寸） |

### JS 行为覆盖

| 图标 | data-action | JS 处理位置（agents.js） | 行为 |
|---|---|---|---|
| `←` | `back` | L369-376 | 拦截点击，执行 `window.location.href` 导航 |
| `ⓘ` | `info` | L247-305 | 点击创建 `info-tooltip` 浮层，4 秒自动消失 |
| `↕` | 跟随 `th.sortable` `sort` | L396-466 | 切换排序方向，更新 `.sort-mark` 文本 |

### 覆盖率总结

| 维度 | 数量 | 状态 |
|---|---|---|
| 符号种类 | 11 种 + 2 种宏传入 | 全部有行为说明 |
| 装饰性图标 | 8 种（🤖×2, 🧾, 📁, ⬇️, ⬆️, ♻️, ⚠️, 💡） | CSS 定义尺寸和行为 |
| 动作性图标 | 3 种（←, ⓘ, ↕） | JS 绑定 data-action |
| 有 aria-hidden | 所有 `<span class="emoji" aria-hidden="true">` | 符合无障碍要求 |
| 有 title 属性 | 所有 `.info-icon` | 悬浮展示原生 tooltip |

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
