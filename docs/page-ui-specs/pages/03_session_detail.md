# Session Detail 页面规约

## 定位

Session Detail 是单个 session 的调试页，解释 trace、payload、attribution、失败信号和上下文成本。目标结构只保留 Trace、Payload 两个主 tab。

## 页面布局

- 路由：`/sessions/<agent>/<session_id>`；模板：`session.html`；支持 `?export=mhtml`。
- 面包屑固定为 Dashboard / Sessions / agent / short session id。
- Hero 区在首屏顶部，展示 session 标题、agent、model、时间、duration、session URL 和核心 KPI。
- Hero 下方是诊断卡片区：Token Timeline + Cache Health、Tool Cost & ROI、Bug Mining & Regression Seeds、Context Budget。
- 主内容区只有两个 tab：Trace、Payload。
- Trace tab 内部是筛选条 + round 全宽列表，不展示 sidecar。
- Payload tab 是左右布局：左侧 call selector，右侧 call detail。
- MHTML 导出页面必须保持同样信息层级和交互能力。

## 控件和候选项

- Trace filter 候选项至少包含 `All`、`Failed`。
- Expand control 是一个全局 toggle，文案在 `Expand all` 和 `Collapse all` 之间切换。
- 每个 LLM call 和 subagent call 固定提供 `Request Attribution`、`Response Attribution`、`Payload` 操作。
- Payload call selector 候选项来自当前 session 的 LLM call 和 subagent call，按 trace 顺序排列。
- Payload detail 内固定有 `Request Attribution`、`Response Attribution`、`Raw Request`、`Raw Response` 四个区块。
- Payload raw/preview 展示模式候选项固定为 `Rendered`、`Raw`。

## 文字内容

- 主 tab 文案固定为 `Trace`、`Payload`。
- Hero KPI label 固定为 Tokens、Fresh、Cache Read、Cache Write、Output、Rounds、Tools、Subagents、Duration、Failure Signals。
- 诊断卡标题固定为 `Token Timeline + Cache Health`、`Tool Cost & ROI`、`Bug Mining & Regression Seeds`、`Context Budget`。
- Round 标题使用 `R<round_number>` 加 summary；summary 缺失时显示 `Untitled round`。
- 原文缺失时必须显示 unavailable 原因、precision 和 source，不用空白区域代替。

## 数据指标与口径

- Tokens = Fresh + Cache Read + Cache Write + Output。
- Fresh 来自未缓存输入 token。
- Cache Read 来自缓存读取输入 token。
- Cache Write 来自缓存写入输入 token。
- Output 来自模型输出 token，不把 reasoning 隐含 token 混入可见输出，除非字段口径明确。
- Rounds 使用当前 session 的 assistant round 或 assistant message 计数。
- Tools 使用 tool call 计数；Failed Tools 使用失败 tool result 计数。
- Subagents 使用 subagent call 或 subagent instance 计数。
- Token Timeline 横轴按 round 或 call 顺序，tooltip 显示 round/call id、时间、四类 token 数量和总量。
- Cache Health 展示 Cache Read Ratio；公式是 Cache Read / (Fresh + Cache Read + Cache Write)。
- Tool Cost & ROI 至少展示工具调用次数、失败次数、工具相关 token 量、失败工具占比。
- Bug Mining & Regression Seeds 展示失败类型、失败工具、错误摘要、可复制回归种子或定位信息。
- Context Budget 展示 session 或当前 round 的上下文分布，并明确统计口径是 session-level 还是 round-level。
- Trace 与 Payload 使用同一 call id，必须能互相定位。

## 交互逻辑

- 进入页面时默认展开第一个 failed round；没有失败时展开 R1。
- 点击 round header 或 round 任意非按钮区域切换展开/收起。
- 点击 round 内按钮只执行按钮动作，不触发 round toggle。
- 点击 `Expand all` 展开所有 round；再次点击 `Collapse all` 收起到默认状态。
- Trace filter 选择 `Failed` 时只显示 failed round 或含失败信号的 round。
- 点击 `Request Attribution` 打开对应 call 的 request attribution。
- 点击 `Response Attribution` 打开对应 call 的 response attribution。
- 点击 `Payload` 打开或切换到 Payload 中对应 call。
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
- 不恢复 Round Map、Inspector 默认三栏、Map/Inspector/Focus 模式按钮、Density toggle 或无效占位按钮。
