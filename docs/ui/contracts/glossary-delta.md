# Token Glossary Delta 文档：生产模板 vs HIFI

> 对比源：`src/session_browser/web/templates/glossary.html`（生产，基于 base.html）vs `/Users/zhehan/Downloads/feipi-session-browser-hifi-integrated-v1/pages/token-glossary.html`（HIFI）
> T153 生成，2026-05-21

---

## 1. 结构差异（Structural）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| S1 | 模板系统 | Jinja2 `{% extends "base.html" %}`，sidebar/topbar/footer 由 base 提供 | 独立 HTML，内嵌 `<div class="app">` + sidebar + topbar + footer | structural | 需要迁移 |
| S2 | 页面标题区 | 无独立 `.page-head`，直接以搜索卡片开头 | `.page-head` 含 `<h1>Token Glossary</h1>` + 定位说明 `<p>` | structural | 需要迁移 |
| S3 | 指标网格 | 不存在 | `.metric-grid` 含 4 个 `.card.metric-card`（Token Types / Derived Metrics / Provider Fields / Round Signals），各含 icon + label + info-icon + value + note | structural | 需要迁移 |
| S4 | 搜索/过滤栏 | `.card` + `.filter-bar`：`<input type="search" id="glossary-search">` + `#glossary-match-count` | 无搜索栏 | structural | 生产独有 |
| S5 | 空状态 | `#glossary-empty.empty-state.is-hidden` 简单文本 | 无空状态组件 | structural | 生产独有 |
| S6 | Badge 规范示范区 | `.card.glossary-table-section`：使用 Jinja2 宏渲染状态/Token/Agent/Tool/Anomaly badge 示例 | `.card.legend-card`：`.legend-grid` 含 Agent / Status / Token Segment 三组纯 HTML badge + dot 元素 | structural | 需要对齐 |
| S7 | Token 概览区 | `.card` + `.glossary__intro`：两段说明文本（输入端三部分 + Provider 差异） | 无独立概览卡片，内容分散到各 section | structural | 生产独有 |
| S8 | 术语表格结构 | `.card.glossary-table-section` + `.table-scroll` + `table.data-table[data-table-enhanced]`，共 6 个独立卡片 | `article.card.section-card.full-width` + `.table-wrap` + `table.glossary-table.wide-table`，共 4 个 section，每节含 `.section-head` + `.section-desc` | structural | 需要对齐 |
| S9 | 表格标题 | `.card-title` 内含 `<span.token-badge>` 或纯文本 | `.section-head` 含 `<h2>` + `.info-icon`（可交互说明入口） | structural | 需要对齐 |
| S10 | 表格描述文本 | `<p class="text-xs text-muted">` 在表格上方 | `<p class="section-desc">` 在 `.section-head` 下方，使用 `<span class="sample-value">` 标记示例值 | structural | 需要对齐 |
| S11 | 底部提示条 | 无 | `.note-strip`：`.note-icon` + 页面定位说明 | structural | 需要迁移 |
| S12 | 数据属性 | `data-table-enhanced` 表格增强 | 无 `data-table-enhanced` | structural | 需要对齐 |

---

