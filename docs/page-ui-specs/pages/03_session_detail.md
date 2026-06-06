# Session Detail 页面规约

## 定位

Session Detail 是单个 session 的核心调试页，用于解释 trace、payload、request attribution、response attribution、失败信号、上下文成本和处理耗时。目标结构只保留 `Trace`、`Payload` 两个主 tab。

## 页面布局

- 路由固定为 `/sessions/<agent>/<session_id>`；模板固定为 `session.html`；MHTML 导出参数固定为 `?export=mhtml`。
- 面包屑固定为 `Dashboard / Sessions / <agent> / <short session id>`。
- 首屏顺序固定为 Page Head、Hero KPI、诊断卡片区、主 tab。
- Hero KPI 区展示 session 标题、agent、model、project、Created、Updated、Duration、Process Time、session id copy 和核心 KPI。
- 诊断卡片区固定包含 `Token Timeline + Cache Health`、`Tool Cost & ROI`、`Bug Mining & Regression Seeds`、`Context Budget`。
- 主内容区固定包含 `Trace`、`Payload` 两个 tab。
- Trace tab 固定为筛选条加 trace round table；round 展开后展示按时间顺序排列的步骤卡片。
- Payload tab 固定为左右布局：左侧 call selector，右侧 selected call detail。
- MHTML 导出必须保留 Hero KPI、诊断卡片、Trace 展开、payload modal、Payload tab 切换和 attribution 展开交互。

## 文字内容

- 主 tab 文案固定为 `Trace`、`Payload`。
- Hero KPI label 固定为 `Total Tokens`、`Cache Reuse`、`Rounds`、`LLM Calls`、`Tool Calls`、`Time`。
- 诊断卡标题固定为 `Token Timeline + Cache Health`、`Tool Cost & ROI`、`Bug Mining & Regression Seeds`、`Context Budget`。
- Trace table 列名固定为 `Round`、`Summary`、`Metrics`、`Signals`、`Time`。
- Payload 右侧标题固定为 `Selected Call Detail`。
- Round 标题使用 `R<round_number>` 加 summary；summary 缺失时显示 `Untitled round`。
- 原文缺失时显示 unavailable 原因、precision 和 source，不用空白区域代替。

## Hero KPI

### Total Tokens

- 一级值：`Fresh + Cache Read + Cache Write + Output`。
- 二级指标固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
- `Fresh` 表示 provider billed input 中没有命中 cache 的输入 token。
- `Cache Read` 表示 provider reported cache read input token。
- `Cache Write` 表示 provider reported cache creation/write input token。
- `Output` 表示模型可见输出 token，不把隐藏 reasoning token 混入该值。
- 四个二级指标合计必须等于一级值；无法对齐时一级值显示 `N/A`，tooltip 说明缺失字段、来源和精度。

### Cache Reuse

- 一级值：`Cache Read / (Fresh + Cache Read + Cache Write)`。
- 二级指标固定为 `Input-side Tokens`、`Fresh Spike Rounds`、`Low-cache Rounds`。
- `Input-side Tokens` 表示 `Fresh + Cache Read + Cache Write`。
- `Fresh Spike Rounds` 表示 fresh token 高于当前 session round fresh token 中位数 2 倍的 round 数。
- `Low-cache Rounds` 表示 round-level cache read ratio 小于 20.0% 的 round 数。
- 分母为 0 时一级值显示 `N/A`，tooltip 展示 `Input-side Tokens = 0`。

### Rounds

- 一级值：assistant round 数。
- 二级指标固定为 `User Prompts`、`Assistant Turns`、`Subagent Runs`。
- `User Prompts` 表示人工输入触发的 user message 数。
- `Assistant Turns` 表示主 agent assistant 输出轮数。
- `Subagent Runs` 表示独立 subagent 上下文启动次数。

### LLM Calls

