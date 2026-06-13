# Session Detail UI Spec

## Requirements

### Requirement: Single trace-first debug page

The session detail page SHALL provide a run-analysis experience as a stable, offline-capable debug page. The first viewport SHALL summarize run health, token cost, cache health, workload, and active time. Trace and Payload SHALL remain drill-down workspaces.

#### Scenario: Session summary display

The page SHALL display:
- Session title
- Agent name, model, project, created/updated timestamps, session id, and the indexed local session file path when available
- Exactly five primary KPI cards: Run Health, Total Tokens, Cache Health, Workload, Active Time
- Run Health secondary metrics: Issue Rounds, Failed Tools, Payload Gaps, Attribution Gaps
- Total Tokens secondary metrics: Fresh, Cache Read, Cache Write, Output
- Cache Health secondary metrics: Input-side Tokens, Low-cache Rounds, Fresh Spike Rounds
- Workload secondary metrics: Main Calls, Subagent Calls, Tool Calls, Subagent Runs
- Active Time secondary metrics: Duration, Waiting Time, Model Time, Tool Time

Each primary KPI card SHALL render no more than four secondary KPI values.

The Hero SHALL display the local session file path as a `Session file` row when the index or parser has resolved a JSONL source path. The row SHALL expose a copy button with `data-action="copy"` and `data-copy-text` set to the full path. If no file path is known, the row SHALL be omitted.

#### Scenario: Token component extraction

Token metrics SHALL use exactly five component fields:
- Fresh: mutually exclusive new input component for display totals
- Cache Read: provider-reported cache read input tokens
- Cache Write: provider-reported cache creation/write input tokens
- Output: provider-reported visible output tokens
- Total: Fresh + Cache Read + Cache Write + Output

When provider cache read is a subset of input tokens, including OpenAI/Codex `cached_input_tokens`, Fresh SHALL be computed as `input_tokens - cached_input_tokens` for tokenbar, Total, Fresh spike, and round/tooltips. Provider request input MAY still be shown separately in attribution summaries or provider-total metadata, but it SHALL NOT be stacked as Fresh beside its cached subset. For Codex, each effective `event_msg.token_count` cumulative snapshot SHALL create one LLM-call round; repeated snapshots whose `total_token_usage` has no component growth SHALL NOT create a round or contribute tokens and SHALL be recorded as token diagnostics.

#### Scenario: Analysis cards display

The page SHALL display analysis cards for:
- Agents Breakdown
- Context Budget
- Tool Impact
- Issues & Repro Seeds

Agents Breakdown SHALL span the full analysis grid width on desktop and SHALL include `main agent` as the first selectable candidate followed by subagent runs. Selecting a candidate SHALL switch the token/cache timeline in the same card. Context Budget, Tool Impact, and Issues & Repro Seeds SHALL use the two-column grid on desktop and single-column layout on narrow screens.

#### Scenario: Issue summary display

The page SHALL display issue cards for:
- Failed rounds with aggregated failed tool call counts
- Highest token round

Issue cards SHALL be clickable buttons that jump to and expand the target round. When no issues exist, display "No actionable issues detected." The Hero issue strip SHALL NOT display "No issues found" when any tool failure, LLM error, payload gap, or attribution error exists.

#### Scenario: Trace list

The page SHALL display a vertical list of all rounds. Each round SHALL show:
- Round number and status
- Summary/title text
- Tool count and failure count
- Token count
- Time
- Signals: Failed, Subagent, Payload Gap, Attribution Gap

Round Metrics SHALL NOT display LLM call count. Round token bars SHALL use a full-width gray track, with the colored token mix scaled against the largest round token total in the current session.

Round Signals SHALL render only actual signal badges. Rounds without Failed, Subagent, Payload Gap, or Attribution Gap SHALL render no placeholder signal badge.

The first failed round SHALL be expanded by default; if no failures, expand R1.

#### Scenario: Trace controls

