# Session Detail 页面规约

- Token KPI、缓存比例、round/call/subagent、attribution 遵循 `common.md` 的 `Token Measurement Provenance`。session 级估算不复制到无 usage 的 call；未知输入不进入低缓存筛选或伪造 0% 折线，导入 scope 保持独立。

## 定位

Session Detail 先展示会话身份与 Token 用量，再通过唯一的「执行过程」回答：哪个轮次执行了什么、是否失败、依据在哪里。

## 页面布局

- 个人详情使用 `/sessions/<agent>/<session_id>`；导入详情复用 `session.html`。静态归档见 [Session Export Contract](../../session-export-contract.md)。
- 在线详情自上而下为会话头与指标、Token 分析、执行过程三段。会话头展示 Agent、标题以及有内容时的首问入口，不在标题旁重复首问；模型、项目、ID、文件路径折进「会话信息」。
- 四张会话指标卡和 Token 分析直接可读。桌面验收覆盖 1024 CSS px 及以上；分析区左侧为 Agent 候选表，右侧为关联图表。执行过程没有同级 tab，不重复绘制平铺工具列表。
- 执行过程以轮次为行，展开读取该轮助手回复、子 Agent、工具指令与结果；同一回复声明的工具保留归属、独立输入和结果。失败定位、筛选和翻页都作用于这张表。
- 除明确失败或可信计时外，不显示泛化的执行判断。没有失败不等于成功，未记录时长也不等于零；必要的口径放在对应数值的提示中，不重复贴免责声明。
- 原文首先从对应轮次、调用或工具查看；需要跨记录查找时才展开执行区内的原文索引。不预取所有正文或所有页。
- 静态 HTML/MHTML 保留冻结数据与原生展开操作，不模拟在线交互。

### 导入分析范围

- `/imports/<import_id>` 复用单一执行过程、Token 摘要及原文/归因下钻，不为导入改变主视图结构；完整入口行为见 `09_imports.md`。
- 导入详情面包屑为 `导入分析 / <filename>`，主导航高亮导入分析。
- Hero 前常驻“仅分析此文件，不计入个人统计。”，并提供“导入另一个文件”“返回个人 Sessions”；范围提示不能被异步 metadata 加载替换。
- 范围提示仅显示一次，不在 Token 卡上重复。
- 所有 round/payload/attribution/bucket-detail 请求均来自 `/api/imports/<import_id>`；原来源 session ID 不能导致回落个人 API。
- 导入详情不暴露服务器临时路径，不提供会错误访问个人同 ID 会话的导出按钮；个人详情与离线导出行为保持。

## 文字内容

- 同一页自上而下阅读，不提供标签栏。列表完全载入时不显示分页提醒；部分载入时给出范围和操作。
- Hero 的四张原生指标卡分别呈现 Token 总量、输入端缓存命中率、本地记录工作量和耗时。
- Hero 本地文件路径行 label 固定为 `Session file`，展示索引或解析阶段定位到的本地 JSONL 绝对路径；路径缺失时不渲染该行。
- Hero 本地文件路径行必须提供 `Copy session file path` 按钮，按钮使用统一 `data-action="copy"` 和完整 `data-copy-text` 路径，供用户直接粘贴到终端或编辑器。
- 每张卡直接显示主值及多个相关子值，最多四个二级指标，不为了对齐补低价值指标。数值和必要标签不依赖点击；补充口径、分母和来源可在就近提示中查看。
- Round 标题使用 `R<round_number>` 加 summary；summary 缺失时显示 `Untitled round`。
- 原文缺失时显示 unavailable 原因、precision 和 source，不用空白区域代替。

## Hero KPI

### Total Tokens

