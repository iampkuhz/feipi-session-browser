# Session Detail UI Spec

## Requirements

### Requirement: 紧凑命令与工具输出保持可追溯
单工具响应 SHALL 以 `#N` 和实际安全命令为主，在桌面尽量单行排列状态、耗时与证据入口；多工具与多响应边界、子 Agent 上下文、分页及稳定定位 MUST 保留，长命令与窄屏可自然折行。摘要 SHALL 只提取明确结构字段或可完整解析的单次静态执行包装，不执行源文本，不拆分多语句调用，未知或歧义格式回退原文。

#### Scenario: 静态包装与动态表达式
- **WHEN** 已知包装包含静态 cmd/command/script，或不能可靠解析的动态命令
- **THEN** 前者 SHALL 展示实际指令并保留完整参数入口；后者 SHALL 保留原摘要，不猜测运行值，不改变执行身份或计时。

#### Scenario: 按需阅读多行工具命令
- **WHEN** 已按需取得的完整工具 Input 是有界、无歧义且仅含一个 `cmd`、`command` 或 `script` 字符串字段的 JSON 对象，字段值含真实换行
- **THEN** 弹框 SHALL 以纯文本保留解码后的换行、缩进、引号及反斜线，完整原始参数保持可展开、可独立复制；复制命令文本与复制原始参数 SHALL 明确区分。不新增默认正文读取，不执行、分类或拆分脚本，不改变工具身份、组数或计时。
- **AND** 重复键、多字段、嵌套或动态包装、非字符串、无效 JSON、已截断或超界输入 SHALL 保持完整 Input 的既有呈现；单行参数保持原样。不得从解码恢复已遮盖内容，不适用于模型 Request/Response 或工具 Result。

#### Scenario: 工具结果包含包装和输出正文
- **WHEN** 工具结果具有明确文本 output/result 或受支持的 Script completed/Output 包装
- **THEN** metadata SHALL 在结果上方，工具输出占据内容宽度；声明命令、包装说明和完整原始载荷保持可达且可独立复制，不把它们当最终输出。未知/歧义/非文本/超界格式 SHALL 保留完整记录；已记录空字符串 SHALL 区别于缺失。模型响应入口仍独立，不适用工具结果提取。

### Requirement: 单页 trace-first 调试体验

Session Detail 由本地服务提供在线运行分析；下载的 HTML/MHTML 是另行打开的静态离线档案。默认顺序为执行判断、可扫读的响应分组动作、按需 Token 分析与完整记录证据。Trace 与 Payload 保留为两个主入口。

#### Scenario: 会话摘要展示

页面必须展示：
- Session 标题。
- 默认保留 Agent 与标题；model、project、created/updated 时间、session id 与源文件路径放入可键盘展开的会话信息，保留复制入口。
- Total Tokens、Cache Health、Workload 与全部诊断卡片保留在执行过程之后的按需证据区域。Run Health 与 typed Source Task Active 保留原二级入口和测量边界。
- Run Health 二级指标：Issue Rounds、Failed Tools、Payload Gaps、Attribution Gaps。
- Total Tokens 二级指标：Fresh、Cache Read、Cache Write、Output。
- Cache Health 二级指标：Input-side Tokens、Low-cache Rounds、Fresh Spike Rounds。
- Workload 二级指标：Main records、Subagent records、Tool Calls、Subagent Runs；记录数不是可证明的模型调用数。
- Source Task Active 只使用来源任务窗口；Model Execution 和 Tool Execution 缺测不从差值推算。

每个主 KPI 卡最多渲染 4 个二级指标。Hero 区在索引或 parser 已解析 JSONL 源路径时，必须以 `Session file` 行展示本地路径，并提供 `data-action="copy"` 与 `data-copy-text` 复制按钮；没有路径时省略该行。

#### Scenario: Token 组件提取

Token 指标必须只使用 5 个当前组件字段：
- Fresh：互斥的新输入组件，用于展示合计。
- Cache Read：provider 上报的缓存读取输入 token。
- Cache Write：provider 上报的缓存创建/写入输入 token。
- Output：provider 上报的可见输出 token。
- Total：`Fresh + Cache Read + Cache Write + Output`。

当 provider 的 Cache Read 是 input tokens 子集时，例如 OpenAI/Codex `cached_input_tokens`，Fresh 必须按 `input_tokens - cached_input_tokens` 计算，并用于 tokenbar、Total、Fresh spike、round tooltip。Provider Request Input 可在 attribution 摘要或 provider 计量元数据中单独展示，但不得和它的缓存子集并列叠加为 Fresh。Codex 中，带明确响应身份的 `token_usage_record` 形成独立模型调用行；仅有旧版累计计数时，有正向组件增量且能闭合的 `event_msg.token_count` 可作为边界。重复计数或与响应计量互为镜像的快照不得重复生成调用或累计 token。缺少可靠边界的记录保留为逻辑分组，不计作已验证模型调用。

#### Scenario: Analysis cards 展示

页面必须展示 Agents Breakdown、Context Budget、Tool Impact、Issues & Repro Seeds。Agents Breakdown 在桌面端必须横跨完整分析网格宽度，并将 `main agent` 作为第一个可选项，后面列出 subagent runs。切换候选项时，同一卡片内的 token/cache timeline 必须同步切换。Context Budget 在桌面端必须横跨完整分析网格宽度并独占一行，Tool Impact 与 Issues & Repro Seeds 在下一行提供可键盘展开的入口（工具默认收起，问题有线索时展开）；窄屏使用单列布局并保持相同语义顺序。

#### Scenario: Removed token-driver cards are absent

页面不得把 `Top Token Drivers` 或 `Call Token Footprint Distribution` 渲染为独立诊断卡。Token-driver 明细只能出现在 `Agents Breakdown` 的 tooltip/候选行 metadata，或出现在 `Tool Impact` 指定的工具结果 token pressure 位置。相关 tooltip 不得展示旧标签 `Call Tokens`、`Call Token Footprint`、`Top Call`、`Top Lane` 或原始 main/subagent split 文案。

#### Scenario: Issue 摘要展示

页面必须展示 failed rounds（含聚合 failed tool call 数）和 highest token round 的 issue cards。Issue card 必须是可点击按钮，并跳转展开对应 round。没有问题时展示 `No actionable issues detected.`；只要存在 tool failure、LLM error、payload gap 或 attribution error，Hero issue strip 不得展示 `No issues found`。

#### Scenario: Trace 列表

页面必须展示所有 rounds 的纵向列表。每个 round 必须展示 round number、status、摘要/title、tool count、failure count、token count、time，以及 Failed、Subagent、Payload Gap、Attribution Gap 信号。Round Metrics 不展示 LLM call count。Round token bars 必须使用全宽灰色 track，并按当前 session 中最大 round token total 缩放彩色 token mix。

Round Signals 只渲染真实存在的 signal badge；没有 Failed、Subagent、Payload Gap、Attribution Gap 的 round 不渲染占位 badge。第一个失败 round 默认展开；没有失败时默认展开 R1。

#### Scenario: Trace 控制

页面必须提供 All / Failed 状态过滤，以及 Expand All / Collapse All 按钮。Failed 过滤必须展示 failed rounds 和包含任意 failure signal 的 rounds。过滤状态必须反映到 `trace_status` URL 参数；选中 round 和 tab 必须反映到 `round` 与 `tab` URL 参数。

#### Scenario: 行内 round detail

round 展开后必须展示：
- User prompt 摘要。
- Assistant response 摘要。
- 源 block 存在时展示 Assistant Thinking 与 Assistant Text 事件行。
- Tool call 行，包含 status、duration、command preview、result preview、result token estimate 和 result payload action。duration 只使用来源观测；未知不补零，显式零不回退到时间戳差值；毫秒摘要为零而纳秒正值时显示小于 1ms。
- 多工具声明只表示同一来源组，不凭同一 block 或相邻 timestamp 宣称 Parallel Tool Group。只有可靠起止区间才可讨论实际重叠。
- Subagent run 行，带局部 expand/collapse-all 控制和每个 subround 的展开/折叠开关。
- Failed tool error 摘要。
- 仅在存在 payload data 时展示 payload 按钮。

Expanded timeline 不渲染独立的 LLM summary card 或 LLM call card。单调用行的 Request/Response 不在展开内容中重复；多记录分组在展开后提供各成员的 Request/Response，正文及归因沿用同一弹框。

Assistant thinking、assistant text 和不可用处理事件行必须使用与 tool call 行一致的紧凑单行高度。Assistant text row payload 只包含 assistant text/thinking 内容；同一 model response 中的 tool_use commands 必须由独立 tool call 行展示，不得在 assistant text row payload 中重复。展开 detail 面板必须和展开 round 行、下一条 round 行保持可见间距。

Codex rollouts 中，同一 assistant 文案如果同时出现在 `event_msg.agent_message` 和 `response_item.message role=assistant`，Session Detail 必须把两者关联为一个 assistant text 事件。存在 `response_item.message` 时它是 canonical payload source；`event_msg.agent_message` 只作为 UI/status mirror 或缺省展示来源，不得生成第二条相同 timeline row。

Codex rollouts 中，父线程通过 `spawn_agent` tool 创建子线程且 child rollout 暴露 `session_meta.source.subagent.thread_spawn.parent_thread_id` 等稳定证据时，Session Detail 必须把 child LLM calls 和 child tools 归属为 `scope="subagent"`，设置稳定 `subagent_id` 和 `parent_tool_call_id`，并用父 `spawn_agent` tool output 填充 `subagent_summary`。父 main agent 的 token、tool 和 attribution totals 不得吞并 child 内部 LLM calls 或 tools；缺少稳定可见证据时不得从隐藏 runtime 推断 subagent。

单调用的 round row 与 subagent call row 分别提供 `Request` 和 `Response`，在同一正文弹框内按需展开对应的输入或输出归因。多记录分组须展开后按调用查看，不把某个成员的归因当作整组归因。每个 subagent round summary row 必须可独立点击并支持键盘展开/折叠。

Trace 按会话内分页顺序标记 R/G 行；该行号不是全局调用序号。正文和归因须使用当前行及稳定调用身份定位；兼容接口保留 round-local 索引，不将其显示为全局调用编号。

