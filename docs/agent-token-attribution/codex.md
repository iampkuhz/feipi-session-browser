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

| Codex 来源 | 统一候选 |
|---|---|
| `session_meta.payload.base_instructions.text` | `system_instructions` |
| `response_item.message(role="developer")` | 根据内容标签和来源语义映射到 `system_instructions`、`runtime_context`、`skill_definitions` 或 `repo_context`。 |
| `response_item.message(role="system")` | 根据内容标签和来源语义映射到 `system_instructions`、`runtime_context`、`skill_definitions` 或 `repo_context`。 |
| `<skills_instructions>` | `skill_definitions` |
| `<plugins_instructions>` | `skill_definitions` |
| `<permissions instructions>` | `runtime_context` |
| `<app-context>` | `runtime_context` |
| `<collaboration_mode>` | `runtime_context` |
| `<environment_context>` | `runtime_context` |
| `AGENTS.md`、`.codex/AGENTS.md`、`CLAUDE.md`、`.claude/CLAUDE.md`、可见 `<INSTRUCTIONS>` | 行为规则映射到 `system_instructions`；仓库内容映射到 `repo_context`。 |
| raw request `tools[]` | `tool_definitions` |
| `session_meta.payload.dynamic_tools` | `tool_definitions` |
| Codex builtin tool catalog fallback | `tool_definitions` |
| `tool_search_output.tools[]` | `tool_definitions` |
| `.mcp.json` 中进入模型提示的 tool/server 名称 | schema 文本映射到 `tool_definitions`；运行连接事实映射到 `runtime_context`。 |
| `event_msg.user_message.message` | `user_input` |
| `event_msg.user_message.images`、`local_images`、`text_elements` | `user_input` |
| raw request `input[]` prior items | `conversation_history` |
| rollout 中的 prior assistant messages | 原始输出 call 后，在后续 call 中映射为 `conversation_history`。 |
| `response_item.function_call_output.output` | 被下一次 call 消费时映射为 `tool_results`。 |
| `response_item.custom_tool_call_output.output` | 被下一次 call 消费时映射为 `tool_results`。 |
| 包含 file/search/diff 内容的 tool output | 主要映射为 `tool_results`，可在 sub-source note 中标记 `repo_context`，不得重复计数。 |
| `response_item.reasoning` | 当前 `reasoning_output`；后续 provider state 可映射为 `reasoning_state`。 |
| `response_item.function_call`、`response_item.custom_tool_call` | `tool_calls` |
| `response_item.message(role="assistant")` 自然语言 | `assistant_output` |
| `response_item.message(role="assistant")` 结构化 citation/protocol block | `structured_output` |

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