The page SHALL provide:
- All / Failed status filter
- Expand All / Collapse All buttons

The Failed filter SHALL show failed rounds and rounds containing any failure signal. The filter state SHALL be reflected in `trace_status` URL parameter. Selected round and selected tab SHALL be reflected in `round` and `tab` URL parameters.

#### Scenario: Inline round detail

When a round is expanded, it SHALL show:
- User prompt summary
- Assistant response summary
- Assistant thinking and assistant text event rows when those source blocks exist
- Tool call rows with status, duration, command preview, result preview, result token estimate, and result payload action. Duration SHALL prefer explicit tool wall time and fall back to the difference between tool call and tool output timestamps when wall time is unavailable or zero.
- Parallel tool groups only when tool calls share one assistant block or near-identical trigger time
- Subagent run rows with local expand/collapse-all control and per-subround expand/collapse toggle
- Failed tool error summaries
- Payload buttons only when payload data exists

Expanded timeline SHALL NOT render an LLM summary card or legacy LLM call card. LLM usage, request/response payload actions, and request/response attribution actions SHALL be available from the round summary row, Payload tab, or payload modal instead of duplicated inside expanded details.

Assistant thinking, assistant text, and fallback event rows SHALL use the same compact single-line height as tool call rows. Assistant text row payloads SHALL contain only assistant text/thinking content; tool_use commands from the same model response SHALL be shown by their own tool call rows and SHALL NOT be repeated inside the assistant text row payload. Expanded round detail SHALL render as a separated panel with visible spacing from the opened round row and the following round row.

For Codex rollouts, when the same assistant text appears as both `event_msg.agent_message` and `response_item.message role=assistant`, Session Detail SHALL associate them as one assistant text event. The `response_item.message` record SHALL be the canonical payload source when present, and `event_msg.agent_message` SHALL be treated as a UI/status mirror or fallback rather than a second timeline row.

Round rows and subagent round summary rows SHALL expose request attribution and response attribution status/actions directly. Each subagent round summary row SHALL be independently clickable and keyboard-toggleable to expand or collapse its own detail steps. The visible attribution action labels SHALL be `request` and `response`. Users SHALL NOT need to open an inner LLM call card to access attribution.

Main round attribution action titles SHALL use the session-global LLM call number, while attribution API payload IDs MAY keep the round-local `IX` index required by `/attribution/{round}/{call}`. Later rounds SHALL NOT display a repeated `LLM Call #1` title when they refer to global calls #2, #3, and so on.

Expanded round row state SHALL be drawn within the row boundary and SHALL NOT overlap adjacent round borders.

#### Scenario: Payload tab and modal

The page SHALL provide a persistent Payload tab with:
- Left call selector with All / Failed / Missing / Error filters
- Right selected call detail
- Detail sections in this fixed order: Overview, Request Attribution, Response Attribution, Raw Request, Raw Response, Related Results

The selector SHALL keep an internal scroll area on desktop and narrow screens. Selecting a coverage matrix cell SHALL switch to the Payload tab, apply the corresponding selector filter, and select the first matching failed/missing/error call.

Request attribution bucket details SHALL render explanatory and inspectable content for reconstructed request sources. For Claude Code, the `API messages 数组` bucket SHALL be reconstructed from the current LLM call boundary: prior assistant `request_full` values, prior assistant text/tool_use entries, and the current call `request_full`, stopping before the current assistant response and excluding future rounds. Its aggregate token count SHALL be the sum of each item's full `content_token_estimate`, not an estimate from truncated previews. The bucket SHALL explain that it represents the Anthropic API `messages` request field and SHALL list each message with role, content type, optional tool name, token estimate, and content preview. When original full content is available in local logs or reconstructed context, each detail item SHALL expose it through a second-level expansion. The `内置系统提示` bucket SHALL render a masked preview when visible `<system-reminder>` content is captured from the local transcript; when no visible content is captured, it SHALL render an explicit unavailable/estimated explanation instead of an empty body.