Expanded round row 状态线必须绘制在该 row 边界内，不得覆盖相邻 row 边框。

#### Scenario: Payload tab 与 modal

页面必须提供常驻 Payload tab：左侧 call selector，支持 All / Failed / Missing / Error 过滤；右侧展示选中 call 详情。详情分区顺序固定为 Overview、Request Attribution、Response Attribution、Raw Request、Raw Response、Related Results。Selector 在桌面和窄屏都必须保留内部滚动区域。点击 coverage matrix cell 必须切换到 Payload tab，应用对应 selector filter，并选中第一条匹配的 failed/missing/error call。

Request attribution bucket details 必须展示可解释、可检查的重建 request sources。Claude Code 的 `API messages 数组` bucket 必须按当前 LLM call 边界重建：当前 call 之前的 assistant `request_full`、assistant text/tool_use，以及当前 call 的 `request_full`，并在当前 assistant response 前停止，排除未来 rounds。聚合 token 必须汇总每条 item 的完整 `content_token_estimate`，不得用截断 preview 重新估算。bucket 必须说明它代表 Anthropic API `messages` request 字段，并列出 role、content type、可选 tool name、token estimate 和 content preview。本地日志或重建上下文中有原文时，detail item 必须支持二级展开查看完整内容。

`内置系统提示` bucket 捕获到可见 `<system-reminder>` 内容时必须展示脱敏 preview；未捕获可见内容时必须展示明确的不可用/估算说明，不得留空。

Claude Code request attribution 的 `tool_definitions` bucket 必须表示 request 侧发送给模型的工具定义，不得表示 response 侧实际调用过的 tool call。session JSONL 包含 `agent-setting` 事件时，主 agent call 必须先解析 `<cwd>/.claude/agents/{agent}.md`，再解析 `~/.claude/agents/{agent}.md`，并在存在显式 `tools:` frontmatter 时使用该 agent 文件。Subagent call 必须从父 `Agent` tool call metadata 解析具体 subagent type，并使用该 subagent 自己的 agent 文件。没有 custom agent 设置、subagent type、可读定义文件或显式 `tools:` 列表时，必须使用完整 Claude Code builtin tool registry。不得从 `tool_calls_raw` 或 observed tool call names 推断 `tool_definitions`。

Attribution bucket cards 在动态 modal 内必须使用与模板 payload bucket 一致的展开契约。点击 bucket header 必须展开或折叠 detail body，并同步 `hidden`、`is-expanded` 和 `aria-expanded`。

Request attribution coverage metadata 必须折叠进顶部摘要区域。`provider_request_input`、本地重建合计、coverage ratio、residual tokens 不得在底部作为独立 `覆盖率与不确定性` 区重复渲染。泛化 residual 可能来源尾注不得展示，除非有具体结构化来源支撑。

动态 attribution modal 必须使用两级 bucket detail 交互。第一次点击贡献来源 bucket 时展示紧凑子分类卡片；子分类卡片折叠高度必须一致，只展示短摘要和紧凑 metadata。点击子分类卡片后，必须在该卡片内展示所有本地可用的完整内容、raw JSON 或完整说明文本。

当 attribution bucket 没有结构化 `details`，但包含 `summary`、`source`、`count_label` 或 `content_preview` 时，modal 必须把这些字段作为缺省 detail 展示，不得渲染成不可展开或空白。

Request attribution buckets 返回 UI 前必须经过全局 token attribution taxonomy 归一化。每个 request bucket payload 必须包含 `agent_bucket_key`、`canonical_key`、`category_key`、`category_label`、`color_key` 和 `display_order`；`label` 必须使用全局中文 label。Canonical request token categories 包含：`当前用户输入`、`对话消息上下文`、`工具结果上下文`、`工具定义`、`MCP 工具元数据`、`运行上下文片段`、`系统/开发者指令`、`本地指令上下文`、`Agent/Subagent 提示`、`内置系统提示`、`Provider 会话状态`、`推理配置`、`运行时封装开销` 和 `未定位`。不同 agent 的等价 raw 输入键（例如 raw `tool_schemas`）必须归一化为同一 canonical key、label 和 `color_key=tool_definitions`。

没有 raw request body 的 Codex session，request attribution 必须从 rollout 数据重建可见 request sources。`session_meta.base_instructions` 和首个 user 前 role 为 `developer` 或 `system` 的 `response_item` message 必须进入 raw `instructions`，并在 canonical `系统/开发者指令` 分类下展示可见 source text 和结构化 bucket details。`function_call_output` 与 `custom_tool_call_output` 事件必须带入下一次 assistant request 并归入 raw `tool_outputs`，序列化后显示为 canonical `工具结果上下文`，本地可见输出文本可通过 detail expansion 查看。Provider reported `cached_input_tokens` / Cache Read 只在 request summary 中作为 `Cache Read` 和 provider accounting metadata 展示；不得创建 raw `provider_cached_context` bucket，不得参与本地重建 coverage，不得和 conversation messages、tool outputs 或 tool definitions 并列渲染。raw request `tools` 不可用时，Codex request attribution 必须使用 Codex builtin tool catalog 作为当前缺省来源，并补充 observed extra tools；不得只按 observed invoked-tool count 估算工具定义。工具定义 bucket 必须以 canonical key `tool_definitions` 输出，并展示 tool count、每个工具的 token estimate、schema/parameter preview 和本地可见完整 detail。

打开 Trace 正文时按当前调用和方向从后端 attribution API 加载归因，默认折叠在同一弹框内；初始页面不嵌入完整归因。

Qoder session 的 request attribution 可用时必须优先使用 call-scoped `full_messages_array` 重建 Claude-like API messages。该 bucket 必须包含当前 call 边界前 request 侧 user、assistant、tool_use 和 tool_result items，并汇总每个 item 的完整 `content_token_estimate`。Provider reported `cache_read_input_tokens` 只在 request summary 中作为 `Cache Read` 和 provider accounting metadata 展示；不得创建 raw `provider_cached_context` bucket，不得参与本地重建 coverage。`cache_creation_input_tokens` / Cache Write 保留在 usage summary，但不得作为额外 request-source bucket 或 request bucket denominator。Qoder 未持久化完整 available tools schema 时，attribution 必须使用 Claude-Code-like SDK 默认工具定义作为当前缺省来源，并补充 observed Qoder-only tools，而不是只按 invoked tools 估算；工具定义 bucket 必须以 canonical key `tool_definitions` 输出。

页面还必须提供 payload modal：包含 View Request / View Response / View Result 按钮、Rendered / Raw 展示模式切换、多 part 分段展示；tool result payload 的 modal subtitle 和 metadata rail 必须展示 `result tokens` 估算值。该值由 tool result 文本估算，格式为近似 token 数，并作为下一次 LLM call 的 request-pressure metadata，不得标记为 provider reported usage。modal 必须支持 backdrop click、Escape key 和 close button 关闭。

#### Scenario: MHTML 自包含导出

HTML 和 MHTML 离线导出遵循 MHTML Export Spec：保留当前会话已发布的完整记录和原生展开，不复制在线交互界面。

### Requirement: Trace rows 的 ARIA 可访问性

每个 trace row 必须是语义化 `<button type="button">` 元素，并满足：
- `aria-expanded` 反映当前展开状态（`true` 或 `false`）。
- `aria-controls` 指向关联的 trace-detail 元素 ID。
- trace-detail 元素的 `id` 必须匹配 `aria-controls`。

### Requirement: Trace events 的 payload 按钮

Attribution controls、message rows、assistant event rows 和 tool call rows 在存在 payload data 时必须渲染 payload button。按钮必须包含：
- `data-action="open-payload"`。
- 指向 payload source id 的 `data-payload-id`。

### Requirement: Shell residue gate

Session Detail 页面不得渲染：
- Sidebar Round Map（`.round-map` section）。
- Sidebar 中的 Projects / Agents navigation links。
- Topbar shell toggle buttons（sidebar toggle ☰、right panel toggle ☰、focus ●）。
- Map / Inspector / Focus layout mode buttons。
- Density toggle button。
- 可见的 disabled placeholder buttons（search、export、theme）。

### Requirement: No content-modal entry points

页面不得渲染 `content-modal` 元素或任何 `data-content-modal` 按钮。不得定义 `openContentModal` 函数。

### Requirement: Dead button gate

Session Detail 页面每个可见 `<button>` 都必须使用以下受支持的 `data-action` 值：
- `status-all`
- `status-failed`
- `toggle-all`
- `toggle-round`
- `open-payload`
- `open-payload-tab`
- `open-trace-step`
- `select-payload-call`
- `payload-filter`
- `payload-mode`
- `close-modal`
- `close-payload`
- `copy`
- `jump-round`
- `jump-anomaly`
- `retry-attribution`
- `retry-round`
- `toggle-sub-round`
- `toggle-subagent-rounds`
- `md-toggle`（tool result markdown toggle）

### Requirement: No removed entries

Session Detail 页面不得渲染：
- Calls tab、Hotspots tab 或 workbench view switching。
- 默认 Session Detail 入口中的常驻 Inspector panel。
- Round Map。
- Map / Inspector / Focus layout mode buttons。
- Density toggle button。
- 可见的 disabled placeholder buttons（search、export、theme）。
- Failed only / High token / Open selected chips。
- Message / Tool / Error type filters。
- Timeline jump input 和 Go button。
- `× Clear filter` button。
- 独立 Calls tab/table。
- 独立 Hotspots tab/cards。
- Token Usage collapsed chart。

### Requirement: Global shell simplification

Session Detail 的全局导航必须保持精简。Inspector panel 不得作为 Session Detail 页面默认第三列渲染。

### Requirement: Codex subagent diagnostics

Session Detail SHALL surface recognized Codex subagent runs through Agents Breakdown and Trace without merging child usage into the main agent.

#### Scenario: Recognized Codex subagent appears in Agents Breakdown

- **Given** a normalized Codex session includes one or more recognized subagent runs
- **When** Session Detail builds the diagnostics view model
- **Then** the `Agents Breakdown` candidate list SHALL contain `main agent` first
- **And** each Codex subagent run SHALL appear after `main agent` with its own LLM calls, footprint tokens, tools, and failures
- **And** selecting the subagent candidate SHALL switch the timeline to subagent rounds without navigating away from the card.