- 一级值：主 agent LLM call 加 subagent LLM call 总数。
- 二级指标固定为 `Main-agent Calls`、`Subagent Calls`、`Avg Tokens / Call`。
- `Main-agent Calls` 表示当前 session 主 agent 发起的 LLM call 数。
- `Subagent Calls` 表示 subagent 内部发起的 LLM call 数。
- `Avg Tokens / Call` 表示 `Total Tokens / LLM Calls`，分母为 0 时显示 `N/A`。

### Tool Calls

- 一级值：tool call 总数。
- 二级指标固定为 `Distinct Tools`、`Failed Tools`、`Failure Rate`。
- `Distinct Tools` 表示出现过的 tool name 去重数量。
- `Failed Tools` 表示失败 tool result 数。
- `Failure Rate` 表示 `Failed Tools / Tool Calls`，分母为 0 时显示 `N/A`。
- `Failed Tools` 不再作为独立一级 KPI，避免和该卡重复。

### Time

- 一级值：`Process Time`。
- 二级指标固定为 `Duration`、`Waiting Time`、`Updated`。
- `Duration` 使用 `common.md` 的通用时间口径。
- `Process Time` 使用 `common.md` 的主动处理耗时口径。
- `Waiting Time = Duration - Process Time`。
- `Updated` 表示 session 最新 indexed event timestamp。

## 诊断卡片

### 诊断区整体排版

- 宽屏 `>= 1440px`：诊断区使用 2 列 grid。
- 宽屏第 1 行：`Token Timeline + Cache Health` 跨 2 列。
- 宽屏第 2 行：左列 `Tool Cost & ROI`，右列 `Bug Mining & Regression Seeds`。
- 宽屏第 3 行：`Context Budget` 跨 2 列。
- 标准桌面 `1024px-1439px`：诊断区保持 2 列 grid；`Token Timeline + Cache Health` 和 `Context Budget` 跨 2 列，另外两张卡各占 1 列。
- 窄屏 `< 1024px`：诊断区改为单列，四张卡按固定顺序纵向排列。
- 每张卡 header 高度固定为 44px，body 最小高度固定为 220px。
- 诊断卡不嵌套子卡；内部 stat 使用 compact stat 行，表格使用 `common.md` 的 `Compact Table`。

### Token Timeline + Cache Health