- 一级值：`Fresh + Cache Read + Cache Write + Output`。
- 二级指标固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
- `Fresh` 表示互斥的新输入分段；当 provider 的 Cache Read 是 input token 子集（例如 OpenAI/Codex `cached_input_tokens`）时，Fresh 使用 `input_tokens - cached_input_tokens`，避免 Total 重复计入缓存命中输入。
- `Cache Read` 表示 provider reported Cache Read input token。
- `Cache Write` 表示 provider reported cache creation/write input token。
- `Output` 表示模型可见输出 token，不把隐藏 reasoning token 混入该值。
- Codex 以带明确响应身份的 `token_usage_record` 作为独立模型调用边界；仅有旧版累计计数时，有正向组件增量且能闭合的 `event_msg.token_count` 可作为边界。镜像或重复计数不增加调用数或 token；证据不足时显示记录分组，不推断真实模型调用。assistant 文本是展示材料，不是计量边界。
- Codex 重复 `total_token_usage` 累计快照不得创建 round、不得贡献 token；诊断中必须保留 record index、timestamp、累计 total 和 `contribution=0`。
- 四个二级指标合计必须等于一级值；无法和来源总量对齐时一级值仍显示互斥 component sum，tooltip 说明 component sum、source total、缺失字段、来源和精度。
- 四个二级 token 指标展示 `绝对值 · 占比`，占比相对 Total Tokens，并按占比标记颜色。

### Cache Health

- 一级值：`Cache Read / (Fresh + Cache Read + Cache Write)`。
- 二级指标固定为 `Input-side Tokens`、`Low-cache Rounds`、`Fresh Spike Rounds`。
- `Input-side Tokens` 表示 `Fresh + Cache Read + Cache Write`。
- `Low-cache Rounds` 表示 round-level Cache Read ratio 小于 20.0% 的 round 数。
- `Fresh Spike Rounds` 表示 fresh token 高于当前 session round fresh token 中位数 2 倍的 round 数。
- 分母为 0 时一级值显示 `N/A`，tooltip 展示 `Input-side Tokens = 0`。

### Workload

- 一级值：主 agent 和 subagent 的归一化记录总数。
- 二级指标为 `Main records`、`Subagent records`、`Tool Calls`、`Subagent Runs`。
- `Main records` 表示归一化的主 agent 记录数，不等同于已验证的模型调用数。
- `Subagent records` 表示归一化的子 agent 内部记录数，不计入主 agent。
- `Tool Calls` 使用全局 tool call 总数；如需展示主 agent 口径，必须与全局总数区分。
- `Subagent Runs` 表示独立 subagent 上下文启动次数。

### 耗时

- 来源任务窗口用 MAIN 源任务窗口的 union（`timing.activeTaskSeconds`），不是模型推理。任务活动、墙钟、Agent Turn workload、模型和工具的执行耗时按实际来源区分，不互为替代。
- 遵循 `common.md` 的 typed timing 精度。缺来源明确标记，不用 legacy execution、零值或跨夜 transcript span 补齐；不从墙钟减工具工作量推算模型耗时。
- 在线详情的时长用秒或分秒表达；不足一秒保留可用精度，实测零、非零和未知不能混淆。
- 会话开始时刻与耗时卡分开呈现。只有来源明确记录启动才称为启动时间；普通记录时间点不冒充启动。已测工作量并非会话墙钟，必要的来源或口径说明就近呈现。

## Token 分析

### Agents Breakdown

- `Agents Breakdown` 左为候选表、右为所选 Agent 的图表。候选表优先展示 Agent、已记录模型、本地记录、已确认调用、Token、工具与失败。文件与 ID 通过所选 Agent 的「来源 ID 与文件」获取。超过约五个候选后列表内部滚动。
- 归一化记录和有响应/累计计量边界证据的调用分别计数；未确认边界的记录不作为调用次数。会话级模型不回填进未知的 Agent 记录。
- 主 Agent 默认选中。柱图和缓存折线只使用所选 Agent 在当前 Trace 已加载轮次内的用量；混合轮按真实归属汇总。同一个轮次在图表和 Trace 使用同一 R/G 标识。
- 柱图使用共享 `TokenProvenance` 构成与来源提示，保留鼠标、键盘和跳转；折线只使用完整服务商上报输入，以 Cache Read / Input 计。