For Claude Code request attribution, the `tool_schemas` bucket SHALL represent request-side tool definitions, not response-side invoked tool calls. When the session JSONL contains an `agent-setting` event, main-agent calls SHALL resolve that named agent from `<cwd>/.claude/agents/{agent}.md` first and `~/.claude/agents/{agent}.md` second, then use that agent file's explicit `tools:` frontmatter when present. Subagent calls SHALL resolve the specific subagent type from the parent `Agent` tool call metadata and use that subagent's own agent file. If no custom agent setting, subagent type, readable definition, or explicit `tools:` list is available, Claude Code request attribution SHALL use the full Claude Code builtin tool registry. Claude Code request attribution SHALL NOT infer `tool_schemas` from `tool_calls_raw` or observed tool call names.

Attribution bucket cards rendered dynamically inside the modal SHALL use the same expandable contract as template-rendered payload buckets. Clicking a bucket header SHALL expand or collapse its detail body and SHALL keep `hidden`, `is-expanded`, and `aria-expanded` synchronized.

Request attribution coverage metadata SHALL be folded into the top summary area. Provider total, locally reconstructed total, coverage ratio, and residual tokens SHALL NOT be repeated as a standalone bottom `覆盖率与不确定性` section. Generic residual likely-source footers such as `unclassified overhead` SHALL NOT be rendered unless backed by a concrete structured source.

The dynamic attribution modal SHALL use a two-level bucket detail interaction. The first click on a contribution-source bucket SHALL reveal compact subcategory cards. Those subcategory cards SHALL have a consistent collapsed height and show only a short summary plus compact metadata. Clicking a subcategory card SHALL reveal all locally available full content, raw JSON, or full explanatory text inside that card.

When an attribution bucket has no structured `details` object but does include `summary`, `source`, `count_label`, or `content_preview`, the modal SHALL render those fields as fallback bucket details instead of making the bucket appear non-expandable or empty.

Request attribution buckets SHALL be normalized through the global token attribution taxonomy before being returned to the UI. Each request bucket payload SHALL include `agent_bucket_key`, `canonical_key`, `category_key`, `category_label`, `color_key`, and `display_order`; `label` SHALL be the global Chinese label. The canonical request token categories SHALL include: `当前用户输入`, `对话消息上下文`, `工具结果上下文`, `工具定义`, `MCP 工具元数据`, `运行上下文片段`, `系统/开发者指令`, `本地指令上下文`, `Agent/Subagent 提示`, `内置系统提示`, `Provider 会话状态`, `推理配置`, `运行时封装开销`, and `未定位`. Equivalent buckets from different agents, such as `tool_schemas`, SHALL share the same label and `color_key`.

For Codex sessions without a raw request body, request attribution SHALL reconstruct visible request sources from rollout data. `session_meta.base_instructions` and pre-user `response_item` messages with `developer` or `system` role SHALL contribute to raw `instructions` and render under the canonical `系统/开发者指令` category with visible source text in structured bucket details. `function_call_output` and `custom_tool_call_output` events SHALL be carried into the next assistant request and attributed as raw `tool_outputs`, rendering under canonical `工具结果上下文`, with locally available output text available through detail expansion. Provider reported `cached_input_tokens` / cache read SHALL remain visible only in the request summary as `Cache Read` and provider total accounting metadata; it SHALL NOT create a raw `provider_cached_context` bucket, SHALL NOT contribute to locally reconstructed coverage, and SHALL NOT be rendered beside conversation messages, tool outputs, or tool schemas. When raw request `tools` are unavailable, Codex request attribution SHALL use a Codex builtin tool catalog fallback and add observed extra tools; it SHALL NOT estimate tool schemas only from observed invoked-tool count. The raw `tool_schemas` bucket SHALL render under canonical `工具定义` and expose a tool count, per-tool token estimate, schema/parameter preview, and full locally available detail.