- 卡片定位：展示每个 round 的 token 构成和 cache reuse 健康度，是 Session Detail 的第一诊断入口。
- 图表区域占卡片 body 高度的 72%；下方 compact stat 行占 28%。
- 图表类型固定为按 round 顺序排列的堆叠柱状图。
- x 轴显示 round number，标签格式固定为 `R1`、`R2`、`R3`。
- 左 y 轴显示 total tokens，轴标题固定为 `Tokens`。
- 右 y 轴显示 cache read ratio，轴标题固定为 `Cache Read %`，范围固定为 0% 到 100%。
- 堆叠顺序固定为 Fresh、Cache Read、Cache Write、Output。
- Cache Read Ratio 以折线叠加在柱状图上；折线只使用右 y 轴。
- 不渲染配套明细表；round 和 call 细节通过 `common.md` 的 `Chart Tooltip` 展示。
- tooltip header 固定展示 round id 和 round start time。
- tooltip 行顺序固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`、`Total`、`Cache Read Ratio`、`LLM Calls`、`Tool Calls`。
- tooltip value 列右对齐，share 列右对齐，Total 行上方显示 separator。
- tooltip note 区展示 fallback、missing usage、fresh spike、low cache 中命中的诊断说明。
- 下方 compact stat 固定显示 `Input-side Tokens`、`Cache Read Ratio`、`Fresh Spike Rounds`、`Low-cache Rounds`。

### Tool Cost & ROI

- 卡片定位：展示工具调用是否产生高成本、失败和重复调用压力。
- 顶部 compact stat 固定显示 `Tool Calls`、`Distinct Tools`、`Failed Tools`。
- 下方固定展示 `Tool Summary` `Compact Table`。
- `Tool Summary` 行数固定为调用次数最高的 5 个工具。
- `Tool Summary` 列固定为 `Tool`、`Calls`、`Tokens`、`Failure`。
- `Tool` 示例值：`Read`、`Bash`、`Grep`、`WebFetch`。
- `Calls` 示例值：`12`，表示该 tool 在当前 session 的调用次数。
- `Tokens` 示例值：`42.1k`，表示该 tool 相关 context/result 估算 token。
- `Failure` 示例值：`2 · 16.7%`，前者为失败次数，后者为失败率。
- 表格长文本通过 `common.md` 的 `Chart Tooltip` 底部 note 样式展示完整 tool name、top command、失败摘要和来源。

### Bug Mining & Regression Seeds

- 卡片定位：沉淀可复现缺陷线索，服务 UI 质量门、parser 回归和 payload 诊断。
- 该卡只展示失败信号 `Compact Table`，不展示图表。
- 行数固定为最高严重度的 5 条信号。
- 列固定为 `Signal`、`Evidence`、`Seed`。
- `Signal` 示例值：`Tool failure`、`Round API 500`、`Parser fallback`、`Payload unavailable`、`Attribution error`。
- `Evidence` 示例值：`Bash exit 1 · /api/sessions/.../round/3`，最长 120 字符，超出后截断。
- `Seed` 示例值：`session_id + R3 + call_2`，点击复制完整复现定位串。
- severity 不单独占列，通过 `Signal` badge tone 表示：critical 使用红色，warning 使用琥珀色，info 使用灰色。
- 没有信号时展示 `No regression seed found` 空态，空态保留卡片高度。

### Context Budget

- 卡片定位：解释本次 session 的上下文预算被哪些内容消耗。
- 图表类型固定为水平分段条形图。
- 分段固定为 System、History Messages、Current User Prompt、Tool Results、Subagent Context、Output。
- x 轴显示 token share，范围固定为 0% 到 100%。
- y 轴只有一行，标题固定为 `Session Context`。
- 分段条下方固定展示 legend；legend 顺序和分段顺序一致。
- 不渲染配套明细表；细节通过 `common.md` 的 `Chart Tooltip` 展示。
- tooltip 固定展示 `Segment`、`Tokens`、`Share`、`Source`、`Precision`。
- 卡片标题栏右侧固定显示统计层级，候选值固定为 `Session-level`、`Selected round`。

## Trace Tab

### Trace Tab 目标

- Trace 是默认打开的 tab，是当前仓库最高频调试入口。
- Trace 默认以 table 形态展示 round 列表，保证长 session 能快速扫描、排序和定位失败。
- Round 展开后使用 step card 形态展示详细过程，吸收高保真稿中可读性更好的时间线结构。
- Trace 和 Payload 使用同一 call id、round id、payload id，必须能互相定位。

### Trace Toolbar

- toolbar 左侧固定展示说明文案：`Round 内按时间顺序纵向推进；并发 tool calls 作为一个 batch 分组显示。`
- toolbar 右侧固定展示 status segmented control 和 expand control。
- status segmented control 候选项固定为 `All`、`Failed`。
- expand control 是一个全局 toggle，文案固定在 `Expand all` 和 `Collapse all` 之间切换。
- 后续加入搜索控件时，搜索框固定放在 toolbar 左侧说明文案下方，不改变 status segmented control 的位置。
- Trace filter 状态必须写入 URL 参数 `trace_status`。

### Trace Round Table

- 表格固定使用 5 列：`Round`、`Summary`、`Metrics`、`Signals`、`Time`。
- `Round` 列宽固定为 72px，展示 `R<round_number>` 和状态色。
- `Summary` 列占剩余主宽，展示 round summary。
- `Metrics` 列宽固定为 220px，展示 tool count、LLM call count、`Token Cell`。
- `Signals` 列宽固定为 180px，展示 failed、manual input、subagent、payload missing、attribution error 的 badge。
- `Time` 列宽固定为 132px，展示 round start time。
- `Summary` 示例值：`Fix template macro scope`，表示该 round 的主要动作摘要。
- `Metrics` 示例值：`2 tools · 1 LLM · 24.1k`，token 数值后跟 `Tokenbar`。
- `Signals` 示例值：`Failed`、`Subagent`、`Manual Input`。
- `Time` 示例值：`14:23:11`，tooltip 展示完整 timestamp、round duration、process time。
- table header 中只有 `Metrics` 的 token 排序入口可点击，排序字段固定为 total tokens。
- 当前展开 row 必须有明确背景色，并和下一行 expanded detail 视觉连在一起。

### Expanded Round Detail

- expanded detail 只在当前 round 展开时渲染。
- detail 内部固定为一条纵向 timeline，左侧是 timeline rail，右侧是 step card。
- step 顺序固定为原始 trace 顺序；同一时间段内的并发 tool calls 合并为一个 `Tool Batch`。
- step 类型固定为 `User Message`、`LLM Call`、`Tool Batch`、`Tool Result`、`Subagent Run`、`System Signal`。
- `User Message` card 展示 role、摘要、timestamp、输入 preview；preview 最长 3 行。
- `LLM Call` card 展示 call index、model、lane、status、input/cache read/cache write/output 四项 usage。
- `LLM Call` card 操作固定为 `Request`、`Response`、`Request 归因`、`Response 归因`、`Open in Payload`。
- `Tool Batch` card header 展示 batch title、tool 数、失败数、duration。
- `Tool Batch` card body 使用行式列表，列固定为 tool name、command preview、result preview、status、duration、`Result` action。
- `Subagent Run` card 展示 subagent name、独立上下文 badge、status、sub-round 数、token summary。
- `Subagent Run` 内部的 sub-round 按 `SR<sub_round_id>` 展示，保留内部 LLM call 和 tool batch。
- `System Signal` card 展示 parser fallback、payload missing、round API error、attribution error。

### LLM Call Attribution

- `Request 归因` 入口打开 request attribution payload。
- request attribution 内容固定包含请求摘要、时间线、用量分布、归因明细、参数可用性、重建上下文预览。
- 请求摘要字段固定为 agent、model、source、total input、fresh input、cache read、cache write、unknown、coverage。
- `Response 归因` 入口打开 response attribution payload。
- response attribution 内容固定包含响应摘要、归因备注、响应总览、用量分布、归因明细、blocks 明细、可见内容摘要、参数可得性。
- 响应摘要字段固定为 agent、model、source、request_id、call_id、total output、visible text、tool use、metadata、coverage、finish reason。
- attribution bucket card header 固定展示 bucket label、precision、tokens、percent、expand chevron。
- bucket 展开区展示 source、content preview、解释文本和动态加载结果。

### Payload Modal

- Trace 内点击 `Request`、`Response`、`Result`、`Request 归因`、`Response 归因` 时打开 payload modal。
- modal header 固定展示 payload title、payload id、Close button。
- modal body 固定为 metadata rail 加 main content 的双栏布局。
- metadata rail 展示 kind、status、size、source、tool、tool status 中可用字段。
- main content 根据 payload kind 展示 context、response、tool result、attribution、diagnostic error。
- payload 内容缺失时 modal 不显示空白，必须展示 requested payload、metadata、possible reasons。
- modal 内必须提供 `Open in Payload tab` 操作，点击后切换到 Payload tab 并选中同一 call。

## Payload Tab

### Payload Tab 目标

- Payload tab 是持久化深度查看区，服务原始请求、原始响应、tool result、subagent payload 和 attribution 对照。
- Payload tab 不替代 Trace 的 quick modal；它用于长内容阅读、复制、跨 call 比较和从 payload 反向定位 trace step。

### Payload Layout

- Payload tab 固定为两栏 grid。
- 左侧 call selector 宽度固定为 320px，右侧 selected call detail 占剩余宽度。
- 标准桌面和宽屏保持两栏；窄屏 `< 1024px` 改为上下布局，call selector 在上，detail 在下。
- call selector 使用 sticky header，滚动区域只在左栏内部滚动。
- selected call detail header sticky 在右栏顶部，内容区域内部滚动。
- 左右两栏的滚动互不影响。

### Call Selector

- call selector 数据来自当前 session 的 LLM call、subagent call、tool result payload。
- 列表按 trace 顺序排列，并按 round 分组。
- 分组标题格式固定为 `R<round_number> · <round summary>`。
- call item 标题格式固定为 `LLM Call #<index>`、`Subagent · <name>`、`Tool Result · <tool name>`。
- call item meta 固定展示 model、status、input token、output token、payload availability。
- call item 右侧固定展示 status badge：`available`、`partial`、`missing`、`error`。
- 默认选中第一个 failed call；没有 failed call 时选中第一个 LLM call。
- 当前选中项必须有左侧 active bar 和背景色。