### Token 构成

- 卡片定位：解释当前 session 用量的可验证构成，而非模型 context window 占用率。
- 图表类型固定为水平分段条形图。
- 分段来自 DTO 的真实分类/纳入状态；Tool Results 是构成之外的本地估算，不塞进构成条。
- x 轴显示 token share，范围固定为 0% 到 100%。
- y 轴只有一行，标题固定为 `Session Context`。
- 分段条可在空间足够时内嵌分类名和占比；窄分段隐藏内嵌文字，但保留 tooltip。
- 图例简短，标签、数值、占比和来源就近排列；长标签可回流，桌面窗口内不溢出。顺序和色标与构成条一致。
- 不渲染配套明细表或每分类独立 progress track；细节通过 `common.md` 的 `Chart Tooltip` 展示。
- tooltip 固定展示 `Segment`、`Tokens`、`Share`、`Source`、`Precision`。
- 仅明确纳入且有可用 share 的分段参与构成；Partial 为近似、非服务商精确统计。构成条与图例仅列有正占比的已纳入项。指标卡保留实测零，未知不补 0%。缓存比率仅使用完整服务商上报输入，分母不含 Output。

## 执行过程

### 轮次导航

- 轮次表本身即执行过程，不另设轮次页。
- Trace 默认以 table 形态展示 round 列表，保证长 session 能快速扫描、排序和定位失败。
- Round 展开后使用 step card 形态展示详细过程，吸收高保真稿中可读性更好的时间线结构。
- Trace 和 Payload 使用同一 call id、round id、payload id，必须能互相定位。

### Trace Toolbar

- 说明从简；同一响应声明多个工具只表示来源分组，不表示并行。
- toolbar 右侧固定展示 status segmented control 和 expand control。
- status segmented control 候选项固定为 `All`、`Failed`、`Low cache`。
- `Low cache` 展示 round-level Cache Read ratio 小于 20.0% 的 round，用于定位 Hero `Low-cache Rounds`。
- expand control 是一个全局 toggle，文案固定在 `Expand all` 和 `Collapse all` 之间切换。
- Trace filter 状态必须写入 URL 参数 `trace_status`。

### Trace Round Table

- 五列分别展示轮次标识、摘要、Token、原文入口和时间点；已观察到的状态或缺口随摘要显示，不设独立信号列或空占位。
- 轮次列展示 `R<round_number>` 或分组标识以及对应的状态。
- Codex 的 `R<round_number>` 表示第 N 个有效 LLM call round，而不是第 N 个可见 assistant 文本窗口；无可见文本但有 tool_use 或 usage 的 Codex call 也必须保留为 round。
- 摘要列占剩余主宽，展示当前轮短摘要：优先可见用户输入，其次工具名称/次数与短操作预览，再回退助手文本。必须解析当前调用的 inline/catalog/sequence 引用，过滤系统上下文及工具结果；不得跨轮借文或嵌入长代码/输出。真正缺失显示 `摘要未记录`。
- 轮次计数要区分本地归一化记录数、已确认模型调用数及新声明的工具执行数；消费历史工具结果不计为新执行。
- `Token Cell` 的彩色 tokenbar 宽度必须按当前 session 最大 round token total 归一化，最大 round 为满宽，其他 round 按比例缩短；未占用的轨道使用灰色背景显示与最大 round 的差距。
- 原文入口列展示当前调用可用的 Request 和 Response；多记录分组从展开行按调用查看。
- 时间列只展示当前调用或其响应来源引用中第一个已记录的时间点（Asia/Shanghai）；无源时间显示 `未记录`，不用 session 更新时间或耗时代替。
- 表头的 Token 排序按 total tokens。
- 当前展开 row 必须有明确背景色和行内状态线；状态线不得超出 row 自身边界或侵入相邻 round。

### Expanded Round Detail

