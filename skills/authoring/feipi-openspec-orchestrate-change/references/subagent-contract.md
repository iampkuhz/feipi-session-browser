# 子 Agent 契约 — 活跃变更继承

子 agent 只执行 main agent 委派的单个 scoped task。

## 核心规则

1. 先读取 `tmp/active_change.json` 和 handoff 指定的当前任务片段。
2. 只修改 `Allowed files/directories`，不得扩大范围或回滚其他 agent 的编辑。
3. handoff 至少包含 Goal、Task id、Task source、Allowed/Forbidden files、Required context、Expected output、
   Validation command 和 Failure policy；同一 agent 的不同实例使用唯一 `agent_id`。
4. 有写入的并行任务必须使用不重叠文件范围；subagent 不修改 active change 注册。
5. 按 handoff 原样运行验证。失败只在允许范围内修复；不可修复或必须越界时返回 `FAIL` 或 `BLOCKED`。
6. 输出只包含 `Status: PASS|FAIL|BLOCKED`、Changed files、Validation、Effect checks、Risks，不贴长日志。
7. required validation 的 failed、warning、skipped、not-run 或 unavailable 均不得描述为 PASS。
