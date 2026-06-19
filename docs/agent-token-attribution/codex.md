# Codex Token 归因适配器

## 1. 适用范围

| 项 | 值 |
|---|---|
| Runtime key | `codex` |
| API family | `openai_responses` |
| Provider | `openai` |
| 主数据源 | Codex rollout JSONL |
| 可选数据源 | raw request body、raw response body、本地项目指令文件 |
| 目标 | 将 Codex 可见来源映射到统一 `Attribution Candidate`，再映射到 token accounting fields。 |

本适配器不定义跨 agent 模型，只把 `README.md` 的共享模型应用到 Codex rollout 事件。

## 2. 调用边界

有效的 `event_msg.token_count` 关闭一次 Codex `LLM call` 的 usage accounting。

| 规则 | Codex 行为 |
|---|---|
| 有效关闭 | token-count event 相对上一累计快照有组件增量时，创建一个 `LLM call`。 |
| 重复关闭 | token-count event 没有组件增量时只写 diagnostics，不创建 call、不贡献 token。 |
| 只关闭 usage | `token_count` 只关闭 usage，不决定附近所有 item 的 request/response 方向。 |
| Request snapshot | 当前 call 的 request input 必须在该 call 的模型输出前冻结。 |
| Response snapshot | closing token count 前发出的 assistant message、reasoning item 和 tool call 属于当前 call output。 |
| Runtime event | tool output 和 tool-search output 是 runtime event；只有被后续 request 消费时才变成 model input。 |

Codex 不得用可见 UI round、phase label、`event_msg.agent_message` 或 `task_complete` 替代 `LLM call` 边界。

## 3. 方向规则

方向由模型生产/消费决定，不由外层 `response_item` 名称决定。

| Codex 事件或 item | 归因候选 | 方向 |
|---|---|---|
| `response_item.reasoning` | `reasoning_output` | 当前 call 的 `output_tokens`；若 provider 后续复用，才可能成为后续 `reasoning_state`。 |
| `response_item.function_call` | `tool_calls` | 当前 call 的 `output_tokens`。 |
| `response_item.custom_tool_call` | `tool_calls` | 当前 call 的 `output_tokens`。 |
| `response_item.message(role="assistant")` | `assistant_output` 或 `structured_output` | 当前 call 的 `output_tokens`。 |
| `response_item.function_call_output` | `tool_results` | runtime event；被下一次 call 消费时才是 input。 |
| `response_item.custom_tool_call_output` | `tool_results` | runtime event；被下一次 call 消费时才是 input。 |
| `tool_search_output.tools[]` | `tool_definitions` | runtime-discovered tool definitions；被后续 call included 时成为 input。 |
| `event_msg.user_message` | `user_input` | 供下一次有效 model call 消费的 request-side input。 |
| `event_msg.agent_message` | 默认无 candidate | 展示镜像或 fallback preview；存在 canonical assistant message 时不得重复计数。 |
| `task_started` / `task_complete` | 默认无 candidate | metadata 或 trace state；除非显式进入后续 request，否则不是模型 input/output。 |

Codex 的关键规则是：

```text
tool_call = current call model output
tool_result = runtime event
tool_result becomes input only in a later model call
```

## 4. Codex 字段到候选的映射

Codex 专用来源必须先映射到统一 `Attribution Candidate`。同一个 candidate 再根据 call 状态映射到不同 accounting field。

本节只使用可代码化规则：字段路径、role、content part type、精确 tag、source locator、call 边界和内容哈希。不得用大模型或语义判断把一段文本再细分。

### 4.1 拆分与去重规则

scan 先把原始记录规范化为 `source_unit`，再按表格路由到 candidate。表格中的每一行都匹配一个独立 `source_unit`，不依赖上一行或下一行。

`source_unit` 至少包含：

```text
source_id = call_id + origin_path + event_order + part_index + unit_type + byte_range
dedupe_key = call_id + canonical_source_locator + unit_type + sha256(normalized_content)
origin_path = JSONL 字段路径、raw request 字段路径或本地 source locator
canonical_source_locator = project wrapper 中的文件路径；没有显式文件路径时等于 origin_path
unit_type = 下表中的确定性类型
content = 原始文本或 JSON payload
```

去重和优先级：

- 同一个 `source_id` 只能贡献一次 token；父级容器只做 provenance，不再贡献 token。
- 同一个 `dedupe_key` 在同一 call 中只保留优先级最高的来源；用于合并 raw request 和 rollout 中内容相同的可见注入。
- 同一 call 同时有 raw request body 和 rollout fallback 时，raw request 的 `instructions` / `input[]` / `tools[]` 优先；fallback 只补 raw 中不存在的来源。
- `AGENTS.md` / `CLAUDE.md` 可见注入和 `<INSTRUCTIONS>` 是同一个 project-instruction 来源的两种外观；命中 project instruction wrapper 后只生成一个 `project_instruction_bundle`，不得再按文件名或标签重复生成第二个来源。
- 如果同一内容后来作为 tool output 再出现，它属于新的 runtime event；进入后续 call 时归为 `tool_results`，可带 `sub_source=repo_context`，但不得额外生成独立 `repo_context` token。