### Selected Call Detail

- detail header 固定展示 selected call title、round id、model、status、token summary、timestamp。
- detail header actions 固定为 `Copy raw`、`Open trace step`、`Copy call id`。
- detail body 固定按顺序展示 `Overview`、`Request Attribution`、`Response Attribution`、`Raw Request`、`Raw Response`、`Related Results`。
- `Overview` 展示 call id、payload id、source、precision、duration、process time、availability。
- `Request Attribution` 使用左右结构：左侧 request summary，右侧 bucket detail。
- `Response Attribution` 使用左右结构：左侧 response summary，右侧 bucket detail。
- attribution bucket 列固定为 `Bucket`、`Tokens`、`Share`、`Source`、`Precision`。
- `Bucket` 示例值：`History messages`、`Tool results`、`Current user prompt`、`System sources`、`Visible text`、`Tool use`。
- `Tokens` 示例值：`12.2k`，表示该 bucket 估算 token 数。
- `Share` 示例值：`47.8%`，表示该 bucket 在当前 request input、response output 归属总量中的比例。
- `Source` 示例值：`provider reported`、`transcript`、`local estimate`。
- `Precision` 示例值：`exact`、`estimated`、`residual`、`unavailable`。
- `Raw Request` 和 `Raw Response` 均固定包含 `Rendered`、`Raw` 分段控件。
- `Rendered` 展示结构化 block、message role、tool_use、tool_result 和 text preview。
- `Raw` 展示原始 JSON 和原始文本，使用 mono 字体和内部滚动。
- `Related Results` 展示和该 call 直接关联的 tool result、subagent result、diagnostic payload。

