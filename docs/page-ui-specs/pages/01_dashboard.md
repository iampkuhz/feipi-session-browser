# Dashboard 页面规约

## 定位

Dashboard 是全局运行状态和单 agent 深度分析的统一入口。页面默认展示 `All agents` 聚合概览；当 agent scope 选择 Claude Code、Qoder、Codex 中任意一个时，页面切换为单 agent 深度分析状态，并承接原 Agent Detail 页面中仍有价值的模型、工具、失败信号、模型效率和当前 agent sessions 信息。

Dashboard 不再跳转到独立 Agent Detail 页面。所有 agent 汇总和单 agent 深度信息都在 Dashboard 内完成。

## 页面布局

### 页面骨架

- 路由固定为 `/` 和 `/dashboard`；模板固定为 `dashboard.html`。
- 页面使用统一 shell；Sidebar 当前项高亮 `Dashboard`。
- Page Head 左侧显示标题 `Dashboard`，副标题固定说明当前页面同时支持全局概览和单 agent 深度分析。
- Page Head 右侧固定放置 agent scope selector、时间粒度 segmented control、`View Sessions` 按钮。
- 页面主体从上到下固定为 5 个区块：
  1. KPI 区。
  2. Trend 总览区。
  3. Token 分析区。
  4. Scope 分支区。
  5. 状态和错误反馈区。
- `Hot Sessions & Signals` 从 Dashboard 中移除；页面不保留该卡片、该标题、该表格和该点击行为。

### KPI 区

- KPI 区固定为 6 张 metric card。
- 宽屏下固定 6 列；普通桌面宽度固定 3 列 2 行；每张卡高度一致。
- 每张 KPI card 固定为两层结构：
  - 第一层：一级指标 label、一级指标 value、单位、相对上次索引的变化提示。
  - 第二层：2 到 4 个二级指标，使用紧凑行展示，label 左对齐，value 右对齐。
- KPI 使用当前 agent scope 下的全部已索引数据重算；时间粒度 segmented control 不影响 KPI。
- 数值必须使用 tabular number；token 缩写保留一位小数；百分比保留一位小数。
- 二级指标必须有 tooltip，tooltip 固定说明定义、计算公式、统计范围。

固定 6 张 KPI card 如下：

1. `Projects`
   - 一级值：当前 scope 下出现过 session 的 project key 去重数。
   - 二级指标固定为 `Active 24h`、`Active 7d`、`New 7d`。
   - `Active 24h`：最近 24 小时内有 session event 的 project 去重数。
   - `Active 7d`：最近 7 个自然日内有 session event 的 project 去重数。
   - `New 7d`：first seen timestamp 落在最近 7 个自然日内的 project 去重数。
   - Projects 卡不展示 `Top Project`；最高频项目、项目贡献和项目内趋势归 Project Detail 展示。
2. `Sessions`
   - 一级值：当前 scope 下已索引 session 总数。
   - 二级指标固定为 `Today`、`7d Avg`、`Median Duration`、`Avg Rounds`。
   - `Today`：first user message timestamp 落在当前自然日内的 session 数。
   - `7d Avg`：最近 7 个自然日每日 session 数的算术平均值，保留一位小数。
   - `Median Duration`：当前 scope 下 session duration 的中位数；duration 使用最后一个 event timestamp 减去第一个 event timestamp。
   - `Avg Rounds`：当前 scope 下每个 session 的 LLM round 数平均值，保留一位小数。
3. `Total Tokens`
   - 一级值：`Fresh + Cache Read + Cache Write + Output` 的合计。
   - 二级指标固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
   - `Fresh`：模型输入侧新消耗 token 数，不含 cache read 和 cache write。
   - `Cache Read`：从缓存读取并计入输入侧的 token 数。
   - `Cache Write`：写入缓存并计入输入侧的 token 数。
   - `Output`：模型输出 token 数。
   - 四个二级指标的合计必须等于一级值；字段缺失时一级值显示可计算部分，tooltip 明确列出缺失字段。