- expanded detail 只在当前 round 展开时渲染。
- detail 内部固定为一条纵向 event timeline，左侧是 timeline rail，右侧是紧凑事件行。
- detail 面板必须与展开 round 行和下一条 round 行保持可见间距；detail 外框不得与上下 round 边框贴合或重合。
- step 顺序固定为原始 trace 顺序；assistant thinking/text、tool_use、tool_result、subagent run 必须按 timestamp 排列。
- step 类型为 `User Message`、`Assistant Thinking`、`Assistant Text`、`Tool Call`、来源工具组、`Tool Result`、`Subagent Run`、`System Signal`；同组多工具只表示声明来源，缺少可信执行区间重叠证据不得称为 `Parallel Tool Group`。expanded timeline 不渲染 `LLM Summary` 或独立 `LLM Call` card。
- `User Message` 行展示 role、摘要、timestamp、输入 preview；preview 最长 3 行，长内容从 payload 打开。
- `Assistant Thinking` 行展示 thinking 摘要、timestamp、source block 和 payload 入口；必须使用与 `Tool Call` 行同等高度的单行紧凑布局，长文本单行截断。
- `Assistant Text` 行展示对用户可见文本摘要、timestamp 和 payload 入口；必须使用与 `Tool Call` 行同等高度的单行紧凑布局，长文本单行截断。该行 payload 只展示 assistant text / thinking 内容，不重复展示同一 LLM response 中已经在后续 `Tool Call` 行平铺展示的 tool call。
- Codex 原始 JSONL 中同一 assistant 文案可能同时出现为 `event_msg.agent_message` 和 `response_item.message role=assistant`；Trace 必须把两者关联为同一个 assistant text 事件，优先使用 `response_item.message` 作为 canonical payload source，`event_msg` 只作为 UI/status mirror 或缺省处理，不得重复展示两行相同文本。
- 单调用行的 Request/Response 不在展开内容中重复；多记录分组在展开后提供各成员的 Request/Response，正文与归因使用同一弹框。
- `Fresh` 表示 tokenbar 和 Total 的互斥新输入分段；request attribution 摘要可单独展示 Provider Request Input / Provider 请求输入，用于解释归因分母。
- `Tool Call` 行固定展示 tool name、command preview、result preview、timestamp、duration、result token estimate、`Result` action；duration 仅使用来源明确测得的耗时，保留测量口径与精度；零是实测零，正数不足 1ms 也不能显示为零或未知，缺测不补值。不得用 call/output 或相邻 timestamp 差、TTFT、总时长减工具工作量推算模型或工具时间；result token estimate 使用 `~<compact>`，且必须和 Result modal 中的 `result tokens` 数值一致。
- 点击 `Result` 打开的 tool result payload modal 必须在 metadata rail 和 modal subtitle 展示该 result 文本的估算 token 数，字段名固定为 `result tokens`，数值格式为 `~<compact> tokens`；该值表示该 tool result 大概率进入下一次 LLM request 的输入压力，不得标记为 provider reported。
- 同一响应声明多个 tool_use 仅表示来源分组，不表示并行；相邻时间戳不能证明执行区间重叠。
- 工具组 header 展示本地响应边界和下发工具数；动作聚焦工具类别、状态和已测耗时；摘要不复述命令。模型耗时未知只在组外集中说明，不用墙钟减工具工作量推算。
- `Subagent Run` 行展示 subagent name、独立上下文 badge、status、sub-round 数、token summary 和局部 `Expand all` / `Collapse all` 控制。
- `Subagent Run` 内部的 sub-round 按 `SR<sub_round_id>` 展示；每个 sub-round summary 行必须可点击或键盘切换自身展开/折叠，并直接展示 request/response attribution 状态和入口，不再默认展开内部 LLM call card。
- `System Signal` 行展示 parser 缺省处理、payload missing、round API error、attribution error。

### LLM Call Attribution