### Payload Empty And Error States

- 当前 session 没有 call 时，call selector 显示 `No payload-capable calls`，右侧展示回到 Trace 的操作。
- selected call 缺少 request payload 时，`Raw Request` 显示 unavailable reason、source、precision。
- selected call 缺少 response payload 时，`Raw Response` 显示 unavailable reason、source、precision。
- attribution 构建失败时，对应 attribution 区块展示 error type、message、fallback、source，不隐藏区块。
- payload 内容超过 1000 行时，默认折叠到前 200 行，`Raw` 区顶部展示 `Show full raw`。

## Trace Tab 交互逻辑

### Trace 默认状态

- 页面进入时默认打开 Trace tab。
- 默认展开第一个 failed round；没有 failed round 时展开 R1。
- URL 中存在 `round=<round_number>` 时，优先展开该 round 并滚动到可视区域顶部。
- Trace filter 默认值为 `All`。

### Trace 操作

- 点击 round header 和 round row 任意非按钮区域切换展开状态。
- 点击 row 内按钮只执行按钮动作，不触发 round toggle。
- 点击 `Expand all` 展开所有 round，并把按钮文案切换为 `Collapse all`。
- 点击 `Collapse all` 收起所有 round，再恢复默认展开规则。
- 选择 `Failed` 后只显示 failed round 和含失败信号的 round。
- status filter、展开状态、选中 round 必须写入 URL 参数。
- 键盘 focus 到 round row 后按 Enter 切换展开状态。
- payload modal 打开时，Esc 关闭 modal；modal 关闭后 focus 回到触发按钮。
- lazy-loaded round detail 请求失败时，expanded detail 行展示 retry 操作，不折叠当前 round。

