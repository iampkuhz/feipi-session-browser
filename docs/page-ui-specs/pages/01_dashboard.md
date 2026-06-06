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

固定 6 张 KPI card 如下：

1. `Projects`
   - 一级值：当前 scope 下出现过 session 的 project key 去重数。
   - 二级指标：`Active 24h`、`Active 7d`、`Top Project`。
   - `Top Project` 显示 session 数最高的 project key 和该 project 的 session 数；无数据时显示 `N/A`。
2. `Sessions`
   - 一级值：当前 scope 下已索引 session 总数。
   - 二级指标：`Today`、`7d Avg`、`With Failed Tools`、`Latest Active`。
   - `With Failed Tools` 统计 failed tool result 数量大于 0 的 session 数。
3. `Total Tokens`
   - 一级值：`Fresh + Cache Read + Cache Write + Output` 的合计。
   - 二级指标固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
   - 四个二级指标的合计必须等于一级值；字段缺失时一级值显示可计算部分，tooltip 明确列出缺失字段。
4. `Prompt Activity`
   - 一级值：用户发起输入数量，按 user message 事件计数。
   - 二级指标：`User Prompts`、`Assistant Turns`、`Tool Calls`、`Prompts / Session`。
   - `Prompts / Session` 使用 `User Prompts / Sessions` 计算，sessions 为 0 时显示 `N/A`。
5. `Cache Read Ratio`
   - 一级值：`Cache Read / (Fresh + Cache Read + Cache Write)`。
   - 二级指标：`Input-side Tokens`、`Fresh Ratio`、`Cache Write Ratio`、`Cache Read Tokens`。
   - `Fresh Ratio` 使用 `Fresh / Input-side Tokens`；`Cache Write Ratio` 使用 `Cache Write / Input-side Tokens`。
6. `Failed Tools`
   - 一级值：failed tool result 总数。
   - 二级指标：`Tool Calls`、`Failure Rate`、`Sessions With Failure`、`Top Failed Tool`。
   - `Failure Rate` 使用 `Failed Tools / Tool Calls`；tool calls 为 0 时显示 `N/A`。

### Trend 总览区

- Trend 总览区固定为一个 section，section 内固定 3 张同级 trend card，顺序固定为 `Session Trend`、`Token Trend`、`Prompt Activity Trend`。
- 三张 trend card 不使用 tab 切换；三张卡必须同时可见。
- 每张 trend card 的内容布局固定为左图右表：
  - 图表区域宽度占卡片内容宽度 68%。
  - 明细表区域宽度占卡片内容宽度 32%。
  - 卡片最小高度为 320px；图表绘图区高度固定为 220px 到 260px。
- 时间粒度控制固定影响三张 trend card、Token 分析区和 all agents 占比柱状图。
- 时间粒度的数据窗口固定如下：
  - `Day`：最近 30 个自然日，x 轴标签格式 `MM-DD`。
  - `Week`：最近 20 个 ISO week，x 轴标签格式 `YYYY-Www`，tooltip 显示完整日期范围。
  - `Month`：最近 12 个自然月，x 轴标签格式 `YYYY-MM`。
- 三张 trend card 的表格固定使用 6 行摘要，不列出全部时间点。
- 6 行摘要顺序固定为 `Latest point`、`Previous point`、`Rolling average`、`Peak point`、`Lowest point`、`Selected range total`。
- `Rolling average` 的窗口固定为 Day 最近 7 点、Week 最近 4 点、Month 最近 3 点。
- Hover 图表点必须高亮同一 range point 对应的表格行；hover 表格行必须高亮同一 range point 对应的图表点。

#### Session Trend

- 图表类型固定为纵向柱状图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 session count，从 0 开始。
- `All agents` scope 下，每个柱子按 agent 分段堆叠，分段顺序固定为 Claude Code、Qoder、Codex。
- 单 agent scope 下，每个柱子使用当前 agent 的单一颜色。
- tooltip 固定展示 `Range point`、`Sessions`、`Share of visible range`、`Claude Code sessions`、`Qoder sessions`、`Codex sessions`、`Failed-tool sessions`。
- 单 agent scope 下 tooltip 中其它 agent 行不展示。
- 明细表列固定为 `Row`、`Range point`、`Sessions`、`Share`、`Delta`、`Failed-tool sessions`。
- `Delta` 使用当前行值减去前一个 range point 的值；`Selected range total` 的 `Delta` 显示 `N/A`。

#### Token Trend

