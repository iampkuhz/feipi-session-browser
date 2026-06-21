# Codex Token 归因适配器

> 本文只定义 **Codex rollout / OpenAI Responses 的通用提取逻辑**。
> 具体会话、文件名、record 编号、逐 call 数据和反向验证结果放在样例文档中，不进入本文件。

## 1. 目标与边界

| 项 | 值 |
|---|---|
| Runtime key | `codex` |
| API family | `openai_responses` |
| 主事实源 | Codex rollout JSON object stream |
| 可选证据 | raw request、raw response、调用时 tool snapshot、版本化 Codex catalog |
| 输出 | 独立 `LLMCall`、request/response occurrence、usage accounting、source attribution、diagnostics |

本适配器遵循两个分离原则：

1. **Token accounting** 回答“这一 call 如何计费”：`fresh_input_tokens`、`cache_read_tokens`、`cache_write_tokens`、`output_tokens`。
2. **Attribution candidate** 回答“这些 token 可能来自哪里”：`user_input`、`system_instructions`、`tool_definitions`、`conversation_history`、`tool_results`、`reasoning_state` 等。

本文不声称能够：

- 从 `encrypted_content` 恢复 reasoning 明文；
- 从 aggregate usage 精确反推出 request 内每个来源的 provider token 数；
- 从被截断的 sidecar 恢复被删掉的字符；
- 在没有版本或快照证据时，把当前 builtin/MCP schema 当成历史事实；
- 复刻 provider 私有序列化或隐藏 prompt。

---

## 2. 术语：`normalize_record` 与完整提取状态机

旧文档同时使用“normalize 函数”和“规范化算法”，边界不清。新版只保留下面两个术语。

### 2.1 单条记录规范化：`normalize_record`

```text
normalize_record(raw_record, static_config) -> NormalizedEvent[]
```

它是**无状态纯函数**：相同输入和相同静态配置必须产生相同输出。它只处理单条 artifact 的形状，不读取“前一条/后一条事件”。

允许做：

- 统一字段别名和 item type；
- 保留原始 payload、source span、record index、provider `call_id`；
- 把一个 message 拆成 content parts；
- 按精确 wrapper/tag 拆分 developer/system 注入块；
- 把 tool schema 统一为稳定形状；
- 标记事件的**固有类别**：模型输出、请求侧事件、usage、镜像、metadata；
- 生成内容哈希，但不据此跨记录删除内容。

禁止做：

- 决定该 item 属于第几个 `LLM call`；
- 冻结 request snapshot；
- 把上一 call 的 output 变成下一 call 的 input occurrence；
- 计算累计 usage delta；
- 更新 active tools；
- 跨记录去重；
- 把 cache token 分配给具体来源。

### 2.2 完整 Call 提取状态机：`extract_calls`

```text
extract_calls(normalized_events, sidecars, catalogs) -> LLMCall[]
```

它是**按 thread 有状态**的流程，负责：

- thread 分组和 parent/child 关联；
- sidecar 匹配和质量判断；
- generation segment 与 call 边界；
- request snapshot 冻结；
- item occurrence 的 request/response/runtime 方向；
- active tool 状态迁移；
- usage delta、accounting fields 和 diagnostics；
- 只针对“同一物理 occurrence 的多份证据”去重。

因此二者不是两个同义算法：

```text
parse_json_objects
  -> normalize_record          # 单条、无状态、只改形状
  -> extract_calls             # 跨记录、有状态、决定归属
  -> attribute_and_report
```

`split_prompt_text`、`normalize_tool_schema` 只是 `normalize_record` 内部 helper，不再单独称为“规范化算法”。

---

## 3. 证据源与优先级

优先级必须按“要证明什么”分别确定，不能简单规定 raw 永远优先或 rollout 永远优先。