对 `raw request instructions`、`response_item.message(role in {"developer","system"}).content[].text`，以及未匹配 `event_msg.user_message.message` 且整个 text part 命中下表任一精确 wrapper/tag 的 model-input 文本，使用下面的确定性 text splitter：

1. 按精确起止标记抽取已知 block；匹配大小写敏感，tag 不完整或嵌套不配对时不抽取。
2. 已抽取 block 的 byte range 标记为 consumed；不允许重叠 range。
3. 未 consumed 的非空文本生成 `prompt_plain_text`；该默认归类只由容器来源决定，不分析文本语义。

| text splitter 产物 | 精确匹配规则 | 来源内容说明 | 统一候选 |
|---|---|---|---|
| `project_instruction_bundle` | 整个 text part 符合 `# <file> instructions for <path>` + 空行 + `<INSTRUCTIONS>...</INSTRUCTIONS>`；`<file>` 只接受 `AGENTS.md`、`.codex/AGENTS.md`、`CLAUDE.md`、`.claude/CLAUDE.md`。 | Codex 注入的项目指令文件内容和其来源路径。 | `system_instructions` |
| `visible_instructions_block` | 整个 text part 是完整 `<INSTRUCTIONS>...</INSTRUCTIONS>` block，且不带 `# <file> instructions for <path>` header。 | 无文件 header 的可见项目/会话指令块。 | `system_instructions` |
| `skills_instructions_block` | 完整 `<skills_instructions>...</skills_instructions>` block。 | skill 清单、触发规则、读取方式和资源复用规则。 | `skill_definitions` |
| `plugins_instructions_block` | 完整 `<plugins_instructions>...</plugins_instructions>` block。 | plugin 使用规则及其 skills、MCP tools、apps 能力关系。 | `skill_definitions` |
| `permissions_block` | 完整 `<permissions instructions>...</permissions instructions>` block。 | sandbox、审批策略、文件系统和网络权限。 | `runtime_context` |
| `app_context_block` | 完整 `<app-context>...</app-context>` block。 | Codex 桌面应用能力和交互约束。 | `runtime_context` |
| `collaboration_mode_block` | 完整 `<collaboration_mode>...</collaboration_mode>` block。 | 当前协作模式和用户输入等待策略。 | `runtime_context` |
| `environment_context_block` | 完整 `<environment_context>...</environment_context>` block。 | cwd、shell、日期时区、workspace root 和文件系统权限。 | `runtime_context` |
| `prompt_plain_text` | 上述 block 抽取后剩余的非空文本，来源必须是 `raw request instructions` 或 role 为 `developer` / `system` 的 message text part。 | 未带已知 tag 的 developer/system 指令文本。 | `system_instructions` |

Codex 适配器不按自然语言内容把 `AGENTS.md` / `CLAUDE.md` 拆成“行为规则”和“仓库内容”。这类可见注入整体归为 `system_instructions`；普通仓库文件、diff、搜索命中只在 raw input 文件上下文或 tool output 中出现时进入 `repo_context` 相关记录。

### 4.2 Source unit 到候选的路由表

