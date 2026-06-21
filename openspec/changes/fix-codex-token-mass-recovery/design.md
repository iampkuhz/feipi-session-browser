# 设计：修正 Codex Token Mass 归因恢复

## 当前状态

- Codex parser 只把 `function_call_output` / `custom_tool_call_output` 放入 pending tool results，遗漏 `tool_search_output`，导致 M2 request 缺少 `call_XsbhHJb7vGOu1oAP5oFqgBr7`。
- `_parse_subagent_rollouts_for_parent()` 把 child `thread_info.model` 设置为 `model_provider`，后续 `_build_round()` 又优先使用该值，导致 child call model 为 `litellm-local` 而不是真实 turn `model=gpt-5.5`。
- Codex request builder 与 `CodexTokenAccountingMapper` 对 source units 做本地 token 估算，并在估算值超过 fresh denominator 时缩放；这会把 occurrence/content coverage 伪装成 provider token mass。
- 当前 `docs/agent-token-attribution/codex.md` 仍包含“candidate 到 fresh/cache 行为”的强映射和 `session_meta.dynamic_tools` token-bearing 假设，不符合用户新分析。

## 提议方法

1. 将 Codex 文档替换为用户审核后的新版逻辑，明确 `normalize_record` 与 `extract_calls` 边界、sidecar 质量、full replay/continuation、`encrypted_content` 和 token-mass 精度边界。
2. parser 中把 `tool_search_output` 作为 runtime request event：当前 call 不纳入 response output；在下一 call 的 `request.tool_result_ids` 与 source_units `tool_results` 中出现；tool execution status 不再标记 missing。
3. 子线程 call model 优先取 `turn_context.payload.model`，仅在缺失时回退 thread info / provider。
4. Codex source-unit request accounting 只列出 candidates/sources 和 `token_status=unknown_mass`；`fresh_input_tokens.unattributed_tokens` 保留完整 fresh input，`candidate_total_tokens=0`。response side 保留 provider aggregate reasoning/output；非 reasoning 多 lane 不伪拆分。
5. 更新 `expected.normalized.jsonc` 与测试断言，让目标样例与 `~/Downloads/normalized.json` 的中间结构一致，同时保留 runtime artifact 的 compact source unit catalog。

## 风险

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| UI 仍假设 candidates 有 tokens。 | 中 | 中 | 保留 `tokens` 字段为 0，并增加 `token_status` / `token_precision` 说明。 |
| 调整 Codex mapper 影响旧 Codex tests。 | 中 | 中 | 只修改 Codex mapper；Claude/Qoder mapper 不动。 |
| `tool_search_output` 形状与普通 tool output 不完全相同。 | 中 | 低 | 用 call_id/status/output/tools payload 原样记录，不做 schema 二次拆分。 |
| 文档替换导致与现有短文不一致。 | 低 | 低 | 用户明确提供新版文档作为优化参考，本次同步仓库文档。 |

## 回滚

回滚本 change 修改的 Codex 文档、Codex parser、Codex mapper/builder、目标 expected normalized 与测试即可。normalized schema 不变，回滚不会影响 artifact 读取兼容性。