| 要证明的事实 | 首选证据 | 次选证据 |
|---|---|---|
| rollout 事件顺序、typed item、provider call id | rollout | 无 |
| 实际 request `input[]` / `tools[]` 顺序 | 未截断 raw request | rollout 状态重建 |
| 当前模型生成的 output items | rollout `response_item` 或非空 raw `output[]` | `event_msg.agent_message` 仅作 fallback preview |
| call 级 usage | 有效 `token_count` / raw usage 交叉校验 | 单一可用方 |
| effective instructions/tools | 未截断 wire snapshot | raw request、rollout、版本化 catalog 综合 |
| builtin/default prompt | 匹配 `cli_version` 和 hash 的 catalog | `unavailable` |
| MCP/plugin schema | 调用时 snapshot 或未截断 wire | 事后查询只能 `estimated` |

### 3.1 Sidecar 质量

| 状态 | 判定 | 使用方式 |
|---|---|---|
| `sidecar_exact` | shape 正确，token-bearing 字段没有截断 | 可作 canonical request/response |
| `sidecar_truncated` | token-bearing 字段出现截断占位符 | 只采用未截断部分，不做字符级完整性声明 |
| `sidecar_envelope_only` | response envelope/usage 可用，但流式 `output=[]` | 校验 usage、id、effective context；output 取 rollout |
| `sidecar_mislabeled` | 文件名是 response，实际内容是 request | 不作为 response |
| `sidecar_unmatched` | 无法可靠关联 thread/call | 仅 diagnostics |

**`output=[]` 不等于模型没有输出。** 对流式 callback，完整 item 可能只存在于 rollout。

---

## 4. Canonical 数据结构

### 4.1 `NormalizedEvent`

```text
NormalizedEvent {
  event_id
  thread_hint
  record_index
  source_locator
  raw_payload
  event_kind          # MODEL_OUTPUT | REQUEST_EVENT | USAGE | MIRROR | METADATA
  item_type?
  role?
  provider_call_id?
  content_parts[]
  intrinsic_units[]
  evidence_level
}
```

### 4.2 `ItemOccurrence`

同一个 canonical item 可以在不同 call 中有不同 occurrence：

```text
ItemOccurrence {
  occurrence_id
  canonical_item_id
  llm_call_id
  direction           # request_input | response_output | runtime_between_calls | display_mirror
  physical_plane      # instructions | input[i] | tools[i] | rollout record
  candidate
  source_locator
  evidence_level
  token_status        # exact_aggregate | estimated | unknown | not_token_bearing
}
```

例如同一 reasoning item：

```text
产生时：Call N     / response_output / reasoning_output
重放时：Call N + 1 / request_input   / reasoning_state
```

不得在 canonical item 上保存永久的 `direction=response`。

### 4.3 `LLMCall`

```text
LLMCall {
  llm_call_id
  thread_id
  ordinal
  request_snapshot {
    instructions_plane
    input_plane
    tools_plane
    settings_plane
  }
  response_occurrences[]
  runtime_events_after_output[]
  usage
  raw_request_ref?
  raw_response_ref?
  diagnostics[]
}
```

---

## 5. JSON object stream 与 thread 分组

### 5.1 解析

Codex rollout 可能是 pretty-printed、连续拼接的顶层 JSON object，不保证“一物理行一个对象”。解析器必须：

1. 读取完整字节流；
2. 跳过空白/BOM；
3. 用 streaming decoder 连续解析顶层 object；
4. 保存 `record_index`、byte range 和原始字节 hash；
5. 遇到损坏 object 时输出明确 diagnostic，不把内部文本行当事件。

### 5.2 Thread scope

优先使用：

1. `session_meta.payload.id`；
2. raw request 的显式 thread id；
3. 可靠 correlation metadata；
4. `prompt_cache_key` 只能辅助，不能单独作真值。

每个 thread 独立维护 history、active tools、open segments、usage baseline 和 call ordinal。并发 child 的 token 不得按时间窗口混入 parent。

---

## 6. `normalize_record` 的确定性规则

### 6.1 事件固有类别