| 匹配条件（确定性） | 来源内容说明 | 提取方法 | 统一候选 |
|---|---|---|---|
| `session_meta.payload.base_instructions.text` 为非空 string | 会话基础指令文本。 | 整个 string 生成一个 `base_instructions_text` unit。 | `system_instructions` |
| `session_meta.payload.dynamic_tools[]` 为 array | 会话动态工具目录。 | 每个 top-level array item 生成一个结构化 unit；保留工具名、描述和 schema。 | `tool_definitions` |
| `session_meta.payload.cwd`、`originator`、`cli_version`、`source`、`thread_source`、`model_provider`、`git.*` 非空 | 会话运行事实。 | 收集白名单字段为一个 `session_runtime_metadata` JSON unit。 | `runtime_context` |
| raw request `instructions` 为 string | OpenAI Responses 顶层 instructions。 | 对该 string 运行 4.1 text splitter；按产物 candidate 输出。 | 由 splitter 产物决定 |
| `response_item.message(role in {"developer","system"}).content[]` 中 text part 非空 | Codex rollout 可见 developer/system message。 | 对每个 text part 运行 4.1 text splitter；按产物 candidate 输出。 | 由 splitter 产物决定 |
| raw request `tools[]` 为 array | 本次请求发送给模型的工具 schema。 | 每个 tool JSON 生成一个 `raw_tool_schema` unit。 | `tool_definitions` |
| Codex builtin tool catalog fallback 被启用 | raw request `tools[]` 不可用时的内置工具目录。 | 仅在 raw tools 缺失时，按 catalog tool item 生成 unit。 | `tool_definitions` |
| `tool_search_output.tools[]` 为 array | tool search 返回的工具定义候选。 | 记录为 `discovered_tool_schema`；只有该 tool 后续进入 raw `tools[]`、`dynamic_tools` 或 fallback catalog 时才计入对应 call input。 | `tool_definitions` |
| `.mcp.json` reader 产出 `server/tool schema` unit | MCP server/tool 的名称、描述和参数 schema。 | 只读取 JSON 中确定字段：`mcpServers.*`、`tools[].name`、`tools[].description`、`tools[].inputSchema`。 | `tool_definitions` |
| `.mcp.json` reader 产出 `connection metadata` unit | MCP server 启用、命令、连接或权限事实。 | 只读取 JSON 中确定字段：server key、`command`、`args`、`env` key 名、启用状态；敏感值脱敏。 | `runtime_context` |
| `event_msg.user_message.message` 存在 | 当前用户输入文本。 | 整个 message 字段生成 `current_user_text` unit；不解析其中的 XML-like 文本。 | `user_input` |
| `event_msg.user_message.images`、`local_images`、`text_elements` 非空 | 当前用户多模态输入。 | 每个图片引用、本地路径或 text element 生成 unit。 | `user_input` |
| raw request `input[]` 中属于当前 call 的用户 item | 当前 call 消费的用户消息。 | 用 call 边界和对应 `event_msg.user_message` 匹配；生成 `current_user_input_item`。 | `user_input` |
| raw request `input[]` 中 `type="message"` 且早于当前 call 的 user/assistant item | 历史对话消息。 | 按 item 原样生成 `prior_message_item`；不重新拆分为当前输出。 | `conversation_history` |
| raw request `input[]` 中 `type` 为 `function_call` / `custom_tool_call` 且早于当前 call 的 item | 历史模型工具调用结构。 | 按 item 原样生成 `prior_tool_call_item`。 | `conversation_history` |
| raw request `input[]` 中 `type` 为 `function_call_output` / `custom_tool_call_output` 的 item | 被当前 call 消费的工具结果。 | 提取 result `output` / `content` payload，生成 `request_tool_result`。 | `tool_results` |
| raw request `input[]` 或 provider state 中显式 reasoning state item | provider 回传或复用的历史推理状态。 | 只在存在明确 reasoning/state item 或引用字段时生成 unit。 | `reasoning_state` |
| rollout 中当前 call 之前的 assistant message 被后续 call 重放 | 后续 call 的历史 assistant 输出。 | 以原始 assistant output 的 content hash 关联，生成 `prior_assistant_message`。 | `conversation_history` |
| `response_item.function_call_output.output` 或 `response_item.custom_tool_call_output.output` | tool runtime result。 | 当前 event 只入 pending；被下一次 call 消费时生成 `request_tool_result`。 | `tool_results` |
| tool output 的 tool adapter 已确定 `output_kind` 为 `file` / `search` / `diff` | 工具返回的仓库文件片段、搜索命中或 diff。 | 仍按 `request_tool_result` 计入；只附加 `sub_source=repo_context`，不从文本内容二次判定。 | `tool_results` |
| raw request `input[]` 中存在显式 file context item 或 text part 以 `File:` / `file:` / `path:` 行开头 | 请求直接携带的仓库文件上下文。 | 提取该 item/text part 为 `request_file_context`；不与 tool result 重复。 | `repo_context` |
| 当前 call 的 `response_item.reasoning` | 当前 call 生成的 reasoning item。 | 在产生它的 call 中生成 `reasoning_output` unit。 | `reasoning_output` |
| 当前 call 的 `response_item.function_call` 或 `response_item.custom_tool_call` | 当前 call 生成的工具调用请求。 | 提取工具名、参数和 call id。 | `tool_calls` |
| 当前 call 的 `response_item.message(role="assistant").content[]` text / output_text part | 当前 call 生成的 assistant 自然语言或 Markdown。 | 提取 text 字段；annotations/citations 作为该 text 的 metadata，不单独计 token。 | `assistant_output` |
| 当前 call 的 `response_item.message(role="assistant").content[]` 非 text part，或 raw response 中显式 JSON/schema/citation block item | 当前 call 生成的机器可读结构化输出。 | 只按 part `type` 或 raw response item type 判定；不根据文本长相猜测。 | `structured_output` |

未命中任何匹配条件的记录不得强行归因；只能进入 diagnostics（例如 `unclassified_visible_input`），并保留 origin path 供后续补规则。

raw request 或 raw response 可用时优先使用 raw body；不可用时从 rollout 可见事件重建，不编造 hidden content。

## 5. Codex 中候选到 Token 类型的行为

