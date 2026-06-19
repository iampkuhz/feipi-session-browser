# Qoder Token 归因适配器

## 1. 适用范围

| 项 | 值 |
|---|---|
| Runtime key | `qoder` |
| API family | `qoder_broker` |
| Broker | `qoder` |
| 底层 provider | 根据 message/usage shape 判定为 Anthropic-like 或 OpenAI-like |
| 主数据源 | Qoder session transcript 和 broker usage fragments |
| 可选数据源 | 项目 `.qoder/rules`、Qoder model policy/config、default tool catalog |
| 目标 | 将 Qoder 可见来源映射到统一 `Attribution Candidate`，再映射到 token accounting fields 和 credits。 |

本适配器应用 `README.md` 的共享模型。Qoder 可能同时暴露 token-like usage 和 credit billing；credits 是 billing metadata，不替代 token accounting fields。

## 2. 调用边界

| 规则 | Qoder 行为 |
|---|---|
| 有效关闭 | 带可用 token/credit 数据的 grouped assistant message 或 usage fragment 关闭一次 `LLM call`。 |
| Fragment merge | 同一逻辑 assistant message 的 usage fragments 必须先合并，再归一化 token fields。 |
| `active_message_id` | 只作为 fragment correlation key，不是 token accounting field。 |
| raw body 缺失 | 从 transcript 和本地 context 重建可见 call-scoped input；不得编造 hidden broker prompt text。 |
| Credit events | 有稳定证据时附着到同一逻辑 call；否则 credit attribution 保持 unavailable。 |
| Request snapshot | 必须在当前 assistant output 前停止；后续 tool results 和 assistant messages 属于后续 calls。 |

## 3. 方向规则

| Qoder 来源 | 归因候选 | 方向 |
|---|---|---|
| 当前 user message 或 prompt fragment | `user_input` | request-side input。 |
| 当前 user attachments 或 IDE-provided text elements | `user_input` | 被包含时属于 request-side input。 |
| `full_messages_array` 或 call-scoped prior transcript | `conversation_history` | request-side input。 |
| 当前 assistant message 前的 tool result / function result items | `tool_results` | 消费它们的 call 的 request-side input。 |
| available tools schema 或 default Claude-Code-like tool catalog | `tool_definitions` | request-side input。 |
| `.qoder/rules`、project rules、`AGENTS.md`、`CLAUDE.md` | 根据语义映射到 `system_instructions` 或 `repo_context`。 |
| Qoder IDE/runtime policy、model policy、cwd、workspace facts | `runtime_context` | 只有发送给模型时才属于 request-side input。 |
| compact summaries 或 broker context references | 表示模型上下文时为 `conversation_history`；表示 provider state 时为 `reasoning_state`。 |
| assistant text | `assistant_output` | 当前 call 的 `output_tokens`。 |
| visible thinking 或 reasoning fragments | `reasoning_output` | 当前 call 的 `output_tokens`。 |
| tool/function call blocks | `tool_calls` | 当前 call 的 `output_tokens`。 |
| structured response blocks | `structured_output` | 当前 call 的 `output_tokens`。 |

Tool result 不是模型 output；tool call 是模型 output。Credit records 不是 content candidates。

## 4. Qoder 字段到候选的映射

| Qoder 来源 | 统一候选 |
|---|---|
| transcript 当前 user message | `user_input` |
| `full_messages_array` 当前 user item | `user_input` |
| `full_messages_array` prior items | `conversation_history` |
| `full_messages_array` tool_result/function result items | `tool_results` |
| Qoder observed/default tool schemas | `tool_definitions` |
| Claude-Code-like default tool catalog fallback | `tool_definitions` |
| `.qoder/rules/**` | 行为规则映射到 `system_instructions`；仓库内容映射到 `repo_context`。 |
| `AGENTS.md`、`.codex/AGENTS.md`、`CLAUDE.md` | 行为规则映射到 `system_instructions`；仓库内容映射到 `repo_context`。 |
| Qoder model policy、runtime wrapper、IDE context | `runtime_context` |
| compacted conversation summary | `conversation_history` |
| provider state 或 opaque broker context id | `reasoning_state` 或 metadata only；不得编造 source text。 |
| assistant final text | `assistant_output` |
| visible reasoning/thinking fragments | `reasoning_output` |
| function/tool call structure | `tool_calls` |
| structured response block | `structured_output` |

