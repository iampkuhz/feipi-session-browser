# Dashboard 页面规约

## 定位

Dashboard 是全局运行状态和单 agent 深度分析的统一入口。页面默认展示 `All agents` 聚合概览；当 agent scope 选择 Claude Code、Qoder、Codex 中任意一个时，页面切换为单 agent 深度分析状态，并承接原 Agent Detail 页面中仍有价值的模型、工具、失败信号、模型效率和当前 agent sessions 信息。

Dashboard 不再跳转到独立 Agent Detail 页面。所有 agent 汇总和单 agent 深度信息都在 Dashboard 内完成。

## 页面布局

### 页面骨架

- 路由固定为 `/` 和 `/dashboard`；模板固定为 `dashboard.html`。
- 页面使用统一 shell；Sidebar 当前项高亮 `Dashboard`。
- Page Head 左侧显示标题 `Dashboard`，副标题固定说明当前页面同时支持全局概览和单 agent 深度分析。
- Page Head 右侧固定放置 agent scope selector、时间粒度 segmented control；不得放置 `View Sessions` 按钮。
- Dashboard 主内容区在宽屏下必须放宽可用内容宽度，优先让图表和表格获得横向空间；不得因为过窄的全局 content max-width 导致图表 card 在 `>=1440px` 视口中明显被挤压。
- 页面主体从上到下固定为 5 个区块：
  1. KPI 区。
  2. Trend 总览区。
  3. Cache Health 区。
  4. Scope 分支区。
  5. 状态和错误反馈区。
- `Hot Sessions & Signals` 从 Dashboard 中移除；页面不保留该卡片、该标题、该表格和该点击行为。

### KPI 区

- KPI 区固定为 6 张 metric card。
- 超宽屏 `>=1680px` 下固定 6 列；普通桌面宽度固定 3 列 2 行；每张卡高度一致，主数字和 badge 不得裁切。
- 每张 KPI card 固定为两层结构：
  - 第一层：一级指标 label、一级指标 value、单位、变化 badge 必须在同一紧凑主行内展示；变化 badge 视觉上必须贴近一级指标 value，不得漂到卡片最右侧造成口径断裂。
  - 第二层：2 到 4 个二级指标，使用紧凑行展示，label 左对齐，value 右对齐。
- KPI card 内不得保留独立 info icon；解释说明必须下沉到指标行本身。
- 变化 badge 使用紧凑 badged text 展示相对变化或当前窗口辅助变化值，例如 `+6.0%`、`+10`、`N/A`。
- 变化 badge 的口径必须可解释：Sessions、Total Tokens、Prompt Activity、Cache Read Ratio、Failed Tools 默认对比当前可见窗口最后两个 range point；Projects 默认展示 `New 7d`。
- 每张 KPI card 的一级指标行必须提供 hover/focus tooltip，说明一级值和变化 badge 的统计口径。
- KPI 使用当前 agent scope 下的全部已索引数据重算；时间粒度 segmented control 不影响 KPI。
- 数值必须使用 tabular number；token 缩写保留一位小数；百分比保留一位小数。
- 二级指标行必须有 hover/focus tooltip，tooltip 固定说明定义、计算公式、统计范围；tooltip 必须使用具体字段口径，不得只写 `定义与计算公式` 这类占位文案。

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
   - `Fresh`：本次请求实际新增/发送的输入规模，cache read 和 cache write 作为独立组件展示，不从 Fresh 扣减。
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