#### Scenario: Recognized Codex subagent appears in Trace

- **Given** a Codex round has a recognized subagent run
- **When** the Trace round is expanded
- **Then** the round SHALL show a `Subagent Run` event row
- **And** each visible subagent round summary row SHALL expose `request` and `response` attribution actions when payload ids are available.


### Requirement: Trace 内容证据与调用身份一致
Session Detail SHALL 从当前轮所引用的 inline/catalog/sequence 可见文本或工具声明生成短摘要与源时间。它 MUST NOT 使用 session 更新时间、耗时或另一轮的文本代替当前轮时间或摘要；缺失来源 SHALL 明确标记。摘要 SHALL 过滤系统上下文、工具结果及长正文并应用默认脱敏。

工具短摘要 SHALL 对契约明确且参数有效的等待读取操作说明动作含义：精确 `write_stdin` 的有效 session ID 与明确空 `chars`、精确 `wait` 的有效 cell ID 且未请求终止。非空输入、终止请求、未知工具或无效参数 SHALL 保留原摘要兜底。原工具名和完整 Input/Result SHALL 可达；摘要转换仍应用原脱敏和长度上限，不合并调用、不推断进程关系、任务完成或耗时。

默认耗时诊断 SHALL 在确定执行上下文与可验证测量口径内，按原工具名展示已测累计工作量、单次最长、调用/测量覆盖及稳定代表动作入口。多次短调用的累计不得被单次最长替代；未知耗时不补零，合法零计入已测，部分覆盖和其他口径需就近说明。聚合取冻结全范围，不取当前分页或截断/脱敏preview；逐事件来源定位符不等于测量事件族。父子上下文、未知身份或不同口径不得混为全局排名；有界展示需披露截断，不给墙钟占比、模型耗时或完整瓶颈结论。

同类有多个已测调用时，紧凑诊断卡 SHALL 提供默认收起的耗时明细，从同一冻结上下文/口径最多取单次耗时前3个独立调用，保留安全命令摘要、观测时长和稳定ID定位。当前摘要页之外的候选 SHALL 无需下载全部前缀即可发现并定位；不因同名/同preview合并调用，不预取全文、不重排执行时间线，明确有界候选并非全部慢项或根因。

存在可信耗时卡且未观察工具失败时，零失败 SHALL 使用紧凑状态说明并保留不证明任务成功或记录完整的边界；通用完整计量和异步解释可复用既有计量说明。模型未测、累计非墙钟/关键路径、未知非零与覆盖 SHALL 默认近邻可见，非零未比较/缺测/其他口径及组截断不得隐藏。真实失败整卡、命令和首失败定位，以及无工具/无可信计量指导不得降级。

有工具、未观察失败、已测工具数为零且无上下文计量项时，原状态卡标题 SHALL 优先显示“无可用工具时长”，而非“0 个工具有失败信号”；原未观察失败不证明成功/完整的正文、无法按耗时判断慢项及查看操作/结果的指引 SHALL 保留。真实失败、无工具、合法已测零时长、有时长但不可可信累计或非空计量项 SHALL 保持各自分支；不改变计量、状态、原文、归属、请求或卡片结构。

本地流式内容与独立导入的已物化制品 SHALL 使用相同预览规则，优先本轮可见用户输入，其次工具计数及短操作，最后助手文本。历史用户引用 SHALL 只归属首次出现的轮次；完整 Request 仍可保留历史上下文。

#### Scenario: 纯工具轮及后续结果消费
- **WHEN** R1 声明工具 A，R2 消费 A 的结果并声明同名工具 B
- **THEN** R1 的模型 Response 与 Tool Input/Result SHALL 按 A 的身份关联，R2 SHALL 仅计 B 为新执行；可见摘要 SHALL 区分两个操作。

#### Scenario: 响应有边界证据但输出未记录
- **WHEN** 响应记录的 `response === true`、`toolCount === 0` 且 `outputAvailable === false`
- **THEN** 组头 SHALL 显示“本地未记录工具声明”，而非“下发 0 个工具”；本地零声明计数 SHALL NOT 被表达为完整 provider 输出确定未下发工具。
- **AND** 有本地输出的零工具组、正数工具批次与非响应组 SHALL 保持原呈现；缺省可用性标识不得当作明确 `false`。工具计数、执行行、归属、耗时及后续结果消费关联 SHALL 保持，不新增告警或请求。

#### Scenario: 独立 Input 与未知模型来源分别表达
- **WHEN** session-content 的生产 occurrence 证据可核独立工具参数，而模型 owner 仍未确认
- **THEN** 既有命令位置 SHALL 显示该工具安全预览，原 Input/Result SHALL 独立按需可查，不因缺少模型 Response 误报“参数未记录”。来源未确认、未观察模型输出及模型输入输出不可用 SHALL 保持，不造调用/归属/response refs，不授予同参累计资格；无证/冲突/不完整/截断/超预算仍诚实缺失。
- **AND** 复用现有脱敏、转义、严格解析及预览/正文预算，不新增 DTO/API、默认请求、payload/catalog 预取、面板或 CSS。完整正常父子合成源中 call1/tool2、500ms/exit7、Result 与既有权威 Agent 标签 SHALL 保持；1440/390 默认可见命令，按需原参数和 Result 可读，定位请求完成且目标稳定后验证焦点。此内容可读不代表任务完成或模型响应已记录。
- **AND** 默认共享敏感字段策略 SHALL 同时遮盖 api_key/apiKey 与 api-key 等号参数、现支持的带引号值及 JSON 字段，不在安全命令预览暴露其值；FULL/noMasking/custom 与非敏感字段原语义保持。本场景不声称任意 shell 语法或未知凭证命名均已覆盖。

### Requirement: 展开区域不得重复概览工具操作
纯工具响应概览 SHALL NOT 与对应工具执行并列成为重复 timeline-item。独立助手文本、独立调用和子 Agent SHALL 保持可定位；成员操作 SHALL 绑定稳定 call ID。

#### Scenario: 按需展开与布局
- **WHEN** 用户展开 Round 的工具正文
- **THEN** Tool Input 和 Tool Result SHALL 独立按需加载并在桌面双栏、窄屏单栏展示；单页全量成员 SHALL 不显示调试式分页文案。

### Requirement: 缺失诊断和索引错误保持真实含义
诊断未提供、未加载、加载失败及测量为空 SHALL 可区分。工具计数 SHALL 解释本地归一化口径。非成功响应缺少 generation header SHALL NOT 单独被判定为换代；成功续页仍 SHALL 验证 generation，真实换代 SHALL 阻断内容合并并给出刷新路径。

#### Scenario: HTTP 错误不是索引换代
- **WHEN** 同一快照的 Round 返回无 generation header 的 HTTP 500
- **THEN** 页面 SHALL 显示可重试加载失败，不伪报 index changed；409 或不同 generation SHALL 显示刷新恢复路径。


### Requirement: Token 展示层级与共享分列

Context Budget SHALL 使用内容驱动的紧凑网格，保留分类标签、数值、占比、来源邻近。只有明确纳入且有可用 share 的分类参与构成；Partial SHALL 明确为近似非服务商精确统计，未知/未上报 SHALL 不补零。Tool Results SHALL 明确为构成之外的本地估算。缓存比率 SHALL 只用完整的服务商上报输入。

#### Scenario: 共享入口与窄屏

- **WHEN** 在桌面或 390px 视口查看列表、项目 Token Cell、Dashboard Token 趋势、详情 Agent/Round/Trace/call
- **THEN** Token 构成弹框使用共享色标/类型、数量/来源、占比列及 viewport popover，支持 hover/focus/Escape，长标签不截断；每个入口保留自己正确的分母与估算/未知/实测零状态。

#### Scenario: 按需诊断不删除能力

- **WHEN** 打开“运行诊断与耗时”、Tool Impact 或 Issues & Repro Seeds
- **THEN** 原有 typed timing、问题覆盖状态、工具明细、Round 跳转与定位串仍可达；没有分析不冒充零问题。

### Requirement: 可理解的多 Agent 协作概览
Session 详情页 SHALL 在紧凑过程附近提供有界协作概览，直接说明谁委派给谁、任务摘要、发起响应/工具及已记录回传证据。只有明确委派进入层级；等待、消息和结果报告作为有向往来，不把 Agent 标签或 Token 候选表冒充协作关系。方向 SHALL 使用文字和可访问名称表达，不依赖颜色、hover 或缩进。

#### Scenario: 概览、支路与原文
- **WHEN** 用户查看 sibling 或主 Agent → A → B 的记录
- **THEN** 默认 SHALL 提供有限参与者与关系及完整数量/截断说明，深层使用明确支路或 breadcrumb，390px 不无限右缩进。
- **AND** 每条明确关系 SHALL 可定位发起工具/响应、按需读取任务原文、查看该 Agent 执行及对应往来证据；回传目标未确认时 SHALL 如实标注，不捏造返回箭头。
- **AND** `included/childIncluded` SHALL 表示同冻结范围内有可经现有过程入口读取的上下文过程；已确认 call 或明确工具 scope 与完整执行实例均可提供依据。缺模型 call 不得否认已有工具过程，也不因此授予模型 owner、完整采集、完成状态或累计资格；spawn 目标、候选 raw、catalog、观测及 unknown owner 本身均不足以授予过程入口。
- **AND** 任务/消息/Result 全文 SHALL 继续按需读取，不按每个 Agent/round 预取全文，不依赖分页当前页判断有无 child。

#### Scenario: Agent 阅读与耗时
- **WHEN** 用户选择一个完整实例进入过程，或从关系定位未加载的发起/结果
- **THEN** 同 scope 后端 SHALL 按完整实例过滤并稳定定位，保留回到全部/所选支路的路径和焦点；Agent 筛选不是仅隐藏当前页。过程与诊断 SHALL 使用一致范围，包含有明确工具上下文但没有模型 call 的过程，仍标注模型来源未确认；不得只开放按钮却返回空过程，不补造 call/owner。MAIN 工具的目标实例不得当执行者，未知、匿名或与已知 call 冲突的身份不获得新的资格。
- **AND** 已测耗时及覆盖 SHALL 仍限同上下文/口径，父等待和子执行分开，不相加为 Session 墙钟、模型耗时、并行或关键路径。
- **AND** 新分页/筛选 SHALL 保留 generation、游标绑定、竞态及 409/500 恢复；normal 与 import 复用各自 api_base，不回个人 API 找 child。

