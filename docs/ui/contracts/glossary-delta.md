# Token Glossary Delta 文档：生产模板 vs HIFI（当前快照）

> 对比源：`src/session_browser/web/templates/glossary.html`（生产，基于 base.html）
> vs `/Users/zhehan/Downloads/feipi-session-browser-hifi-integrated-v1/pages/token-glossary.html`（HIFI）
> T153 更新，2026-05-21
> 注：本快照反映当前生产状态（已包含 T156 .page-head + T157 .metric-grid）。

---

## 1. 已完成迁移（无需再改）

| # | HIFI 元素 | 生产状态 | 说明 |
|---|---|---|---|
| D1 | `.page-head` + `<h1>` + subtitle | 已迁移 | 第 22-25 行 |
| D2 | `.metric-grid` 含 4 个 `.metric-card` | 已迁移 | 第 28-61 行（值/文案略有差异，结构已对齐） |
| D3 | `.card.filter-card` 搜索栏 | 生产保留 | HIFI 无搜索，生产特有功能 |
| D4 | `#glossary-empty` 空状态 | 生产保留 | HIFI 无此组件 |
| D5 | `section.card.section` + `.section-head` + `.section-title` | 已迁移 | 结构类似，但 element tag 与 class 命名不同（见 S1） |
| D6 | `.table-wrap` 表格容器 | 已迁移 | 所有表格均使用 `.table-wrap` |
| D7 | info-icon on section-heads | 部分迁移 | section-head 有 `.info-icon` 但使用 emoji `info` + `title`；需对齐 HIFI 的 `ℹ️` 样式 |

---

## 2. 结构差异（待迁移/对齐）

| # | 差异点 | 生产模板 | HIFI 页面 | 优先级 |
|---|---|---|---|---|
| S1 | Section 容器 | `<section class="card section">` | `<article class="card section-card full-width">` | 低 |
| S2 | Badge 示范区 | Jinja2 宏渲染：`{{ status_success("成功") }}` 等 5 组 badge | `.legend-card` + `.legend-grid` + `.legend-block` + `.row`，纯 HTML `.badge.cc/.cx/.qd` + `.dot.*` | 高 |
| S3 | Token 组成表列结构 | 5 列：指标 / 定义 / 公式 / Anthropic / OpenAI（6 行含 subtotal） | 3 列：Term / 中文说明 / Example（6 行） | 高 |
| S4 | 派生指标表内容 | 7 行：Cache Reuse / Cache Write Ratio / Output Ratio / Tools/Round / Tokens/Round / Tokens/Minute / Failed/Session | 6 行：Total Tokens / Input-side / Cached / Cache Reuse / Output Rate / Tool Failure Rate | 中 |
| S5 | Provider Mapping 组织 | Provider→Model→4 字段列（4 行：Anthropic/qwen/OpenAI/Codex） | Canonical Field→Claude Code/Codex/Qoder→中文说明（6 行） | 高 |
| S6 | Round Signals 语义 | 6 行"信号检测规则"（failed tool / llm error / long tool / tool burst / high write / large input） | 6 行"术语定义"（Round / Step / Tool Batch / Subagent Run / Status / Duration） | 中 |
| S7 | 表格 class | `.data-table` + `data-table-enhanced` | `.glossary-table.wide-table`（`.mapping-table` for Provider） | 中 |
| S8 | section-title 内容 | `<span class="section-title">文本</span>` | `<div class="section-head"><h2>英文标题</h2><span class="info-icon">ℹ️</span></div>` | 低 |
| S9 | section-sub/desc | `<p class="section-sub">` | `<p class="section-desc">` 含 `<span class="sample-value">` | 中 |

---

## 3. 样式差异（CSS 需新增/对齐）

| # | 差异点 | 生产 CSS | HIFI CSS | 影响文件 |
|---|---|---|---|---|
| W1 | `.legend-card` | 不存在 | `.legend-card` + `.legend-grid` + `.legend-block` + `.legend-title` + `.row` + `.badge.cc/.cx/.qd` + `.dot.claude/.codex/.qoder/.total` | glossary.css |
| W2 | `.note-strip` | 不存在 | `.note-strip` + `.note-icon` flex 布局 | glossary.css |
| W3 | `.info-icon` on metric-label | 不存在 | `.metric-label .info-icon` hover tooltip | glossary.css / style.css |
| W4 | `.section-card` vs `.card.section` | `.card.section` | `.card.section-card.full-width` | glossary.css |
| W5 | `.glossary-table` | 无此 class | `.glossary-table` + `.wide-table` + `.mapping-table` | glossary.css |
| W6 | `.sample-value` / `.formula` / `.muted` 单元格样式 | 使用 `<code>` + `mono text-xs` | `.sample-value` / `.formula` / `.muted` 语义类 | glossary.css |
| W7 | `.term` 单元格样式 | 使用 `<span class="token-badge">` | `<td class="term">` 直接修饰 | glossary.css |
| W8 | Provider 字段单元格（Codex/Qoder 无值时） | 使用 `<span class="badge badge-muted">不上报</span>` | `<td class="muted">—</td>` | glossary.css |