4. `Prompt Activity`
   - 一级值：用户发起输入数量，按 user message 事件计数。
   - 二级指标固定为 `Assistant Turns`、`Tool Calls`、`Prompts / Session`。
   - `Assistant Turns`：assistant message 事件总数。
   - `Tool Calls`：tool call 事件总数，不区分成功和失败。
   - `Prompts / Session`：`User Prompts / Sessions`，sessions 为 0 时显示 `N/A`。
5. `Cache Read Ratio`
   - 一级值：`Cache Read / Input-side Tokens`，其中 `Input-side Tokens = Fresh + Cache Read + Cache Write`。
   - 二级指标固定为 `Eligible Sessions`、`P50 Session Ratio`、`Low-read Sessions`。
   - `Eligible Sessions`：`Input-side Tokens > 0` 的 session 数，也是 Cache Read Ratio 可参与计算的分母样本。
   - `P50 Session Ratio`：eligible sessions 的 per-session cache read ratio 中位数。
   - `Low-read Sessions`：eligible sessions 中 per-session cache read ratio 小于 20.0% 的 session 数。
   - Cache Read Ratio 卡不重复展示 token 总量；token 绝对值只在 Total Tokens 和 token 图表中展示。
6. `Failed Tools`
   - 一级值：failed tool result 总数。
   - 二级指标固定为 `Failure Rate`、`Affected Sessions`、`Repeated Failure Sessions`。
   - `Failure Rate`：`Failed Tools / Tool Calls`，tool calls 为 0 时显示 `N/A`。
   - `Affected Sessions`：failed tool result 数量大于 0 的 session 数。
   - `Repeated Failure Sessions`：failed tool result 数量大于 1 的 session 数。
   - Failed Tools 卡不展示 `Tool Calls` 原始总量，不展示最高频失败工具；工具调用总量归 Prompt Activity，工具分布归 Tool Distribution。

### Trend 总览区

- Trend 总览区固定为一个 section，section 内固定 3 张同级 trend card，顺序固定为 `Session Trend`、`Token Trend`、`Prompt Activity Trend`。
- 三张 trend card 不使用 tab 切换；三张卡必须同时可见。
- 每张 trend card 的内容布局固定为顶部标题栏加全宽图表，不渲染静态明细表。
- 每张 trend card 的标题栏右侧固定显示 `Latest` 和 `Range total` 两个紧凑 stat。
- 每张 trend card 的图表宽度占卡片内容宽度 100%；图表绘图区高度固定为 240px 到 280px。
- 每张 trend card 的图表左侧必须显示 y 轴标题，格式固定为 `Y-axis: <metric name> (<unit>)`。
- 每张 trend card 的所有 range point 细节都通过 `common.md` 的 `Chart Tooltip` 展示，不把每个 range point 的数值同时铺成表格。
- 时间粒度控制固定影响三张 trend card、Token 分析区和 all agents 占比柱状图。
- 时间粒度的数据窗口固定如下：
  - `Day`：最近 30 个自然日，x 轴标签格式 `MM-DD`。
  - `Week`：最近 20 个 ISO week，x 轴标签格式 `YYYY-Www`，tooltip 显示完整日期范围。
  - `Month`：最近 12 个自然月，x 轴标签格式 `YYYY-MM`。
- `Latest` stat 展示当前可见窗口最后一个 range point 的 y 轴真实值。
- `Range total` stat 展示当前可见窗口内所有 range point 的 y 轴真实值合计。
- Hover 图表点必须高亮当前 range point；tooltip 使用 `Chart Tooltip` 的 header、label、value、share 三列布局，并展示该点的 y 轴真实值、占比、辅助指标。

#### Session Trend

- 图表类型固定为纵向柱状图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 session count，从 0 开始。
- 图表 y 轴标题固定为 `Y-axis: Sessions (count)`。
- `All agents` scope 下，每个柱子按 agent 分段堆叠，分段顺序固定为 Claude Code、Qoder、Codex。
- 单 agent scope 下，每个柱子使用当前 agent 的单一颜色。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定展示 `Range point`、`Sessions`、`Share of visible range`、`Delta from previous point`、`Claude Code sessions`、`Qoder sessions`、`Codex sessions`、`Failed-tool sessions`。
- 单 agent scope 下 tooltip 中其它 agent 行不展示。
- tooltip 示例固定包含 `06-06 · Sessions 42 · Share 8.4% · Delta +6 · Failed-tool sessions 3`。