- Trend 总览区固定为一个 section，section 内固定 4 张同级 chart card，宽屏顺序固定为第一行 `Session Trend`、`Prompt Activity Trend`，第二行 `Token Trend`、`Cache Health`。
- `Session Trend`、`Token Trend`、`Prompt Activity Trend`、`Cache Health` 不使用 tab 切换；四张卡必须同时可见。
- 每张 chart card 的内容布局固定为顶部标题栏加全宽图表，不渲染静态明细表。
- `Session Trend`、`Token Trend`、`Prompt Activity Trend` 的标题栏右侧固定显示 `Latest` 和 `Range total` 两个紧凑 stat；`Cache Health` 的标题栏右侧固定显示 `Latest ratio`、`Lowest ratio` 两个紧凑 stat。
- 所有 chart card 不展示 subtitle；图表口径、维度解释和注意事项全部放入 title 旁 info icon 的 tooltip。
- 每张 chart card 的图表宽度占卡片内容宽度 100%；图表绘图区高度固定为 240px 到 280px。
- 每张 chart card 的 y 轴只显示刻度值；不得显示可见的 `Y-axis: <metric name> (<unit>)` 纵向标题文字。
- 每张 chart card 的所有 range point 细节都通过 `common.md` 的 `Chart Tooltip` 展示，不把每个 range point 的数值同时铺成表格。
- 宽屏 `>=1440px` 时 chart card 固定为 2 列 2 行；标准桌面和窄宽兜底优先每行 2 张，空间不足时再降为单列，任何断点下文字不得溢出或重叠。
- 时间粒度控制固定影响三张 trend card、Cache Health 区和 all agents 占比柱状图。
- 时间粒度的数据窗口固定如下：
  - `Day`：最近 30 个自然日，x 轴标签格式 `MM-DD`。
  - `Week`：最近 20 个 ISO week，x 轴标签格式 `YYYY-Www`，tooltip 显示完整日期范围。
  - `Month`：最近 12 个自然月，x 轴标签格式 `YYYY-MM`。
- `Latest` stat 展示当前可见窗口最后一个 range point 的 y 轴真实值。
- `Range total` stat 展示当前可见窗口内所有 range point 的 y 轴真实值合计。
- Hover 图表点必须高亮当前 range point，并在最近的 range point 处显示一条竖向虚线参考线；tooltip 使用 `Chart Tooltip` 的 header、label、value、share 三列布局，并展示该点的 y 轴真实值、占比、辅助指标。
- 折线图和面积图的 marker、hover target、竖向虚线必须与 SVG path 使用同一套 x/y 坐标基准；marker 必须落在折线真实相交点上，不得相对折线左偏或右偏。
- 折线图的 x 坐标必须落在对应 range point 的 label 中心；不得使用 plot 两端 0%/100% 作为首尾点位导致折线、marker、hover 竖线与 x 轴文字错位。
- 折线图遇到中间缺失值时必须跳过缺失点，并从上一个可计算点直接连接到下一个可计算点；tooltip 中该缺失点的折线值显示 `N/A`，不得把未知值画成真实 `0%` 或 `0`。
- Hover tooltip 的绘制层级必须高于图表中的 marker、竖向虚线和其它未 hover 的 range point；不得出现点位覆盖在 tooltip 上或显示在 tooltip 内部。
- tooltip 中分 agent、分 token 类型或分来源的明细行与 `Total` 行之间必须有水平分隔线。
- Chart Tooltip 必须根据文本内容自适应排版：label 可以换行，数值和占比列不换行，tooltip 不得出现文字重叠、截断或横向溢出视口；靠近图表左右边缘时 tooltip 必须向图表内侧对齐。

#### Session Trend

- 图表类型固定为纵向柱状图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 session count，从 0 开始。
- y 轴只显示 session count 刻度值，不显示 `Y-axis: Sessions (count)` 纵向标题。
- `All agents` scope 下，每个柱子按 agent 分段堆叠，分段顺序固定为 Claude Code、Qoder、Codex。
- 单 agent scope 下，每个柱子使用当前 agent 的单一颜色。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定展示 `Range point`、`Sessions`、`Share of visible range`、`Delta from previous point`、`Claude Code sessions`、`Qoder sessions`、`Codex sessions`。
- 单 agent scope 下 tooltip 中其它 agent 行不展示。
- tooltip 不展示 `Failed-tool sessions count`；失败工具属于 `Failed Tools` KPI、Failure Signals 和 session/detail 分析，不进入 Session Trend hover。
- tooltip 示例固定包含 `06-06 · Sessions 42 · Share 8.4% · Delta +6`。

