# 智能体 Token 归因模型

## 1. 用途

智能体 Token 归因用来解释一次 agent 会话中每个 `LLM call` 的 token 如何流动，以及这些 token 可能来自哪些内容来源。本文是跨 agent 的统一模型，只定义稳定概念和适配器契约；具体 JSONL 字段、扫描流程、API payload 和 UI 展示细节由实现文档或各 agent 适配器负责。

核心分离原则：

- `TokenAccountingField` 描述 token 如何计费。
- `Attribution Candidate` 描述 token 可能来自哪里。
- 同一个 candidate 在不同 call 中可以映射到不同 accounting field。
- 调试证据、coverage、residual、source refs 和 payload shape 不是顶层归因模型。

## 2. 支持的智能体适配器

| Agent | 适配器文件 | Runtime key | API family |
|---|---|---|---|
| Claude Code | `claude-code.md` | `claude_code` | `anthropic_messages` |
| Codex | `codex.md` | `codex` | `openai_responses` |
| Qoder | `qoder.md` | `qoder` | `qoder_broker` |

未知 agent 只能使用保守的 estimate-only 处理，不得套用上述适配器的字段规则。

## 3. Token 计费字段

顶层 token accounting 只保留四个稳定字段：

| 字段 | 含义 |
|---|---|
| `fresh_input_tokens` | 当前 call 新进入模型上下文、未由 provider cache read 覆盖的输入 token。 |
| `cache_read_tokens` | 当前 call 由 provider/broker 报告为 cache hit 的输入 token。 |
| `cache_write_tokens` | 当前 call 被 provider/broker 报告为写入 cache 的输入 token；没有稳定字段时为 unavailable 或 0。 |
| `output_tokens` | 当前 call 中模型产生的输出 token，包括 assistant text、reasoning output、tool calls 或结构化输出。 |

派生关系：

```text
input_tokens = fresh_input_tokens + cache_read_tokens
total_tokens = fresh_input_tokens + cache_read_tokens + cache_write_tokens + output_tokens
```

如果 provider 的 cache read 是 input tokens 子集，例如 OpenAI/Codex 的 `cached_input_tokens`，则：

```text
fresh_input_tokens = input_tokens - cache_read_tokens
cache_read_tokens = cached_input_tokens
```

`Fresh`、`Cache Read`、`Cache Write`、`Output` 可以作为 UI label，但模型文档使用上方四个字段作为稳定名称。

## 4. 归因候选

`Attribution Candidate` 是来源标签，不是计费字段。Candidate 只回答“token 可能来自哪里”，不回答“token 如何收费”。

### 请求侧候选

| 归因候选 | 含义 |
|---|---|
| `user_input` | 当前用户输入、附件或多模态内容。 |
| `system_instructions` | 平台、developer/system、仓库规则或运行时注入的行为指令。 |
| `tool_definitions` | tools/functions schema、参数结构和工具说明。 |
| `skill_definitions` | skills、plugins、slash commands、agent capabilities 或类似能力目录。 |
| `runtime_context` | cwd、shell、权限、沙箱、时间、客户端能力、协作模式等运行事实。 |
| `conversation_history` | 当前 call 前已进入模型上下文的 user/assistant/tool activity 历史。 |
| `tool_results` | 工具执行结果在后续 call 中作为模型输入被消费的内容。 |
| `reasoning_state` | provider 可复用或回传的 reasoning state；具体行为依赖 provider。 |
| `repo_context` | 仓库文件、diff、搜索结果、项目规则文件或本地代码片段。 |

### 响应侧候选

| 归因候选 | 含义 |
|---|---|
| `assistant_output` | 模型返回给用户可见的自然语言或 markdown 文本。 |
| `reasoning_output` | 当前 call 产生的 visible/hidden/encrypted reasoning 输出。 |
| `tool_calls` | 当前 call 中模型发出的 tool/function/custom tool 调用结构。 |
| `structured_output` | 当前 call 输出中的结构化响应块、citations、JSON-like blocks 或协议片段。 |

更细的来源名，例如 `AGENTS.md`、`CLAUDE.md`、MCP tool schema、Codex `<skills_instructions>`、Qoder IDE context 或 Claude Code system reminder，应放在适配器文档里，先映射到统一 candidate，再映射到 accounting field。

## 5. 候选到 Token 类型的映射

Candidate 和 accounting field 是多对多关系。一个来源首次进入模型时通常属于 `fresh_input_tokens`；后续复用时可能属于 `cache_read_tokens`；被 provider 标记创建 cache 时可能属于 `cache_write_tokens`；模型生成内容属于 `output_tokens`。