Codex 通常报告 OpenAI-style input、cached input 和 output usage。Candidate 归属取决于 call 状态：

| 候选 | 首次模型消费 | 后续 call / 复用 |
|---|---|---|
| `user_input` | `fresh_input_tokens` | 通常不进入 `cache_read_tokens`；如果作为历史重放，则成为 `conversation_history`。 |
| `system_instructions` | `fresh_input_tokens` | provider cache 报告复用时为 `cache_read_tokens`。 |
| `tool_definitions` | `fresh_input_tokens` | cached 时为 `cache_read_tokens`；runtime-discovered tools 首次 included 时为 fresh。 |
| `skill_definitions` | `fresh_input_tokens` | cached 时为 `cache_read_tokens`。 |
| `runtime_context` | 新内容为 `fresh_input_tokens` | 复用且 provider 报告 cached 时为 `cache_read_tokens`。 |
| `repo_context` | 新引入时为 `fresh_input_tokens` | 重放且 cached 时为 `cache_read_tokens`。 |
| `conversation_history` | 取决于 provider accounting，可为 fresh 或 cache read | 稳定 cached history 通常为 `cache_read_tokens`。 |
| `tool_results` | 被后续 call 首次消费时为 `fresh_input_tokens` | 重放或 cached 时为 `cache_read_tokens`。 |
| `reasoning_state` | provider-dependent input state | provider-dependent。 |
| `assistant_output` | 当前 call 的 `output_tokens` | 后续 call 可作为 `conversation_history` 被消费。 |
| `reasoning_output` | 当前 call 的 `output_tokens` | provider 暴露/使用时，后续可作为 `reasoning_state`。 |
| `tool_calls` | 当前 call 的 `output_tokens` | 后续可出现在 `conversation_history` 或 tool activity context 中。 |
| `structured_output` | 当前 call 的 `output_tokens` | 后续可作为 `conversation_history` 被消费。 |

Codex 文档不得暗示 `Fresh` 是 request source attribution 的固定分母。`fresh_input_tokens`、`cache_read_tokens` 和 `cache_write_tokens` 是 accounting fields；candidates 解释这些 fields 里的可能来源。

## 6. 子代理规则

Codex subagent rollout 拥有独立 token scope。

| 事件 | 规则 |
|---|---|
| parent `spawn_agent` function call | parent 当前 call 的 `tool_calls`，计入 parent `output_tokens`。 |
| parent `spawn_agent` function output | parent-side runtime tool result；只有被后续 parent call 消费时才成为 parent `tool_results`。 |
| child rollout `session_meta.source.subagent.thread_spawn` | 证明 child rollout 属于 subagent scope。 |
| child `event_msg.token_count` | 创建 child scope 内的 child `LLM call`；child tokens 留在 child scope。 |
| child tool calls/results | 留在 child scope，不得膨胀 parent tool 或 token totals。 |
| parent `wait_agent` result | 被后续 parent call 消费时为 parent-side `tool_results`。 |
| parent assistant message 中的 `subagent_notification` | parent assistant output 或 metadata；不是 child output，也不能替代 child rollout usage。 |

parent 和 child attribution 可以为 trace navigation 建立关联，但 accounting fields 必须分开。

## 7. 用量字段映射

Codex usage 必须归一化为四个共享 accounting fields。

| 共享字段 | Codex/OpenAI 来源 |
|---|---|
| `fresh_input_tokens` | `input_tokens - cached_input_tokens`，下限为 0；只有累计 usage 时先计算有效 delta。 |
| `cache_read_tokens` | `cached_input_tokens`、`input_tokens_details.cached_tokens` 或等价 per-call/cumulative delta 字段。 |
| `cache_write_tokens` | provider cache write 字段；不可用时为 unavailable 或 0，不从 residual 推断。 |
| `output_tokens` | `output_tokens`、`completion_tokens` 或有效 cumulative output delta。 |

派生规则：

```text
input_tokens = fresh_input_tokens + cache_read_tokens
total_tokens = fresh_input_tokens + cache_read_tokens + cache_write_tokens + output_tokens
reasoning_tokens <= output_tokens
```

`reasoning_tokens` 是 `output_tokens` 的子集或 breakdown，不是额外顶层 accounting field。raw `total_tokens` 可以作为 diagnostics evidence，但除非实现进入 total-only fallback，否则不得覆盖归一化组件公式。

## 8. 适配器非目标

本适配器不定义：

- normalized artifact schema；
- on-demand attribution API payload shape；
- preview 截断或 source locator 格式；
- coverage、residual、precision 或 evidence bookkeeping 的核心模型；
- UI bucket label、颜色、排序或 modal 行为；
- `pending_request_refs` 等 parser 变量名作为适配器契约。

这些细节属于实现文档、代码、测试或独立 OpenSpec 变更。
