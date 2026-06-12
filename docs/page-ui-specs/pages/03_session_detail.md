# Session Detail 页面规约

## 定位

Session Detail 是单个 session 的运行分析页，用于在首屏回答本次运行的健康状态、成本、缓存、工作量和耗时，并在诊断区解释成本来源、可疑 round/call/subagent、工具影响、payload 覆盖和上下文预算。目标结构只保留 `Trace`、`Payload` 两个主 tab，Trace/Payload 作为下钻工作区。

## 页面布局

- 路由固定为 `/sessions/<agent>/<session_id>`；模板固定为 `session.html`；MHTML 导出参数固定为 `?export=mhtml`。
- 面包屑固定为 `Dashboard / Sessions / <agent> / <short session id>`。
- 首屏顺序固定为 Page Head、Hero KPI、诊断卡片区、主 tab。
- Hero KPI 区展示 session 标题、agent、session id copy、session 本地文件路径 copy 和 5 张一级 KPI：`Run Health`、`Total Tokens`、`Cache Health`、`Workload`、`Active Time`。
- Hero 下方 summary strip 只展示未在 hero/meta/KPI 中重复出现的短状态信息，例如 `updated`、`branch`；不得重复展示 session id、model、project、created。
- 诊断卡片区固定包含 `Agents Breakdown`、`Context Budget`、`Tool Impact`、`Issues & Repro Seeds`。
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
- 诊断卡标题固定为 `Agents Breakdown`、`Context Budget`、`Tool Impact`、`Issues & Repro Seeds`。
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
- `Fresh` 表示互斥的新输入分段；当 provider 的 cache read 是 input token 子集（例如 OpenAI/Codex `cached_input_tokens`）时，Fresh 使用 `input_tokens - cached_input_tokens`，避免 Total 重复计入缓存命中输入。
- `Cache Read` 表示 provider reported cache read input token。
- `Cache Write` 表示 provider reported cache creation/write input token。
- `Output` 表示模型可见输出 token，不把隐藏 reasoning token 混入该值。
- 四个二级指标合计必须等于一级值；无法和来源总量对齐时一级值仍显示互斥 component sum，tooltip 说明 component sum、source total、缺失字段、来源和精度。
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
- 宽屏第 1 行：`Agents Breakdown` 跨 2 列。
- 宽屏第 2 行固定为 `Context Budget`、`Tool Impact` 两列。
- 后续行按固定顺序排布：`Issues & Repro Seeds`。
- 标准桌面 `1024px-1439px`：诊断区保持 2 列 grid；`Agents Breakdown` 跨 2 列，其他卡各占 1 列。
- 窄屏 `< 1024px`：诊断区改为单列，全部卡片按固定顺序纵向排列。
- 每张卡 header 高度固定为 44px，body 最小高度固定为 220px。
- 诊断卡不嵌套子卡；内部 stat 使用 compact stat 行，表格使用 `common.md` 的 `Compact Table`。

### Agents Breakdown