#### Scenario: 同一响应的委派阅读层次
- **WHEN** 委派视图当前页连续关系有相同且明确的完整发起者与响应身份
- **THEN** 页面 SHALL 用共享响应标题组织这些委派，保留每项方向、任务、独立工具与状态/报告、过程入口和证据；不按相同显示序号、标签或工具名合并。
- **AND** 数量 SHALL 仅说明当前连续已加载片段，不暗示完整响应批次数量；不重排、不跨分页拼组、不推断并行或合并耗时，未知身份保持独立关系。
- **AND** 分组 SHALL 不新增折叠步骤，不改变等待/报告往来的顺序与语义；390px 不无限缩进，不裁切任务或丢失返回焦点。

#### Scenario: 所选往来的任务与创建归属证据分层
- **WHEN** 所选上下文的往来当前页存在相邻的明确委派声明与创建目标 ID 回执
- **THEN** 只有完整发起者、响应、工具与目标逐字一致且身份和关联依据明确、当前页配对唯一、无父关系问题时，页面 SHALL 将任务作为一个主卡，把该回执保留在卡内既有证据展开区；任务方向、摘要、过程入口与创建归属简述默认可见，不增嵌套折叠。
- **AND** 声明与回执 SHALL 仍各计一条事实，分页仍按原始事实数；回执的类型、完整身份、来源、Result 与定位不得丢失，不把按目标聚合的报告预览当作同一工具配对依据。
- **AND** 等待及本次状态报告 SHALL 保持独立与原序；未配对、身份缺失/冲突、重复配对、交错或跨页的事实不拼组、不重排，不猜唯一父级。创建 ID 回执不是 child 回答、任务完成或结果接收证明。
- **AND** 分层 SHALL 不增加任务到完整发起记录的激活次数，不新增请求、预取、缓存或离线能力承诺，追加页不得重建前页节点或夺取焦点。

#### Scenario: 同一 Agent 跨区域标签一致
- **WHEN** 协作关系、默认耗时诊断与执行过程独立加载、续页或切换快照
- **THEN** 同一完整上下文身份 SHALL 使用一致的 Agent 标签；不得按各区域可见顺序分别分配冲突编号，不能只在用户点击筛选后才纠正。
- **AND** 仅工具过程的存在性接线 SHALL 保留已登记 call/明确目标的 canonical 标签前缀和编号；新增执行上下文只能按来源顺序追加，不扩大既有 `contextLabels` 权威范围或按所选页重新编号。
- **AND** 权威标签未取得或失效时 SHALL 使用可区分的完整身份兜底，不冒充已确认编号；迟到标签更新 SHALL 保留既有分页、展开与焦点状态，不为标签预取全文或全部参与者。

#### Scenario: 缺失与既有能力
- **WHEN** 关系缺失、不唯一、未包含、未加载或结果未记录
- **THEN** 页面 SHALL 区分这些原因，未知状态不伪装已完成；无关系时提供简短能力说明，不造空树。
- **AND** 紧凑命令、工具输出双层、失败定位、复制、键盘、原文惰性、隐私及完整静态导出 SHALL 保留；不承诺离线复刻在线协作交互，MHTML 定位限制继续明示。

#### Scenario: 协作概览不淹没执行排查
- **WHEN** 默认查看协作关系，或从关系进入某个 Agent 的过程与耗时
- **THEN** 默认 SHALL 以紧凑关系呈现方向、任务、发起序号、必要缺失/冲突与报告概况；完整定位操作、逐条往来及重复的关联依据 SHALL 分层按需查看，不逐关系平铺全部按钮和共同解释。
- **AND** 所选 Agent 的上下文与同口径已测耗时/覆盖 SHALL 在实际入口落点就近可见或有明确可见的诊断路径，不只更新远处屏外数据；不能从当前页临时累加，不新增另一套计量事实。
- **AND** 收紧呈现 SHALL 保留全部证据、未知/截断披露、深层支路和键盘返回，不靠固定高度裁切或隐藏全部关系规避阅读成本。

#### Scenario: 从操作耗时理解委派来源
- **WHEN** 用户默认扫描不同执行上下文的已测操作
- **THEN** 页面 SHALL 以紧凑操作行保留各上下文、原工具名、已测累计、单次最长、测量覆盖、安全代表命令及稳定定位，既有缺测/其他口径/截断与计量边界默认可见；不为紧凑而裁切命令或隐藏全部慢项。除下述同家族已测子集线索的窄例外，不混排不同上下文的累计工作量；完整累计仍按上下文分块，不作任务成本或效率排名。
- **AND** 计量近邻 SHALL 可显示当前已加载明确委派来源及对应响应，并一次定位到独立任务关系；关联使用完整目标、发起者、响应和工具身份，不按编号或名称猜唯一父级，不把上下文累计当作某次委派耗时。
- **AND** 来源 SHALL 只覆盖实际已加载关系，追加页不遗失前页来源，多来源不得压成唯一父级；读取中、失败、当前视图未提供和无法确认 SHALL 保持可区分，不预取全参与者或原文补全。
- **AND** 统一耗时线索中的确定子上下文 SHALL 在累计和单次两种列表提供显式的任务与往来入口，复用完整上下文身份及既有有界 `exchanges` 查询；默认不新增请求，不要求先补齐全部委派或记住 Agent 编号。主上下文、匿名、冲突或不足以确认的目标不得据名称猜定向入口。
- **AND** 入口 SHALL 展示所选上下文范围的相关往来，保留多来源、方向、安全任务摘要、完整发起记录/工具及按需原文；不得把全部相关往来命名为唯一父任务或保证首个有界页必有委派声明，未加载范围和无可确认声明须诚实说明。上下文累计不因此归于某次委派。
- **AND** 每次显式激活至多请求一个既有有界页，续页仍由用户触发；读取中和失败不得将旧上下文内容冒充新选择，Retry 与迟到响应遵守当前选择和冻结范围。有效读取完成后引导焦点至对应协作范围，但用户已进行更后操作时不得抢回焦点或滚动；合法数据仍应用。不得新增全量参与者/原文预取或独立来源缓存。
- **AND** 关系视图/范围或 generation 改变 SHALL 撤销旧关联；迟到来源只修补关联区域，保留已有计量节点、展开、分页和焦点，不复制计量事实或移动完整计量卡到每条委派。

#### Scenario: 默认说明匹配阅读层级
- **WHEN** 零失败紧凑诊断包含多个已展示的可信上下文/口径分块
- **THEN** 相同的仅已测、非完整瓶颈、慢不等于异常说明 SHALL 默认集中出现一次；每块身份、独立上下文、观测来源与仅本上下文/同口径比较仍 SHALL 就近可见。单块、失败、无工具及无可信计量指导不得因去重降级。
- **AND** 当前范围有工具、未观察到失败且无任何可用工具时长与计量分块时，默认说明 SHALL 先明确无法按耗时判断慢项，并指向现有操作与结果证据；保留测量覆盖、未纳入比较数量、模型未测、未知非零及工具返回不证明任务完成。完整计量口径和异步状态限制 SHALL 仍在既有计量说明中按需可达，不用来源特例、时间差或新面板补出结论；有失败、可信计量或无工具的指导不因此改变。
- **AND** 仅面向子 Agent 目标的来源桥接 SHALL 不在主上下文展示必然无匹配的来源状态；无适用子上下文计量时，不显示仅解释该桥接的提示。此省略不证明主上下文没有上游关系，也不得删除子上下文的读取中、失败、未知或当前有界视图未提供说明。

#### Scenario: 记录身份与编号可见
- **WHEN** 紧凑过程包含有明确本地模型响应边界的记录，或独立调用边界未确认的本地响应记录
- **THEN** 组头 SHALL 默认可见地显示已有记录类型和定位编号，不仅放在 aria-label、hover 或折叠证据中；编号仅用于本地记录定位，不表示真实 provider 请求次数，同组也不表示并行。既有模型输入/输出仅含本地可见材料的边界 SHALL 保留。
- **AND** 没有响应边界类型的协作摘要及来源桥接 SHALL 用中性的发起记录编号，不无条件称为已确认模型响应；不从 execution 当前页猜类型或预取补全。完整发起者/call/tool/target 关联、同记录多工具、分页续组、模型与工具结果分层及键盘返回 SHALL 保持。

### Requirement: 截断概览仍可发现可信单次长操作
当默认计量分组被上下文上限截断且存在可信候选时，页面 SHALL 在失败判断之后、完整累计分块之前提供统一耗时线索区；单次已测最大值及完整执行身份默认可见，单次至多三条明细无需选择 Agent、最多一次指标切换可读。存在下述已测累计候选时默认展示累计列表，否则直接展示单次列表；不平铺两套至多六条明细，不通过预取全部参与者或原文补全。

#### Scenario: 长操作位于未展示的上下文
- **WHEN** 同一冻结范围内第九个或更后上下文含明确的 exec_command 执行器观测
- **THEN** 候选 SHALL 从完整范围、当前 Agent 筛选中选取，而非仅前八个分组；仅对 exec_command、executor_reported 与 codex:exec_command_end 事件族的确定身份单次调用，按精确纳秒及稳定完整身份取前三项。
- **AND** 单次活动列表每项 SHALL 就近显示执行上下文、安全命令、单次时长与稳定定位；另一指标的最大值与完整身份默认摘要可见。权威标签未到时用完整身份兜底，迟到标签不重建计量、抢焦点或改变范围。
- **AND** 该家族的可信已测数、同工具总数及未知时长、其他口径、未确认身份排除范围 SHALL 如实披露；零和亚毫秒保真，未知不补零，匿名/冲突/推断或不支持口径不得占据候选。
- **AND** 这仅允许同家族具体单次观测作为排查线索，不是 Agent 效率、任务成本、累计、墙钟、并行、关键路径、异常或完整瓶颈排名。父 wait/poll 与其他家族不混入；原累计、覆盖和短调用集中点 SHALL 保留。

