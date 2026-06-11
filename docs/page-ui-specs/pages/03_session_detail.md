# Session Detail 页面规约

## 定位

Session Detail 是单个 session 的运行分析页，用于在首屏回答本次运行的健康状态、成本、缓存、工作量和耗时，并在诊断区解释成本来源、可疑 round/call/subagent、工具影响、payload 覆盖和上下文预算。目标结构只保留 `Trace`、`Payload` 两个主 tab，Trace/Payload 作为下钻工作区。

## 页面布局

- 路由固定为 `/sessions/<agent>/<session_id>`；模板固定为 `session.html`；MHTML 导出参数固定为 `?export=mhtml`。
- 面包屑固定为 `Dashboard / Sessions / <agent> / <short session id>`。
- 首屏顺序固定为 Page Head、Hero KPI、诊断卡片区、主 tab。
- Hero KPI 区展示 session 标题、agent、session id copy、session 本地文件路径 copy 和 5 张一级 KPI：`Run Health`、`Total Tokens`、`Cache Health`、`Workload`、`Active Time`。
- Hero 下方 summary strip 只展示未在 hero/meta/KPI 中重复出现的短状态信息，例如 `updated`、`branch`；不得重复展示 session id、model、project、created。
- 诊断卡片区固定包含 `Main Agent Breakdown`、`Context Budget`、`Tool Impact`、`Subagent Breakdown`、`Issues & Repro Seeds`。
- 主内容区固定包含 `Trace`、`Payload` 两个 tab。
- Trace tab 固定为筛选条加 trace round table；round 展开后展示按时间顺序排列的步骤卡片。
- Payload tab 固定为左右布局：左侧 call selector，右侧 selected call detail。
- MHTML 导出必须保留 Hero KPI、诊断卡片、Trace 展开、payload modal、Payload tab 切换和 attribution 展开交互。

## 文字内容

- 主 tab 文案固定为 `Trace`、`Payload`。
- Hero KPI label 固定为 `Run Health`、`Total Tokens`、`Cache Health`、`Workload`、`Active Time`。
- Hero 本地文件路径行 label 固定为 `Session file`，展示索引或解析阶段定位到的本地 JSONL 绝对路径；路径缺失时不渲染该行。
- Hero 本地文件路径行必须提供 `Copy session file path` 按钮，按钮使用统一 `data-action="copy"` 和完整 `data-copy-text` 路径，供用户直接粘贴到终端或编辑器。
- 每张一级 KPI 下方二级 KPI 数量允许为 0-4；实际 Session Detail 首屏每张卡保留 3-4 个高信息量二级 KPI，不为了视觉对齐添加低价值指标。
- 每个一级 KPI 和二级 KPI 必须提供 tooltip，解释当前指标口径、分母、来源或定位入口。
- 诊断卡标题固定为 `Main Agent Breakdown`、`Context Budget`、`Tool Impact`、`Subagent Breakdown`、`Issues & Repro Seeds`。
- Trace table 列名固定为 `Round`、`Summary`、`Metrics`、`Signals`、`Time`。
- Payload 右侧标题固定为 `Selected Call Detail`。
- Round 标题使用 `R<round_number>` 加 summary；summary 缺失时显示 `Untitled round`。
- 原文缺失时显示 unavailable 原因、precision 和 source，不用空白区域代替。

## Hero KPI

### Run Health

- 一级值固定为 `Completed`、`Completed with issues`、`Failed` 三选一。
- 二级指标固定为 `Issue Rounds`、`Failed Tools`、`Payload Gaps`、`Attribution Gaps`。
- `Issue Rounds` 表示含 tool failure、LLM error、payload gap、attribution gap 或 session anomaly 的 round 数。
- `Failed Tools` 使用全局失败 tool call 口径，并展示 `失败数 · 失败率`；失败率按比例标记 ok/warn/bad 色。
- `Payload Gaps` 表示 Payload tab selector item 中 `missing` 或 `error` 的缺口数量。
- `Attribution Gaps` 表示 request/response attribution 构建失败或不可用的数量。
- 只要 Tool failure、LLM error、payload missing、attribution error 任一存在，Hero issue strip 不得显示 `No issues found`。

### Total Tokens

- 一级值：`Fresh + Cache Read + Cache Write + Output`。
- 二级指标固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
- `Fresh` 表示本次请求实际新增/发送的输入规模，cache read 和 cache write 作为独立组件展示，不从 Fresh 扣减。
- `Cache Read` 表示 provider reported cache read input token。
- `Cache Write` 表示 provider reported cache creation/write input token。
- `Output` 表示模型可见输出 token，不把隐藏 reasoning token 混入该值。
- 四个二级指标合计必须等于一级值；无法和来源总量对齐时一级值仍显示 component sum，tooltip 说明 component sum、source total、缺失字段、来源和精度。
- 四个二级 token 指标展示 `绝对值 · 占比`，占比相对 Total Tokens，并按占比标记颜色。