| 归因候选 | `fresh_input_tokens` | `cache_read_tokens` | `cache_write_tokens` | `output_tokens` |
|---|---|---|---|---|
| `user_input` | 是 | 通常否 | 否 | 否 |
| `system_instructions` | 首次使用 | 复用且命中 cache | 依赖 provider | 否 |
| `tool_definitions` | 首次使用 | 复用且命中 cache | 依赖 provider | 否 |
| `skill_definitions` | 首次使用 | 复用且命中 cache | 依赖 provider | 否 |
| `runtime_context` | 新内容 | 复用内容 | 依赖 provider | 否 |
| `conversation_history` | 新引入内容 | 复用内容 | 依赖 provider | 否 |
| `tool_results` | 首次被模型消费 | 重放或复用 | 依赖 provider | 否 |
| `reasoning_state` | 依赖 provider | 依赖 provider | 依赖 provider | 否 |
| `repo_context` | 新内容 | 复用内容 | 依赖 provider | 否 |
| `assistant_output` | 否 | 否 | 否 | 是 |
| `reasoning_output` | 否 | 否 | 否 | 是 |
| `tool_calls` | 否 | 否 | 否 | 是 |
| `structured_output` | 否 | 否 | 否 | 是 |

重要约束：

- 不得把 candidate name 当作 token accounting field。
- 不得把 request attribution 的分母固定绑定到 `fresh_input_tokens`。
- 不得创建 `provider_cached_context` 这类来源 candidate 来解释 cache read；cache read 是 accounting field。
- 不得从 residual、hidden prompt 或不可见 provider state 伪造来源正文。

## 6. 跨 Call 状态迁移规则

一次 `LLM call` 的归因必须先确定 call 边界，再确定内容方向，最后映射 accounting field。

| 状态迁移 | 规则 |
|---|---|
| 首次出现的输入 | 某来源首次进入当前 call 的模型输入时，可映射为 `fresh_input_tokens`。 |
| 复用输入 | 某来源已被 provider cache 命中或作为已缓存上下文复用时，可映射为 `cache_read_tokens`。 |
| 创建 cache 的输入 | provider/broker 明确报告 cache creation 时，相关输入可映射为 `cache_write_tokens`。 |
| 模型输出 | assistant text、reasoning、tool call、structured response 都属于当前 call 的 `output_tokens`。 |
| tool call 到 tool result | tool call 是当前 call 的模型输出；tool result 是 runtime event，只有进入后续 call 的模型输入时才成为 `tool_results`。 |
| assistant output 进入历史 | 当前 call 的 `assistant_output` 在后续 call 中可作为 `conversation_history` 输入。 |
| reasoning output 进入状态 | 当前 call 的 `reasoning_output` 在 provider 支持时，后续 call 可作为 `reasoning_state`。 |
| repo/tool 内容重放 | 文件内容、搜索结果或工具结果被重复带入模型时，可从 fresh 转为 cache read，取决于 provider accounting。 |

实际 call 分析表应以四个 accounting fields 为列，而不是以 candidate 为列：

```text
| Call | Fresh Input | Cache Read | Cache Write | Output |
|---|---|---|---|---|
| req1 | user_input; system_instructions; tool_definitions | none | unavailable | reasoning_output; tool_calls |
```

每个单元格内部可以列出 candidate、source、extraction rule、estimated token share 和 notes，但这些是分析层信息，不是顶层模型字段。

## 7. 智能体适配器职责

每个适配器只负责把本 agent 的可见数据映射到统一模型：

1. 定义范围（scope）：runtime key、API family、provider/broker 和主要数据源。
2. 定义调用边界：什么事件关闭一次 `LLM call`，重复 usage 如何处理。
3. 定义方向规则：哪些 item 是当前 output，哪些 runtime event 会进入下一次 input。
4. 定义来源到候选映射：具体字段或文件先映射到统一 `Attribution Candidate`。
5. 定义候选到 token 行为：这些 candidate 在首次出现、复用、cache write 和 output 中如何计入四个 fields。
6. 定义 agent 专属边界情况：例如 subagent、raw payload 缺失、provider state、reasoning state。
7. 定义用量字段映射：provider usage 字段如何归一化为四个 accounting fields。

适配器不应重新定义跨 agent candidate 集合，也不应把 UI bucket、API payload 或 parser artifact 当作核心模型。

## 8. README.md 不定义的内容

本 README 不定义以下实现细节：

- 具体 JSONL field path 或 provider raw payload path。
- scan phase、on-demand phase、pending refs 或 record iteration 流程。
- normalized artifact schema、API response payload、preview 截断长度或 source locator 格式。
- coverage、residual、precision、evidence level 的持久字段设计。
- Codex、Claude Code、Qoder 的专用 bucket 名称或 parser 变量名。
- UI 展示组件、颜色、排序、modal drilldown 或 payload tab 结构。

这些内容可以放入适配器文档、实现设计文档、OpenSpec 增量或代码注释中。