#### Scenario: 未截断的多上下文重点
- **WHEN** 当前计量未截断、为全部 Agent 范围、零工具失败、原计量块身份均明确，且实际可信候选涉及至少两个不同完整执行上下文
- **THEN** 页面 SHALL 复用同一统一线索与下述原生计量明细分层，使长子操作或重复短调用集中点不因上下文顺序落后于主操作；候选、顺序、默认指标和已有动作含义不变，不增加第二榜或请求。资格不得仅依据合格组总数或同上下文不同工具数推定。
- **AND** 不满足该窄例外的未截断范围 SHALL 保持既有默认计量与指导；某指标无候选时不造空入口，有另一指标时直接显示可用列表，两者均无时不造空榜。其他家族不自动混排。

### Requirement: 同类已测累计集中点与单次线索分层
统一耗时线索区 SHALL 允许同一冻结范围及当前 Agent 筛选内、确定身份的 exec_command 执行器观测子集按精确已测累计比较，作为发现重复短调用集中点的窄例外；该比较不是实际总耗时、任务成本、效率、墙钟或完整瓶颈排序。

#### Scenario: 未展示上下文包含大量短调用
- **WHEN** 默认前八个计量组之外有同类工具的多次可信观测
- **THEN** 服务端 SHALL 从完整范围先确认身份及测量资格，再按精确累计纳秒和稳定完整身份选取至多三个组，不从已返回八组重建。仅累计 exec_command、executor_reported、codex:exec_command_end 事件族的原始纳秒；父 wait/poll、推断和其他口径不混入，不跨上下文相加。
- **AND** 一个组的已记录同名调用 SHALL 均满足确定声明身份与唯一已解析委派依据；无法确认的整组及无法归组调用如实排除，不猜匿名身份。计时允许部分覆盖：缺测和其他口径不补零，有至少一条可信观测即可入选，合法零和亚毫秒保真。
- **AND** 默认每行 SHALL 显示完整上下文、已测累计、已测/同名总次数、最长单次及非零缺测/其他口径；代表动作明确为本组单次最长，不把全部累计归给该调用或某项任务。稳定代表动作定位与上下文过程入口保持不同含义。
- **AND** 全范围同名调用覆盖、身份边界排除及合格组数 SHALL 在裁剪前统计，计数互斥闭合；候选行覆盖不冒充全范围覆盖，组数不称 Agent 数。默认就近说明只比较已测子集，缺测可改变真实总量顺序，记录内覆盖不证明采集完整。

#### Scenario: 单一线索区切换指标
- **WHEN** 累计与单次指标都有可信候选
- **THEN** 默认 SHALL 展示至多三条累计明细及单次最大值/完整身份摘要；切换后展示原单次至多三项并保留累计最大值/完整身份/覆盖摘要。任意时刻只有一个活动明细列表，不混合评分或按 Agent 去重不同调用。
- **AND** 切换 SHALL 只消费已返回数据，保留按钮焦点，不改变 Agent、过程分页或关系范围，不请求原文、全参与者或新诊断。过程续页/定位不重置当前指标，Agent 范围或冻结内容换代后重新选择可用默认指标；迟到标签只局部同步。
- **AND** 累计未知或无资格时 SHALL 直接回退可用单次列表，不显示空累计入口；未截断仅在上述多上下文窄例外中替代原平铺层，不无条件新增重复层。静态全文与现有离线边界保留，不把在线切换冒充未经验证的离线交互。

### Requirement: 耗时线索的动作优先级匹配指标粒度
统一耗时线索 SHALL 使用已有动作，以真实 DOM 顺序体现累计与单次排查粒度，不增按钮、说明、默认请求或新导航状态。

#### Scenario: 行动优先级匹配指标粒度
- **WHEN** 用户读取统一耗时线索的累计或单次列表
- **THEN** 累计项的可用动作 SHALL 按真实 DOM 顺序显示“查看上下文过程”、“定位代表调用”、“查看任务与往来”；单次项 SHALL 保持“定位此动作”在前、可用任务入口在后。视觉和键盘顺序一致，不通过 CSS 重排制造不同次序，不增新按钮、说明或默认请求。
- **AND** 现有动作的文字、完整身份、范围和聚焦合同 SHALL 保持：上下文选择仍先显示就近计量，再通过既有链接进入同范围的有界过程；代表定位仍是当前范围内的单次工具，不将累计归于代表或某项任务。不宣称重排减少了点击数或加载全部调用。

### Requirement: 失败线索就近显示执行归属
默认失败卡 SHALL 在首个失败命令近邻显示该工具已记录的执行上下文，避免按后续计量块猜归属；不将父等待报告当作子工具成功或整项任务完成。

#### Scenario: 子 Agent 失败且父等待报告已返回
- **WHEN** 首个失败工具有明确 main/subagent scope，或子 Agent 身份尚未确认
- **THEN** 失败卡 SHALL 复用该工具身份与跨区域标签：明确主会话、具名子上下文或身份未记录；权威编号未取得时保留完整身份兜底，不按当前位置猜编号。
- **AND** 迟到标签 SHALL 仅同步既有身份文本，保留失败命令、数量、定位 target、计量、分页与焦点；不增加请求、猜测父级或复制任务计量。缺少工具上下文时 SHALL 不伪装主会话。

### Requirement: 协作导航名称符合实际去向
导航 SHALL 区分查看现有协作概览与返回真实来源位置，不用是否存在协作事实冒充用户已有返回路径，不删除有用的概览跳转。

#### Scenario: 尚未从协作入口进入过程
- **WHEN** 页面有可用协作概览但用户尚无有效来源入口
- **THEN** 过程旁导航 SHALL 显示查看 Agent 协作的含义，并聚焦当前协作位置；不得以返回支路暗示并不存在的阅读历史。
- **AND** 没有可用协作位置时 SHALL 隐藏该入口，保留既有无关联说明，不造空支路。

#### Scenario: 返回真实协作来源
- **WHEN** 用户从委派、参与者或往来中的有效入口进入 Agent 过程
- **THEN** 导航 SHALL 明确表示返回协作位置，激活后聚焦原始来源入口；不把所有来源都命名为委派支路。只有工具过程、模型来源未确认的有效入口同样适用，不能以模型记录缺失撤掉真实返回路径。
- **AND** 来源节点因视图替换、快照换代或失效不再可用时 SHALL 撤销旧返回语义，按当前可用概览降级或隐藏；普通追加、迟到标签和局部来源更新不得丢失仍有效的返回位置。不得为导航新增请求、改变过程范围、计量或证据关联。
- **AND** 选择过程尚未完成时用户已激活协作导航，迟到的选择完成 SHALL 不夺走新的导航焦点；原数据读取和范围可按既有 epoch 继续，不通过额外请求或取消有效数据来模拟返回。

### Requirement: 统一线索与上下文计量明细分层
已有可信统一耗时线索实际呈现、当前为全部 Agent 范围、未观察工具失败且包含多个身份明确的上下文/口径块时，页面 SHALL 将原逐上下文计量收进一个默认关闭的原生“上下文计量明细”，作为默认逐块计量的有条件分层例外。统一线索、全范围覆盖、非零排除和组截断、模型未测、未知非零、非墙钟/关键路径及任务非完成边界 SHALL 仍默认可见；不删明细、不改数据、候选、排序、前八上限或请求。

#### Scenario: 默认概览下沉重复计量
- **WHEN** 上述资格成立
- **THEN** 一次展开 SHALL 可达原有全部已载分块的身份、工具/口径、覆盖、来源、代表动作、慢项及定位，summary SHALL 如实说明已载/总计量组数及非排名，仅截断时称前缀，不称 Agent 数或保证未载组可继续读取。部分覆盖组的非零缺测/其他口径及完整归属 SHALL 在外侧保留紧凑提示，不能只以总数掩盖局部缺口。
- **AND** 折叠时，已载非 exec_command 工具或不同计时 kind 的上下文、工具名、已测累计、已测/总数及非零缺口 SHALL 默认以紧凑次级计量行保留，不能只在 summary 列名称而隐藏已知时长。不得与可信 exec 候选混排或跨家族求和，也不得从代表动作的 source 推断整组家族；这些行不宣称列出全部未比较来源或完整瓶颈。
- **AND** 无统一线索、未截断且不符合多上下文窄例外、单块、失败、无工具/时长、身份不明或选择了 Agent 时 SHALL 保持既有默认计量与指导；仅“有可信计量的失败页说明文字窄分层”所述条件允许说明归属例外，不折叠失败卡或其计量卡，尤其所选 Agent 的近邻累计与覆盖不能多一次展开。详细计量与计量方法说明 SHALL 分开，不通过固定高度裁剪隐藏内容。

#### Scenario: 披露与有效来源焦点保留
- **WHEN** 同一 Agent 范围和冻结 generation 内追加过程、切指标或收到迟到标签/来源
- **THEN** 已展开的明细、相关原生展开及有效焦点 SHALL 保留；指标和局部来源更新不重建这些有效节点，不因披露自动请求全文或全部关系。显式更换范围/generation SHALL 按当前资格重新初始化，不新增导航历史。
- **AND** 显式返回的有效原来源位于关闭的祖先 details 内时 SHALL 先揭示再聚焦原节点；失效来源仍按既有规则降级，不复活旧来源、不抢更后用户操作焦点。离线归档能力边界不因在线披露扩大。

### Requirement: 初始委派与后续输入分层可发现
协作页面 SHALL 区分初始委派、追加输入声明、工具本次提交回执和等待报告，不把创建树当完整往来，也不将追加输入配成创建归属回执或child回答。新事实仍使用已有方向、安全摘要、来源定位与按需Input/Result，不新增默认全文或消息图。

#### Scenario: 默认可发现追加输入
- **WHEN** 冻结source/import范围内存在input声明，即使它不在当前已载委派或往来页中
- **THEN** 原“全部协作往来”入口 SHALL 明示全冻结范围inputDeclarationTotal，仅计input/declaration，独立于当前selection/view/前缀；无此事实时保持原字样，不把回执数/卡数/委派数混入。不默认新请求，不承诺一次进入即到第一条追加输入，原分页仍有界手动。
- **AND** 只有追加输入但无创建委派时，空树指导 SHALL 不谎称没有往来，既有入口仍可发现；不为此新建Agent或父边。