- `Request` 打开当前调用的正文，弹框内可展开输入归因。
- Trace round row 和 subround summary 行必须提供 request attribution 入口；通过当前调用的弹框查看归因依据。
- 单调用行只提供一对 `Request` / `Response` 按钮；多记录分组须展开后按调用查看归因。弹框定位保留调用身份，不以 round-local 序号冒充全局调用编号。
- request attribution 内容固定包含 topgrid 元信息、用量分布、归因明细、重建上下文预览。
- request attribution 的 topgrid 固定合并展示调用身份、请求摘要、调用信息/时间线/请求参数与覆盖率；桌面宽度下顶部三个 summary card 必须同一行展示，不得再使用左侧 metadata rail 承载这些信息。
- 请求摘要字段固定为 agent、model、source、API family、provider、call id、Request 内容分母、Fresh、Cache Read、Cache Write、Provider 请求输入、本地重建、coverage、残差；不得在归因明细底部另起 `覆盖率与不确定性` 表格。
- request attribution 不展示泛化的残差可能来源尾注；只有存在可验证、结构化来源时才应进入具体 bucket 或诊断说明。
- request attribution 的Request 内容分母固定为 `Fresh`，用于 request 用量分布、bucket percent、coverage 和 unlocated residual；`Cache Read` 与 `Cache Write` 都是 provider/broker accounting 组件，只在摘要中展示，不作为和对话消息、工具结果并列的 request 内容 bucket。
- request attribution 候选分类必须使用全局 token 归因分类树，API payload 必须为每个 bucket 输出 `agent_bucket_key`、`canonical_key`、`category_key`、`category_label`、`color_key`、`display_order`，并把 `label` 规范为全局中文 label；前端颜色和排序必须使用 canonical metadata，不得按 agent raw bucket key 自行决定。
- 全局 request token 归因分类树固定为：`当前用户输入`、`对话消息上下文`、`工具结果上下文`、`工具定义`、`MCP 工具元数据`、`运行上下文片段`、`系统/开发者指令`、`本地指令上下文`、`Agent/Subagent 提示`、`内置系统提示`、`Provider 会话状态`、`推理配置`、`运行时封装开销`、`未定位`。
- 每个 agent 只能在自己的映射规则文件中维护 raw bucket key 到全局分类的映射；旧 raw 输入键 `tool_schemas` 必须归一化为 canonical key `tool_definitions`，并使用同一个 `color_key=tool_definitions`。
- Claude Code request attribution 的 `API messages 数组` 必须按当前 LLM call 边界重建：依次使用当前 call 之前的 assistant `request_full`、assistant text/tool_use，以及当前 call 的 `request_full`，匹配到当前 call 后停止；不得把后续 round/subround 的 assistant text、tool result 或 request_full 算入当前 request。
- Claude Code request attribution 的 `tool_definitions` 表示 request 侧发送给模型的工具定义，不得从 response 侧实际调用过的 tool call 或 `tool_calls_raw` 推断。主 agent 若在 session JSONL 中存在 `agent-setting`，必须优先按 `<cwd>/.claude/agents/{agent}.md`、再按 `~/.claude/agents/{agent}.md` 读取该 agent 的显式 `tools:`；subagent 必须按父 `Agent` tool call 中解析到的 `subagent_type` 读取对应 subagent 自己的 `tools:`。找不到自定义 agent、定义文件或显式 `tools:` 时，必须使用 Claude Code 全量 builtin tool registry。
- request attribution 的 `API messages 数组` bucket 展开区必须说明它对应发送给模型的 Anthropic API `messages` 字段，并逐条展示 role、content type、tool name、token 估算和内容 preview；bucket 汇总 token 必须使用每条消息的完整 `content_token_estimate` 求和，不得用截断 preview 重新估算；当原始全文在本地日志或重建上下文中可见时，条目必须支持二次展开查看完整内容。
- request attribution 的 `内置系统提示` bucket 若从本地 transcript 捕获到可见 `<system-reminder>` 内容，必须展示脱敏 preview；若未捕获，必须展示明确的不可见/估算说明，不得空白。
- Codex request attribution 在没有 raw request body 时，必须从 rollout 开头可见的 `session_meta.base_instructions` 和 `response_item` 中 role 为 `developer` / `system` 的 message 重建 raw `instructions` bucket，序列化后统一显示为 `系统/开发者指令`。
- Codex parser 必须把 `function_call_output` / `custom_tool_call_output` 作为下一次 assistant request 的 tool output 来源，request attribution 必须将其归入 raw `tool_outputs` bucket，序列化后统一显示为 `工具结果上下文`，不得落入 unknown。
- Codex provider reported `cached_input_tokens` / Cache Read 必须只作为 request 摘要中的 `Cache Read` 与 `Provider 请求输入` accounting 信息展示；不得生成 raw `provider_cached_context` bucket，不得计入本地重建 coverage，不得和对话消息、工具结果、工具定义等 request 内容来源并列。
- Codex request attribution 在没有 raw request `tools` 数组时，必须使用 Codex builtin tool catalog 作为工具定义缺省来源，并补充本 session 观测到的额外工具；不得只按 observed tools 数量乘固定常数估算。`tool_definitions` bucket 必须展示 tool count、每个工具的 token estimate、schema/参数 preview 和完整 detail。
- Qoder request attribution 必须优先使用 call-scoped `full_messages_array` 重建 Claude-like API messages bucket；该 bucket 必须包含当前 call 边界前的 user/assistant/tool_use/tool_result 输入，并使用完整 `content_token_estimate` 求和。
- Qoder provider reported `cache_read_input_tokens` 必须只作为 request 摘要中的 `Cache Read` 与 `Provider 请求输入` accounting 信息展示；不得生成 raw `provider_cached_context` bucket，不得计入本地重建 coverage；`cache_creation_input_tokens` / Cache Write 同样只在摘要中展示，不进入 request bucket 分母。
- Qoder 未持久化完整 available tools schema 时，request attribution 必须使用 Claude-Code-like SDK 默认工具定义并补充本 session 观测到的 Qoder-only 工具；不得只按实际调用过的工具数量估算完整工具定义。
- `Response` 打开当前调用的正文，弹框内可展开输出归因。
- Trace round row 和 subround summary 行必须提供 response attribution 入口；通过当前调用的弹框查看归因依据。
- response attribution 内容固定包含 topgrid 元信息、用量分布、归因明细、blocks 明细、可见内容摘要。
- response attribution 的 topgrid 固定合并展示调用身份、响应摘要、归因备注与参数可得性；不得再使用左侧 metadata rail 承载这些信息。
- 响应摘要字段固定为 agent、model、source、request_id、call_id、total output、visible text、tool call、metadata、coverage、finish reason。
- response attribution 的工具 bucket 展开区必须展示 assistant response 中实际产生的 tool call / tool input，不得展示 request 侧工具定义或 input schema。
- 用量分布和归因明细必须占用 attribution modal 内容区全宽，不得被 side rail 挤压。
- attribution bucket card header 固定展示 bucket label、precision、tokens、percent、expand chevron。
- attribution modal 里动态渲染的 bucket card 必须带有与静态 payload 模板一致的可展开语义；点击 bucket header 展开/折叠详情时必须同步 `hidden`、`is-expanded` 和 `aria-expanded`。
- 打开正文弹框时按调用和方向通过 `/api/sessions/{agent}/{session_id}/attribution/...` 加载，默认折叠，不在初始 HTML 预嵌完整归因。
- attribution modal 的 bucket detail 必须是两层展开：第一层点击贡献来源 bucket 后，若存在 `details.explanation`，先以一行全宽说明文字直接展示在展开区顶部，不得把说明伪装成子分类 card；随后展示该 bucket 内部的子分类 card，所有子分类 card 必须单列排列且每个独占一行，不得在桌面宽度下排成多列；子分类 card 折叠态只展示精简摘要、来源/role/type/token 等短 meta，折叠态高度一致；第二层点击某个子分类 card 后，在该 card 内展示可得的完整原始内容或完整解释。
- 当 attribution bucket 没有结构化 `details` 但有 `summary`、`source`、`count_label` 或 `content_preview` 时，modal 必须把这些字段作为 缺省 detail 展示，不得渲染成无法展开的空行。
- attribution bucket percent 为当前弹框中参与分布 bucket 的显示占比，单个 bucket 不得超过 100%。
- bucket 展开区必须优先使用结构化 `details.items[*].full_content`、`full_content`、`content` 或 raw JSON 字段展示完整信息；provider cache hit、previous_response_id 等本地不可见正文的来源必须展示完整解释，不得伪造原文。