#### Token Trend

- 图表类型固定为折线图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 total tokens，从 0 开始。
- 图表 y 轴标题固定为 `Y-axis: Total Tokens (tokens)`。
- 折线只展示 `Total Tokens`；token 组成放在 `Token Trend by Composition` 卡片中展示。
- `All agents` scope 下 tooltip 必须展示三个 agent 的 token 贡献值和占比。
- 单 agent scope 下 tooltip 必须展示当前 agent 的 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局，token 行按 Fresh、Cache Read、Cache Write、Output 顺序展示。
- tooltip 固定展示 `Range point`、`Total Tokens`、`Share of visible range`、`Delta from previous point`、`Fresh`、`Cache Read`、`Cache Write`、`Output`、`Cache Read Ratio`。
- tooltip 示例固定包含 `2026-W23 · Total 2.4M · Fresh 520k · Read 1.3M · Write 180k · Output 400k · Cache 61.2%`。

#### Prompt Activity Trend

- 图表类型固定为纵向柱状图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 user prompt count，从 0 开始。
- 图表 y 轴标题固定为 `Y-axis: User Prompts (count)`。
- `All agents` scope 下，每个柱子按 agent 分段堆叠，分段顺序固定为 Claude Code、Qoder、Codex。
- 单 agent scope 下，每个柱子使用当前 agent 的单一颜色。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定展示 `Range point`、`User Prompts`、`Assistant Turns`、`Tool Calls`、`Prompts / Session`。
- `All agents` scope 下 tooltip 追加三个 agent 的 user prompt 贡献值和占比。
- tooltip 示例固定包含 `06-06 · User Prompts 318 · Assistant Turns 301 · Tool Calls 1,482 · Prompts / Session 7.6`。

### Token 分析区

Token 分析区固定为两张卡片，顺序固定为 `Token Trend by Composition`、`Cache Health`。宽屏下 `Token Trend by Composition` 占 2/3 宽度，`Cache Health` 占 1/3 宽度；普通桌面宽度下两张卡上下排列。

#### Token Trend by Composition

- 图表类型固定为堆叠面积图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 total tokens，从 0 开始。
- 堆叠层顺序从下到上固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
- 图表绘图区高度固定为 220px 到 260px。
- 卡片标题栏右侧固定显示 `Latest total` 和 `Range total`。
- legend 固定展示四个 token 类型，每个 legend 项显示当前可见时间窗口内的合计和占比。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局，token 行按 Fresh、Cache Read、Cache Write、Output 顺序展示。
- tooltip 固定展示 `Range point`、`Fresh`、`Cache Read`、`Cache Write`、`Output`、`Total Tokens`，每一项都显示数量和占比。
- 该卡不渲染配套明细表；分段数量、占比、delta 全部通过 legend 和 tooltip 展示。
- tooltip 示例固定包含 `06-06 · Fresh 520k · Read 1.3M · Write 180k · Output 400k · Total 2.4M`。

#### Cache Health

- Cache Health 不再展示两条互补折线。
- 图表类型固定为单折线图加异常标记。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 `Cache Read Ratio`，范围固定为 0% 到 100%。
- 折线只显示 `Cache Read Ratio`。
- Fresh spike 使用图表点上的红色三角标记展示，不再作为第二条折线展示。
- Fresh spike 判定规则固定为：当前 range point 的 Fresh tokens 大于 `max(1.8 × rolling median fresh tokens, rolling median fresh tokens + 2 × MAD)`。
- Fresh spike 的 rolling window 固定为 Day 最近 7 点、Week 最近 4 点、Month 最近 3 点；历史点不足时 Fresh spike 显示 `N/A`。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定展示 `Range point`、`Cache Read Ratio`、`Input-side Tokens`、`Fresh`、`Cache Read`、`Cache Write`、`Fresh Spike`。
- 卡片标题栏右侧固定显示 `Latest ratio`、`Lowest ratio`、`Fresh spikes` 三个紧凑 stat。
- 该卡不渲染配套明细表；每个点的 Input-side Tokens、Fresh spike 阈值、Fresh spike 判定结果全部通过 tooltip 展示。
- tooltip 示例固定包含 `06-06 · Cache Read Ratio 61.2% · Input-side 2.0M · Fresh Spike Yes · Fresh 720k > threshold 510k`。