Trace request/response attribution actions SHALL load attribution payloads on demand via the backend attribution API when clicked. Initial slim page render SHALL keep attribution actions and payload IDs but SHALL NOT embed complete request/response attribution payload data.

For Qoder sessions, request attribution SHALL use the call-scoped `full_messages_array` as the primary Claude-like API messages reconstruction when available. The bucket SHALL include request-side user, assistant, tool_use, and tool_result items up to the current call boundary and SHALL sum each item's full `content_token_estimate`. Provider reported `cache_read_input_tokens` SHALL remain visible only in the request summary as `Cache Read` and provider total accounting metadata; it SHALL NOT create a raw `provider_cached_context` bucket and SHALL NOT contribute to locally reconstructed coverage. `cache_creation_input_tokens` / cache write SHALL remain visible in the usage summary but SHALL NOT be treated as an extra request-source bucket or request bucket denominator. When Qoder does not persist the full available tools schema, attribution SHALL use the Claude-Code-like SDK default tool definitions plus observed Qoder-only tools instead of estimating schemas only from invoked tools; raw `tool_schemas` SHALL render under canonical `工具定义`.

The page SHALL also provide a modal dialog for viewing payloads with:
- View Request / View Response / View Result buttons
- Rendered / Raw display mode toggle
- Multi-part segmented display
- Tool result payloads SHALL expose a `result tokens` estimate in the modal subtitle and metadata rail. This value SHALL be derived from the tool result text, formatted as an approximate token count, and treated as request-pressure metadata for the likely next LLM call rather than provider-reported usage.
- Close via backdrop click, Escape key, or close button

#### Scenario: MHTML self-contained export

MHTML export SHALL produce self-contained HTML with inline CSS and JS. The exported page SHALL preserve all interactions when opened offline. No external network requests SHALL be required.

### Requirement: ARIA accessibility for trace rows

Each trace row SHALL be a semantic `<button type="button">` element with:
- `aria-expanded` reflecting the current expanded state ("true" or "false")
- `aria-controls` referencing the associated trace-detail element ID
- The trace-detail element SHALL have an `id` matching the `aria-controls` value

### Requirement: Payload buttons on trace events

Attribution controls, message rows, assistant event rows, and tool call rows SHALL render a payload button when payload data exists. The button SHALL have:
- `data-action="open-payload"` attribute
- `data-payload-id` referencing a payload source id

### Requirement: Shell residue gate

The session detail page SHALL NOT render:
- Sidebar Round Map (the `.round-map` section)
- Projects / Agents navigation links in sidebar
- Topbar shell toggle buttons (sidebar toggle ☰, right panel toggle ☰, focus ●)
- Map / Inspector / Focus layout mode buttons
- Density toggle button
- Visible disabled placeholder buttons (search, export, theme)

### Requirement: No content-modal entry points

The page SHALL NOT render a `content-modal` element or any `data-content-modal` buttons. The `openContentModal` function SHALL NOT be defined.

### Requirement: Dead button gate

Every visible `<button>` on the session detail page SHALL have a supported `data-action` value from this list:
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
- `md-toggle` (tool result markdown toggle)

### Requirement: No removed entries

The session detail page SHALL NOT render:
- Calls tab, Hotspots tab, or workbench view switching
- Resident Inspector panel as a default session detail entry
- Round Map
- Map / Inspector / Focus layout mode buttons
- Density toggle button
- Visible disabled placeholder buttons (search, export, theme)
- Failed only / High token / Open selected chips
- Message / Tool / Error type filters
- Timeline jump input and Go button
- × Clear filter button
- Independent Calls tab/table
- Independent Hotspots tab/cards
- Legacy Token Usage collapsed chart

### Requirement: Global shell simplification

The global navigation for session detail SHALL be simplified. The Inspector panel SHALL NOT be rendered as a default third column on session detail pages.