### Cache Health

- 一级值：`Cache Read / (Fresh + Cache Read + Cache Write)`。
- 二级指标固定为 `Input-side Tokens`、`Low-cache Rounds`、`Fresh Spike Rounds`。
- `Input-side Tokens` 表示 `Fresh + Cache Read + Cache Write`。
- `Low-cache Rounds` 表示 round-level cache read ratio 小于 20.0% 的 round 数。
- `Fresh Spike Rounds` 表示 fresh token 高于当前 session round fresh token 中位数 2 倍的 round 数。
- 分母为 0 时一级值显示 `N/A`，tooltip 展示 `Input-side Tokens = 0`。

### Workload

- 一级值：主 agent LLM call 加 subagent LLM call 总数。
- 二级指标固定为 `Main Calls`、`Subagent Calls`、`Tool Calls`、`Subagent Runs`。
- `Main Calls` 表示当前 session 主 agent 发起的 LLM call 数。
- `Subagent Calls` 表示 subagent 内部发起的 LLM call 数。
- `Tool Calls` 使用全局 tool call 总数；如需展示主 agent 口径，只在 tooltip 或 Tool Impact 中说明 `Main tools`。
- `Subagent Runs` 表示独立 subagent 上下文启动次数。

### Active Time

- 一级值：`Process Time`。
- 二级指标固定为 `Duration`、`Waiting Time`、`Model Time`、`Tool Time`。
- `Duration` 使用 `common.md` 的通用时间口径。
- `Process Time` 使用 `common.md` 的主动处理耗时口径。
- `Waiting Time = Duration - Process Time`。
- `Model Time` 使用 session model execution seconds；不可得时显示 `N/A`，不隐藏。
- `Tool Time` 使用 session tool execution seconds；不可得时显示 `N/A`，不隐藏。

## 诊断卡片

### 诊断区整体排版

- 宽屏 `>= 1440px`：诊断区使用 2 列 grid。
- 宽屏第 1 行：`Main Agent Breakdown` 跨 2 列。
- 宽屏第 2 行固定为 `Context Budget`、`Tool Impact` 两列。
- 后续行按固定顺序排布：`Subagent Breakdown`、`Issues & Repro Seeds`；其中 `Subagent Breakdown` 必须跨 2 列占整行。
- 标准桌面 `1024px-1439px`：诊断区保持 2 列 grid；`Main Agent Breakdown` 和 `Subagent Breakdown` 跨 2 列，其他卡各占 1 列。
- 窄屏 `< 1024px`：诊断区改为单列，全部卡片按固定顺序纵向排列。
- 每张卡 header 高度固定为 44px，body 最小高度固定为 220px。
- 诊断卡不嵌套子卡；内部 stat 使用 compact stat 行，表格使用 `common.md` 的 `Compact Table`。

### Main Agent Breakdown