### Scope 分支区

- Scope 分支区根据 agent scope 渲染两套互斥内容。
- agent scope 为 `All agents` 时，只渲染 All agents 模式内容。
- agent scope 为 Claude Code、Qoder、Codex 中任意一个时，只渲染单 agent 模式内容。

#### All agents 模式：Agent Contribution Comparison

- `Agent Contribution Comparison` 固定展示在 Token 分析区下方。
- 该区固定包含 3 张同级柱状图卡片，顺序固定为 `Session Share`、`Token Share`、`Prompt Activity Share`。
- 每张卡的图表类型固定为 100% 横向堆叠柱状图。
- 每张卡只展示一根柱子；柱子分段固定为 Claude Code、Qoder、Codex。
- x 轴固定为 0% 到 100%；y 轴固定显示当前指标名称。
- 每个分段内部显示 agent 名称和占比；分段宽度不足 56px 时只显示占比，agent 名称移入 tooltip。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定展示 agent 名称、当前指标绝对值、当前指标占比、当前指标全体合计。
- 三张图使用同一套 agent 颜色，颜色顺序固定为 Claude Code、Qoder、Codex。
- 该区不渲染配套明细表；绝对值、占比、全体合计通过 tooltip 展示。
- 三张柱状图下方固定展示一句 scope summary，格式为 `Dominant: <agent> leads sessions, <agent> leads tokens, <agent> leads prompts`。

#### All agents 模式：All Agents

- `All Agents` 表固定展示在 `Agent Contribution Comparison` 下方。
- 表格列固定为 `Agent`、`Sessions`、`Tokens`、`Prompt Activity`、`Projects`、`Failure`、`Last Active`。
- 表格固定展示 Claude Code、Qoder、Codex 三行。
- `Tokens` 单元格必须使用 token cell：总量数字、tokenbar、tooltip 中的 Fresh、Cache Read、Cache Write、Output。
- 点击 agent 行后不跳转到 Agent Detail；点击行为固定为把 Dashboard agent scope 切换到该 agent。
- 行内 `View Sessions` 操作跳转到 `/sessions?agent=<agent>`。
- 列含义和示例：
  - `Agent`：agent badge；示例值 `Claude Code`。
  - `Sessions`：该 agent session 总数加 session share；示例值 `842 · 65.6%`。
  - `Tokens`：该 agent total tokens 加 token share；示例值 `31.2M · 72.9%`，tooltip 展示四类 token 分段。
  - `Prompt Activity`：该 agent user prompt 数加 prompt share；示例值 `5,480 · 61.4%`。
  - `Projects`：该 agent 覆盖的 project key 去重数；示例值 `18`。
  - `Failure`：failed tool count 加 failure rate；示例值 `108 · 2.8%`。
  - `Last Active`：该 agent 最新 session event 距当前时间；示例值 `2 min ago`。

#### All agents 模式：Agent / Model Efficiency

- `Agent / Model Efficiency` 表固定展示在 `All Agents` 下方。
- 表格列固定为 `Agent`、`Model`、`Sessions`、`Tokens / Session`、`Cache Read`、`Failure`。
- 表格每行代表一个 agent + model 组合。
- 排序固定为 `Sessions` 降序。
- model 缺失时显示 `Unknown model`。
- 点击表格行跳转到 `/sessions?agent=<agent>&model=<model>`。
- 列含义和示例：
  - `Agent`：agent badge；示例值 `Codex`。
  - `Model`：模型名称；示例值 `gpt-5.1-codex`。
  - `Sessions`：该 agent + model 组合的 session 数；示例值 `173`。
  - `Tokens / Session`：平均 total tokens per session，括号内展示 input/output 摘要；示例值 `26.6k · in 24.8k / out 1.8k`。
  - `Cache Read`：该组合的 aggregate cache read ratio；示例值 `54.1%`。
  - `Failure`：failed tools per session；示例值 `0.08 / session`。

