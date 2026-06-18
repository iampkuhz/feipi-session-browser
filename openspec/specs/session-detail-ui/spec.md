# Session Detail UI Spec

## Requirements

### Requirement: 单页 trace-first 调试体验

Session Detail 页面必须提供稳定、可离线使用的 run analysis 调试体验。首屏必须概览运行健康度、token 成本、缓存健康度、工作量和活跃耗时；Trace 与 Payload 作为下钻工作区保留。

#### Scenario: 会话摘要展示

页面必须展示：
- Session 标题。
- Agent 名称、model、project、created/updated 时间、session id；已解析本地 JSONL 路径时展示索引源文件路径。
- 正好 5 个主 KPI：Run Health、Total Tokens、Cache Health、Workload、Active Time。
- Run Health 二级指标：Issue Rounds、Failed Tools、Payload Gaps、Attribution Gaps。
- Total Tokens 二级指标：Fresh、Cache Read、Cache Write、Output。
- Cache Health 二级指标：Input-side Tokens、Low-cache Rounds、Fresh Spike Rounds。
- Workload 二级指标：Main Calls、Subagent Calls、Tool Calls、Subagent Runs。
- Active Time 二级指标：Duration、Waiting Time、Model Time、Tool Time。

每个主 KPI 卡最多渲染 4 个二级指标。Hero 区在索引或 parser 已解析 JSONL 源路径时，必须以 `Session file` 行展示本地路径，并提供 `data-action="copy"` 与 `data-copy-text` 复制按钮；没有路径时省略该行。

#### Scenario: Token 组件提取

Token 指标必须只使用 5 个当前组件字段：
- Fresh：互斥的新输入组件，用于展示合计。
- Cache Read：provider 上报的缓存读取输入 token。
- Cache Write：provider 上报的缓存创建/写入输入 token。
- Output：provider 上报的可见输出 token。
- Total：`Fresh + Cache Read + Cache Write + Output`。

当 provider 的 Cache Read 是 input tokens 子集时，例如 OpenAI/Codex `cached_input_tokens`，Fresh 必须按 `input_tokens - cached_input_tokens` 计算，并用于 tokenbar、Total、Fresh spike、round tooltip。Provider Request Input 可在 attribution 摘要或 provider 计量元数据中单独展示，但不得和它的缓存子集并列叠加为 Fresh。Codex 中每个有效的 `event_msg.token_count` 累计快照必须生成一个 LLM-call round；重复快照如果 `total_token_usage` 没有组件增量，不得生成 round 或贡献 token，并应记录 token diagnostics。

#### Scenario: Analysis cards 展示

页面必须展示 Agents Breakdown、Context Budget、Tool Impact、Issues & Repro Seeds。Agents Breakdown 在桌面端必须横跨完整分析网格宽度，并将 `main agent` 作为第一个可选项，后面列出 subagent runs。切换候选项时，同一卡片内的 token/cache timeline 必须同步切换。Context Budget、Tool Impact、Issues & Repro Seeds 在桌面端使用两列网格，窄屏使用单列布局。

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
- Tool call 行，包含 status、duration、command preview、result preview、result token estimate 和 result payload action。duration 优先使用明确的 tool wall time；wall time 缺失或为 0 时，使用 tool call 到 tool output 的 timestamp 差值。
- 只有同一 assistant block 触发多个 tool calls，或 tool_use timestamp 差值接近并发阈值时才渲染 Parallel Tool Group。
- Subagent run 行，带局部 expand/collapse-all 控制和每个 subround 的展开/折叠开关。
- Failed tool error 摘要。
- 仅在存在 payload data 时展示 payload 按钮。

Expanded timeline 不渲染独立的 LLM summary card 或 LLM call card。LLM usage、request/response payload action、request/response attribution action 必须从 round summary 行、Payload tab 或 payload modal 进入，不在 expanded details 中重复展示。

Assistant thinking、assistant text 和不可用处理事件行必须使用与 tool call 行一致的紧凑单行高度。Assistant text row payload 只包含 assistant text/thinking 内容；同一 model response 中的 tool_use commands 必须由独立 tool call 行展示，不得在 assistant text row payload 中重复。展开 detail 面板必须和展开 round 行、下一条 round 行保持可见间距。

Codex rollouts 中，同一 assistant 文案如果同时出现在 `event_msg.agent_message` 和 `response_item.message role=assistant`，Session Detail 必须把两者关联为一个 assistant text 事件。存在 `response_item.message` 时它是 canonical payload source；`event_msg.agent_message` 只作为 UI/status mirror 或缺省展示来源，不得生成第二条相同 timeline row。

Round rows 与 subagent round summary rows 必须直接暴露 request attribution 和 response attribution 状态/action。每个 subagent round summary row 必须可独立点击并支持键盘展开/折叠。可见 attribution action label 固定为 `request` 和 `response`；用户不得为了访问 attribution 再打开内部 LLM call card。

主 round attribution action title 必须使用 session-global LLM call 编号；attribution API payload id 可继续使用 `/attribution/{round}/{call}` 所需的 round-local `IX` index。后续 rounds 不得把全局第 2、第 3 个 call 显示成重复的 `LLM Call #1`。

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

Trace request/response attribution actions 必须在点击时通过后端 attribution API 按需加载 payload。初始 slim page render 必须保留 attribution actions 和 payload IDs，但不得嵌入完整 request/response attribution payload data。

Qoder session 的 request attribution 可用时必须优先使用 call-scoped `full_messages_array` 重建 Claude-like API messages。该 bucket 必须包含当前 call 边界前 request 侧 user、assistant、tool_use 和 tool_result items，并汇总每个 item 的完整 `content_token_estimate`。Provider reported `cache_read_input_tokens` 只在 request summary 中作为 `Cache Read` 和 provider accounting metadata 展示；不得创建 raw `provider_cached_context` bucket，不得参与本地重建 coverage。`cache_creation_input_tokens` / Cache Write 保留在 usage summary，但不得作为额外 request-source bucket 或 request bucket denominator。Qoder 未持久化完整 available tools schema 时，attribution 必须使用 Claude-Code-like SDK 默认工具定义作为当前缺省来源，并补充 observed Qoder-only tools，而不是只按 invoked tools 估算；工具定义 bucket 必须以 canonical key `tool_definitions` 输出。

页面还必须提供 payload modal：包含 View Request / View Response / View Result 按钮、Rendered / Raw 展示模式切换、多 part 分段展示；tool result payload 的 modal subtitle 和 metadata rail 必须展示 `result tokens` 估算值。该值由 tool result 文本估算，格式为近似 token 数，并作为下一次 LLM call 的 request-pressure metadata，不得标记为 provider reported usage。modal 必须支持 backdrop click、Escape key 和 close button 关闭。

#### Scenario: MHTML 自包含导出

MHTML export 必须生成内联 CSS 与 JS 的自包含 HTML。离线打开导出页面时必须保留所有交互，不需要外部网络请求。

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