| 原始 item | `event_kind` |
|---|---|
| `reasoning` | `MODEL_OUTPUT` |
| `function_call` / `custom_tool_call` / `tool_search_call` | `MODEL_OUTPUT` |
| `message(role="assistant")` | `MODEL_OUTPUT` |
| `function_call_output` / `custom_tool_call_output` / `tool_search_output` | `REQUEST_EVENT` |
| `message(role="developer"/"system"/"user")` | `REQUEST_EVENT` |
| `event_msg.token_count` | `USAGE` |
| `event_msg.user_message` / `event_msg.agent_message` | `MIRROR` |
| `task_started` / `task_complete` / `turn_context` | `METADATA` |

该表只标记“固有事件类型”；最终属于哪一个 call，由 `extract_calls` 决定。

### 6.2 Message 拆分

每个 content part 单独生成 unit，并保留父 message locator。只按明确字段和完整 tag 拆分，不做自然语言语义分类。

| 精确形状 | unit | candidate hint |
|---|---|---|
| `# AGENTS.md instructions for ...` + 完整 `<INSTRUCTIONS>...</INSTRUCTIONS>` | `project_instruction_bundle` | `system_instructions` |
| 完整 `<INSTRUCTIONS>...</INSTRUCTIONS>` | `visible_instructions_block` | `system_instructions` |
| `<skills_instructions>...</skills_instructions>` | `skills_instructions_block` | `skill_definitions` |
| `<plugins_instructions>...</plugins_instructions>` | `plugins_instructions_block` | `skill_definitions` |
| `<permissions instructions>...</permissions instructions>` | `permissions_block` | `runtime_context` |
| `<app-context>...</app-context>` | `app_context_block` | `runtime_context` |
| `<collaboration_mode>...</collaboration_mode>` | `collaboration_mode_block` | `runtime_context` |
| `<environment_context>...</environment_context>` | `environment_context_block` | `runtime_context` |
| `<subagent_notification>...</subagent_notification>` | `subagent_notification` | `tool_results` / runtime input |

规则：

- tag 必须完整、大小写匹配、不可重叠；
- 已抽取 byte range 不再生成第二份 token-bearing unit；
- developer/system 容器的未匹配非空文本为 `prompt_plain_text`；
- role 为 `user` 的文本不能仅凭 role 一律归 `user_input`，要在状态机中结合 wrapper 和镜像关系判断。

### 6.3 Tool schema 规范形状

统一为：

```text
ToolDefinition {
  type
  namespace?
  name
  description?
  parameters?        # inputSchema / parameters 的规范字段
  strict?
  defer_loading?
  raw_payload
}
```

这只是字段形状转换，不表示该工具已经进入某次 request。

`session_meta.dynamic_tools` 是 catalog/provenance。只有在以下任一条件成立时才生成 token-bearing occurrence：

- 未截断 raw request 的 `tools[]` 明确包含；
- rollout 中的 `tool_search_output` 被某次 request 消费；
- raw 不可用，且版本化 fallback 明确证明该动态工具在当次请求中激活。

fallback 从 `dynamic_tools` 构造首轮 active tools 时，默认只纳入 `deferLoading != true` 的工具；不得把整个延迟目录都算进 request。

---

## 7. `extract_calls` 状态机

### 7.1 每 thread 状态

```text
history
active_tools
instructions_state
open_generation_segment?
unclosed_segments_fifo[]
request_event_seen_after_model_output
last_cumulative_usage
matched_sidecars
```

### 7.2 Segment 构造

```text
for event in thread_order:
  if event.kind == MODEL_OUTPUT:
    if no open segment or request_event_seen_after_model_output:
      segment = new segment
      segment.request_snapshot_fallback = freeze_current_request_state()
      enqueue segment
    append event to segment.response_items
    append canonical item to replayable history
    request_event_seen_after_model_output = false

  elif event.kind == REQUEST_EVENT:
    append event to history
    apply_request_state_transition(event)   # 如 tool_search_output 更新 semantic active tool view
    if open segment exists:
      append event to segment.runtime_events_after_output
    request_event_seen_after_model_output = true

  elif event.kind == MIRROR:
    correlate_with_canonical_item_or_keep_as_fallback()

  elif event.kind == USAGE:
    usage = normalize_usage(event)
    if usage is duplicate/zero:
      record diagnostic
    else:
      close oldest compatible unclosed segment

  elif event.kind == METADATA:
    update provenance only
```