#### 单 agent 模式：Agent Deep Dive

- 单 agent 模式固定展示 `Agent Deep Dive` 区。
- `Agent Deep Dive` 承接原 Agent Detail 的有效信息；不展示独立 Agent selector 卡片，因为 Page Head 已经提供 agent scope selector。
- `Agent Activity Trend` 不单独重复展示；它由 Trend 总览区的三张 trend card 承接。
- `Agent Deep Dive` 固定包含 5 个组件，顺序固定为 `Model Mix`、`Tool Distribution`、`Failure Signals`、`Model Efficiency Detail`、`Agent Sessions`。

#### 单 agent 模式：Model Mix

- `Model Mix` 固定展示为一张横向柱状图，不渲染配套明细表。
- 图表类型固定为横向柱状图。
- y 轴显示 model 名称；x 轴显示 tokens。
- 每个柱子右侧显示 token 占比和 session 数。
- 柱子排序固定为 tokens 降序。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定展示 `Model`、`Sessions`、`Session Share`、`Tokens`、`Token Share`、`Cache Read Ratio`、`Failed/session`。
- tooltip 示例固定包含 `claude-sonnet-4.5 · Sessions 641 · Tokens 23.8M · Token Share 76.3% · Cache 63.0% · Failed 0.12/session`。

#### 单 agent 模式：Tool Distribution

- `Tool Distribution` 固定展示为一张横向柱状图，不渲染配套明细表。
- 图表类型固定为横向柱状图。
- y 轴显示 tool name；x 轴显示 tool calls。
- 柱子排序固定为 calls 降序。
- 工具名缺失时显示 `Unknown tool`。
- 每个柱子右侧显示 call share 和 failure rate。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定展示 `Tool`、`Calls`、`Call Share`、`Tokens`、`Token Share`、`Failed`、`Failure Rate`。
- tooltip 示例固定包含 `Bash · Calls 1,840 · Call Share 20.6% · Tokens 5.4M · Failed 76 · Failure 4.1%`。

#### 单 agent 模式：Failure Signals

- `Failure Signals` 只在单 agent 模式展示。
- 该卡片展示当前 agent 的聚合异常信号，不展示跨 agent 热点 session。
- 表格列固定为 `Signal Type`、`Severity`、`Count / Rate`、`Representative Session`、`Last Seen`。
- `Signal Type` 候选固定为 `Tool failure`、`Cache read drop`、`Fresh spike`、`Long duration`、`Unknown model`。
- `Severity` 候选固定为 `High`、`Medium`、`Low`。
- `Representative Session` 点击进入 Session Detail。
- 同一 signal type 有多个 session 时，代表 session 固定选择 `Last Seen` 最新的一条。
- 列含义和示例：
  - `Signal Type`：聚合信号类型；示例值 `Cache read drop`。
  - `Severity`：严重级别；示例值 `High`。
  - `Count / Rate`：命中次数加当前 agent 范围内的占比；示例值 `18 · 2.1%`。
  - `Representative Session`：该信号最新代表 session；示例值 `fde647cf`。
  - `Last Seen`：该信号最新出现时间；示例值 `16 min ago`。

#### 单 agent 模式：Model Efficiency Detail