#### Scenario: 追加内容与有限回执含义
- **WHEN** 用户阅读全部或所选上下文往来中的input事实
- **THEN** 声明 SHALL 明确谁向谁追加输入、发起记录/工具与有界安全内容；可复用原preview字段但标签为追加内容，不称初始任务。合法items无法安全提取文本时明确摘要未解析，不能丢整条事实或默认铺JSON。
- **AND** 回执 SHALL 最多说明工具报告排队接受；缺失/错误/冲突不得说已收到、采用或完成。interrupt与submission_id按需原文保留，不新造生命周期；当前页没回执不冒充全范围缺结果。非delegate类型不得无条件落入等待文案，未知kind中性兜底。
- **AND** 原创建配对、完整四元身份、稳定定位、范围/generation/导入隔离和有效焦点 SHALL 保持；1440/390方向/类型/边界用文字自然折行，不靠颜色或hover，离线能力不因此扩大。


### Requirement: 明确追加输入提交错误的默认关注与精确证据
页面 SHALL 在原执行判断近邻，用紧凑提示和单一入口展示“全冻结范围已记录N条明确追加输入提交错误”。计数仅包含`input/result_report/explicit_error`事实，不双计声明、不计queued，不按工具ID去重成尝试数；未知、未采集、缺失不能推为错误。它不改变工具执行失败、耗时、首工具或任务结论；零条不证明没有发生错误，资源截断和解析限制仍须披露。

#### Scenario: 现有响应给出全冻结首错线索
- **WHEN** 正常或导入冻结内容存在明确错误，包括首个往来窗口之外的事实
- **THEN** 原collaboration响应 SHALL 提供全范围`inputSubmissionErrorReportTotal`和至多一个`firstInputSubmissionError {cursor, exchangeOffset}`；不依赖当前view/selection/分页，不携带任意错误正文、路径或原文，不增加默认请求或payload读取。
- **AND** 首错cursor SHALL 绑定同快照的`exchanges`、空selection、limit20及`evidence_window=input_submission_error`；marker只允许此组合及非空cursor，响应以`evidenceWindow`回显。普通scope不变，跨快照/筛选/marker串用须拒绝；游标不是授权或签名凭证。

#### Scenario: 一次进入实际错误而非无错误前缀
- **WHEN** 用户激活错误入口
- **THEN** 仅请求一个受保护有界窗口，核对响应marker、offset和首项明确错误后聚焦真实事实，不复用裸tool/call first-match、不自动翻到末页。无法确认则显示重试/刷新，不退回任意卡。
- **AND** 窗口 SHALL 明示实际已载起点–终点/总事实数与未载前缀；续页手动并保留marker、窗口起点及原节点。普通view/selection切换退出该窗口。

#### Scenario: 整个错误窗口不以歧义ID猜原文
- **WHEN** 保护窗口及其追加页提供主行或嵌套reports的Input/Result
- **THEN** 服务端 SHALL 对至多4×limit候选完整核验冻结工具/声明身份，提供`toolPayloadState=unique|ambiguous|unconfirmed`；只有unique开放既有按需原文。重复工具、声明或call冲突不授资格；未知owner、目标未采集和唯一工具的多结果/镜像本身不构成重复工具。
- **AND** 保护窗口 SHALL 不生成旧裸tool/call execution定位入口，仍保留方向、完整来源身份和精确错误事实；歧义原文明确无法唯一定位，不删除错误。工具级Result可包含该工具全部已记录结果，不冒称单一回执、child回答或接收/采用/完成证明。不宣称旧全部入口或全局payload歧义已修复。

#### Scenario: 注意摘要独立于当前DOM来源和迟到意图
- **WHEN** 协作切view/selection、参与者、续页/Retry失败、过程重绘或generation变化
- **THEN** 同代已接纳全冻结摘要 SHALL 与DOM委派sourceStatus分离，不变为当前所选Agent的错误数；初次读取/失败/字段缺失不得伪报零。新scope/generation撤旧ref与导航，旧响应不能复活；409刷新、普通失败重试沿现生命周期。
- **AND** 更新只影响稳定注意slot，不重建原判断、计量、过程或展开、不抢焦点，并保持宽屏迟到阅读锚点。显式进入后更后操作优先，返回仅到同代仍connected的真实原入口，与现协作/热点返回独立。390/1440/宽屏自然可读，不新增通用状态面板或扩大离线承诺。

### Requirement: 明确协作声明的主摘要优先安全操作文本
同冻结scope与完整工具occurrence下，有唯一明确的delegate/input声明且参数文本有效安全时，执行过程与诊断共用主摘要 SHALL 优先显示“委派任务/追加输入”文本；不以裸工具名、任意message或结果猜资格。未知/冲突/非法/无安全文本、非文本或无法诚实概括的混合输入 SHALL 保持原安全预览。catalog/inline与normal/import策略一致，不依赖事实/目录先后或跨scope裸ID。原严格解析、64×1024字符参数、脱敏与180字符摘要预算保留；不增加前端字段/默认请求/面板，不改变wait_agent等其它工具、原名/计数/状态/计时/定位，完整Input/Result按需可达，不推送达/采用/完成或任务成本。

#### Scenario: 已确认文本意图不先读协议壳
- **WHEN** 同范围完整工具有唯一明确委派或追加输入声明，原Input有有效message/prompt或可诚实概括的文本items
- **THEN** 主摘要显示有界安全任务/追加内容，目标和控制参数仍保留在原Input；normal/import及catalog/inline结果一致。
- **AND** 无明确资格、身份冲突、非法/超预算/非文本或不够诚实的混合内容使用原预览；调用数量、原Input/Result及发起记录与工具定位不变，默认零新增请求。

### Requirement: 既有累计项内的同完整输入热点
页面 SHALL 仅消费服务端有界且可核的同完整输入最大项，在既有累计项内条件性最多一条安全提示；不新建同层榜/分类器，不替换或重新绑定原累计、最长单次代表及其定位，不把上下文累计或输入组累计归给某一次调用、委派或业务任务。

#### Scenario: 默认识别重复短调用的具体输入
- **WHEN** 同一确认上下文有200次可信500ms调用，完整输入alpha20次、beta180次且全部可识别，父累计项原本可见
- **THEN** 1440与390默认 SHALL 在该100s/200项内先读出被包含的已测90s及180/180次，再读对应安全beta摘要与本组2种参数记录；长摘要不得把核心时长推到阅读末尾。输入100%识别是提示资格不变量，其200/200详细适用计数 SHALL 在既有计量说明中可核，不在默认层与时长覆盖/父组覆盖重复堆字段。原alpha最长500ms、原定位、上下文/任务入口与粒度标签保持。不得要求先加载20/40/全部过程或自算次数，安全命令与数字自然折行且不横溢。
- **AND** 新行 SHALL 明确为同完整输入调用的已测累计最多，不称同业务操作总成本；180/180是该输入的时长覆盖，200/200是父组输入识别覆盖，不混同全范围采集完整。partial场景 SHALL 显示例如179/180的已测覆盖及非零缺测/其他口径，沿原默认已测子集与未知可改变顺序说明，不补零。

#### Scenario: 资格不足保持原布局
- **WHEN** 父组输入识别不完整、冲突/超限、只有一种输入、全部唯一、最大输入未重复可信测量，或无安全可核证据
- **THEN** 页面 SHALL 省略新行，不用preview猜合并、不增加暂无占位/可识别子集榜或新默认免责声明；原累计、覆盖和指导保持，不把省略解释为零或无异构操作。同preview的不同完整输入 SHALL 仍分组不同，单个多行script不拆调用。

#### Scenario: 两种既有载体共享事实而不扩显示规则
- **WHEN** 当前为统一累计列表，或所选Agent/单块的原近邻累计显示
- **THEN** 统一累计项 SHALL 消费同一个服务端可选事实；旧近邻Workload只有完整context+name与可信父组一致且计时集合/精确和/覆盖一致时才接入该事实，不从代表source推整组、不再次聚合或放宽旧资格。新行仍嵌在原组内，所选Agent不多一次展开，不产生独立面板/状态。
- **AND** 单次metric的活动单次项 SHALL 不混入输入累计；已有反向累计摘要保持原值，切回累计读取新提示，不平铺新3+3榜。Agent切换、过程20→40续页、范围/generation与迟到标签/来源 SHALL 遵守既有隔离、有效展开、指标、返回和焦点合同，normal/import不串用事实。
- **AND** 默认呈现 SHALL 不新增请求或预取原文；本行最多允许下述一个复用既有寻址的行内样例定位入口，不新增导航协议。原“定位代表调用”仍指alpha最长，不偷换为beta。安全证据与完整Input仍走既有按需路径，任何将来的新行定位只能复用既有完整工具身份handler。父wait、原35s单次最大、关系tuple、任务/回执分层及模型未知/全范围覆盖不因本行改变。
- **AND** 导出仅可承接安全投影文本，不携原文/hash或新增离线请求；本段不宣称已验证HTML/MHTML/离线交互，不扩大既有静态档案边界。

#### Scenario: 从同参数累计线索定位一个样例
- **WHEN** 合格同输入最大项已显示且包含当前冻结范围可核的工具身份
- **THEN** 页面 MAY 仅在该行的安全摘要之后提供一个明确“一次调用”粒度的行内定位入口，复用服务端选定工具的既有 `data-execution-locate` 寻址、当前过程范围和有界目标页，不从preview猜工具，不先逐页读到样例，不另建导航协议或自动切换Agent。统一累计与合格所选Agent近邻使用同一个入口语义；单次活动项与无资格行不出现入口。
- **AND** 该入口 SHALL 不替换原最长代表定位，不将该样例称为90s单次或180次全验。显式定位只读取既有过程摘要；Input/Result仍须原生按需操作，不默认展开证据、预载payload或新增原文/hash字段。目标 SHALL 按实际API工具身份核对，不假定某个硬编码beta序号。
- **AND** 入口 SHALL 属于热点说明行而非原三个同层动作组；1440/390保持90s/覆盖优先、自然折行与键盘可达。定位后聚焦既有工具节点；现指标/有效披露、epoch和更后意图优先、原真实协作tuple及返回焦点合同保持。不新增虚假的“返回热点”来源历史，不扩大离线交互或导出请求能力。