### Payload Modal

- Trace 内点击 `Request`、`Response` 或 `Result` 时打开 payload modal。
- modal header 固定展示 payload title、payload id、Close button。
- modal body 固定为 metadata rail 加 main content 的双栏布局。
- metadata rail 展示 kind、status、size、result tokens、source、tool、tool status 中可用字段；`result tokens` 只在 `tool.result` / `subagent.tool.result` payload 中展示。
- main content 根据 payload kind 展示 context、response、tool result、attribution、diagnostic error。
- payload 内容缺失时 modal 不显示空白，必须展示 requested payload、metadata、possible reasons。

## 从执行记录查看原文

- 点击模型 Request / Response 查看该调用的本地记录；工具输入和结果从「工具原文」展开。正文与归因共用弹框，不推断完整 HTTP 上下文。
- 执行区的折叠原文索引可按 Agent 查找本地记录，首次打开才请求有界索引；确认存在的方向才提供按钮。拒绝跨代续页，失效或网络错误提供恢复操作。

## 执行过程交互

### Trace 默认状态

- 默认显示轮次索引；`round` 和 `trace_status` 分别定位轮次或应用筛选。
- 默认不展开正文，明确的深链或点击才读取轮次。
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

## 数据口径

- Created、Updated 使用源 timestamp；Wall Duration、Task Active 使用 `common.md` 的 typed timing 口径。
- Rounds 使用当前 session 的 assistant round 计数。
- legacy `LLM Calls` 仅汇总主 agent 和 subagent 的本地 normalized 逻辑记录数，须就近标明“本地记录”，不得将 records 相加宣称真实 provider 请求总量；只有来源边界证据充分时才另显示对应已确认边界计数及覆盖。
- Tool Calls 使用 tool call 计数；Failed Tools 使用失败 tool result 计数。
- Subagent Runs 使用独立 subagent 上下文启动次数。
- Output 来自模型可见输出 token，不把 hidden reasoning token 混入可见输出。
- Trace、Payload、payload modal 内的 token 值必须共享同一 usage source。
- 不同来源数据产生差异时，必须展示 source、precision、缺省原因。
- Token Driver 只作为 `Agents Breakdown` 的提示或候选行附属信息，不映射为独立卡片。
- 执行过程的状态与 Failed 筛选使用已观察的失败证据。没有失败记录不等于会话成功；工具错误和缺失证据仍在关联记录中可见。