- 图表类型固定为折线图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 total tokens，从 0 开始。
- 折线只展示 `Total Tokens`；token 组成放在 `Token Trend by Composition` 卡片中展示。
- `All agents` scope 下 tooltip 必须展示三个 agent 的 token 贡献值和占比。
- 单 agent scope 下 tooltip 必须展示当前 agent 的 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
- 明细表列固定为 `Row`、`Range point`、`Total Tokens`、`Fresh`、`Cache Read`、`Cache Write`、`Output`、`Cache Read Ratio`。
- `Selected range total` 行展示当前可见时间窗口内各 token 类型的合计。

#### Prompt Activity Trend

- 图表类型固定为纵向柱状图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 user prompt count，从 0 开始。
- `All agents` scope 下，每个柱子按 agent 分段堆叠，分段顺序固定为 Claude Code、Qoder、Codex。
- 单 agent scope 下，每个柱子使用当前 agent 的单一颜色。
- tooltip 固定展示 `Range point`、`User Prompts`、`Assistant Turns`、`Tool Calls`、`Prompts / Session`。
- `All agents` scope 下 tooltip 追加三个 agent 的 user prompt 贡献值和占比。
- 明细表列固定为 `Row`、`Range point`、`User Prompts`、`Assistant Turns`、`Tool Calls`、`Prompts / Session`、`Failed Tools`。

### Token 分析区

Token 分析区固定为两张卡片，顺序固定为 `Token Trend by Composition`、`Cache Health`。宽屏下 `Token Trend by Composition` 占 2/3 宽度，`Cache Health` 占 1/3 宽度；普通桌面宽度下两张卡上下排列。

#### Token Trend by Composition