### Requirement: 默认执行热点携带同快照权威上下文显示提示
既有execution响应 SHALL 为当前有界过程与诊断实际引用且有完整call权威依据的上下文携带`contextLabels`，默认热点不依赖参与者目录分页即可使用与collaboration一致的标签。完整key SHALL 仍是唯一身份；label只作显示，不改变归属、分组、排序、tuple、计量、请求或任务成本。本段补强已有“同一Agent跨区域标签一致”的默认取得路径，不取消真实无权威hint时的完整身份兜底。

#### Scenario: 热点不在默认参与者前缀
- **WHEN** 当前完整冻结范围十child中，实际canonical catalog确认100s累计（含beta90s）与35s单次属于Agent8/9，而默认协作只返回5个participants与5个items且未含这些key
- **THEN** 1440/390默认热点 SHALL 直接显示对应权威标签，无须先比raw ID、选择Agent、加载目录或等待协作请求成功；真实normal/import对各自可核上下文共享本规则而不串用内容；单文件只含main时保持主会话文案，不制造child。具体编号来自同快照实际遍历，不由ID尾数或诊断次序猜测。
- **AND** 默认请求/过程分页与计量不变，不新增HTTP、自动参与者/往来翻页、原文或来源邻居读取；100s上下文累计、90s同完整输入累计与35s单次仍各按原口径，不归到一次委派任务，主会话现有文案保持。

#### Scenario: 全冻结遍历口径与有界输出
- **WHEN** execution发生selected/status/target/cursor/limit筛选，或call顺序包含非数字ID、main非首、匿名占位与跨unit重复key
- **THEN** 权威hint SHALL 来自与collaboration同一全冻结内容、同一首次key登记/ordinal实现，先登记全calls再筛选；main/匿名占位沿原算法，不局部重编号、不复制两套算法。工具阶段追加不改变已登记call key标签；仅工具/缺call权威身份 SHALL 不借label猜归属。
- **AND** 响应 SHALL 仅返回当前items与既有有界诊断字段实际引用key和call权威集合的交集，不暴露全participants catalog、不返回未载候选目录。上界按当前DTO引用槽与limit计算为`2P+69`（P≤100），不得用另猜cap截掉可见热点。收集 SHALL 复用现有metadata流，不增内容cursor/独立全内容扫描、domain/持久schema/parser/index/cache或通用registry。

#### Scenario: 标签接纳不破坏同代优先与换代隔离
- **WHEN** 有效execution页返回hint、同代过程追加或迟到collaboration标签更新
- **THEN** 页面 SHALL 复用完整key label cache，hint只补同代缺值、已载协作标签优先；迟到标签只换既有文本，保留分页、指标、有效DOM/details、动作身份和焦点。hint不得进入导致诊断随过程页重建的数值签名。
- **AND** 新冻结generation接纳时 SHALL 清旧Map后接纳当前有效hint，不被同batch后置清理擦掉、不从旧page跨代补回；未发布/失败批次和过期epoch不得写入当前authority。500/Retry、409、normal/import隔离及更后用户焦点意图保护保持；真正无hint/失效标签仍诚实fallback，不以此替代上述已确认默认热点目标。
- **AND** 导出仅可消费安全静态标签文本，不增加离线请求或交互承诺；本规划验证不表示产品或MHTML效果已实现。

### Requirement: 首个失败工具的安全具体依据
默认失败卡 SHALL 在原有一句话位置消费同一server失败判定派生的有界firstFailureEvidence，区分有效非零退出、明确执行器负面状态与工具结果失败线索；不复制任意错误原文、不增加前端第二分类器、面板或请求，不改变原失败真值/数量/首工具顺序/target/命令/归属/计量。首个依据不是唯一根因，也不等同整个任务失败。

#### Scenario: 一句具体事实覆盖可达信号
- **WHEN** 真实Codex normal/import首工具分别有exit7/completed、无exit/cancelled、exit0/failed或exit0/completed加工具结果error线索
- **THEN** 1440/390默认 SHALL 分别读到退出码7、执行器cancelled（取消）、执行器failed（失败）或工具结果记录含失败线索，并保留不等同整个任务失败及原定位；不把取消称错误、completed/exit0称成功，不要求先展开原文才知依据。
- **AND** server SHALL 从既有firstFailureTool用同一判定按有效非零exit→精确failed/error/cancelled执行器状态→既有result signal选择一个依据，保留原空值/大小写/空白/exit优先级及全部failed语义。载体 SHALL 仅含有限kind、适用的integer exitCode或白名单executorStatus，不含任意tool.status文本/源路径/hash；不新增内容扫描/索引/持久字段或改schemaVersion。obs0/tool7反向冲突只作DTO等价保护，不冒称当前Codex真实源复现或为此扩源。

#### Scenario: 缺失与更新仍保诚实边界
- **WHEN** 依据缺失/null/未知或首摘要缺失，或同冻结范围发生续页、目标定位、迟到标签与换代
- **THEN** 缺失依据 SHALL 用中性指路兜底，不由raw字段猜依据；非法DTO值不得成为默认错误原文，正向有据场景不得以兜底代目标。已有安全命令/数量/身份/定位、同代label仅文本更新、有效节点/展开/焦点及scope/epoch/generation/import隔离 SHALL 保持；稳定首工具依据不因过程页/hint子集而重建诊断，不增加HTTP/payload/catalog预载。
- **AND** 本段 SHALL 保持既有静态导出安全边界，不新增离线请求或交互承诺；新依据在离线导出中的展示不纳入本段已验证能力，后续若承接须另供实际验证。规划通过不得视为实现。

### Requirement: 有可信计量的失败页说明文字窄分层
仅当前`failures>0 && measuredTools>0 && workloads.length>0`时，页面 SHALL 将原默认完整measurement说明放入现有“计量说明”，默认保coverage与短安全边界。此规则是“统一线索与上下文计量明细分层/默认概览下沉重复计量”中失败保持既有默认计量与指导的**说明文字归属窄例外**；不折叠、下沉或删除失败整卡及其已有计量卡，不改变失败依据/归属/命令/定位或计量。

#### Scenario: 可信失败卡旁保短边界、详情保全文
- **WHEN** 真实normal child或cancelled import满足上述条件
- **THEN** 1440/390默认 SHALL 保已测/总量、未比较及实际组截断，模型耗时未测、累计非墙钟/关键路径、—来源未知非零、工具返回不证明整个任务完成及“日志未明确记录时，异步任务状态未知”条件句；卡原scope/口径/缺测、来源仅已展示与累计非某次任务限制保持。全范围混口径总和及wait/poll长例举不再平铺默认，但原数值/完整解释 SHALL 在既有默认closed的原生计量说明内一次键盘展开可读，不新增details/面板/DTO/请求/扫描或分类器。
- **AND** 同冻结过程分页/target与late label SHALL 保原p/卡/按钮、有效节点/焦点/已展开详情，scope/epoch/generation/import隔离照旧；不得因移动说明改数量/target或推取消等于任务结束。

#### Scenario: 条件外不改变原指导
- **WHEN** compact、unmeasured、zero、无可信workloads、失败无时长或其它不满足条件的情况
- **THEN** 原默认指导与详情归属 SHALL 完全保持，未知不补0；合法实测0仍按已测次数判断，不用总时长是否大于0替代资格。真实raw链与DTO-only边界验证 SHALL 分开；本段不承诺MHTML新文本或离线交互已验，须另供证据。

### Requirement: 耗时热点的协作往来提供有界原位返回
在线页面由耗时热点显式进入某上下文的任务与协作往来时，SHALL 提供“返回耗时位置”，仅返回当前仍连接且有效的原热点入口，恢复焦点与可见位置。该来源 SHALL 与协作卡进入所选过程的来源独立，不构造跨 DOM 重建的导航历史；不得把替代节点、最近 Agent 或当前页首项当原来源，不扩大离线交互能力。

#### Scenario: 查明热点任务后返回同一入口
- **GIVEN** 可信热点对应的上下文不在默认已载协作页中，用户从该热点打开任务与往来
- **WHEN** 正确上下文的既有往来窗口完成加载，原入口仍有效
- **THEN** 用户 SHALL 能通过键盘或指针返回同一个热点按钮；任务、发起者、发起记录与原四元身份保持，累计时长不归属某次委派，不增加默认请求。
- **AND** 390px 与1440px均自然换行、返回焦点与位置可见；指标切换或节点替换使来源失效时 SHALL 撤销该返回能力，不复活或猜测来源。
- **AND** 失败重试 SHALL 保留仍有效的原热点而非临时Retry控件；迟到响应不得抢占用户随后选择的焦点，原有协作→过程→协作返回合同保持。

### Requirement: 主会话来源计时可从耗时排查直达
在线执行判断附近 SHALL 在全部或主会话范围且同冻结代存在明确 MAIN 任务或轮次计时时，提供次级入口直达既有 Source Task Active 卡，不复制面板、数值或新增请求。资格仅取 typed `activeTaskSeconds` 或 `agentTurnSeconds` 的合法 measured/partial 值，包含实测 0；缺测不是 0，不能依赖 wall/model/tool 值推断资格。

#### Scenario: 查看已记录的主会话计时
- **WHEN** 上述计时可用，用户在全部或主会话范围显式激活查看入口
- **THEN** 页面 SHALL 展开原 Token 分析与运行诊断祖先，并将可见位置与键盘焦点交给现有计时卡；390px 与1440px自然换行，不读取额外 API 或原文。
- **AND** 任务窗口、Agent Turn、逐工具观测累计与模型执行 SHALL 保持各自来源口径，不用任务减工具推算模型，不改既有 N/A、计量或离线交互能力。

