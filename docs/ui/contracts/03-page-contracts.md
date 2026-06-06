# 03 页面功能标准 v3

> 本文件是当前仓库页面功能标准要求。来源为
> `/Users/zhehan/Downloads/feipi-ui-page-spec-v3`，已按本仓库页面、组件和质量门体系整理。
>
> 本标准描述目标状态，不描述历史迁移过程；与旧版 HIFI/contract 条款冲突时，以本文件为准。

## 页面范围

当前标准页面包括：

- Dashboard：全局和单 agent 数据概览，包含 agent 列表和 Agent / Model Efficiency 表格。
- Sessions：session 完整检索和浏览列表。
- Session Detail：单个 session 的 trace、payload 和归因解释页，只包含 Trace / Payload 两个主 tab。
- Projects：project 列表。
- Project Detail：单个 project 详情。
- Agent Detail：单个 agent 深度统计，可通过选择器切换 agent。

不提供独立 Agents 列表页。Agent 列表信息归入 Dashboard，单个 agent 的深度信息归入 Agent Detail。

## 全局要求

- 所有页面使用同一套 Sidebar、Topbar、Page Head、Card、Table、Badge、Token Cell、Pagination、Tooltip、Modal 组件。
- 左侧 Sidebar 主导航只包含 Dashboard、Sessions、Projects；Agent Detail 通过 Dashboard 的 agent 表格和选择器进入。
- 主内容区域为高密度桌面 UI；不得为了视觉留白降低信息密度。
- 页面必须支持宽屏显示；宽屏多余空间优先分配给主内容列、标题列、图表和明细表，不分配给短字段列。
- 不允许出现 Dense / Comfortable / Columns / Export / Keyboard shortcuts 这类布局或工具按钮。
- 不允许同一 UI 组件存在多套同义 class、多套视觉风格或兼容别名样式。
- 不允许页面级 CSS 重定义共享组件样式。
- 不允许文本重叠；空间不足时使用横向滚动、截断和 tooltip。
- 不允许删除已有核心页面、核心表格字段、搜索、过滤、排序、分页、行跳转、行展开能力。
- 新 UI 可以重新组织信息，但不能减少用户原本可见和可操作的信息。
- 所有不可用数据必须显示来源或不可用原因，不允许静默隐藏。

## 共享组件标准

### Data Table

- 所有列表表格使用统一 `data table` contract。
- 表头排序按钮必须占满整个表头单元格宽度和高度；hover 区域与单元格一致。
- 文本列默认左对齐；数值列使用 tabular number。是否右对齐由页面指定，不得各页面随机处理。
- 列宽通过模板化单位定义，例如 `unit-1`、`unit-2`、`unit-fluid`；不得在模板里随机写 inline px。
- 短列可固定宽度；主列吸收额外宽屏空间。
- 表格必须支持横向滚动，不能压缩到文本重叠。

### Token Cell

- token cell 固定结构：左侧为总 token 数字，右侧为 tokenbar。
- tokenbar hover 显示 tooltip。
- tooltip 每行包含 dot 颜色、分类名称、token 数量、token 占比。
- tooltip 各列必须垂直对齐，数值使用 tabular font。
- token cell 内不得出现无意义的 `tokens` 文案或多行 legend。

### Badge

- Agent、Model、Provider、Status、Severity 都使用模板化 badge。
- 多个 agents 必须显示为多个独立 badge，不能合并成一个字符串 badge。

### Chart

- 图表必须有明确 x 轴、y 轴、legend、tooltip。
- 鼠标悬停必须展示可读的精确数值，不只展示颜色或总量。
- 堆叠图、折线图、柱状图的颜色语义必须跨页面一致。
- 图表不承担不清楚口径的数据展示；如果统计口径无法明确，应移动到更具体的页面或卡片。

## 交互标准

- 搜索框 focus 时必须显示清晰边框和轻量阴影。
- 搜索、过滤、排序、分页必须保持可见且可用。
- 表头点击排序必须可用；排序状态必须有图标和 aria 状态。
- 不允许用快捷键提示替代表面可见操作。
- tooltip 用于解释 tokenbar、图表点、异常信号和不可用原因。
- modal 或 drawer 用于 request/response attribution 和 payload preview。
- modal 必须有关闭按钮、Esc 关闭和点击遮罩关闭行为。
- Round header 和 round 任意非按钮区域点击时切换展开/收起。
- 不在每个 round 内展示独立 Expanded 按钮。
- 全局只保留一个 Expand all / Collapse all 切换按钮。