- 卡片定位：统一展示 main agent 和 subagent 的 token 构成、cache reuse 健康度、高成本 call、工具调用和失败，是 Session Detail 的第一诊断入口。
- 卡片必须跨 2 列占整行，内部固定为 1/3 + 2/3 两列布局。
- 左侧 1/3 为 agent 候选列表和摘要信息；第一项必须是 `main agent`，后续为每个 subagent run。
- 每个候选行必须单行展示 agent name、短 id、LLM calls、Footprint Tokens、Tools、Failures。
- 左侧列表最多同时显示 5 个候选；超过 5 个时列表区域固定高度并在内部上下滚动，不得继续撑高整张卡片。
- `main agent` 默认选中；点击候选行时只切换右侧 timeline，不直接跳转 Trace。
- `main agent` 的 `Footprint Tokens` 使用主 round token 合计；subagent 的 `Footprint Tokens` 表示 subagent 内部 LLM token、父 Agent result token、内部 tool result token 的 footprint 合计，tooltip 必须拆分来源。
- subagent cost driver 的 tokens、share、reason 必须合并到对应 subagent 行的 tooltip 或 compact metadata，不再单独出现在 Top Cost Drivers 表格。
- 右侧 2/3 展示选中 agent 的 token/cache timeline，图表类型固定为按 round 顺序排列的堆叠柱状图。
- `main agent` x 轴显示 session round number，标签格式固定为 `R1`、`R2`、`R3`；subagent x 轴显示 subagent round，标签格式固定为 `SR1`、`SR2`。
- 左 y 轴显示 total tokens，轴标题固定为 `Tokens`。
- 右 y 轴显示 cache read ratio，轴标题固定为 `Cache Read %`，范围固定为 0% 到 100%。
- 堆叠顺序固定为 Fresh、Cache Read、Cache Write、Output。
- Cache Read Ratio 以折线叠加在柱状图上；折线只使用右 y 轴。
- 低缓存 round、fresh spike round、payload missing/error round 不在柱子附近显示文字 badge；命中任一诊断标签时，只在该 round 下方显示一个红色 spike 三角 marker。
- 点击 `main agent` 柱子跳到 Trace 对应 round，并写入 `tab=trace&round=<round_number>`；点击 subagent 柱子写入 `subagent`/`subagentround` 参数并滚动到对应 `SRx`；目标必须靠近视口顶部，不得居中或偏下。
- 不渲染配套明细表；round 和 call 细节通过 `common.md` 的 `Chart Tooltip` 展示。
- `main agent` tooltip header 固定展示 round id 和 round start time；subagent tooltip header 固定展示 subagent round、parent round 和 start time。
- tooltip 行顺序固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`、`Total`、`Cache Read Ratio`、`Calls`。
- tooltip value 列右对齐，share 列右对齐，Total 行上方显示 separator。
- tooltip 必须使用 viewport 级 fixed 浮层，并基于鼠标位置渲染在鼠标上方；横向根据鼠标离左右屏幕边缘的剩余空间选择右上或左上，且不得遮挡当前 hover 的柱子、spike 或 x 轴标签。
- tooltip note 区使用 `Badge Text` 作为标签名，展示 fallback、missing usage、fresh spike、low cache、payload gap、cost driver 中命中的完整 badge 文本；红色 spike 三角只作为“该 round 有 badge text”的视觉提示，不承载截断文本。
- 命中 Top 5 cost driver 的主 agent call 必须在对应 round 的 `Badge Text` 中展示完整 driver、tokens、share、model。
- `Call Cost Distribution` 和 `Top Cost Drivers` 不再作为独立诊断卡渲染；timeline tooltip 不展示 `Call Tokens`、`Call Cost`、`Top Call`、`Top Lane` 或 main/subagent split。main agent 成本由本卡 tooltip 表达，subagent 成本由本卡候选行表达，tool result 成本由 `Tool Impact` 表达。
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

- 表格固定使用 6 列：`Round`、`Summary`、`Metrics`、`Attribution`、`Signals`、`Time`。
- `Round` 列宽固定为 72px，展示 `R<round_number>` 和状态色。
- `Summary` 列占剩余主宽，展示 round summary。
- `Metrics` 列宽固定为 220px，只展示 tool count 和 `Token Cell`；不得展示 LLM call count。
- `Token Cell` 的彩色 tokenbar 宽度必须按当前 session 最大 round token total 归一化，最大 round 为满宽，其他 round 按比例缩短；未占用的轨道使用灰色背景显示与最大 round 的差距。
- `Attribution` 列宽固定为 180px，展示 main request/response attribution 入口；按钮可见文字固定为 `request` 和 `response`，title/tooltip 可展示 call id、payload id、覆盖率和可用性。
- `Signals` 列宽固定为 180px，只在命中 `Failed`、`Subagent`、`Payload Gap`、`Attribution Gap` 时展示对应 badge；无信号时保持空白，不显示占位 badge。
- `Time` 列宽固定为 132px，展示 round start time。
- `Summary` 示例值：`Fix template macro scope`，表示该 round 的主要动作摘要。
- `Metrics` 示例值：`2 tools · 24.1k`，token 数值后跟比例化 `Tokenbar`。
- `Attribution` 示例值：`request · response`，按钮 title 展示 call id、payload id 和覆盖率。
- `Signals` 示例值：`Failed`、`Subagent`、`Payload Gap`、`Attribution Gap`。
- `Time` 示例值：`14:23:11`，tooltip 展示完整 timestamp、round duration、process time。
- table header 中只有 `Metrics` 的 token 排序入口可点击，排序字段固定为 total tokens。
- 当前展开 row 必须有明确背景色和行内状态线；状态线不得超出 row 自身边界或侵入相邻 round。

### Expanded Round Detail

- expanded detail 只在当前 round 展开时渲染。
- detail 内部固定为一条纵向 event timeline，左侧是 timeline rail，右侧是紧凑事件行。
- detail 面板必须与展开 round 行和下一条 round 行保持可见间距；detail 外框不得与上下 round 边框贴合或重合。
- step 顺序固定为原始 trace 顺序；assistant thinking/text、tool_use、tool_result、subagent run 必须按 timestamp 排列。
- step 类型固定为 `User Message`、`Assistant Thinking`、`Assistant Text`、`Tool Call`、`Parallel Tool Group`、`Tool Result`、`Subagent Run`、`System Signal`；expanded timeline 不渲染 `LLM Summary` 或独立 `LLM Call` card。
- `User Message` 行展示 role、摘要、timestamp、输入 preview；preview 最长 3 行，长内容从 payload 打开。
- `Assistant Thinking` 行展示 thinking 摘要、timestamp、source block 和 payload 入口；必须使用与 `Tool Call` 行同等高度的单行紧凑布局，长文本单行截断。
- `Assistant Text` 行展示对用户可见文本摘要、timestamp 和 payload 入口；必须使用与 `Tool Call` 行同等高度的单行紧凑布局，长文本单行截断。该行 payload 只展示 assistant text / thinking 内容，不重复展示同一 LLM response 中已经在后续 `Tool Call` 行平铺展示的 tool command。
- Codex 原始 JSONL 中同一 assistant 文案可能同时出现为 `event_msg.agent_message` 和 `response_item.message role=assistant`；Trace 必须把两者关联为同一个 assistant text 事件，优先使用 `response_item.message` 作为 canonical payload source，`event_msg` 只作为 UI/status mirror 或 fallback，不得重复展示两行相同文本。
- LLM usage、request/response payload 和 request/response attribution 入口由 round summary 行、Payload tab 和 payload modal 承载，不在 expanded timeline 中重复展示。
- `Fresh` 表示 tokenbar 和 Total 的互斥新输入分段；request attribution 摘要可单独展示 provider request input / Provider 总计，用于解释归因分母。
- `Tool Call` 行固定展示 tool name、command preview、result preview、timestamp、duration、result token estimate、`Result` action；duration 优先使用 tool wrapper 输出的 wall time，wall time 缺失或为 0 时使用 tool call 到 tool output 的 timestamp 差值兜底，不得把有明确时间跨度的 tool 统一显示为 `0s`；result token estimate 使用 `~<compact>`，且必须和 Result modal 中的 `result tokens` 数值一致。
- 点击 `Result` 打开的 tool result payload modal 必须在 metadata rail 和 modal subtitle 展示该 result 文本的估算 token 数，字段名固定为 `result tokens`，数值格式为 `~<compact> tokens`；该值表示该 tool result 大概率进入下一次 LLM request 的输入压力，不得标记为 provider reported。
- 只有原始事件同一 assistant block 内触发多个 tool_use，或 tool_use timestamp 差值小于并发阈值时，才合并为 `Parallel Tool Group`；非并发 tool call 不得被无条件合并。
- `Parallel Tool Group` header 展示并发原因、tool 数、失败数、duration，body 使用行式 tool 列表。
- `Subagent Run` 行展示 subagent name、独立上下文 badge、status、sub-round 数、token summary 和局部 `Expand all` / `Collapse all` 控制。
- `Subagent Run` 内部的 sub-round 按 `SR<sub_round_id>` 展示；每个 sub-round summary 行必须可点击或键盘切换自身展开/折叠，并直接展示 request/response attribution 状态和入口，不再默认展开内部 LLM call card。
- `System Signal` 行展示 parser fallback、payload missing、round API error、attribution error。

### LLM Call Attribution

- `Request 归因` 入口打开 request attribution payload。
- Trace round row 和 subround summary 行必须提供 request attribution 入口；Payload tab 保留完整归因详情。
- Trace round row 上 request/response 按钮的可见文字固定为 `request` / `response`；modal title 使用 session 级全局 LLM call 编号，API 定位用的 payload id `llm-R{round}-IX{call}` 可继续使用 round-local call index，不得因此把 R2/R3 等后续 round 显示成重复的 `LLM Call #1`。
- request attribution 内容固定包含 topgrid 元信息、用量分布、归因明细、重建上下文预览。
- request attribution 的 topgrid 固定合并展示调用身份、请求摘要、调用信息/时间线/请求参数与覆盖率；桌面宽度下顶部三个 summary card 必须同一行展示，不得再使用左侧 metadata rail 承载这些信息。
- 请求摘要字段固定为 agent、model、source、API family、provider、call id、内容分母、fresh input、cache read、cache write、Provider 总计、本地重建、coverage、残差；不得在归因明细底部另起 `覆盖率与不确定性` 表格。
- request attribution 不展示泛化的残差可能来源尾注；只有存在可验证、结构化来源时才应进入具体 bucket 或诊断说明。
- request attribution 的内容分母固定为 `Fresh`，用于 request 用量分布、bucket percent、coverage 和 unknown/residual；`Cache Read` 与 `Cache Write` 都是 provider reported accounting 组件，只在摘要中展示，不作为和对话消息、工具结果并列的 request 内容 bucket。
- request attribution 候选分类必须使用全局 token 归因分类树，API payload 必须为每个 bucket 输出 `agent_bucket_key`、`canonical_key`、`category_key`、`category_label`、`color_key`、`display_order`，并把 `label` 规范为全局中文 label；前端颜色和排序必须使用 canonical metadata，不得按 agent raw bucket key 自行决定。
- 全局 request token 归因分类树固定为：`当前用户输入`、`对话消息上下文`、`工具结果上下文`、`工具定义`、`MCP 工具元数据`、`运行上下文片段`、`系统/开发者指令`、`本地指令上下文`、`Agent/Subagent 提示`、`内置系统提示`、`Provider 会话状态`、`推理配置`、`运行时封装开销`、`未定位`。
- 每个 agent 只能在自己的映射规则文件中维护 raw bucket key 到全局分类的映射；例如 Claude Code、Codex、Qoder 的 `tool_schemas` 都必须映射到 `工具定义`，并使用同一个 `color_key=tool_definitions`。
- Claude Code request attribution 的 `API messages 数组` 必须按当前 LLM call 边界重建：依次使用当前 call 之前的 assistant `request_full`、assistant text/tool_use，以及当前 call 的 `request_full`，匹配到当前 call 后停止；不得把后续 round/subround 的 assistant text、tool result 或 request_full 算入当前 request。
- request attribution 的 `API messages 数组` bucket 展开区必须说明它对应发送给模型的 Anthropic API `messages` 字段，并逐条展示 role、content type、tool name、token 估算和内容 preview；bucket 汇总 token 必须使用每条消息的完整 `content_token_estimate` 求和，不得用截断 preview 重新估算；当原始全文在本地日志或重建上下文中可见时，条目必须支持二次展开查看完整内容。
- request attribution 的 `内置系统提示` bucket 若从本地 transcript 捕获到可见 `<system-reminder>` 内容，必须展示脱敏 preview；若未捕获，必须展示明确的不可见/估算说明，不得空白。
- Codex request attribution 在没有 raw request body 时，必须从 rollout 开头可见的 `session_meta.base_instructions` 和 `response_item` 中 role 为 `developer` / `system` 的 message 重建 raw `instructions` bucket，序列化后统一显示为 `系统/开发者指令`。
- Codex parser 必须把 `function_call_output` / `custom_tool_call_output` 作为下一次 assistant request 的 tool output 来源，request attribution 必须将其归入 raw `tool_outputs` bucket，序列化后统一显示为 `工具结果上下文`，不得落入 unknown。
- Codex provider reported `cached_input_tokens` / cache read 必须只作为 request 摘要中的 `Cache Read` 与 `Provider 总计` accounting 信息展示；不得生成 raw `provider_cached_context` bucket，不得计入本地重建 coverage，不得和对话消息、工具结果、工具定义等 request 内容来源并列。
- Codex request attribution 在没有 raw request `tools` 数组时，必须使用 Codex builtin tool catalog 作为 tool schema fallback，并补充本 session 观测到的额外工具；不得只按 observed tools 数量乘固定常数估算。该 bucket 必须展示 tool count、每个工具的 token estimate、schema/参数 preview 和完整 detail。
- Qoder request attribution 必须优先使用 call-scoped `full_messages_array` 重建 Claude-like API messages bucket；该 bucket 必须包含当前 call 边界前的 user/assistant/tool_use/tool_result 输入，并使用完整 `content_token_estimate` 求和。
- Qoder provider reported `cache_read_input_tokens` 必须只作为 request 摘要中的 `Cache Read` 与 `Provider 总计` accounting 信息展示；不得生成 raw `provider_cached_context` bucket，不得计入本地重建 coverage；`cache_creation_input_tokens` / cache write 同样只在摘要中展示，不进入 request bucket 分母。
- Qoder 未持久化完整 available tools schema 时，request attribution 必须使用 Claude-Code-like SDK 默认工具定义并补充本 session 观测到的 Qoder-only 工具；不得只按实际调用过的工具数量估算完整 tool schemas。
- `Response 归因` 入口打开 response attribution payload。
- Trace round row 和 subround summary 行必须提供 response attribution 入口；Payload tab 保留完整归因详情。
- response attribution 内容固定包含 topgrid 元信息、用量分布、归因明细、blocks 明细、可见内容摘要。
- response attribution 的 topgrid 固定合并展示调用身份、响应摘要、归因备注与参数可得性；不得再使用左侧 metadata rail 承载这些信息。
- 响应摘要字段固定为 agent、model、source、request_id、call_id、total output、visible text、tool command、metadata、coverage、finish reason。
- response attribution 的工具 bucket 展开区必须展示 assistant response 中实际产生的 tool command / tool input，不得展示 request 侧工具定义或 input schema。
- 用量分布和归因明细必须占用 attribution modal 内容区全宽，不得被 side rail 挤压。
- attribution bucket card header 固定展示 bucket label、precision、tokens、percent、expand chevron。
- attribution modal 里动态渲染的 bucket card 必须带有与静态 payload 模板一致的可展开语义；点击 bucket header 展开/折叠详情时必须同步 `hidden`、`is-expanded` 和 `aria-expanded`。
- Trace round/subround 行里的 request/response attribution 按钮不得依赖初始 HTML 中预嵌完整归因 payload；点击按钮时必须通过 `/api/sessions/{agent}/{session_id}/attribution/...` 后端 API 获取最新归因 payload 并基于 API 返回渲染。
- attribution modal 的 bucket detail 必须是两层展开：第一层点击贡献来源 bucket 后，若存在 `details.explanation`，先以一行全宽说明文字直接展示在展开区顶部，不得把说明伪装成子分类 card；随后展示该 bucket 内部的子分类 card，所有子分类 card 必须单列排列且每个独占一行，不得在桌面宽度下排成多列；子分类 card 折叠态只展示精简摘要、来源/role/type/token 等短 meta，折叠态高度一致；第二层点击某个子分类 card 后，在该 card 内展示可得的完整原始内容或完整解释。
- 当 attribution bucket 没有结构化 `details` 但有 `summary`、`source`、`count_label` 或 `content_preview` 时，modal 必须把这些字段作为 fallback detail 展示，不得渲染成无法展开的空行。
- attribution bucket percent 为当前弹框中参与分布 bucket 的显示占比，单个 bucket 不得超过 100%。
- bucket 展开区必须优先使用结构化 `details.items[*].full_content`、`full_content`、`content` 或 raw JSON 字段展示完整信息；provider cache hit、previous_response_id 等本地不可见正文的来源必须展示完整解释，不得伪造原文。