## 2. 样式差异（Styling）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| W1 | CSS 引用 | 依赖 base.html 的 `style.css` + `ui-primitives.css` + `legacy-aliases.css` | `../assets/token-glossary/token-glossary.css` + `../assets/common-hifi-rules.css` | styling | 需要迁移 |
| W2 | 指标卡片样式 | 无 | `.metric-card` + `.metric-icon`（48px 圆角方块，4 色：purple/green/orange/blue）+ `.metric-label` + `.metric-value.mono` + `.metric-note` | styling | 需要迁移 |
| W3 | 图例卡片样式 | 无 | `.legend-card` + `.legend-grid` + `.legend-block` + `.legend-title` + `.row`（flex 排列 badge） | styling | 需要迁移 |
| W4 | Section 卡片样式 | `.card.glossary-table-section` + `mb-3` 间距 | `.card.section-card.full-width` + `.section-head` + `.section-desc` | styling | 需要对齐 |
| W5 | 表格容器 | `.table-scroll`（横向滚动容器） | `.table-wrap` | styling | 需要对齐 |
| W6 | 表格样式 | `.data-table`（base.html 提供） | `.glossary-table.wide-table` | styling | 需要对齐 |
| W7 | 术语单元格 | 使用 `<span class="token-badge">` 或 `<span class="badge">` 包裹 | `.term` 类直接修饰 `<td>` | styling | 需要对齐 |
| W8 | 示例值单元格 | `<code>` 标签 + `mono text-xs` | `.sample-value` 或 `.formula` 或 `.muted` | styling | 需要对齐 |
| W9 | info-icon 样式 | 无（生产模板无 info-icon） | `.info-icon`（hover tooltip + 点击 popover） | styling | 需要迁移 |
| W10 | Badge 样式（Agent） | 宏生成 `.badge.badge-claude`/`.badge-codex`/`.badge-qoder` | `.badge.cc`/`.badge.cx`/`.badge.qd` + `.dot.claude`/`.codex`/`.qoder` 圆点 | styling | 需要对齐 |
| W11 | Badge 样式（Status） | 宏生成 `.badge.badge-success`/`.badge-warning`/`.badge-error`/`.badge-info`/`.badge-muted` | `.badge.ok`/`.badge.warn`/`.badge.err`/`.badge.info` | styling | 需要对齐 |
| W12 | 底部提示条样式 | 无 | `.note-strip`：flex 布局，`.note-icon` + `.muted` 说明文本 | styling | 需要迁移 |

---

## 3. 行为差异（Behavioral）

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 | 状态 |
|---|---|---|---|---|---|
| B1 | 搜索交互 | `<input>` on input 即时过滤，150ms debounce，`filterGlossary()` 搜索所有表格行文本，显示匹配计数 `#glossary-match-count`，无匹配时显示 `#glossary-empty` | 无搜索功能 | behavioral | 生产独有 |
| B2 | 表格增强 | `data-table-enhanced` 属性（可能触发 JS 排序/高亮等增强） | 无表格增强 | behavioral | 生产独有 |
| B3 | info-icon 交互 | 无 | 每个 `.section-head` 和 `.metric-card` 的 `.info-icon` 有 `title` 属性（中文 tooltip），hover 显示 tooltip，点击打开详细说明 popover | behavioral | 需要迁移 |
| B4 | metric info 交互 | 无 | 每个 metric card 的 `.info-icon` 有 `data-action`（行为合同文档中定义），触发 toast 显示口径说明 | behavioral | 需要迁移 |
| B5 | 帮助/快捷键 | base.html 提供 `?` 和 `⌘` 按钮 | HIFI 有 `data-action="help"` 和 `data-action="shortcuts"` 按钮在 topbar | behavioral | base.html 已提供 |
| B6 | Settings | base.html 提供 Settings 入口 | HIFI 有 `data-action="settings"` 在 sidebar footer | behavioral | base.html 已提供 |
| B7 | 导航 | base.html 提供侧边导航 | HIFI 内嵌 sidebar nav，当前页 `.nav-link.active` 高亮 Token Glossary | behavioral | base.html 已提供 |

---

## 4. 数据绑定差异