- 图表类型固定为堆叠面积图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 total tokens，从 0 开始。
- 堆叠层顺序从下到上固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
- 图表绘图区高度固定为 220px 到 260px。
- legend 固定展示四个 token 类型，每个 legend 项显示当前可见时间窗口内的合计和占比。
- tooltip 固定展示 `Range point`、`Fresh`、`Cache Read`、`Cache Write`、`Output`、`Total Tokens`，每一项都显示数量和占比。
- 明细表固定放在图表下方，列固定为 `Token Type`、`Latest point`、`Selected range total`、`Share`、`Delta`。
- 表格行固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`、`Total Tokens`。

#### Cache Health

- Cache Health 不再展示两条互补折线。
- 图表类型固定为单折线图加异常标记。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 `Cache Read Ratio`，范围固定为 0% 到 100%。
- 折线只显示 `Cache Read Ratio`。
- Fresh spike 使用图表点上的红色三角标记展示，不再作为第二条折线展示。
- Fresh spike 判定规则固定为：当前 range point 的 Fresh tokens 大于 `max(1.8 × rolling median fresh tokens, rolling median fresh tokens + 2 × MAD)`。
- Fresh spike 的 rolling window 固定为 Day 最近 7 点、Week 最近 4 点、Month 最近 3 点；历史点不足时 Fresh spike 显示 `N/A`。
- tooltip 固定展示 `Range point`、`Cache Read Ratio`、`Input-side Tokens`、`Fresh`、`Cache Read`、`Cache Write`、`Fresh Spike`。
- 明细表固定放在图表下方，列固定为 `Range point`、`Input-side Tokens`、`Fresh`、`Cache Read`、`Cache Write`、`Cache Read Ratio`、`Fresh Spike`。
- 明细表固定展示 `Latest point`、`Previous point`、`Rolling average`、`Lowest cache read`、`Highest fresh`、`Selected range total` 六行。

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
- tooltip 固定展示 agent 名称、当前指标绝对值、当前指标占比、当前指标全体合计。
- 三张图使用同一套 agent 颜色，颜色顺序固定为 Claude Code、Qoder、Codex。
- 该区下方固定展示一张 `Agent Contribution Table`，列固定为 `Agent`、`Sessions`、`Session Share`、`Tokens`、`Token Share`、`User Prompts`、`Prompt Share`。
- `Agent Contribution Table` 固定展示 Claude Code、Qoder、Codex 三行；无数据的 agent 行显示 0 和 0.0%。

#### All agents 模式：All Agents

- `All Agents` 表固定展示在 `Agent Contribution Comparison` 下方。
- 表格列固定为 `Agent`、`Provider`、`Sessions`、`Projects`、`Tokens`、`Tool Calls`、`Failed Tools`、`Failure Rate`、`Last Active`。
- 表格固定展示 Claude Code、Qoder、Codex 三行。
- `Tokens` 单元格必须使用 token cell：总量数字、tokenbar、tooltip 中的 Fresh、Cache Read、Cache Write、Output。
- 点击 agent 行后不跳转到 Agent Detail；点击行为固定为把 Dashboard agent scope 切换到该 agent。
- 行内 `View Sessions` 操作跳转到 `/sessions?agent=<agent>`。

#### All agents 模式：Agent / Model Efficiency

- `Agent / Model Efficiency` 表固定展示在 `All Agents` 下方。
- 表格列固定为 `Agent`、`Model`、`Sessions`、`Tokens`、`Avg tokens/session`、`Avg input/session`、`Avg output/session`、`Cache Read Ratio`、`Failed/session`。
- 表格每行代表一个 agent + model 组合。
- 排序固定为 `Tokens` 降序。
- model 缺失时显示 `Unknown model`。
- 点击表格行跳转到 `/sessions?agent=<agent>&model=<model>`。

#### 单 agent 模式：Agent Deep Dive

- 单 agent 模式固定展示 `Agent Deep Dive` 区。
- `Agent Deep Dive` 承接原 Agent Detail 的有效信息；不展示独立 Agent selector 卡片，因为 Page Head 已经提供 agent scope selector。
- `Agent Activity Trend` 不单独重复展示；它由 Trend 总览区的三张 trend card 承接。
- `Agent Deep Dive` 固定包含 5 个组件，顺序固定为 `Model Mix`、`Tool Distribution`、`Failure Signals`、`Model Efficiency Detail`、`Agent Sessions`。

#### 单 agent 模式：Model Mix

- `Model Mix` 固定展示为左图右表。
- 图表类型固定为横向柱状图。
- y 轴显示 model 名称；x 轴显示 tokens。
- 每个柱子右侧显示 token 占比和 session 数。
- 表格列固定为 `Model`、`Sessions`、`Session Share`、`Tokens`、`Token Share`、`Cache Read Ratio`、`Failed/session`。
- 表格排序固定为 `Tokens` 降序。

#### 单 agent 模式：Tool Distribution

- `Tool Distribution` 固定展示为左图右表。
- 图表类型固定为横向柱状图。
- y 轴显示 tool name；x 轴显示 tool calls。
- 表格列固定为 `Tool`、`Calls`、`Call Share`、`Tokens`、`Token Share`、`Failed`、`Failure Rate`。
- 表格排序固定为 `Calls` 降序。
- 工具名缺失时显示 `Unknown tool`。

#### 单 agent 模式：Failure Signals

- `Failure Signals` 只在单 agent 模式展示。
- 该卡片展示当前 agent 的聚合异常信号，不展示跨 agent 热点 session。
- 表格列固定为 `Signal Type`、`Count`、`Severity`、`Rate`、`Representative Session`、`Last Seen`。
- `Signal Type` 候选固定为 `Tool failure`、`Cache read drop`、`Fresh spike`、`Long duration`、`Unknown model`。
- `Severity` 候选固定为 `High`、`Medium`、`Low`。
- `Representative Session` 点击进入 Session Detail。
- 同一 signal type 有多个 session 时，代表 session 固定选择 `Last Seen` 最新的一条。

#### 单 agent 模式：Model Efficiency Detail

- `Model Efficiency Detail` 表固定展示在三张分析卡下方。
- 表格列固定为 `Model`、`Sessions`、`Avg input`、`Avg output`、`Cache read`、`Tool calls/session`、`Failed/session`、`Notes`。
- 表格排序固定为 `Sessions` 降序。
- `Notes` 只显示固定标签：`Primary model`、`High input`、`Low cache reuse`、`High failure`、`Low sample`、`Normal`。
- 每行点击跳转到 `/sessions?agent=<agent>&model=<model>`。

#### 单 agent 模式：Agent Sessions

- `Agent Sessions` 表固定展示当前 agent 范围内的 sessions。
- 表格列固定为 `Title`、`Project`、`Model`、`Tokens`、`Rounds`、`Tools`、`Failed`、`Duration`、`Updated`。
- 默认排序固定为 `Updated` 降序。
- 分页固定每页 20 条。
- `Tokens` 单元格必须使用 token cell。
- 点击 project 单元格进入 Project Detail。
- 点击 session 行进入 Session Detail。
- `View Sessions` 按钮跳转到 `/sessions?agent=<agent>`，作为查看同一 agent 完整 session 列表的入口。

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
- `Sessions With Failure` 统计 failed tool result 数量大于 0 的 session。
- `Failed/session = Failed Tools / Sessions`。

## 交互逻辑

- 切换 agent scope 后，全页所有数值和表格必须同步更新；不得保留旧 scope 的局部数据。
- 切换时间粒度后，KPI 不变，Trend 总览区、Token 分析区、`Agent Contribution Comparison` 更新。
- hover 任意图表点展示真实数值和占比；tooltip 不展示归一化后的内部绘图值。
- hover 图表 legend 时，高亮对应序列，非对应序列降低透明度到 30%。
- hover tokenbar 时展示 Fresh、Cache Read、Cache Write、Output 的数量和占比。
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