#### Token Trend

- 图表类型固定为堆叠面积图加 total 折线。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 total tokens，从 0 开始。
- y 轴只显示 token 刻度值，不显示 `Y-axis: Total Tokens (tokens)` 纵向标题。
- `Token Trend` 同时承载原 `Token Trend by Composition` 的 token 组成分析能力，不再单独渲染 `Token Trend by Composition` 卡片。
- 堆叠层顺序从下到上固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`；total 折线连接每个 range point 的合计值，不得渲染成彼此孤立的横线片段。
- legend 固定展示四个 token 类型，每个 legend 项显示当前可见时间窗口内的合计和占比。
- `All agents` scope 下 tooltip 只按 token 类型展示 `Fresh`、`Cache Read`、`Cache Write`、`Output` 的值和占比；不得追加 Claude Code、Qoder、Codex 等 agent token 贡献行。
- 单 agent scope 下 tooltip 同样只展示当前 agent scope 内聚合后的 `Fresh`、`Cache Read`、`Cache Write`、`Output`，不展示其它 agent 行。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局，token 行按 Fresh、Cache Read、Cache Write、Output 顺序展示。
- tooltip 固定展示 `Range point`、`Total Tokens`、`Share of visible range`、`Delta from previous point`、`Fresh`、`Cache Read`、`Cache Write`、`Output`。
- Token Trend tooltip 不展示 `Cache Read Ratio`；该指标属于 `Cache Health` 图表，避免同一区域重复解释。
- tooltip 示例固定包含 `2026-W23 · Total 2.4M · Fresh 520k · Read 1.3M · Write 180k · Output 400k`。

#### Prompt Activity Trend

- 图表类型固定为柱线组合图。
- x 轴显示当前时间粒度的 range point。
- 左 y 轴显示 user prompt count，从 0 开始；右 y 轴显示 `Avg Prompts / Session`，从 0 开始。
- 左右 y 轴只显示刻度值，不显示 `Y-axis: User Prompts (count)` 或 `Y-axis: Avg Prompts / Session` 纵向标题。
- `All agents` scope 下，每个柱子按 agent 分段堆叠，分段顺序固定为 Claude Code、Qoder、Codex。
- 单 agent scope 下，每个柱子使用当前 agent 的单一颜色。
- `Avg Prompts / Session` 使用右轴折线连接每个 range point，计算口径为 `User Prompts / Sessions`；sessions 为 0 时该点折线断开，tooltip 显示 `N/A`。
- 折线转折点必须与对应柱状图 range point 的柱心对齐，不得使用 plot 两端 0%/100% 作为首尾点位导致折线相对柱子偏左或偏右。
- `Assistant Turns` 和 `Tool Calls` 是辅助量，不作为主图形系列展示；它们只在 tooltip 中作为辅助行展示，避免把不同量纲混入同一视觉编码。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定分为三段：`User Prompts (bars)`、`Avg Prompts / Session (line)`、`Auxiliary`。
- `User Prompts (bars)` 段使用 agent 色点展示各 agent 的 user prompt count 和占比，并展示 `Total User Prompts`；不得把 avg prompt/session 合并到 agent prompt count 行。
- `Avg Prompts / Session (line)` 段使用与折线一致的有色短虚线 key 展示折线值；`All agents` scope 下先展示整体 `Overall` 平均，再展示各 agent 的 `User Prompts / Sessions` 参考值。
- `Auxiliary` 段只展示 `Assistant Turns` 和 `Tool Calls`。
- tooltip 示例固定包含 `06-06 · User Prompts 318 · Assistant Turns 301 · Tool Calls 1,482 · Prompts / Session 7.6`。

### Cache Health

Cache Health 固定作为 Trend 总览区第二行右侧 chart card；`Token Trend by Composition` 不再作为独立卡片存在。

- 图表类型固定为多折线图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 `Cache Read Ratio`；上界固定包含 `100%`，并显示 100% 网格线；下界根据当前可见 range point 的最低可计算 ratio 向下减 5 个百分点后取不小于 `0%` 的值。
- 当任一 agent 的 ratio 为 `0%` 时，下界必须为 `0%`，且折线不得与底部坐标轴重叠到不可见。
- 折线固定展示 `Average`、Claude Code、Qoder、Codex 的 cache read ratio。
- `All agents` scope 下 `Average` 折线高亮加粗，三个 agent 折线保留但视觉权重降低。
- 单 agent scope 下当前 agent 折线高亮加粗，`Average` 和其它 agent 折线保留但视觉权重降低。
- `Average` / `All agents` 的颜色固定使用中性黑灰，不得使用品牌紫或 Claude Code 紫色，避免和 Claude Code 系列混淆。
- Cache Health 的 legend 和 tooltip 中，折线系列示意必须使用对应颜色的短横线，不得使用圆点；圆点只用于柱状图或面积分层类别。
- 当某个 agent 在可见窗口内只有孤立的可计算 ratio、无法形成连续折线段时，该点必须以同色短横线展示，不得因为 SVG path 只有 `M` 命令而完全不可见。
- 当某个 agent 的 session 只有 input/output token 但原始 usage 未上报 cache read/write 字段，或该 agent 在该 range point 没有 input-side token 数据时，该 agent 的 Cache Read Ratio 视为不可计算，折线和 marker 都跳过该点；tooltip 显示 `N/A` 和未上报或缺失的 input-side token 数；不得把不可计算点渲染为真实 `0%`，也不得在坐标轴底部补虚假点。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定展示 `Range point`、`Cache Read Ratio`、`Input-side Tokens`、`Fresh`、`Cache Read`、`Cache Write`。
- Dashboard 是聚合统计页，不计算、不统计、不标记 Fresh spike；Fresh spike 只允许在 Session Detail 的 round 级视图中体现。
- 卡片标题栏右侧固定显示 `Latest ratio`、`Lowest ratio` 两个紧凑 stat。
- 卡片不展示 subtitle；需要说明口径时放入 title 旁 info icon tooltip。
- 该卡不渲染配套明细表；每个点的 Input-side Tokens 和 token 类型数量通过 tooltip 展示。
- tooltip 示例固定包含 `06-06 · Cache Read Ratio 61.2% · Input-side 2.0M · Fresh 720k · Cache Read 1.2M · Cache Write 80k`。

### Scope 分支区

- Scope 分支区根据 agent scope 渲染两套互斥内容。
- agent scope 为 `All agents` 时，只渲染 All agents 模式内容。
- agent scope 为 Claude Code、Qoder、Codex 中任意一个时，只渲染单 agent 模式内容。

#### All agents 模式：Agent Contribution Comparison

- `Agent Contribution Comparison` 固定展示在 Cache Health 区下方。
- 该区固定包含 3 张同级柱状图卡片，顺序固定为 `Session Share`、`Token Share`、`Prompt Activity Share`。
- 每张卡的图表类型固定为 100% 横向堆叠柱状图。
- 每张卡只展示一根柱子；柱子分段固定为 Claude Code、Qoder、Codex。
- x 轴固定为 0% 到 100%；y 轴固定显示当前指标名称。
- 每个分段内部默认显示 agent 名称和占比；分段宽度不足 56px 时只显示占比，分段宽度仍不足以容纳占比时隐藏内部文字，并通过下方 legend 和 tooltip 展示 agent 名称、绝对值、占比。
- tooltip 使用 `common.md` 的 `Chart Tooltip` 布局。
- tooltip 固定展示 agent 名称、当前指标绝对值、当前指标占比、当前指标全体合计。
- 三张图使用同一套 agent 颜色，颜色顺序固定为 Claude Code、Qoder、Codex。
- 该区不渲染配套明细表；绝对值、占比、全体合计通过 tooltip 展示。
- 三张柱状图下方固定展示一句 scope summary，格式为 `Dominant: <agent> leads sessions, <agent> leads tokens, <agent> leads prompts`。

#### All agents 模式：All Agents

- `All Agents` 表固定展示在 `Agent Contribution Comparison` 下方。
- 表格列固定为 `Agent`、`Sessions`、`Tokens`、`Prompt Activity`、`Projects`、`Failure`、`Last Active`。
- 表格固定展示 Claude Code、Qoder、Codex 三行。
- 表格支持列排序；可排序列固定为 `Agent`、`Sessions`、`Tokens`、`Prompt Activity`、`Projects`、`Failure`、`Last Active`。
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
- 表格支持列排序；可排序列固定为 `Agent`、`Model`、`Sessions`、`Tokens / Session`、`Cache Read`、`Failure`。
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
- `Agent Deep Dive` 固定包含 5 个组件，顺序固定为 `Model Mix`、`Tool Distribution`、`Failure Signals`、`Model Efficiency Detail`、`View Sessions CTA`。

#### 单 agent 模式：Model Mix

- `Model Mix` 固定展示为一张 mix card，包含圆环分布图和多个紧凑明细表。
- 圆环图优先展示 `Token Share` 分布，因为 token 消耗比 session 数更能体现模型成本贡献；圆环 tooltip 固定展示 `Model`、`Tokens`、`Token Share`、`Sessions`、`Session Share`。
- mix card 内固定展示两张紧凑表：`Session Distribution` 和 `Token Distribution`。
- `Session Distribution` 表列固定为 `Model`、`Sessions`、`Session Share`，按 session share 降序。
- `Token Distribution` 表列固定为 `Model`、`Tokens`、`Token Share`，按 token share 降序。
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
- `Signal Type` 候选固定为 `Tool failure`、`Cache read drop`、`Long duration`、`Unknown model`。
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
- 表格列固定为 `Model`、`Sessions`、`Avg Tokens`、`Avg Process Time`、`Cache Read`、`Tool Calls / Session`、`Failure`、`Notes`。
- 表格排序固定为 `Sessions` 降序。
- `Notes` 只显示固定标签：`Primary model`、`High input`、`Low cache reuse`、`High failure`、`Low sample`、`Normal`。
- 每行点击跳转到 `/sessions?agent=<agent>&model=<model>`。
- 列含义和示例：
  - `Model`：模型名称；示例值 `opus-4.1`。
  - `Sessions`：该 model 在当前 agent 下的 session 数；示例值 `42`。
  - `Avg Tokens`：平均 total tokens per session，使用 K/M/B 缩写；示例值 `63.8K`。
  - `Avg Process Time`：平均 session 处理耗时，只计算 `model_execution_seconds + tool_execution_seconds`，不使用 session 生命周期 duration；示例值 `9m 42s`。
  - `Cache Read`：cache read ratio；示例值 `54.0%`。
  - `Tool Calls / Session`：tool calls per session；示例值 `14.2`。
  - `Failure`：failed tools per session；示例值 `0.21 / session`。
  - `Notes`：固定标签；示例值 `High input`。

#### 单 agent 模式：View Sessions CTA

- 单 agent 模式不展示 `Agent Sessions` 完整表格，避免 Dashboard 变成 session 列表的重复入口。
- `View Sessions CTA` 固定展示一个大按钮，跳转到 `/sessions?agent=<agent>`，作为查看当前 agent 完整 session 列表的入口。
- CTA 必须展示当前 agent 名称和当前 agent session 总数；示例文案 `View Claude Code Sessions · 842 sessions`。

## 控件和候选项

### Agent scope selector

- selector label 固定为 `Scope`。
- 候选项固定为 `All agents`、`Claude Code`、`Qoder`、`Codex`。
- 默认选中 `All agents`。
- `All agents` 选中态使用中性黑灰；Claude Code、Qoder、Codex 选中态分别使用全局 agent 默认色 `--agent-claude`、`--agent-qoder`、`--agent-codex`，不得统一回退到品牌紫色。
- 切换 scope 后，KPI 区、Trend 总览区、Cache Health 区、Scope 分支区全部重算。
- scope 必须反映到 URL 查询参数 `agent`：
  - `All agents` 使用 `/dashboard`，不写 `agent` 参数。
  - Claude Code 使用 `/dashboard?agent=claude-code`。
  - Qoder 使用 `/dashboard?agent=qoder`。
  - Codex 使用 `/dashboard?agent=codex`。

### 时间粒度 segmented control

- 候选项固定为 `Day`、`Week`、`Month`。
- 默认选中 `Day`。
- 选中态固定使用中性黑灰，禁止复用 Claude Code、Qoder、Codex 的 agent 色或品牌紫色，避免和 agent scope selector 混淆。
- 切换时间粒度只影响 Trend 总览区、Cache Health 区、`Agent Contribution Comparison`。
- 时间粒度必须反映到 URL 查询参数 `grain`，取值固定为 `day`、`week`、`month`。

### 操作按钮

- Page Head 不提供 `View Sessions` 按钮。
- All agents 表行内 `View Sessions` 操作跳转到 `/sessions?agent=<agent>`。
- 单 agent `View Sessions CTA` 大按钮跳转到 `/sessions?agent=<agent>`。
- 页面不提供全局搜索框。
- 页面不提供 Dashboard 内搜索框。
- 页面不提供跳转 Agent Detail 的按钮。

## 文字内容

- 页面标题固定为 `Dashboard`。
- KPI label 固定为 `Projects`、`Sessions`、`Total Tokens`、`Prompt Activity`、`Cache Read Ratio`、`Failed Tools`。
- Trend 标题固定为 `Session Trend`、`Token Trend`、`Prompt Activity Trend`。
- Cache Health 区标题固定为 `Cache Health`；页面不得出现独立 `Token Trend by Composition` 卡片标题。
- All agents 模式标题固定为 `Agent Contribution Comparison`、`All Agents`、`Agent / Model Efficiency`。
- 单 agent 模式标题固定为 `Agent Deep Dive`、`Model Mix`、`Tool Distribution`、`Failure Signals`、`Model Efficiency Detail`。
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
- 切换时间粒度后，KPI 不变，Trend 总览区、Cache Health 区、`Agent Contribution Comparison` 更新。
- hover 任意图表点展示真实数值和占比；tooltip 使用 `common.md` 的 `Chart Tooltip` 布局，不展示归一化后的内部绘图值。
- hover 任意趋势图或 Cache Health 图时，最近 range point 必须显示竖向虚线参考线。
- hover 图表 legend 时，高亮对应序列，非对应序列降低透明度到 30%。
- hover tokenbar 时使用 `common.md` 的 `Chart Tooltip` 布局展示 Fresh、Cache Read、Cache Write、Output 的数量和占比。
- 点击 All agents 模式中的 agent 行切换 Dashboard scope，不进入新页面。
- 点击 model efficiency 行进入带 agent/model 参数的 Sessions。
- 点击单 agent `View Sessions CTA` 进入 `/sessions?agent=<agent>`。
- 图表无数据时显示卡片内空态，不渲染空坐标轴。

## 状态

- 无 session 数据：KPI 显示 0，Trend 总览区、Cache Health 区和 Scope 分支区显示统一空态。
- 当前 scope 无数据：保留 scope selector，页面标题下显示当前 scope 无数据，所有图表卡显示空态。
- 当前时间粒度无数据：Trend 总览区和 Cache Health 区显示该时间窗口无数据，KPI 继续显示当前 scope 全量数据。
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
- 不在 Page Head 右侧提供 `View Sessions` 按钮。
- 不展示独立 `Token Trend by Composition` 卡片。
- 不在 Dashboard 展示、计算或统计 Fresh spike。
- 不出现 Dense、Comfortable、Columns、Export、Keyboard shortcuts。