## Dashboard

### 目标

Dashboard 是全局运行状态页，也支持通过右上角选择器切换为单个 agent 视角。Dashboard 包含趋势、热点和 agent 列表信息，不展示完整 Sessions 明细。

### 标准要求

- 左侧显示页面标题 `Dashboard` 和一句说明。
- 右上角必须有数据范围选择器：All agents / Claude Code / Qoder / Codex。
- 范围选择器影响本页所有 KPI、trend、agent 表格和热点信号。
- 保留全局搜索入口和进入 Sessions 页的按钮。
- KPI 至少展示 Sessions、Input Tokens、Prompt Activity、Bug Signals。
- KPI 必须显示当前值和短说明，例如 7 日均值、cache 比例、今日增量。
- Trend 主卡片标题为 `Session Trend · Token Trend · Prompt Activity Trend` 或等价文案。
- Trend 主卡片支持 Day / Week / Month 切换。
- Day 展示最近 30 天，Week 展示最近 20 周，Month 展示最近 12 个月。
- 左侧 y 轴显示 trend 量，用于 sessions 与 prompt activity 这类 count 类型数据。
- token trend 可使用右侧 y 轴或标准化折线；如果使用标准化折线，tooltip 必须展示真实 token 数。
- trend 图与 trend 表格合计应占据卡片内容区域 80-95% 宽度；legend 和操作控件不得挤占主体展示空间。
- trend 表格位于图表右侧或下方，必须包含 Range point、Sessions、Tokens、Prompts、Cache、Failed tools。
- 鼠标悬停到图表点或表格记录时，悬浮层展示 dot 颜色、分类名称、真实数值、占比或变化率。
- 悬浮层每列垂直对齐，数值使用 tabular font。
- 保留三个 dashboard 级卡片：
  - Token Trend by Composition：展示 Fresh / Cache read / Cache write / Output 的趋势组成，必须有 tooltip。
  - Cache Health：展示 cache read ratio 和 fresh spike，cache health 是独立折线，不参与 token 堆叠。
  - Hot Sessions & Signals：展示异常 session 和严重等级。
- 不在 Dashboard 展示 Context Budget。Context Budget 的口径必须在 Session Detail 中按 session 或 round 明确展示。
- Dashboard 下方包含 All Agents 表：Agent、Provider、Sessions、Projects、Tokens、Tool calls、Failed、Last active。
- Dashboard 下方包含 Agent / Model Efficiency 表：Agent、Model、Sessions、Tokens、Avg/session、Fail。
- Agent 列中的 badge 使用标准 agent badge。
- 点击 agent 行进入 Agent Detail。

### 禁止项

- 不展示 All Sessions 表格。
- 不提供独立 Agents 列表导航入口。
- 不出现 Dense / Comfortable / Columns / Export / Keyboard shortcuts。

## Sessions

### 目标

Sessions 页面是完整 session 检索和浏览页，必须保留搜索、过滤、排序、分页和全部核心字段。

### 标准要求

- 页面标题为 `Sessions`。
- 搜索框支持按标题、project、agent、model、session id 搜索。
- 过滤器至少包含 agent、model、status 或 failure 状态。
- 表格必须包含核心列：Title、Project、Agent、Model、Tokens、Rounds、Tools、Subagents、Duration、Updated。
- Title 和 Project 为主列，吸收宽屏额外空间。
- Agent 使用标准 badge。
- Tokens 使用统一 token cell：左侧数字 + 右侧 tokenbar + hover tooltip。
- Rounds、Tools、Subagents、Duration、Updated 等短列固定模板宽度。
- 空间不足时横向滚动，不允许文本重叠。
- 分页使用当前产品风格：Prev、页码输入、总页数/总记录数、若干页码按钮、page size、Next。
- 必须覆盖默认状态、搜索框 focus 状态、tokenbar tooltip 状态。

### 禁止项

- 不出现 Dense / Comfortable / Columns / Export / Keyboard shortcuts。
- token cell 内不出现多行 legend 或无意义标签。

## Session Detail

### 目标

Session Detail 解释一个 session 的完整行为、payload 和归因。页面只保留 Trace / Payload 两个主 tab。