| # | 差异点 | 生产模板 | HIFI 页面 | 分类 |
|---|---|---|---|---|
| D1 | 内容渲染 | 纯静态 HTML（无 Jinja2 变量循环，只有 badge 宏调用） | 纯静态 HTML（示例数据） | data |
| D2 | Badge 渲染 | Jinja2 宏：`{{ status_success("成功") }}` / `{{ agent_claude("CC") }}` / `{{ tool("Bash") }}` / `{{ anomaly("Long Duration", "warning") }}` | 纯 HTML：`<span class="badge ok">✅ Success</span>` / `<span class="badge cc"><span class="dot claude"></span>CC Claude Code</span>` | data |
| D3 | Token 组成表列结构 | 5 列：指标 / 定义 / 公式 / Anthropic / OpenAI | 3 列：Term / 中文说明 / Example | data |
| D4 | 派生指标表列结构 | 3 列：指标 / 公式 / 解读（7 行） | 3 列：Term / Formula / 中文说明（6 行） | data |
| D5 | Provider 映射表列结构 | 5 列：Provider / 模型 / Input Fresh / Cache Read / Cache Write / Output（4 行，含 qwen） | 5 列：Canonical Field / Claude Code / Codex / Qoder / 中文说明（6 行） | data |
| D6 | Provider 覆盖范围 | Anthropic / qwen（Anthropic 兼容）/ OpenAI / Codex | Claude Code / Codex / Qoder（无 qwen，新增 Qoder 列） | data |
| D7 | 已知限制表 | 6 行：Token 计数因 Provider 而异 / OpenAI/Codex 缺少 cache write / 部分解析失败 / 持续时间精度 / Codex token 估算 / 异常阈值经验值 | 无已知限制表 | data |
| D8 | Session Anomalies 表 | 3 行：Long Duration / Failed Tools / Cache Creation，含规则和严重度 | 无 Session Anomalies 表 | data |
| D9 | Round Signals 表 | 6 行：failed tool / llm error / long tool / tool burst / high write / large input，含规则和严重度 | 6 行：Round / Step / Tool Batch / Subagent Run / Status / Duration，含中文说明和示例 | data |
| D10 | Round Signals 语义 | 聚焦"信号检测规则"（什么条件触发 warning/critical） | 聚焦"术语定义"（Round/Step 是什么） | data |

---

## 5. Missing in production（HIFI 有但生产没有）

| # | 缺失项 | HIFI 实现 | 分类 | 状态 |
|---|---|---|---|---|
| M1 | `.page-head` 页面标题区 | `<h1>Token Glossary</h1>` + 定位说明 `<p>` | structural | 需要迁移 |
| M2 | `.metric-grid` 指标网格 | 4 个 metric card（Token Types 6 / Derived Metrics 6 / Provider Fields 12 / Round Signals 6） | structural | 需要迁移 |
| M3 | `.legend-card` 图例卡片 | Agent / Status / Token Segment 三组图例 | structural | 需要迁移 |
| M4 | `.info-icon` 说明入口 | 每个 section-head 和 metric-card 都有 info-icon + title tooltip | behavioral | 需要迁移 |
| M5 | `.note-strip` 底部提示条 | 页面定位说明（"本页先聚焦必要术语 + 统一口径"） | structural | 需要迁移 |
| M6 | `.section-desc` 结构化描述 | 带 `<span class="sample-value">` 标记的结构化描述文本 | styling | 需要对齐 |
| M7 | Provider Mapping 按 canonical 字段组织 | 左 Canonical → 中 Claude Code/Codex/Qoder → 右中文说明 | data | 需要对齐 |
| M8 | Provider 覆盖 Qoder | Qoder 作为独立 provider 列（`prompt_tokens` / `completion_tokens` / `cache_hit_tokens` / `reasoning_tokens`） | data | 需要迁移 |
| M9 | Round Signals 术语定义 | Round / Step / Tool Batch / Subagent Run / Status / Duration 的术语定义 | data | 需要对齐 |

---

## 6. Production-only（生产有但 HIFI 没有）

| # | 独有点 | 生产实现 | 分类 | 状态 |
|---|---|---|---|---|
| P1 | 搜索过滤栏 | `#glossary-search` + 150ms debounce + `#glossary-match-count` + `#glossary-empty` | behavioral | 生产独有 |
| P2 | Token 概览卡片 | `.glossary__intro` 两段说明文本（输入端三部分 + Provider 差异） | data | 生产独有 |
| P3 | 已知限制表 | 6 行限制说明（Token 编码差异 / cache write 缺失 / 解析失败 / 持续时间精度 / Codex 估算 / 异常阈值） | data | 生产独有 |
| P4 | Session Anomalies 表 | 3 行 anomaly 检测规则（Long Duration / Failed Tools / Cache Creation） | data | 生产独有 |
| P5 | Round Signals 检测规则 | 6 行 signal 触发规则（failed tool / llm error / long tool / tool burst / high write / large input） | data | 生产独有 |
| P6 | Provider 覆盖 qwen | qwen（Anthropic 兼容）作为独立 provider 行 | data | 生产独有 |
| P7 | Token 组成表 OpenAI 列 | Anthropic / OpenAI 两列对比 | data | 生产独有 |
| P8 | `data-table-enhanced` 表格增强 | 表格增强属性 | behavioral | 生产独有 |