- 卡片定位：展示主 agent 每个 round 的 token 构成、cache reuse 健康度和高成本 call，是 Session Detail 的第一诊断入口。
- 图表类型固定为按 round 顺序排列的堆叠柱状图。
- x 轴显示 round number，标签格式固定为 `R1`、`R2`、`R3`。
- 左 y 轴显示 total tokens，轴标题固定为 `Tokens`。
- 右 y 轴显示 cache read ratio，轴标题固定为 `Cache Read %`，范围固定为 0% 到 100%。
- 堆叠顺序固定为 Fresh、Cache Read、Cache Write、Output。
- Cache Read Ratio 以折线叠加在柱状图上；折线只使用右 y 轴。
- 低缓存 round、fresh spike round、payload missing/error round 不在柱子附近显示文字 badge；命中任一诊断标签时，只在该 round 下方显示一个红色 spike 三角 marker。
- 点击柱子跳到 Trace 对应 round，并写入 `tab=trace&round=<round_number>`；目标 round 必须靠近视口顶部，不得居中或偏下。
- 不渲染配套明细表；round 和 call 细节通过 `common.md` 的 `Chart Tooltip` 展示。
- tooltip header 固定展示 round id 和 round start time。
- tooltip 行顺序固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`、`Total`、`Cache Read Ratio`、`Calls`。
- tooltip value 列右对齐，share 列右对齐，Total 行上方显示 separator。
- tooltip 必须使用 viewport 级 fixed 浮层，并基于鼠标位置渲染在鼠标上方；横向根据鼠标离左右屏幕边缘的剩余空间选择右上或左上，且不得遮挡当前 hover 的柱子、spike 或 x 轴标签。
- tooltip note 区使用 `Badge Text` 作为标签名，展示 fallback、missing usage、fresh spike、low cache、payload gap、cost driver 中命中的完整 badge 文本；红色 spike 三角只作为“该 round 有 badge text”的视觉提示，不承载截断文本。
- 命中 Top 5 cost driver 的主 agent call 必须在对应 round 的 `Badge Text` 中展示完整 driver、tokens、share、model。
- `Call Cost Distribution` 和 `Top Cost Drivers` 不再作为独立诊断卡渲染；主 timeline tooltip 不展示 `Call Tokens`、`Call Cost`、`Top Call`、`Top Lane` 或 main/subagent split。主 agent 成本由本卡 tooltip 表达，subagent 成本由 `Subagent Breakdown` 表达，tool result 成本由 `Tool Impact` 表达。
- tooltip 中 `Fresh`、`Cache Read`、`Cache Write`、`Output` 使用对应颜色方块；`Cache Read Ratio` 使用对应颜色短横线。
- 下方不渲染重复 compact stat；`Input-side Tokens`、`Cache Read Ratio`、`Fresh Spike Rounds`、`Low-cache Rounds` 已在 Hero KPI 或 tooltip 中表达。

### Tool Impact

- 卡片定位：展示工具调用体量、失败和结果 token 压力。
- 不在顶部渲染 compact stat；全局汇总固定合并到表格底部 summary 行。
- `All Tool Calls` 使用全局 tool_calls 总数。
- 表格行数固定为 top 5 tools，排序优先级为调用次数、result token、tool name。
- 列固定为 `Tool`、`Calls`、`Result Tokens`、`Failures`。
- `Failures` 展示 `失败数 · 失败率`，失败率按比例标记 ok/warn/bad 色。
- tooltip 必须拆分 `Main` 与 `Subagent` 调用数，避免 Hero 和表格口径冲突。

### Subagent Breakdown

- 卡片定位：展示 subagent 是否贡献了主要成本、工具调用和失败，并支持查看单个 subagent 内部的 token/cache 走势。
- 卡片必须跨 2 列占整行，内部固定为 1/3 + 2/3 两列布局。
- 左侧 1/3 为 subagent 列表和摘要信息；每个 subagent 必须单行展示 subagent name、短 subagent id、LLM calls、Footprint Tokens、Tools、Failures。
- 左侧列表最多同时显示 5 个 subagent；超过 5 个时列表区域固定高度并在内部上下滚动，不得继续撑高整张卡片。
- `Instance` 使用和 call/subagent 颜色映射一致的实例颜色；多个 subagent 共享同一颜色时仍展示不同短 id。
- subagent cost driver 的 tokens、share、reason 必须合并到对应 subagent 行的 tooltip 或 compact metadata，不再单独出现在 Top Cost Drivers 表格。
- `Footprint Tokens` 表示 subagent 内部 LLM token、父 Agent result token、内部 tool result token 的 footprint 合计；tooltip 必须拆分来源。
- 点击左侧 subagent 行时，只切换右侧 timeline，不直接跳转 Trace；行内可保留独立 Trace 跳转按钮后续扩展。
- 右侧 2/3 展示选中 subagent 的 token/cache timeline，视觉和交互与主 `Main Agent Breakdown` 的 timeline 一致，但 x 轴标签使用 subagent round（`SR1`、`SR2`）。
- 右侧 subagent timeline tooltip 固定展示 subagent id、parent round、subagent round、Fresh、Cache Read、Cache Write、Output、Total、Cache Read Ratio、Calls。
- 默认选中 Footprint Tokens 最高的 subagent；没有 subagent 时展示统一空态 `No subagent runs indexed`。

### Issues & Repro Seeds

- 卡片定位：沉淀可复现缺陷线索，服务 UI 质量门、parser 回归和 payload 诊断。
- 不渲染顶部类型聚合卡；问题类型聚合用于排序和 Hero issue strip，不在卡片内重复展示。
- 表格行数固定为最高严重度的 5 条问题。
- 列固定为 `Issue`、`Evidence`、`Round`、`Locator`。
- `Issue` 示例值：`Tool failure`、`LLM error`、`Payload gap`、`Attribution error`。
- `Evidence` 示例值：`Bash exit 1`，最长 160 字符，超出后截断。
- `Round` 示例值：`R3`，点击跳到 Trace 对应 round。
- `Locator` 展示 `Copy locator` 操作，点击复制完整复现定位串，定位串格式包含 session、round 和 payload/tool/call id。
- severity 不单独占列，通过 `Issue` badge tone 表示：critical 使用红色，warning 使用琥珀色，info 使用灰色。
- 没有问题时展示统一空态 `No actionable issues detected`；有失败时 Hero 不得显示 `No issues found`。

### Context Budget

- 卡片定位：解释本次 session 的上下文预算被哪些内容消耗。
- 图表类型固定为水平分段条形图。
- 分段固定为 System、History Messages、Current User Prompt、Tool Results、Subagent Context、Output。
- x 轴显示 token share，范围固定为 0% 到 100%。
- y 轴只有一行，标题固定为 `Session Context`。
- 分段条可在空间足够时内嵌分类名和占比；窄分段隐藏内嵌文字，但保留 tooltip。
- 分段条下方固定展示 legend；legend 顺序和分段顺序一致，颜色必须和上方对应分段一一匹配。
- 不渲染配套明细表或每分类独立 progress track；细节通过 `common.md` 的 `Chart Tooltip` 展示。
- tooltip 固定展示 `Segment`、`Tokens`、`Share`、`Source`、`Precision`。
- 卡片标题栏右侧固定显示统计层级，候选值固定为 `Session-level`、`Selected round`。
- `unavailable` 不得静默显示为 `0.0%`；必须灰显并标注 `unavailable`。

## Trace Tab

### Trace Tab 目标

- Trace 是默认打开的 tab，是当前仓库最高频调试入口。
- Trace 默认以 table 形态展示 round 列表，保证长 session 能快速扫描、排序和定位失败。
- Round 展开后使用 step card 形态展示详细过程，吸收高保真稿中可读性更好的时间线结构。
- Trace 和 Payload 使用同一 call id、round id、payload id，必须能互相定位。

### Trace Toolbar

- toolbar 左侧固定展示说明文案：`Round 内按时间顺序纵向推进；并发 tool calls 作为一个 batch 分组显示。`
- toolbar 右侧固定展示 status segmented control 和 expand control。
- status segmented control 候选项固定为 `All`、`Failed`、`Low cache`。
- `Low cache` 展示 round-level cache read ratio 小于 20.0% 的 round，用于定位 Hero `Low-cache Rounds`。
- expand control 是一个全局 toggle，文案固定在 `Expand all` 和 `Collapse all` 之间切换。
- 后续加入搜索控件时，搜索框固定放在 toolbar 左侧说明文案下方，不改变 status segmented control 的位置。
- Trace filter 状态必须写入 URL 参数 `trace_status`。

### Trace Round Table

- 表格固定使用 5 列：`Round`、`Summary`、`Metrics`、`Signals`、`Time`。
- `Round` 列宽固定为 72px，展示 `R<round_number>` 和状态色。
- `Summary` 列占剩余主宽，展示 round summary。
- `Metrics` 列宽固定为 220px，展示 tool count、LLM call count、`Token Cell`。
- `Signals` 列宽固定为 180px，固定展示 `Failed`、`Subagent`、`Payload Gap`、`Attribution Gap` 四类 badge；无信号时显示低强调空标记。
- `Time` 列宽固定为 132px，展示 round start time。
- `Summary` 示例值：`Fix template macro scope`，表示该 round 的主要动作摘要。
- `Metrics` 示例值：`2 tools · 1 LLM · 24.1k`，token 数值后跟 `Tokenbar`。
- `Signals` 示例值：`Failed`、`Subagent`、`Payload Gap`、`Attribution Gap`。
- `Time` 示例值：`14:23:11`，tooltip 展示完整 timestamp、round duration、process time。
- table header 中只有 `Metrics` 的 token 排序入口可点击，排序字段固定为 total tokens。
- 当前展开 row 必须有明确背景色，并和下一行 expanded detail 视觉连在一起。

### Expanded Round Detail

- expanded detail 只在当前 round 展开时渲染。
- detail 内部固定为一条纵向 timeline，左侧是 timeline rail，右侧是 step card。
- step 顺序固定为原始 trace 顺序；同一时间段内的并发 tool calls 合并为一个 `Tool Batch`。
- step 类型固定为 `User Message`、`LLM Call`、`Tool Batch`、`Tool Result`、`Subagent Run`、`System Signal`。
- `User Message` card 展示 role、摘要、timestamp、输入 preview；preview 最长 3 行。
- `LLM Call` card 展示 call index、model、lane、status、Fresh/Cache Read/Cache Write/Output 四项 usage。
- `Fresh` 表示 provider-reported 本次请求输入规模，不从 cache read/cache write 扣减，不表示本地重建 request 文本 token 数。
- `LLM Call` card 操作固定为 `Request`、`Response`、`Request 归因`、`Response 归因`、`Open in Payload`。
- `Tool Batch` card header 展示 batch title、tool 数、失败数、duration。
- `Tool Batch` card body 使用行式列表，列固定为 tool name、command preview、result preview、status、duration、`Result` action。
- `Subagent Run` card 展示 subagent name、独立上下文 badge、status、sub-round 数、token summary。
- `Subagent Run` 内部的 sub-round 按 `SR<sub_round_id>` 展示，保留内部 LLM call 和 tool batch。
- `System Signal` card 展示 parser fallback、payload missing、round API error、attribution error。

### LLM Call Attribution

- `Request 归因` 入口打开 request attribution payload。
- request attribution 内容固定包含 topgrid 元信息、用量分布、归因明细、重建上下文预览。
- request attribution 的 topgrid 固定合并展示调用身份、请求摘要、时间线、请求参数与覆盖率；不得再使用左侧 metadata rail 承载这些信息。
- 请求摘要字段固定为 agent、model、source、API family、provider、call id、输入分母、fresh input、cache read、cache write、unknown、coverage。
- request attribution 的输入分母固定为 `Fresh + Cache Read`；`Cache Write` 是 provider reported cache creation/write input token，只在摘要中展示，不进入 request 用量分布、bucket percent、coverage 或 unknown/residual 的分母。
- `Response 归因` 入口打开 response attribution payload。
- response attribution 内容固定包含 topgrid 元信息、用量分布、归因明细、blocks 明细、可见内容摘要。
- response attribution 的 topgrid 固定合并展示调用身份、响应摘要、归因备注与参数可得性；不得再使用左侧 metadata rail 承载这些信息。
- 响应摘要字段固定为 agent、model、source、request_id、call_id、total output、visible text、tool command、metadata、coverage、finish reason。
- response attribution 的工具 bucket 展开区必须展示 assistant response 中实际产生的 tool command / tool input，不得展示 request 侧工具定义或 input schema。
- 用量分布和归因明细必须占用 attribution modal 内容区全宽，不得被 side rail 挤压。
- attribution bucket card header 固定展示 bucket label、precision、tokens、percent、expand chevron。
- attribution bucket percent 为当前弹框中参与分布 bucket 的显示占比，单个 bucket 不得超过 100%。
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
- 窄屏 `< 1024px` 时 call selector 仍必须保留内部最大高度和滚动，不得把 selected call detail 推到几屏之后。

### Call Selector

- call selector 数据来自当前 session 的 LLM call、subagent call、tool result payload。
- 列表按 trace 顺序排列，并按 round 分组。
- 分组标题格式固定为 `R<round_number> · <round summary>`。
- call item 标题格式固定为 `LLM Call #<index>`、`Subagent · <name>`、`Tool Result · <tool name>`。
- call item meta 固定展示 model、status、input token、output token、payload availability。
- call item 右侧固定展示 status badge：`available`、`partial`、`missing`、`error`。
- selector filter 固定为 `All`、`Failed`、`Missing`、`Error`。
- 默认选中第一个 failed/missing/error call；没有问题 call 时选中第一个 LLM call。
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
- URL 中同时存在 `subagent=<subagent_id>` 时，必须在展开父 round 后滚动到对应嵌套 subagent block；若同时存在 `subagentround=<sub_round_id>`，必须滚动到该 subagent 内部的 `SR<sub_round_id>`。
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
- URL 中没有 `payload_call_id` 时，默认选中第一个 failed/missing/error call。
- 没有问题 call 时，默认选中第一个 LLM call。
- 没有 payload-capable call 时，右侧展示空态。

### Payload 操作

- 点击 call selector item 更新右侧 detail，并写入 `payload_call_id` URL 参数。
- 点击 `All / Failed / Missing / Error` 更新 selector 可见项，并写入 `payload_filter` URL 参数。
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
- view model 必须提供统一分析对象：`run_health`、`tool_impact`、`subagent_breakdown`、`subagent_timelines`、`context_budget`；cost driver 仅作为 `Main Agent Breakdown` tooltip、`Subagent Breakdown` 行信息和 `Tool Impact` 的内部派生来源，不再映射为独立卡片。
- 失败信号必须统一汇总 round、tool_calls、subagent_runs、payload selector item、attribution errors，并反向驱动 Hero 状态、Issues 表和 Trace Failed filter。

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
