# Codex 样例：019ede24-67de-7b11-b46f-7922530907a9

## 文件

- `019ede24-67de-7b11-b46f-7922530907a9.jsonl`：标准样例主线程输入文件，复制自同目录原始 rollout。
- `rollout-2026-06-19T12-29-48-019ede24-67de-7b11-b46f-7922530907a9.jsonl`：用户提供的原始 Codex 主线程 rollout。
- `rollout-2026-06-19T12-32-38-019ede26-ff03-7a82-bb34-cfab716a498a.jsonl`：Subagent A（Socrates）子线程 rollout。
- `rollout-2026-06-19T12-32-38-019ede26-fff1-7790-ad39-a8a29eda9af4.jsonl`：Subagent B（Goodall）子线程 rollout。
- `litellm_calls/`：人工核对用的真实 API request/response 旁路证据；parser 和 `expected.normalized.jsonc` 生成不得依赖该目录。
- `expected.normalized.jsonc`：normalized v2 人工审查预期。

## 样例摘要

- Agent：`codex`
- Session：`019ede24-67de-7b11-b46f-7922530907a9`
- 项目：`/Users/zhehan/Documents/tools/llm/feipi-session-browser`
- 主线程模型：`gpt-5.5`
- 标准结果：9 个 LLM call（5 个 main、4 个 subagent）、7 个 tool execution
- 覆盖场景：`tool_search`、并行 `spawn_agent`、subagent 内部 `exec_command`、分批 `wait_agent`、父线程接收 `subagent_notification` 后最终汇总

## 行号约定

- Request 侧行号是该 call 发起前，在对应 rollout 中能定位到的关键上下文证据；Codex JSONL 不保存完整 HTTP request body。
- Response 侧行号是该 call 的模型输出段，通常从 `response_item.reasoning` / tool call / assistant message 到关闭该 call 的 `event_msg.token_count`。
- `task_complete` 行只表示线程收口，不算 LLM response。

## Call 对照

| Call | Scope / 发起方 | Request 定位 | Response 定位 | Review 重点 |
|---|---|---|---|---|
| C1 `codex-call-0001` | main：用户 turn 启动主 agent | `019ede24-67de-7b11-b46f-7922530907a9.jsonl` L1-L7 | 同文件 L8-L11 | 首轮主 call；响应声明 `tool_search`，token_count 在 L11。 |
| C2 `codex-call-0002` | main：主 agent 继续规划 | 同文件 L1-L11 | 同文件 L12-L17 | 并行声明两个 `spawn_agent`；L15/L16 返回 Socrates/Goodall 的 `agent_id`。 |
| C3 `codex-subagent-019ede26-ff0-call-0001` | subagent A：Socrates，由 C2 的 `call_WXDap...` 发起 | `rollout-2026-06-19T12-32-38-019ede26-ff03-7a82-bb34-cfab716a498a.jsonl` L1-L7 | 同文件 L8-L11 | A 子线程首轮；执行 `exec_command` 写入并验证 `tmp/subagent-proof-a.md`。 |
| C4 `codex-subagent-019ede26-ff0-call-0002` | subagent A：Socrates 消费工具结果后收口 | 同文件 L1-L11 | 同文件 L12-L14 | A 子线程最终回复 `PASS`；L15 是线程完成事件。 |
| C5 `codex-subagent-019ede26-fff-call-0001` | subagent B：Goodall，由 C2 的 `call_LHCE...` 发起 | `rollout-2026-06-19T12-32-38-019ede26-fff1-7790-ad39-a8a29eda9af4.jsonl` L1-L7 | 同文件 L8-L11 | B 子线程首轮；执行 `exec_command` 写入并验证 `tmp/subagent-proof-b.md`。 |
| C6 `codex-subagent-019ede26-fff-call-0002` | subagent B：Goodall 消费工具结果后收口 | 同文件 L1-L11 | 同文件 L12-L14 | B 子线程最终回复 `PASS`；L15 是线程完成事件。 |
| C7 `codex-call-0003` | main：主 agent 消费两个 `spawn_agent` 结果 | `019ede24-67de-7b11-b46f-7922530907a9.jsonl` L15-L17（加前序历史） | 同文件 L18-L21 | 调用 `wait_agent` 等待子线程；本轮输出先拿到 A 的完成状态。 |
| C8 `codex-call-0004` | main：主 agent 消费 A 的 wait 结果和通知 | 同文件 L20-L22（加前序历史） | 同文件 L23-L25 | 再次 `wait_agent` 等待 B；L24 返回 B 的完成状态。 |
| C9 `codex-call-0005` | main：主 agent 消费 B 的 wait 结果和通知 | 同文件 L24-L26（加前序历史） | 同文件 L27-L29 | 最终汇总 `Subagent A/B: PASS`；L30 是线程完成事件。 |

## 归属判断

- 主线程 `spawn_agent` / `wait_agent` 都是 `scope=main`。
- 子线程内部 `exec_command` 都是 `scope=subagent`，并通过 `parent_tool_call_id` 关联回对应的 `spawn_agent`。
- `subagent_notification` 是父线程后续 request 的用户侧通知证据，不等同于子线程 LLM call。