### Payload Modal

- Trace 内点击 `Request`、`Response`、`Result`、`Request 归因`、`Response 归因` 时打开 payload modal。
- modal header 固定展示 payload title、payload id、Close button。
- modal body 固定为 metadata rail 加 main content 的双栏布局。
- metadata rail 展示 kind、status、size、result tokens、source、tool、tool status 中可用字段；`result tokens` 只在 `tool.result` / `subagent.tool.result` payload 中展示。
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
- URL 深链命中 subagent 或 subagent round 时，必须自动展开对应 subagent block 和目标 sub-round。
- Trace filter 默认值为 `All`。

### Trace 操作

- 点击 round header 和 round row 任意非按钮区域切换展开状态。
- 点击 row 内按钮只执行按钮动作，不触发 round toggle。
- 点击 `Expand all` 展开所有 round，并把按钮文案切换为 `Collapse all`。
- 点击 `Collapse all` 收起所有 round，再恢复默认展开规则。
- 点击 subagent header 右侧的 `Expand all` / `Collapse all` 只切换当前 subagent 的所有 sub-round，不影响其他 round 或其他 subagent；点击单个 `SRx` summary 只切换该 sub-round。
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
- view model 必须提供统一分析对象：`run_health`、`tool_impact`、`agent_breakdown`、`agent_timelines`、`context_budget`；cost driver 仅作为 `Agents Breakdown` tooltip、`Agents Breakdown` 行信息和 `Tool Impact` 的内部派生来源，不再映射为独立卡片。
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