## 状态

- session 数据不可用：展示错误状态和 `Back to Sessions`。
- 无 round：Trace 显示空态和可执行下一步。
- call 没有 raw request：`Raw Request` 显示 unavailable 原因、precision、source。
- call 没有 raw response：`Raw Response` 显示 unavailable 原因、precision、source。
- attribution 构建失败：显示错误摘要、缺省处理 和来源，不隐藏该区块。
- payload 太长：默认 preview，提供 `Show full raw` 和 `Copy raw`。
- payload API 返回 500：在出错的原文入口展示错误状态与重试操作。

## 禁止项

- 不存在独立 Attribution tab。
- 不存在独立 Insights tab。
- 不在页面中展示 All Sessions 表格。
- 不展示 Selected LLM calls、Round diagnostics、sidecar filter。
- 不恢复 Round Map、Inspector 默认三栏、Map/Inspector/Focus 模式按钮、Density toggle、无效占位按钮。
- 不把 Trace 默认形态改成纯卡片列表；纯卡片列表只用于 round 展开后的 step detail。

### TASK-56 内容证据与展开规则

- 本地流式内容与独立导入的已物化制品使用相同短预览规则：优先本轮可见用户输入，其次工具计数及短操作，最后助手文本。catalog/sequence 引用同样提供摘要与源时间；历史用户引用只归属首次出现的轮次，不因导入入口退化为重复工具名。
- Session File 显示加载中、已提供路径、来源未提供及加载失败；仅允许的本地详情展示冻结 source file 元数据，不猜路径，不探测原文件；导入详情不泄露个人路径。
- Token 构成未提供可验证分解时标明不可用；未测量的工具结果 token 不补零。
- 独立助手文本、真正无正文的独立调用、不同工具执行和子 Agent 可单列 timeline-item。纯工具响应仅复述工具名的 `TOOLS` 概览不得与工具执行重复单列；多成员调用的 Request/Response 操作附着首个对应工具行，保留稳定 call ID。
- 工具类别筛选复用 `ui-select` / `ui-select__control`。右侧顺序为状态、时间/耗时、归属、token、操作；用标签区分时间点与执行时长，缺失明确显示。
- 工具行使用单一「工具原文」入口按需读取正文，桌面左右双栏；需要完整弹窗时可从有正文的一侧打开；Tool Input 是命令/参数，Tool Result 是执行输出，不是模型 Response。模型 Response 可包含该调用声明的工具指令列表；后续模型 Request 消费结果不表示重新执行。
- 单页全量成员不渲染分页提示；实际分页显示 `调用记录 · 已显示 N / M` 和 Load more/Retry，加载完成仍保留已分页总数。
- 延续请求保留 generation 检查。HTTP 500 缺 header 显示真实 HTTP 加载错误并允许 Retry；409 或真实不同 generation 阻断合并。个人详情若确认已发布不同代次且能从新视图验证当前阅读目标，最多自动整页恢复一次；无法确认、目标消失或连续换代时改为提示用户。成功但缺 generation 不视作可信快照，不插入内容。