关键点：

- `token_count` **只关闭 usage**，不把它之前的所有记录都判为 response；
- request snapshot 在该 segment 第一个模型输出之前冻结；
- tool result 即使出现在 closing `token_count` 之前，也不会回写刚冻结的 request；
- 若 request event 之后又出现模型输出，应开始新 segment，即使前一 usage 事件晚到；
- 有 exact raw request 时，raw request 覆盖 fallback snapshot，rollout 只用于对齐和 provenance。

### 7.3 Sidecar 与 segment 匹配

优先级：

```text
explicit correlation id
(thread_id, turn_id, provider timestamp, model)
(thread_id, ordinal, typed-input fingerprint)
(thread_id, usage tuple, narrow time window)
```

匹配后必须校验 input item 序列、tool set、model 和 usage；不能只按文件名编号配对。

---

## 8. Request 还原

### 8.1 四个平面

| 平面 | 内容 |
|---|---|
| `instructions_plane` | 顶层 instructions、base instructions、developer/system 注入 |
| `input_plane` | user/assistant/reasoning/tool call/tool result 等 typed history |
| `tools_plane` | 当次实际发送或被加载的 tool definitions |
| `settings_plane` | model、reasoning、text、tool choice、store 等；通常只作配置 provenance |

不要把整份 raw request JSON 当作一个 source bucket。

### 8.2 首轮 seed

在没有 exact raw request 时，首轮 fallback request 由以下内容构成：

- 可证明 token-bearing 的 instructions；
- 首个模型输出前的 developer/system/user typed items；
- 已激活工具集合；
- 必要的显式 multimodal input。

`session_meta.cwd`、`cli_version`、`git`、`source` 等默认是 provenance，不因出现在 metadata 就自动贡献 prompt token。若相同信息出现在 `<environment_context>` 或 raw request 中，则以该真实 occurrence 计入。

### 8.3 Role=`user` 的分类顺序

对每个 user message occurrence，按顺序判断：

1. 是否是已知 project/environment wrapper；
2. 是否是 `<subagent_notification>` 或其他 runtime notification；
3. 是否与 `event_msg.user_message` 构成同一用户输入的镜像；
4. 是否是 raw request 中重放的历史 user message；
5. 最后才归当前 `user_input`。

### 8.4 历史 typed items

| request 中的 item | candidate |
|---|---|
| 早于当前 call 的 user/assistant message | `conversation_history`；当前新 user message例外 |
| 早于当前 call 的 function/custom/tool-search call | `conversation_history` |
| `function_call_output` / `custom_tool_call_output` | `tool_results` |
| reasoning item / encrypted reasoning state | `reasoning_state` |
| 显式 file context | `repo_context` |

上一 call 的 output token 数不能直接当成下一 call 中该 item 的 input token 数。只能确认 item 存在、顺序和内容；输入侧 token mass 仍由当次 provider 序列化决定。

### 8.5 `tool_search_output` 特殊规则

`tool_search_call` 是当前 call 的模型输出；`tool_search_output` 是 runtime 产生、供后续模型消费的 request item。

对后者同时保留两种视图：

- **物理视图**：它在 raw `input[]` 中是一个 typed item；
- **语义视图**：其中 `tools[]` 归到 `tool_definitions`，并更新后续 effective tool view。

但它只是一份物理 token-bearing occurrence，不能同时按“history blob”和“active tools”计两次。

若未截断 wire request 确实同时包含：

1. `input[]` 内的 `tool_search_output`；
2. 顶层 `tools[]` 内独立重复的 schema；

则二者是两个真实物理 occurrence，不能因为内容相同而删除。response envelope 的 effective tools 回显只作验证，不是第三份 request token 来源。

### 8.6 Full replay 与 continuation

- `previous_response_id` 存在：不能假设 raw `input[]` 是完整历史；还要考虑 provider-side continuation。
- `previous_response_id` 为空且 raw `input[]` 明确包含既往 items：按 full replay 处理。
- input token 下降不能单独证明发生删除、压缩或 compaction；必须比较 typed payload 或显式 compaction evidence。