### Hero

Hero 展示 session 关键信息和诊断卡片：

- 基础 KPI：tokens、rounds、tools、subagents、duration、failure signals。
- Token Timeline + Cache Health：同一卡片内展示 token 趋势和 cache health。
- token 使用面积图或柱状图。
- cache health 是独立折线，位于图表上部或单独轴，不参与 token 堆叠。
- 支持左右双 y 轴：左轴为 token 数，右轴为 cache ratio / cache health。
- Tool Cost & ROI：必须展示工具调用次数和 token 量。
- Bug Mining & Regression Seeds：展示 bug signal 和可回归种子。
- Context Budget：展示 session 或当前 round 的上下文分布，必须注明统计口径。

### Tabs

- 只允许两个主 tab：Trace、Payload。

### Trace Tab

- Trace 上方保留筛选框；不展示 sidecar filter。
- Round 占据完整宽度。
- 不展示 Selected LLM calls、Round diagnostics。
- 只保留一个 Expand all / Collapse all 切换按钮。
- 每个 round 不展示 Expanded 按钮；点击 round 任意非按钮区域 toggle。
- Round 必须展示多种场景：有用户输入、有失败、有 tool batch、有 subagent、有 validation 或 test run。
- 每个 LLM call 和 subagent call 都支持 Request Attribution、Response Attribution、Payload 查看。
- Trace 文本不能大段裸露堆叠；长文本使用 preview、折叠、drawer 或 modal。

### Payload Tab

- 左侧为 LLM call / subagent call 选择器。
- 右侧展示被选 call 的 Request Attribution、Response Attribution、Raw Request、Raw Response。
- 能拿到原文时显示 raw preview；拿不到时显示 unavailable 原因和 precision/source。
- Attribution 内容不作为独立 tab 存在，归入 Payload 的 call detail。

### 禁止项

- 不存在独立 Attribution tab。
- 不存在独立 Insights tab。
- 不在页面中展示 All Sessions 表格。

## Projects

### 目标

Projects 页面使用与 Sessions 一致的列表风格，展示项目级统计和进入 Project Detail 的入口。

### 标准要求

- 表格核心列包括 Project、Agents、Sessions、Tokens、Tools、Failed、Last Active。
- Project 为主列，吸收宽屏额外空间。
- Agents 列如果有多个 agent，必须显示多个独立 badge。
- Tokens 使用统一 token cell。
- 短列固定模板宽度。
- 保留搜索、过滤、排序、分页。

### 禁止项

- 不出现 Dense / Comfortable / Columns / Export / Keyboard shortcuts。
- 不把多个 agent 合并成一个 badge。

## Project Detail

### 目标

Project Detail 展示单个项目的 session、agent、tokens、tools 和失败热点。

### 标准要求

- 顶部 KPI：Sessions、Agents、Tokens、Failed Tools。
- Project Token Trend：按 Day / Week / Month 切换。
- Agent Mix：展示项目内 agent 分布。
- Tool Hotspots：展示工具调用次数、token 量、失败率。
- 下方保留项目内 sessions 明细表，复用 Sessions 表格 contract。
- 可通过 agent badge 进入对应 Agent Detail。
- 可通过 session 行进入 Session Detail。
- 图表 hover 显示精确数值和百分比。

## Agent Detail

### 目标

Agent Detail 展示单个 agent 的深度统计，并支持通过选择器切换不同 agent。

### 标准要求

- 顶部右侧必须有 Agent 选择器。
- 切换 agent 会改变全页数据范围。
- 提供返回 Dashboard 的入口。
- KPI：Sessions、Models、Tokens、Failed Tools。
- Agent Activity Trend：展示 sessions、tokens、prompt activity。
- Model Mix：展示模型使用分布。
- Tool Distribution：展示工具调用次数、token 量、失败率。
- Failure Signals：展示常见失败模式。
- Model Efficiency Detail：展示 Avg input、Avg output、Cache read、Tool calls/session、Notes。
- Agent selector 支持切换 Claude Code / Qoder / Codex。
- 图表 hover 展示精确数值。
- 表格行支持进入 filtered Sessions 结果。

### 禁止项

- 不提供独立 Agents 列表页。
- 不重复 Dashboard 中的 All Agents 表，Agent Detail 只展示当前选中 agent 的详情。
