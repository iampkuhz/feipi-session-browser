# Claude Code Token 归因适配器

## 1. 适用范围

| 项 | 值 |
|---|---|
| Runtime key | `claude_code` |
| API family | `anthropic_messages` |
| Provider | `anthropic` 或 Anthropic-compatible broker |
| 主数据源 | Claude Code session JSONL |
| 可选数据源 | raw request body、raw response body、本地项目指令文件、custom agent 文件 |
| 目标 | 将 Claude Code 可见来源映射到统一 `Attribution Candidate`，再映射到 token accounting fields。 |

本适配器应用 `README.md` 的共享模型，不重新定义跨 agent candidate 集合，也不把 content bucket 名称当作 token accounting field。

## 2. 调用边界

Claude Code 的 call boundary 以带 usage 的 assistant message group 为锚点，而不是 UI round 或可见文本本身。

| 规则 | Claude Code 行为 |
|---|---|
| 有效关闭 | 带可用 `message.usage` 的 assistant message 或 message fragment 关闭一次 `LLM call`。 |
| Fragment merge | 同一 message id 的多个 fragment 必须先合并，再选择一个 request snapshot 和一个 accounting snapshot。 |
| `active_message_id` | 只用于关联同一逻辑 call 的 request/response fragments，不是 token accounting field。 |
| 重复 usage | 同一逻辑 call 的重复 usage snapshot 只有在存在真实组件增量时才贡献 token，否则只写 diagnostics。 |
| Request snapshot | request input 必须在当前 assistant response 前停止；未来 assistant fragments 或后续 tool results 不属于当前 call。 |
| Response snapshot | 当前 assistant message 输出的 assistant text、visible thinking 和 tool_use blocks 属于当前 call output。 |

## 3. 方向规则

| Claude Code 来源 | 归因候选 | 方向 |
|---|---|---|
| 当前 turn 的 user `message.content` | `user_input` | 当前 call 的 request-side input。 |
| user attachments、images 或 file blocks | `user_input` | 被包含进 API request 时属于 request-side input。 |
| Anthropic `messages[]` 中的 prior user/assistant/tool_use/tool_result items | `conversation_history` | request-side input。 |
| 当前 assistant call 前返回的 `tool_result` blocks | `tool_results` | 消费它们的 call 的 request-side input。 |
| request 字段 `tools[]` | `tool_definitions` | request-side input。 |
| `<system-reminder>` 中的 skill/plugin listing | `skill_definitions` | 被发送给模型时属于 request-side input。 |
| system/developer prompt 或 Claude Code 内置 prompt | `system_instructions` | request-side input。 |
| `AGENTS.md`、`CLAUDE.md`、`.claude/agents/*.md`、subagent prompt files | 根据内容语义映射到 `system_instructions` 或 `repo_context`。 |
| cwd、git branch、permission mode、sandbox 或 app facts | `runtime_context` | 只有显式发送给模型时才属于 request-side input。 |
| assistant text blocks | `assistant_output` | 当前 call 的 `output_tokens`。 |
| visible thinking/thought blocks | `reasoning_output` | 当前 call 的 `output_tokens`。 |
| assistant `tool_use` blocks | `tool_calls` | 当前 call 的 `output_tokens`。 |
| assistant text 中的 structured citations/protocol blocks | `structured_output` | 当前 call 的 `output_tokens`。 |

Tool schema 和 tool result 是 request-side candidates；tool_use 是 response-side `tool_calls`。当真实 tool registry 或 subagent tool list 可用时，不得从 observed tool_use names 反推 `tool_definitions`。

## 4. Claude Code 字段到候选的映射

| Claude Code 来源 | 统一候选 |
|---|---|
| raw request `system[]` 或 system prompt text | `system_instructions` |
| raw request `messages[]` 当前 user item | `user_input` |
| raw request `messages[]` prior items | `conversation_history` |
| raw request `messages[].content[type="tool_result"]` | `tool_results` |
| raw request `tools[]` | `tool_definitions` |
| `agent-setting` custom agent definition 中显式 `tools:` | tool list 映射到 `tool_definitions`；agent prompt text 映射到 `system_instructions`。 |
| `.claude/agents/{agent}.md` 或 `~/.claude/agents/{agent}.md` | role prompt 映射到 `system_instructions`；显式 tool list 映射到 `tool_definitions`。 |
| `AGENTS.md`、`CLAUDE.md`、`.claude/CLAUDE.md` | 行为规则映射到 `system_instructions`；仓库内容映射到 `repo_context`。 |
| `<system-reminder>` 中的 skill/plugin 或 capability list | `skill_definitions` |
| permission-mode、cwd、version、git branch、entrypoint、user type | `runtime_context` |
| file-history snapshot 或显式发送给模型的 file context | `repo_context` |
| assistant `message.content[type="text"]` | `assistant_output` |
| assistant `message.content[type="thinking"]` 或等价 visible thought | `reasoning_output` |
| assistant `message.content[type="tool_use"]` | `tool_calls` |
| hidden/encrypted thinking usage details | `reasoning_output`，source text 为 unavailable。 |