### Trace 到 Payload

- 点击 `Open in Payload` 切换到 Payload tab，并选中同一 call。
- 点击 payload modal 内 `Open in Payload tab` 执行同一跳转逻辑。
- Trace 跳转到 Payload 时，Payload URL 参数固定写入 `payload_call_id=<call_id>`。

## Payload Tab 交互逻辑

### Payload 默认状态

- 直接打开 Payload tab 时，默认选中 URL 中 `payload_call_id` 对应的 call。
- URL 中没有 `payload_call_id` 时，默认选中第一个 failed call。
- 没有 failed call 时，默认选中第一个 LLM call。
- 没有 payload-capable call 时，右侧展示空态。

### Payload 操作

- 点击 call selector item 更新右侧 detail，并写入 `payload_call_id` URL 参数。
- `Copy raw` 复制当前 selected call 的 raw request 和 raw response 合并文本。
- `Copy call id` 复制当前 selected call id。
- `Open trace step` 切换到 Trace tab，展开对应 round，并滚动到对应 step card。
- 点击 attribution bucket header 展开该 bucket；再次点击收起。
- 动态 bucket 内容加载中显示 inline loading，失败时展示错误摘要和 retry。
- `Rendered` 和 `Raw` 分段控件只影响当前 raw section，不影响另一个 raw section。
- `Show full raw` 展开当前 raw section 的完整内容，并保持内部滚动位置。
- Payload tab 切回 Trace 后，Payload 的 selected call 状态保留在 URL 参数中。

## 数据口径

- Created、Updated、Duration、Process Time 使用 `common.md` 的通用时间口径。
- Rounds 使用当前 session 的 assistant round 计数。
- LLM Calls 使用主 agent 和 subagent 的 LLM call 合计。
- Tool Calls 使用 tool call 计数；Failed Tools 使用失败 tool result 计数。
- Subagent Runs 使用独立 subagent 上下文启动次数。
- Output 来自模型可见输出 token，不把 hidden reasoning token 混入可见输出。
- Trace、Payload、payload modal 内的 token 值必须共享同一 usage source。
- 不同来源数据产生差异时，必须展示 source、precision、fallback reason。

## 状态

- session 数据不可用：展示错误状态和 `Back to Sessions`。
- 无 round：Trace 显示空态和可执行下一步。
- call 没有 raw request：`Raw Request` 显示 unavailable 原因、precision、source。
- call 没有 raw response：`Raw Response` 显示 unavailable 原因、precision、source。
- attribution 构建失败：显示错误摘要、fallback 和来源，不隐藏该区块。
- payload 太长：默认 preview，提供 `Show full raw` 和 `Copy raw`。
- payload API 返回 500：modal 和 Payload tab 均展示错误状态、payload id、retry 操作。

## 禁止项

- 不存在独立 Attribution tab。
- 不存在独立 Insights tab。
- 不在页面中展示 All Sessions 表格。
- 不展示 Selected LLM calls、Round diagnostics、sidecar filter。
- 不恢复 Round Map、Inspector 默认三栏、Map/Inspector/Focus 模式按钮、Density toggle、无效占位按钮。
- 不把 Trace 默认形态改成纯卡片列表；纯卡片列表只用于 round 展开后的 step detail。