如果 Qoder 没有持久化完整 tools schema，适配器可使用当前 Claude-Code-like 默认 tool definitions，并补充 observed Qoder-only tools。不得只按 invoked tool count 估算 `tool_definitions`。

## 5. Qoder 中候选到 Token 类型的行为

| 候选 | 首次模型消费 | 后续 call / 复用 |
|---|---|---|
| `user_input` | `fresh_input_tokens` | 如果重放，通常变成 `conversation_history`。 |
| `system_instructions` | `fresh_input_tokens` | broker/provider 报告 cache activity 时为 `cache_read_tokens` 或 `cache_write_tokens`。 |
| `tool_definitions` | `fresh_input_tokens` | cached 时为 `cache_read_tokens`；报告 cache creation 时为 `cache_write_tokens`。 |
| `runtime_context` | 被发送时为 `fresh_input_tokens` | 复用且 reported cached 时为 `cache_read_tokens`。 |
| `conversation_history` | 根据 underlying usage shape 可为 `fresh_input_tokens` 或 `cache_read_tokens` | 稳定 history 通常映射为 cache read。 |
| `tool_results` | 首次消费时为 `fresh_input_tokens` | 重放或 cached 时为 `cache_read_tokens`。 |
| `repo_context` | 新引入时为 `fresh_input_tokens` | 重复且 cached 时为 `cache_read_tokens`。 |
| `reasoning_state` | provider/broker-dependent | provider/broker-dependent。 |
| `assistant_output` | 当前 call 的 `output_tokens` | 后续 call 可作为 `conversation_history` 被消费。 |
| `reasoning_output` | 当前 call 的 `output_tokens` | provider state 暴露时可被后续 call 消费。 |
| `tool_calls` | 当前 call 的 `output_tokens` | 后续 call 可在 history 中包含 tool activity。 |
| `structured_output` | 当前 call 的 `output_tokens` | 后续 call 可作为 history 被消费。 |

## 6. 额度计费规则

| 场景 | 规则 |
|---|---|
| 额度事件可映射到 call | 将 credits 作为该 call 的 `credit_summary` 或等价 billing metadata 保存。 |
| 额度事件无法映射 | credit attribution 保持 unavailable 并写 diagnostics；不得猜测性分摊到 candidates。 |
| token usage 缺失但 credits 存在 | tokens 仍按 token 规则标记 estimated/unavailable；credits 不变成 token counts。 |
| Underlying provider 为 Anthropic-like | 使用 `cache_read_input_tokens`、`cache_creation_input_tokens`、`input_tokens`、`output_tokens` aliases。 |
| Underlying provider 为 OpenAI-like | 使用 `cached_input_tokens`、`input_tokens`、`output_tokens` aliases，并按 input minus cached input 计算 fresh。 |

## 7. 用量字段映射

| 共享字段 | Qoder 来源 |
|---|---|
| `fresh_input_tokens` | Anthropic-like：cache fields 单独报告时使用 `input_tokens`；OpenAI-like：cache 是 input 子集时使用 `input_tokens - cached_input_tokens`。 |
| `cache_read_tokens` | `cache_read_input_tokens`、`cached_input_tokens`、`cached_tokens` 或 broker alias。 |
| `cache_write_tokens` | `cache_creation_input_tokens`、`cache_write_input_tokens` 或 broker alias；未报告时 unavailable。 |
| `output_tokens` | `output_tokens`、`completion_tokens` 或 broker output alias。 |

派生规则：

```text
input_tokens = fresh_input_tokens + cache_read_tokens
total_tokens = fresh_input_tokens + cache_read_tokens + cache_write_tokens + output_tokens
credits are separate billing metadata
```

Qoder 可能同时暴露 token 和 credit usage。Token candidates 映射到 accounting fields；credit attribution 映射到 billing summaries。

## 8. 适配器非目标

本适配器不定义 parser loop、payload JSON schema、UI bucket colors、coverage/residual bookkeeping、normalized artifact layout 或 preview truncation。这些细节属于实现文档、测试或代码。