---

## 4. 行为差异（JS/交互需新增/对齐）

| # | 差异点 | 生产 | HIFI | 影响文件 |
|---|---|---|---|---|
| B1 | info-icon on metric cards | 无 | `.metric-label .info-icon` 有 `title` 属性（中文 tooltip） | glossary.js / base.html |
| B2 | info-icon popover | 无 | hover tooltip + 点击 popover（详细说明） | glossary.js |
| B3 | 搜索过滤 | 有（150ms debounce + 匹配计数） | 无 | glossary.js -- 保留 |

---

## 5. Missing in production（HIFI 有但生产没有）

| # | 缺失项 | HIFI 实现 | 优先级 | 影响文件 |
|---|---|---|---|---|
| M1 | `.legend-card` 图例卡片 | Agent / Status / Token Segment 三组图例，含 `.badge.cc/.cx/.qd` + `.dot.*` 色点 | 高 | glossary.html + glossary.css |
| M2 | `.note-strip` 底部提示条 | `.note-icon` + 页面定位说明 | 中 | glossary.html + glossary.css |
| M3 | metric-label info-icon | 4 个 metric card 的 `.metric-label` 后跟 `<span class="info-icon" title="...">ℹ️</span>` | 中 | glossary.html |
| M4 | `.section-desc` 结构化描述 | 含 `<span class="sample-value">` 标记 | 中 | glossary.html + glossary.css |
| M5 | Qoder provider 支持 | Provider Mapping 中 Qoder 作为独立列 | 高 | glossary.html（表格内容） |
| M6 | Round Signals 术语化 | Round / Step / Tool Batch / Subagent Run / Status / Duration 术语定义 | 中 | glossary.html（表格内容） |
| M7 | Token Composition 简化为 3 列 | Term / 中文说明 / Example | 中 | glossary.html（表格内容） |
| M8 | Derived Metrics 内容更新 | Total Tokens / Input-side / Cached / Cache Reuse / Output Rate / Tool Failure Rate | 低 | glossary.html（表格内容） |

---

## 6. Production-only（生产有但 HIFI 没有 -- 保留不删）

| # | 独有点 | 生产实现 | 保留理由 |
|---|---|---|---|
| P1 | 搜索过滤栏 | `#glossary-search` + 150ms debounce + `#glossary-match-count` + `#glossary-empty` | 生产实用功能 |
| P2 | Token 概览卡片 | `.glossary__intro` 两段说明文本 | 有价值的补充说明 |
| P3 | 已知限制表 | 6 行限制说明 | 对用户使用有指导价值 |
| P4 | Session Anomalies 表 | 3 行 anomaly 检测规则 | 对 session 分析有参考价值 |
| P5 | Round Signals 检测规则 | 6 行 signal 触发规则 | 可合并到术语定义后作为补充 |
| P6 | qwen provider 行 | Provider Mapping 中 qwen 作为独立行 | 国内用户使用场景 |
| P7 | OpenAI provider 列 | Token 组成表中 OpenAI 列 | 跨 provider 对比有价值 |
| P8 | `data-table-enhanced` 表格增强 | 表格增强属性 | 生产增强功能 |

---

## 7. 迁移优先级与行动项

### 高优先级（结构/内容必须对齐）

| # | 行动项 | 涉及差异 | 文件 |
|---|---|---|---|
| A1 | 新增 `.legend-card` | S2/M1/W1 | glossary.html + glossary.css |
| A2 | Provider Mapping 重构为 Canonical→CC/CX/QD | S5/M5/W8 | glossary.html |
| A3 | Token Composition 表改为 3 列（Term/中文说明/Example） | S3/M7/W6/W7 | glossary.html |

### 中优先级（结构/交互优化）

| # | 行动项 | 涉及差异 | 文件 |
|---|---|---|---|
| A4 | 新增 `.note-strip` | M2/W2 | glossary.html + glossary.css |
| A5 | Round Signals 改为术语定义 | S6/M6 | glossary.html |
| A6 | metric-label 新增 info-icon | M3/W3/B1 | glossary.html |
| A7 | Derived Metrics 内容更新 | S4/M8 | glossary.html |
| A8 | `.section-sub` → `.section-desc` + `.sample-value` | S9/M4/W6 | glossary.html + glossary.css |

### 低优先级（可延后）

| # | 行动项 | 涉及差异 | 文件 |
|---|---|---|---|
| A9 | `section` → `article.section-card` | S1/W4 | glossary.html |
| A10 | `.data-table` → `.glossary-table` | S7/W5 | glossary.html + glossary.css |
| A11 | section-title 改为 `<h2>` | S8 | glossary.html |

---

## 8. 差异统计

| 分类 | 数量 |
|---|---|
| 已完成迁移 | 7 |
| 结构差异（待迁移/对齐） | 9 |
| 样式差异（CSS 需新增/对齐） | 8 |
| 行为差异（JS/交互） | 3 |
| Missing in production | 8 |
| Production-only（保留） | 8 |
| 高优先级行动项 | 3 |
| 中优先级行动项 | 5 |
| 低优先级行动项 | 3 |