- `Model Efficiency Detail` 表固定展示在三张分析卡下方。
- 表格列固定为 `Model`、`Sessions`、`Avg Tokens`、`Cache / Tools`、`Failure`、`Notes`。
- 表格排序固定为 `Sessions` 降序。
- `Notes` 只显示固定标签：`Primary model`、`High input`、`Low cache reuse`、`High failure`、`Low sample`、`Normal`。
- 每行点击跳转到 `/sessions?agent=<agent>&model=<model>`。
- 列含义和示例：
  - `Model`：模型名称；示例值 `opus-4.1`。
  - `Sessions`：该 model 在当前 agent 下的 session 数；示例值 `42`。
  - `Avg Tokens`：平均 input 和平均 output；示例值 `in 61.4k · out 2.4k`。
  - `Cache / Tools`：cache read ratio 加 tool calls per session；示例值 `54.0% · 14.2 tools/session`。
  - `Failure`：failed tools per session；示例值 `0.21 / session`。
  - `Notes`：固定标签；示例值 `High input`。

#### 单 agent 模式：Agent Sessions

- `Agent Sessions` 表固定展示当前 agent 范围内的 sessions。
- `Agent Sessions` 使用通用 `Data Table` 组件。
- 表格列固定为 `Title`、`Project`、`Model`、`Tokens`、`Rounds`、`Tools`、`Subagents`、`Duration`、`Process Time`、`Failure`、`Updated`。
- 默认排序固定为 `Updated` 降序。
- 可排序列固定为 `Tokens`、`Rounds`、`Tools`、`Subagents`、`Duration`、`Process Time`、`Failure`、`Updated`。
- 分页固定每页 20 条。
- `Tokens` 单元格必须使用 token cell。
- 点击 project 单元格进入 Project Detail。
- 点击 session 行进入 Session Detail。
- `View Sessions` 按钮跳转到 `/sessions?agent=<agent>`，作为查看同一 agent 完整 session 列表的入口。
- 列含义和示例：
  - `Title`：session title，空值时使用 session id 后 8 位；示例值 `Fix dashboard cache chart`。
  - `Project`：project key；示例值 `feipi-session-browser`。
  - `Model`：主模型名称；示例值 `claude-sonnet-4.5`。
  - `Tokens`：total tokens，tooltip 展示 Fresh、Cache Read、Cache Write、Output；示例值 `184k`。
  - `Rounds`：assistant round 数；示例值 `18`。
  - `Tools`：tool call 数；示例值 `42`。
  - `Subagents`：subagent run 数；示例值 `2`。
  - `Duration`：通用时间指标 `Duration`；示例值 `36m`。
  - `Process Time`：通用时间指标 `Process Time`；示例值 `9m 42s`。
  - `Failure`：failed tool result 数；示例值 `3 failed`。
  - `Updated`：最后 event 时间；示例值 `2 min ago`。

## 控件和候选项

### Agent scope selector

- selector label 固定为 `Scope`。
- 候选项固定为 `All agents`、`Claude Code`、`Qoder`、`Codex`。
- 默认选中 `All agents`。
- 切换 scope 后，KPI 区、Trend 总览区、Token 分析区、Scope 分支区全部重算。
- scope 必须反映到 URL 查询参数 `agent`：
  - `All agents` 使用 `/dashboard`，不写 `agent` 参数。
  - Claude Code 使用 `/dashboard?agent=claude-code`。
  - Qoder 使用 `/dashboard?agent=qoder`。
  - Codex 使用 `/dashboard?agent=codex`。

### 时间粒度 segmented control

- 候选项固定为 `Day`、`Week`、`Month`。
- 默认选中 `Day`。
- 切换时间粒度只影响 Trend 总览区、Token 分析区、`Agent Contribution Comparison`。
- 时间粒度必须反映到 URL 查询参数 `grain`，取值固定为 `day`、`week`、`month`。

### 操作按钮

- `View Sessions` 按钮固定存在。
- 当前 scope 为 `All agents` 时，按钮跳转到 `/sessions`。
- 当前 scope 为单 agent 时，按钮跳转到 `/sessions?agent=<agent>`。
- 页面不提供全局搜索框。
- 页面不提供 Dashboard 内搜索框。
- 页面不提供跳转 Agent Detail 的按钮。

## 文字内容