---

## 9. Response 还原与可展示内容

### 9.1 Canonical response items

| item | candidate | UI 可展示 |
|---|---|---|
| `reasoning` | `reasoning_output` | summary（若存在）、密文状态、hash、长度、aggregate reasoning token |
| `function_call` / `custom_tool_call` | `tool_calls` | 工具名、namespace、call id、完整 arguments |
| `tool_search_call` | `tool_calls` | query、limit、call id、execution metadata |
| `message(role="assistant")` | `assistant_output` / `structured_output` | 原始 text/part、annotations、phase/status |

以下内容不进入当前 response 正文：

- `function_call_output`、`custom_tool_call_output`、`tool_search_output`；
- developer/system/user input message；
- `event_msg.agent_message` 的重复镜像；
- `task_complete` 等生命周期事件；
- raw response 顶层 `instructions` / `tools` 回显。

### 9.2 Token 精度

```text
reasoning_output_tokens = provider 报告的 reasoning aggregate
non_reasoning_output_tokens = output_tokens - reasoning_output_tokens
```

`non_reasoning_output_tokens` 不是“纯可读文本 token”的通用同义词，它还可能包含 tool call、structured/protocol output 和不可见格式开销。

若同一 call 有多个 tool call 或 text item，而 provider 只给 aggregate usage：

- 可以精确展示每个 item 的原始内容；
- 可以精确展示 call 级合计；
- **不能**声称每个 item 的独立 token 数，除非另有 per-item usage。

### 9.3 `encrypted_content`

可以：

- 原样保存；
- 计算 hash、字符/字节长度；
- 在受控 debug/admin 界面显示密文或截断预览；
- 在兼容的后续 Responses 请求中原样回传；
- 展示 provider 报告的 aggregate reasoning token 数。

不可以：

- 用客户端密钥或常规算法解密成 reasoning 明文；
- 把 base64/密文长度换算成真实 reasoning token；
- 根据后续回答反推原始 chain of thought；
- 在 `summary=[]` 时生成“看似真实”的推理摘要。

可读推理只能来自调用当时显式请求并返回的 reasoning summary；summary 与原始 reasoning tokens 也不是同一内容。

---

## 10. Usage 与 Token accounting

### 10.1 有效 usage

优先使用 per-call `last_token_usage`，并用累计 `total_token_usage` delta 校验：

```text
fresh_input_tokens = max(input_tokens - cached_input_tokens, 0)
cache_read_tokens  = cached_input_tokens
cache_write_tokens = provider 明确字段；否则 unavailable
output_tokens      = output_tokens
reasoning_tokens   = reasoning_output_tokens  # output 的子集
```

规则：

- 所有累计 delta 为 0：重复快照，不创建 call；
- per-call 与累计 delta 不一致：保留两份证据并报 mismatch；
- 累计计数回退：建立新 baseline，不产生负 token；
- 只有 total、没有组件：进入 `total_only_fallback`，不伪造 cache/reasoning breakdown。

### 10.2 来源 bucket 的精度

Call 总 usage 可以精确；request source bucket 通常不能精确。每个 bucket 必须标记：

| 状态 | 含义 |
|---|---|
| `exact_provider` | provider 明确给出该项 token |
| `exact_content` | 内容和 occurrence 精确，但 token mass 未必精确 |
| `estimated_tokenizer` | 用公开 tokenizer/序列化近似 |
| `unknown_mass` | 可知来源存在，但无法可靠估 token |
| `unavailable` | 内容本身不可恢复 |

不得为了让 bucket 总和等于 input usage 而任意缩放。正确报告应保留：

```text
known/estimated buckets
+ unresolved provider serialization / hidden context residual
= exact aggregate input usage
```

### 10.3 Cache 的分配边界

`cached_input_tokens` 只精确到 accounting field。除非 provider 给出 cache-span 或可验证前缀边界，否则不能断言具体哪些 source token 命中 cache。UI 可显示候选或估计，但必须标记 `estimated`。

---

## 11. 去重规则

### 11.1 可以合并