---

## 7. 迁移优先级

| 优先级 | 项目 | 涉及差异 | 原因 |
|---|---|---|---|
| 高 | 页面标题区（S2/M1） | 新增 `.page-head` 含 `<h1>` + 定位说明 | 页面首屏标识，HIFI 标准结构 |
| 高 | 指标网格（S3/M2） | 新增 4 个 metric card（Token Types / Derived Metrics / Provider Fields / Round Signals） | 视觉首屏区域，HIFI 核心新增 |
| 高 | Badge 图例重构（S6/M3/W10/W11） | 从 Jinja2 宏渲染改为纯 HTML legend-card + dot 元素 | 视觉一致性，减少对宏的依赖 |
| 高 | 术语表格结构对齐（S8/S9/S10/W4/W5/W6/W7/W8/M6） | `.card.glossary-table-section` → `article.section-card` + `.section-head` + `.section-desc` | 结构统一，便于后续组件化 |
| 高 | Provider Mapping 重构（D5/D6/D8/M7/M8） | 从 Provider→字段 改为 Canonical→Claude Code/Codex/Qoder，新增 Qoder 列 | 数据口径统一，Qoder 是新 provider |
| 高 | info-icon 迁移（S9/M4/W9/B3/B4） | 每个 section-head 和 metric-card 新增 info-icon + tooltip/popover | HIFI 标准交互，提升可解释性 |
| 中 | Round Signals 语义重构（D9/D10） | 从"检测规则"改为"术语定义"（Round/Step/Tool Batch/Subagent Run/Status/Duration） | 术语页聚焦定义，规则可移至其他页面 |
| 中 | 底部提示条（S11/M5/W12） | 新增 `.note-strip` 页面定位说明 | 辅助说明，提升页面定位清晰度 |
| 中 | Token 组成表列重构（D3/D7） | 从 5 列（指标/定义/公式/Anthropic/OpenAI）改为 3 列（Term/中文说明/Example） | 与 HIFI 结构对齐 |
| 中 | 派生指标表列重构（D4） | 保留 3 列但内容从"指标/公式/解读"改为"Term/Formular/中文说明" | 术语表达统一 |
| 低 | 搜索过滤保留（S4/B1） | 生产独有搜索功能，HIFI 无 | 保留生产实用功能，不迁移到 HIFI 结构 |
| 低 | Token 概览保留（S7/P2） | 生产独有概览卡片 | 有价值的补充说明，可保留 |
| 低 | 已知限制表保留（P3） | 6 行限制说明 | 对用户使用有指导价值 |
| 低 | Session Anomalies 表保留（P4） | 3 行 anomaly 规则 | 对 session 分析有参考价值 |
| 低 | Round Signals 检测规则保留（P5） | 6 行 signal 规则 | 可合并到术语定义后作为补充 |
| 低 | qwen provider 保留（P6） | qwen 作为独立 provider 行 | 国内用户使用场景需要 |
| 低 | data-table-enhanced 保留（P8/B2） | 表格增强属性 | 生产增强功能，不影响结构 |

---

## 8. 差异统计

| 分类 | 数量 |
|---|---|
| 结构差异（Structural） | 12 |
| 样式差异（Styling） | 12 |
| 行为差异（Behavioral） | 7 |
| 数据绑定差异（Data） | 10 |
| **总计** | **41** |
| Missing in production（HIFI 有但生产没有） | 9 |
| Production-only（生产有但 HIFI 没有） | 8 |
| 需要迁移的 P0/P1 任务 | 6（页面标题区、指标网格、Badge 图例、术语表格结构、Provider Mapping、info-icon） |
| 需要迁移的 P2 任务 | 4（Round Signals 语义、底部提示条、Token 组成表列、派生指标表列） |
| 需要保留的生产功能（P3） | 6（搜索过滤、Token 概览、已知限制表、Session Anomalies、Round Signals 规则、qwen provider） |
