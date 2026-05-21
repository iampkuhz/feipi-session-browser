# 03 Page Contracts

## Dashboard

- 顶部 4 个等宽 metric cards。
- 3 张对齐柱状图：Session Trend / Token Trend / Prompt Activity Trend。
- 图表切换为 Day / Week / Month。
- Day=30d，Week=12week，Month=12month。
- Total 只在 tooltip 中显示，不作为灰色柱段渲染。
- 右上角 help/shell icon 不保留。

## Sessions List

- 搜索只支持 Session ID，必须明确提示。
- 表格列：Title / Project / Agent / Model / Tokens / Rounds / Tools / Duration / Updated。
- Token 展示使用 TokenBar + 短格式总量。
- 分页使用 prev + page input + next。

## Session Detail

- Trace / Calls 合并为 Trace workbench。
- 不要右侧 Inspector。
- Round 按时间纵向推进。
- 用户输入 round 使用 teal/green tone，展开后保持视觉 tone。
- LLM Call card 按钮为紧凑按钮组：Context / Response / Result。
- Payload modal 居中，宽 70vw，max 1120px，窄屏 92vw。
- complete tool result 不标红；failed 才红。

## Projects List

- 列表页优先表格，不使用 hero。
- 搜索 project name/path。
- Agents 按 canonical 颜色展示。
- 表格列：Project / Path / Agents / Sessions / Tokens / Tools / Health / Last Active。

## Project Detail

- 复用 Sessions list 表格视觉。
- 不再拆 Input/Cache R/Cache W/Output 多列；用 TokenBar。

## Agents List

- Agent overview + Agent/Model Efficiency 表。
- Agent 颜色：Claude Code purple、Codex green、Qoder orange。

## Agent Detail

- Header + 等宽 metrics + Model Breakdown + Sessions table。
- Sessions table 复用 shared data table 与 TokenBar。

## Token Glossary

- UI 术语用英文。
- 文档说明用中文。
- 保持 reference page 密度，不做大段 prose。

## State Pages

- 404 / error / empty state 使用统一 primitive。
- 按钮行为必须明确。

## HiFi 交叉验证补充

以下观察基于 HIFI_ROOT pages/ 与 docs/ 的实际实现，用于补充原始 contract。

### Dashboard

- HiFi 确认：`dashboard.html` 包含 4 个等宽 metric card（Projects / Sessions / Total Tokens / Failed Tools）。
- 三张图表（Session Trend / Token Trend / Prompt Activity Trend）共享 `scope-switch` 控件，使用同一 `stacked-chart` 组件。
- `Prompt Activity Trend` 子标题明确区分 "user-initiated inputs"，不等同于 Session Trend。
- 右上角无 help/shell icon，与 contract 一致。

### Sessions List

- HiFi 确认：`session-list.html` 搜索框 placeholder 为 "Search Session ID..."，明确限制为 Session ID。
- 除 Session ID 搜索外，HiFi 还提供了 Agent / Model / Project 三个 select 下拉筛选，以及 Apply / Clear All 按钮和 active filter chips。Contract 未覆盖这些筛选能力。
- 表格列实际为：Title / Project / Agent / Model / Tokens(Round/Tools/Duration/Updated）—— 与 contract 一致。TokenBar 嵌入 Tokens 列内。
- 分页使用 `prev + page-input + next`，首页不显示 prev（HiFi 样例为第一页，未显示 prev）。

### Session Detail

- HiFi 确认：Trace / Metrics / Payloads 为三个 tab 子页面，Trace 为主 workbench，无右侧 Inspector。
- Round 纵向推进，manual input round 使用 `class="round-row manual"`，teal/green tone 通过 CSS 实现。
- LLM Call card 按钮组为 Context / Response（紧凑 `btn btn-sm` 变体）。Result 按钮出现在 tool row 上，非 LLM Call card 自身。
- Payload modal：`.modal-backdrop > .modal` 居中展示，HiFi 未显式标注 70vw/max 1120px，由 CSS 控制。
- failed round：`class="round-row failed"` + `badge badge-err`；complete tool result 无红色，仅 failed 标红。

### Projects List

- HiFi 确认：`projects.html` 无 hero，以 metric-grid + filter + table 为主。
- 表格列实际为：Project(含 name + path) / Agents / Sessions / Tokens / Tools / Last Active。
  - **修正**：Path 不是独立列，而是 Project 单元格内的第二行。Health 不是独立列，而是 Tools 列内的 badge（如 "2 failed"）。
  - Contract 原文 "Project / Path / Agents / Sessions / Tokens / Tools / Health / Last Active" 应理解为 6 列表格，Path 和 Health 作为嵌入式子元素。
- Agents 使用 `badge cc/cx/qd` + 色点，按 canonical 颜色展示。

### Project Detail

- HiFi 确认：`project-detail.html` 复用 Sessions list 表格视觉（TokenBar + 相同列结构）。
- Token 不拆分为 Input/Cache R/Cache W/Output 多列，统一用 Tokens + TokenBar，与 contract 一致。

### Agents List

- HiFi 确认：`agents.html` 包含 metric grid（Active Agents / Sessions / Projects / Total Tokens）+ All Agents 对比表。
- Agent 颜色：Claude Code = CC/purple、Codex = CX/green、Qoder = QD/orange。与 contract 一致。
- 效率表（Agent/Model Efficiency）在 HiFi 中未单独出现，contract 提到但当前 HiFi 未覆盖。

### Agent Detail

- HiFi 确认：`agent-detail.html` 包含 Header（agent profile）+ 等宽 metric grid + Model Breakdown 表 + Sessions table。
- Sessions table 复用 TokenBar 和分页规则，与 contract 一致。
- Metric grid 实际为 6 个 card（Sessions / Projects / Input-side Tokens / Output Tokens / Cache Reuse / Failed Tools），多于 contract 暗示的 "等宽 metrics"。

### Token Glossary

- HiFi 确认：`token-glossary.html` 为紧凑 reference page，包含 Badge & Color Legend + 多个表格（Token Composition / Derived Metrics / Provider Mapping / Round Signals）。
- UI 术语英文、中文说明的规则严格执行（Term 英文列 + 中文说明列）。
- 无长段落 prose，符合 contract。

### State Pages

- HiFi 中各页面底部都有 `.state-strip` 空状态示例（no matching sessions / no projects），使用统一 icon + title + muted + action button 模式。
- 无专门 404 / error HiFi 页面；production 代码中 error 处理由 `_serve_error()` 路由负责。
