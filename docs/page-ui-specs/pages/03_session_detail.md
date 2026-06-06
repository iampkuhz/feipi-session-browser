# Session Detail 页面规约

## 定位

Session Detail 是单个 session 的调试页，解释 trace、payload、attribution、失败信号和上下文成本。目标结构只保留 `Trace`、`Payload` 两个主 tab。

## 页面布局

- 路由：`/sessions/<agent>/<session_id>`；模板：`session.html`；支持 `?export=mhtml`。
- 面包屑固定为 Dashboard / Sessions / agent / short session id。
- Hero 区在首屏顶部，展示 session 标题、agent、model、时间、duration、session URL 和核心 KPI。
- Hero 下方是诊断卡片区，固定包含 `Token Timeline + Cache Health`、`Tool Cost & ROI`、`Bug Mining & Regression Seeds`、`Context Budget`。
- 主内容区只有两个 tab：`Trace`、`Payload`。
- Trace tab 内部是筛选条 + round 全宽列表，不展示 sidecar。
- Payload tab 是左右布局：左侧 call selector，右侧 call detail。
- MHTML 导出页面必须保持同样信息层级和离线交互能力。

## 控件和候选项

- Trace filter 候选项固定为 `All`、`Failed`。
- Expand control 是一个全局 toggle，文案在 `Expand all` 和 `Collapse all` 之间切换。
- 每个 LLM call 和 subagent call 固定提供 `Request Attribution`、`Response Attribution`、`Payload` 操作。
- Payload call selector 候选项来自当前 session 的 LLM call 和 subagent call，按 trace 顺序排列。
- Payload detail 内固定有 `Request Attribution`、`Response Attribution`、`Raw Request`、`Raw Response` 四个区块。
- Payload raw/preview 展示模式候选项固定为 `Rendered`、`Raw`。

## 文字内容

- 主 tab 文案固定为 `Trace`、`Payload`。
- Hero KPI label 固定为 `Total Tokens`、`Input-side Tokens`、`Output Tokens`、`Cache Read Ratio`、`Rounds`、`Failed Tools`。
- 诊断卡标题固定为 `Token Timeline + Cache Health`、`Tool Cost & ROI`、`Bug Mining & Regression Seeds`、`Context Budget`。
- Round 标题使用 `R<round_number>` 加 summary；summary 缺失时显示 `Untitled round`。
- 原文缺失时必须显示 unavailable 原因、precision 和 source，不用空白区域代替。

## 数据指标与口径

### Hero KPI 区

1. `Total Tokens`
   - 一级值：`Fresh + Cache Read + Cache Write + Output`。
   - 二级指标固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
2. `Input-side Tokens`
   - 一级值：`Fresh + Cache Read + Cache Write`。
   - 二级指标固定为 `Fresh Ratio`、`Cache Read Ratio`。
   - `Fresh Ratio = Fresh / Input-side Tokens`。
   - `Cache Read Ratio = Cache Read / Input-side Tokens`。
3. `Output Tokens`
   - 一级值：模型可见输出 token。
   - 二级指标固定为 `Output / Round`、`Output Ratio`。
   - `Output / Round = Output / Rounds`。
   - `Output Ratio = Output / Total Tokens`。
4. `Cache Read Ratio`
   - 一级值：`Cache Read / Input-side Tokens`。
   - 二级指标固定为 `Cache Read`、`Input-side Tokens`。
5. `Rounds`
   - 一级值：assistant round 数。
   - 二级指标固定为 `Tool Calls`、`Subagent Calls`。
6. `Failed Tools`
   - 一级值：失败 tool result 数。
   - 二级指标固定为 `Failure Rate`、`Failed Rounds`。

### 诊断卡片

#### Token Timeline + Cache Health

- 图表类型固定为按 round 顺序排列的堆叠柱状图。
- x 轴显示 round number。
- y 轴显示 total tokens。
- 堆叠顺序固定为 Fresh、Cache Read、Cache Write、Output。
- 图表上叠加 Cache Read Ratio 折线，右侧 y 轴范围固定为 0% 到 100%。
- 不渲染配套明细表；round/call 细节通过 hover tooltip 展示。
- tooltip 固定展示 round id、时间、Fresh、Cache Read、Cache Write、Output、Total Tokens、Cache Read Ratio。

#### Tool Cost & ROI

- 该卡片固定展示 3 个紧凑 stat：`Tool Calls`、`Failed Tools`、`Tool Tokens`。
- 该卡片固定展示一张 `Tool Summary` 小表。
- `Tool Summary` 列固定为 `Tool`、`Calls`、`Tokens`、`Failure`。
- `Failure` 单元格展示 failed count 加 failure rate。
- 表格只展示调用次数最高的 5 个工具；完整工具明细放入 tooltip 和 Payload。

#### Bug Mining & Regression Seeds

- 该卡片固定展示失败信号列表，不展示图表。
- 列固定为 `Signal`、`Severity`、`Evidence`、`Seed`。
- `Signal` 示例值：`Tool failure`、`Parser fallback`、`Payload unavailable`。
- `Evidence` 展示错误摘要，最长 120 字符。
- `Seed` 展示可复制的 session id、round id、call id 组合。

#### Context Budget

- 图表类型固定为分段条形图。
- 分段固定为 System、User、Assistant、Tool、Subagent、Output。
- 该卡不渲染配套明细表。
- tooltip 固定展示分段名称、token 数、占比、统计层级。
- 卡片标题栏右侧固定显示统计层级，候选值固定为 `Session-level`、`Round-level`。

### Trace 与 Payload

- Trace 与 Payload 使用同一 call id，必须能互相定位。
- Rounds 使用当前 session 的 assistant round 计数。
- Tools 使用 tool call 计数；Failed Tools 使用失败 tool result 计数。
- Subagents 使用 subagent call 计数。
- Output 来自模型可见输出 token，不把 reasoning 隐含 token 混入可见输出。

## 交互逻辑

- 进入页面时默认展开第一个 failed round；没有失败时展开 R1。
- 点击 round header 和 round 任意非按钮区域切换展开/收起。
- 点击 round 内按钮只执行按钮动作，不触发 round toggle。
- 点击 `Expand all` 展开所有 round；再次点击 `Collapse all` 收起到默认状态。
- Trace filter 选择 `Failed` 时只显示 failed round 和含失败信号的 round。
- 点击 `Request Attribution` 打开对应 call 的 request attribution。
- 点击 `Response Attribution` 打开对应 call 的 response attribution。
- 点击 `Payload` 打开 Payload tab 中对应 call。
- Payload selector 选择某 call 后，右侧四个区块全部刷新为该 call 数据。
- MHTML 导出离线打开时，不依赖外部网络请求，payload modal、round toggle、tab 切换仍可用。

## 状态

- session 数据不可用：展示错误状态和 Back to Sessions。
- 无 round：Trace 显示空态和可执行下一步。
- call 没有 raw request/response：显示 unavailable 原因、precision、source。
- attribution 构建失败：显示错误摘要和来源，不隐藏该区块。
- payload 太长：默认 preview，提供 Raw 查看和复制。

## 禁止项

- 不存在独立 Attribution tab。
- 不存在独立 Insights tab。
- 不在页面中展示 All Sessions 表格。
- 不展示 Selected LLM calls、Round diagnostics、sidecar filter。
- 不恢复 Round Map、Inspector 默认三栏、Map/Inspector/Focus 模式按钮、Density toggle、无效占位按钮。