- raw request 与 rollout 对同一 `input[i]` 的两份证据；
- canonical assistant message 与内容相同、时间相邻的 `event_msg.agent_message` 镜像；
- canonical user input 与对应 `event_msg.user_message` 镜像；
- parent text part 与其拆出的 child units：parent 只作 provenance；
- response envelope 中 request-context 回显与原 request occurrence。

合并必须依赖 locator、index、call id、role、时间和结构关系，不能只靠普通内容 hash。

### 11.2 不能合并

- tool result 与内容相近的 subagent notification；
- 同一文本在不同 turn 的真实重放；
- 相同 schema 在两个真实 request plane 中的独立 occurrence；
- parent 与 child thread 中相似的 handoff；
- 同 call 内两个不同 call id 的相同 arguments；
- reasoning 密文相同但 occurrence 不同的异常重放。

---

## 12. Subagent

- child rollout 是独立 thread 和独立 token scope；
- parent `spawn_agent` 是 parent response 的 `tool_calls`；
- spawn result 是 parent runtime event，被后续 parent call 消费时为 `tool_results`；
- child `session_meta.source.subagent.thread_spawn` 建立 parent-child 关系；
- child usage、tool calls/results 留在 child scope；
- parent `wait_agent` result 和 `<subagent_notification>` 是两个独立 parent-side input occurrence；
- `fork_context=false`：不得自动复制 parent history，只使用 child 自身 seed/handoff；
- `fork_context=true`：只有实际 raw child input 或明确 snapshot 能证明继承内容，不能只凭布尔值臆造具体 token。

---

## 13. 输出证据等级与 diagnostics

### 13.1 Evidence level

```text
exact_rollout
exact_sidecar
sidecar_truncated
versioned_hardcode
snapshot_exact
estimated
unavailable
```

每个 source occurrence 都应保留：

```text
source_locator
content_hash
raw/normalized preview
physical plane
candidate
call/direction
quality/evidence level
diagnostics
```

### 13.2 必须暴露的 diagnostics

至少包括：

- `duplicate_usage_snapshot`
- `usage_component_mismatch`
- `usage_without_generation_segment`
- `sidecar_truncated`
- `sidecar_mislabeled`
- `sidecar_unmatched`
- `raw_rollout_input_mismatch`
- `mirror_without_canonical_item`
- `unclassified_request_text`
- `tool_schema_version_unknown`
- `reasoning_summary_unavailable`
- `provider_serialization_residual`

---

## 14. 最低验收测试

实现至少覆盖：

1. pretty-printed 连续 JSON objects；
2. `tool_search_output` 位于 closing usage 之前，但归下一 request；
3. `function_call_output` 位于 closing usage 之前，但归下一 request；
4. reasoning/tool call 在产生 call 是 output，在下一 call 是 input；
5. streaming response envelope 为 `output=[]`；
6. mislabeled response 实际是 request；
7. developer message 多 content parts 的精确拆分；
8. role=user 的 AGENTS/environment wrapper 不归 human `user_input`；
9. `event_msg.*_message` 镜像去重；
10. tool result 与 subagent notification 不去重；
11. `deferLoading` 工具不被首轮 fallback 全量激活；
12. parent/child usage 完全分离；
13. `previous_response_id` full replay/continuation 两种模式；
14. aggregate usage 可精确、bucket mass 保持 estimated/unknown；
15. `encrypted_content` 只能保存/回传，不生成明文。

---

## 15. 参考伪代码

```text
records = parse_json_objects(rollout_bytes)
events = []
for record in records:
  events.extend(normalize_record(record, static_config))

threads = group_by_thread(events)
for thread in threads:
  matched = match_and_classify_sidecars(thread, sidecars)
  calls = extract_calls(thread.events, matched, catalogs)
  calls = attach_occurrences_and_candidates(calls)
  calls = normalize_accounting(calls)
  emit(calls, diagnostics)
```

实现上的核心不变量是：

```text
typed item 决定固有事件类别
状态机决定 call occurrence
provider usage 决定 accounting 总量
证据等级决定可以声称的精度
```
