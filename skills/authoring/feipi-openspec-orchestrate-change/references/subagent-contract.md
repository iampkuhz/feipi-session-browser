# 子 Agent 契约 — 活跃变更继承

子 agent 只执行 main agent 委派的单个 scoped task。

## 核心规则

1. 先读取 `tmp/active_change.json` 和 handoff 指定的当前任务片段。
2. 只修改 `Allowed files/directories`，不得扩大范围或回滚其他 agent 的编辑。
3. handoff 必须包含 Goal、Task id、Task source、Allowed files/directories、Forbidden files/directories、
   Required context files、Expected output、Validation command、Failure policy；同一 agent 的不同实例使用唯一 `agent_id`。
4. 有写入的并行任务必须使用不重叠文件范围；subagent 不修改 active change 注册。
5. 按 handoff 原样运行验证。失败只在允许范围内修复；不可修复或必须越界时返回 `FAIL` 或 `BLOCKED`。
6. 输出只包含 `Status: PASS|FAIL|BLOCKED`、Changed files、Validation、Effect checks、Risks，不贴长日志。
7. required validation 的 failed、warning、skipped、not-run 或 unavailable 均不得描述为 PASS。

8. main 只能聚合同一 `client/session_id` 的证据；subagent 的 PASS 不替代 main 的独立 required checks。
9. 直接使用当前 Agent 原生 `spawn_agent`/`followup_task` 和原生等待/完成事件，不新增 CLI、队列、receipt、
   callback、watchdog 或仓库状态机。模型路由真源为共享 policy 的 `native_delegation`。
10. 重要实现、复杂分析和独立验证用 `gpt-6.1-sol`，轻量定位用 `gpt-6-luna`；遵守宿主 API 模型/上下文限制，
    模型覆盖要求 `fork_turns="none"` 时显式提供必要上下文。保持当前环境权限，受限时如实报告，由 main 接管或调整范围。
11. 旧 Qoder PASS 不可作为原生验收证据；旧 callback 仅识别为已退役，不重新执行旧链。产品 Qoder session 和安全保护保留。