raw request 和 JSONL reconstruction 同时可用时，优先使用 raw request 顺序。JSONL reconstruction 是 fallback，且必须保持 call-scoped。

## 5. Claude Code 中候选到 Token 类型的行为

| 候选 | 首次模型消费 | 后续 call / 复用 |
|---|---|---|
| `user_input` | `fresh_input_tokens` | 如果重放，通常变成 `conversation_history`。 |
| `system_instructions` | `fresh_input_tokens` | Anthropic cache read 报告复用时为 `cache_read_tokens`；cache creation 报告时可写入 `cache_write_tokens`。 |
| `tool_definitions` | `fresh_input_tokens` | 根据 Anthropic cache usage 进入 `cache_read_tokens` 或 `cache_write_tokens`。 |
| `skill_definitions` | `fresh_input_tokens` | cache 行为跟随 provider usage fields。 |
| `runtime_context` | 被发送时为 `fresh_input_tokens` | 复用时可能为 `cache_read_tokens`。 |
| `conversation_history` | 根据 cache 状态可为 `fresh_input_tokens` 或 `cache_read_tokens` | 稳定历史在 provider 报告时通常为 cache read。 |
| `tool_results` | 首次消费时为 `fresh_input_tokens` | 重放或 cached 时为 `cache_read_tokens`。 |
| `repo_context` | 新引入时为 `fresh_input_tokens` | 重复且 cached 时为 `cache_read_tokens`。 |
| `assistant_output` | 当前 call 的 `output_tokens` | 后续 call 可作为 `conversation_history` 被消费。 |
| `reasoning_output` | 当前 call 的 `output_tokens` | 后续 provider state 依赖 provider，可映射为 `reasoning_state`。 |
| `tool_calls` | 当前 call 的 `output_tokens` | 后续 call 可在 `conversation_history` 中看到对应 tool activity。 |
| `structured_output` | 当前 call 的 `output_tokens` | 后续 call 可作为 `conversation_history` 被消费。 |

## 6. 子代理与工具定义规则

| 场景 | 规则 |
|---|---|
| Main agent 存在 custom agent setting | 先解析项目 `.claude/agents/{agent}.md`，再解析 home `~/.claude/agents/{agent}.md`。 |
| Subagent call | 从 parent `Agent` tool metadata 解析 subagent type，并使用该 subagent 自己的 prompt/tool list。 |
| frontmatter 存在显式 `tools:` | 使用显式 allowed tool list 作为 `tool_definitions`。 |
| 缺少 custom agent 或显式 tool list | 使用 Claude Code builtin tool registry，不使用 observed tool_use names。 |
| parent `Agent` tool_use | 属于 parent 当前 call 的 `tool_calls`；child session tokens 留在 child scope。 |
| child tool_result 返回 parent | 只有被后续 parent call 消费时，才属于 parent-side `tool_results`。 |

## 7. 用量字段映射

| 共享字段 | Claude Code / Anthropic 来源 |
|---|---|
| `fresh_input_tokens` | 根据 provider 语义处理 cache read/write 后的 `input_tokens`；如果 raw usage 已经排除 cache，则直接使用。 |
| `cache_read_tokens` | `cache_read_input_tokens` 或 provider alias。 |
| `cache_write_tokens` | `cache_creation_input_tokens` 或 provider alias。 |
| `output_tokens` | `output_tokens`。 |

派生规则：

```text
input_tokens = fresh_input_tokens + cache_read_tokens
total_tokens = fresh_input_tokens + cache_read_tokens + cache_write_tokens + output_tokens
```

Anthropic-like usage 单独报告 cache creation 时，`cache_write_tokens` 是 cache creation 的 accounting metadata，不得变成单独 content candidate。

## 8. 适配器非目标

本适配器不定义 parser loop、payload JSON schema、UI bucket colors、coverage/residual bookkeeping、normalized artifact layout 或 preview truncation。这些细节属于实现文档、测试或代码。
