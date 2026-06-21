# 提案：修正 Codex Token Mass 归因恢复

## 问题

针对 Codex session `019ede24-67de-7b11-b46f-7922530907a9`，当前 normalized 与归因逻辑仍存在偏差：`tool_search_output` 未被视为后续 request 消费的工具结果，子线程 call model 会被 `model_provider=litellm-local` 覆盖，Codex source-unit accounting 会把可见内容估算值缩放成看似精确的 per-candidate token mass，且仓库内 `docs/agent-token-attribution/codex.md` 与用户提供的新分析文档不完全一致。

## 范围

包含：

- 用用户提供的 `~/Downloads/codex-5.md` 更新 Codex 通用归因文档。
- 对齐 `~/Downloads/codex_3_agents_token_mass_recovery_tables_detailed3.md` 的 9 个业务 call、usage、tool result handoff、subagent scope 和 response/request 分离规则。
- 修正 Codex normalized parser 中 `tool_search_output` 的 runtime-result 归属与子线程模型名。
- 调整 Codex attribution / accounting payload：source_units 表示 occurrence/content coverage，不再把 request bucket 估算值缩放成伪精确 token mass；cache read 只作为 provider accounting 字段展示。
- 更新目标样例 expected normalized 与聚焦测试。

不包含：

- 不依赖 `litellm_calls/` 生成 normalized artifact；sidecar 仍只作为人工核对依据。
- 不修改 Claude Code、Qoder 的归因策略，除非测试公共契约需要断言隔离。
- 不提交真实 session、缓存、密钥、token 或个人配置。

## 用户影响

Codex session detail 中该样例应稳定呈现 9 个业务 call：Main 5 个，两个 subagent 各 2 个；M2 request 能看到 M1 的 `tool_search_output` 结果；subagent call model 显示真实 `gpt-5.5`；request source candidates 显示内容和 evidence，而 token mass 保持 unknown/residual，不再输出看似精确的 bucket 百分比作为真值。

## 验证策略

- OpenSpec layout/schema/active-change/harness 验证。
- Codex normalized 聚焦测试，覆盖目标 session、`tool_search_output` handoff 和 subagent model。
- Codex attribution/accounting 聚焦测试，覆盖 source_units candidate token mass 不伪精确。
- required quality gates。