- 页面标题固定为 `Dashboard`。
- KPI label 固定为 `Projects`、`Sessions`、`Total Tokens`、`Prompt Activity`、`Cache Read Ratio`、`Failed Tools`。
- Trend 标题固定为 `Session Trend`、`Token Trend`、`Prompt Activity Trend`。
- Token 分析卡标题固定为 `Token Trend by Composition`、`Cache Health`。
- All agents 模式标题固定为 `Agent Contribution Comparison`、`All Agents`、`Agent / Model Efficiency`。
- 单 agent 模式标题固定为 `Agent Deep Dive`、`Model Mix`、`Tool Distribution`、`Failure Signals`、`Model Efficiency Detail`、`Agent Sessions`。
- 空态文案必须说明未索引数据，并提供运行 scan 和查看 Sessions 两个下一步。

## 数据指标与口径

### Agent 和 provider

- agent 候选固定为 Claude Code、Qoder、Codex。
- provider 映射固定为：
  - Claude Code：`Anthropic`
  - Qoder：`Qoder`
  - Codex：`OpenAI`
- 未能映射到固定候选的 agent 不进入 Dashboard 主指标；该类数据在 tooltip 中显示为 `Excluded unknown agent data` 并给出数量。

### Token

- `Input-side Tokens = Fresh + Cache Read + Cache Write`。
- `Total Tokens = Fresh + Cache Read + Cache Write + Output`。
- `Cache Read Ratio = Cache Read / Input-side Tokens`。
- token 类型颜色固定且全页面一致：
  - Fresh：蓝色。
  - Cache Read：绿色。
  - Cache Write：紫色。
  - Output：橙色。

### Prompt activity

- `User Prompts` 按 user message 事件计数。
- `Assistant Turns` 按 assistant message 事件计数。
- `Tool Calls` 按 tool call 事件计数。
- `Prompts / Session = User Prompts / Sessions`。

### Failure

- `Failed Tools` 只统计明确失败的 tool result。
- warning、skipped、cancelled 不计入 failed tool result。
- `Affected Sessions` 统计 failed tool result 数量大于 0 的 session。
- `Repeated Failure Sessions` 统计 failed tool result 数量大于 1 的 session。
- `Failed/session = Failed Tools / Sessions`。

## 交互逻辑

- 切换 agent scope 后，全页所有数值和表格必须同步更新；不得保留旧 scope 的局部数据。
- 切换时间粒度后，KPI 不变，Trend 总览区、Token 分析区、`Agent Contribution Comparison` 更新。
- hover 任意图表点展示真实数值和占比；tooltip 使用 `common.md` 的 `Chart Tooltip` 布局，不展示归一化后的内部绘图值。
- hover 图表 legend 时，高亮对应序列，非对应序列降低透明度到 30%。
- hover tokenbar 时使用 `common.md` 的 `Chart Tooltip` 布局展示 Fresh、Cache Read、Cache Write、Output 的数量和占比。
- 点击 All agents 模式中的 agent 行切换 Dashboard scope，不进入新页面。
- 点击 model efficiency 行进入带 agent/model 参数的 Sessions。
- 点击 Agent Sessions 行进入 Session Detail。
- 图表无数据时显示卡片内空态，不渲染空坐标轴。

## 状态

- 无 session 数据：KPI 显示 0，Trend 总览区、Token 分析区和 Scope 分支区显示统一空态。
- 当前 scope 无数据：保留 scope selector，页面标题下显示当前 scope 无数据，所有图表卡显示空态。
- 当前时间粒度无数据：Trend 总览区和 Token 分析区显示该时间窗口无数据，KPI 继续显示当前 scope 全量数据。
- 指标无法计算：显示 `N/A`，tooltip 说明缺少字段、分母为 0、历史窗口不足中的具体原因。
- 数据加载失败：展示错误状态，不展示部分旧数据。

## 禁止项

- 不展示 `Hot Sessions & Signals`。
- 不展示 All scope 下的 All Sessions 表格。
- 不展示 Context Budget；该口径只在 Session Detail 按 session 和 round 展示。
- 不提供全局搜索入口。
- 不提供 Dashboard 内搜索入口。
- 不提供独立 Agents 列表导航入口。
- 不提供 Agent Detail 跳转入口。
- 不出现 Dense、Comfortable、Columns、Export、Keyboard shortcuts。