## Token 构成共享入口

共享弹框实际入口：Sessions Token bar；Projects 与 Project Detail 的 Token Cell；Dashboard Token 趋势；Session Detail 的 Agent 候选、Agent Round 柱、Trace Round bar、延迟加载的主/子 call（导入复用）。统一 `token-provenance.js/css` 色标/类型、数量/来源、占比列；列表可明确显示估算近似占比，Round/Trace 和 Dashboard 保留 provider-only 限制。Dashboard 的时间窗口占比单列说明，不与桶内构成分母混用。Project trend 目前只有来源 disclosure，没有已有四段悬浮入口，不虚构一个。缓存健康/消息数等其他图不属于四段总量构成，保留各自口径。

### 桌面阅读的计量与定位

- 助手回复保留在对应轮次，不在页头重复。已测工具累计工作量和覆盖数保留来源及精度，放在执行过程内，不与会话墙钟时间混用。
- 执行过程保留首个实际失败的定位及已记录的结果。目标已加载时只定位和聚焦，未加载时追加定位片段，不替换已展示的执行记录和列表范围。
- Trace 隐去默认 `1 records`、`0 tools` 及内部分片编号；工具行保持 28px。「工具原文」集中输入和结果，原文索引对未记录的方向不提供空按钮。

### 轮次行与卡片边界

- 桌面轮次表头及摘要行统一 36px。长摘要单行省略，完整内容从标题提示或轮次原文读取。Token 数、色条和计数横排。展开详情不限制此高度。
- 页头与 KPI 的间隙沿用页面底色；白色只在卡片边界内绘制。同级卡片共用 8px 间距、12px 水平内边距和 14px 圆角。执行记录工具栏与表格共享一个边框。