#### Scenario: 未测、子上下文或迟到指标不误归属
- **WHEN** 两项计时均未知，所选范围为子 Agent/匿名上下文，或原冻结代已失效
- **THEN** 页面 SHALL 不显示该入口；冻结代失效时不得保留旧计时事实。恢复全部/主会话范围仅可使用当前有效同代指标，不把 MAIN 计时归给子 Agent。
- **AND** 指标迟到 SHALL 只更新可用入口，不自动展开、滚动或抢焦点；普通分页、标签与有效同代指标同步 SHALL 保留仍有效的 DOM 焦点。
- **AND** 用户显式进入计时卡后，先前挂起的工具定位或子上下文重置完成 SHALL 继续正常应用数据，但不得再夺回焦点或视口；原协作返回保护保持，不引入全局焦点框架。
- **AND** 同代有效、仍聚焦且渲染前完整可见的同一计时卡，被该次过程渲染推离视口时，SHALL 仅补偿原位布局偏移；用户已滚离、转移焦点或冻结资格失效时不得补偿，不重新聚焦或展开。

### Requirement: 协作所选上下文沿用权威标签并保留完整身份
所选协作范围的 breadcrumb SHALL 优先使用同一完整上下文 key 已有的权威标签，与关系卡和所选诊断一致，不另建编号或身份 registry。标签未知时 SHALL 显示完整 key，不猜编号或截成不可区分尾号；底层 selection、查询与来源身份不得改变。

#### Scenario: 跨区识别同一所选 Agent
- **WHEN** 正常或导入页面已知所选上下文的权威标签
- **THEN** breadcrumb SHALL 复用现有短标签呈现，完整所选 key 保留在原“采集与关联原因”折叠证据中，390px 与1440px均可用键盘或指针查看、自然断行，不仅依赖 hover/title，也不新增面板或默认请求。
- **AND** 导入中的标签 SHALL 不暗示外部 child 已采集；主上下文沿用现有权威主标签，未知身份保留完整兜底。

#### Scenario: 迟到标签不改变所选事实或焦点
- **WHEN** 同代权威标签稍后可用，或冻结代与正常/导入范围改变
- **THEN** 同代更新 SHALL 仅同步内部标签文本，保留实际获焦的 breadcrumb 节点、selection、分页、证据展开和计量；不得滚动或抢焦点。
- **AND** 换代 SHALL 撤销旧标签，不跨正常/导入作用域借用；原协作/耗时返回与离线能力边界保持，不增加请求或改变事实关联。

### Requirement: 所选委派视图明确表示向外发起
在线所选上下文的 `delegations` 视图 SHALL 明确表示该上下文作为发起者的委派，不与委派给它的任务混淆。既有参与者和关系入口、所选 breadcrumb、空态 SHALL 使用一致方向说明，不修改 actor/target 筛选、完整身份、事实、请求或计量，也不增加面板。

#### Scenario: 有入向任务但未记录向外委派
- **WHEN** 某上下文有被委派或相关往来，但所选委派页没有它作为 actor 发起的记录
- **THEN** 页面 SHALL 说明未记录该上下文发起的明确委派，并保留“不代表没有工作”；提供既有协作往来的核对指引，不断言它没有被委派、没有工作或没有运行。
- **AND** 全会话追加输入总量不得用作该所选上下文已有追加输入的事实；无输入、未知与全部范围须保持各自诚实表述。

#### Scenario: 只展示该上下文发起的委派
- **WHEN** 所选上下文有向外委派记录
- **THEN** 既有视图 SHALL 仍只显示实际 actor 匹配记录，不混入入向委派；全范围名称保持中性，正常与导入、390px 与1440px的入口方向可读、键盘焦点与原返回行为保持，完整身份和请求数量不变。

### Requirement: 来源计时卡明确中文对象与口径
在线来源计时卡 SHALL 在既有主会话计时入口、卡片及原生详情内使用一致、可理解的中文对象名称与说明，不要求用户自行把英文名称映射为任务活动、轮次累计或记录跨度。保留原卡、稳定 data 身份、数值格式、计量算法和按需层级，不新增时间线、指标卡或默认展开。

#### Scenario: 区分记录跨度、任务活动及工具观测
- **WHEN** 用户从耗时排查进入既有来源计时卡
- **THEN** 可见名称及可访问名称 SHALL 明确主会话任务活动时间、来源记录时间跨度、主会话轮次累计、来源模型计时与来源工具计时；原“计时口径与来源”详情可用键盘或指针按需查看。
- **AND** 说明 SHALL 表达任务计时包含任务期间工具与等待、不等于模型推理；轮次累计为独立口径而非 LLM 调用延迟；来源工具计时与逐工具执行器观测累计不同。记录跨度不表示持续工作，原条件下的任务窗口外跨度不等于用户等待，不以差值推模型或混口径相加。
- **AND** basis SHALL 按已知标识解释汇总方法：任务窗口方法说明重叠只计一次，但标识本身不证明本次已有可用任务时长或原始窗口记录；可用性仍由数值、precision 与 N/A 表达。明确轮次时长与无可用窗口的主任务时长累计不得混称。任务计数说明为计时记录的结束、未闭合或中止，不暗示业务任务成功。

#### Scenario: 呈现澄清不改变测量或导航
- **WHEN** 正常或导入页面展示实测、未知、合法零或 partial 计时，或迟到指标更新
- **THEN** 原数值、N/A、Partial 与资格 SHALL 保持，未知不是零，不从任务、轮次、跨度或工具观测补模型或来源工具计时；390px 与1440px标签和值对应且自然断行。
- **AND** 原计时卡焦点、视口、迟到目标/重置保护及 child 不借 MAIN 计时 SHALL 保持；不得新增请求、改变 selection/计量、prepareTable/列表标签与排序或扩大离线能力。

#### Scenario: 按用户问题查找计时说明
- **WHEN** 用户展开既有“计时口径与来源”详情，查找计时差异、来源依据或记录状态
- **THEN** 原详情 SHALL 以“计时口径”“来源依据”“缺测与记录”引导的三个原生段落组织既有信息，使对象区别、实际条件 basis 与任务外跨度、N/A／Partial 和记录计数分别可定位；不得遗漏原有条件、把未知补零或把计时记录状态当作业务成功。
- **AND** 说明 SHALL 使用单一语义来源，不在字符串说明与卡片中重复维护文案或条件；重复更新仍为三段，来源依据不得残留。原详情、summary、展开状态及有效焦点保持，不增加默认文字、面板、二级折叠、样式或请求；正常与导入、390px 与1440px均自然断行可读。

### Requirement: 宽屏执行与协作独立阅读
可见 Trace 在至少1600px且已确认协作事实时 SHALL 并列展示左侧执行判断、原计时入口及过程与右侧既有协作和状态；完整证据分析置于两栏下方。两栏 SHALL 明确是独立范围，不以横向位置表示时间、因果或逐行归属。

#### Scenario: 联合查看耗时和任务关系
- **WHEN** 用户在宽屏查看全部上下文或选定 Agent
- **THEN** 短过程 SHALL 紧接其判断，不等待右栏结束；协作保留当前范围、顺序、分页及单一 DOM，不因左侧耗时排序或筛选而隐式改变。单工具命令 SHALL 自然换行，不挤成字符列、缩字号或截断。
- **AND** 小于1600px、加载占位或无可确认协作时 SHALL 保持原单列顺序与全宽；不得保留空栏、增加固定高度、sticky、区域内滚动或请求。
- **AND** 迟到事实、续页及宽度切换 SHALL 保留有效原生展开、焦点和正在阅读的位置；原双向定位返回及隐藏 Trace/Payload 语义保持，不扩大离线交互承诺。

### Requirement: 结果首次可辨与准确输入原位往返

Session Detail SHALL 在现payload modal内分层展示输入正文、本地工具结果、归因和原始记录，不新增顶层关系面板或要求用户逐项比对raw。

#### Scenario: 首次Result直接知道结果分别去了哪里
- **WHEN** 一个工具的两个独立结果分别被本地记录2和3明确引用
- **THEN** 首次显式Result响应 SHALL 直接展示两项正文及各自“包含此结果的本地输入”目标，不先逐项请求才能发现目标；一项只预览一个不表示全集，未加载预览、完整零目标和未知/部分/歧义分别说明，其他已确认目标手动有界读取。
- **AND** 390及1440 SHALL 保持“结果正文→目标→必要边界”的顺序，标签使用真实本地记录号与主/子作用域，不以内部ID、颜色或hover作为唯一映射。工具耗时、执行数、模型记录数、Token与归属不变。

#### Scenario: 点击直接定位准确引用并返回原结果
- **WHEN** 用户激活一个已确认目标，即使引用位于首20项之后
- **THEN** 同一modal SHALL 一次取得准确窗口并定位该reference，不先翻前缀/全部过程，不叠modal；“返回结果”恢复原结果项、页、展开、内滚动与实际触发按钮焦点，关闭回到原Trace入口，只保一个返回视图。
- **AND** 整轮聚合Request SHALL 保留现原文与归因入口，不误用单条结果关系视图；准确request与tool-result按支持身份opt-in，不以运行时旧格式兜底掩盖错误。
- **AND** 目标输入 SHALL 首层展示本条工具结果而非整个工具全文；有结果却无单列输入正文不能整体称空，归因与原始记录仍按需可查。归因路径保当前normal/import，不猜轮次或记录位置。

#### Scenario: 正文、完整性与阅读层次诚实
- **WHEN** 展示结果或本地输入
- **THEN** 原始载荷/工具级全文及Copy SHALL 保留，包装输出可易读呈现但不据此猜关系；empty/missing和实际截断分别表达，工具级载荷已截断时首层提示且不称完整记录。输入先正文、再本地工具结果，归因和raw折叠，不以归因计数替代正文。

- **AND** 若未能单列typed结果但工具级安全正文可读，首层 SHALL 显示明确标为“未分项”的可读输出或安全原文，并说明包含关系未确认；不得仅以折叠全文入口替代已可读内容，不造occurrence或关联。

#### Scenario: 更后阅读意图优先且合法归因仍可完成
- **WHEN** 发生同ID重开、关闭、目标导航/返回、scope/visibility/代变化或异步Retry/分页
- **THEN** 旧响应 SHALL 不覆盖新视图、复活返回链或抢焦点/滚动；同一有效视图的分页不能永久取消尚在读取的归因及其Retry，迟到归因失败不强行展开用户未打开的区域。
- **AND** 500 SHALL 保原合法URL及已载内容可重试；400/404要求重读同范围原结果，409撤旧目标与返回入口并要求刷新，不把失败说无包含关系。不自动预取关系/输入或翻页，默认normal7/import6请求及零payload保持。
