# 最小 Agent 运行契约

Claude Code 与 Codex 使用客户端已经选择的 checkout。仓库不为普通读取、编辑或提交维护
Session 状态，也不要求平台事件先完成初始化。机器契约见
`harness/agent-runtime.manifest.yaml`；Gate 机器真相集中在 `scripts/gates/catalog/`，人类手册位于
[`docs/gates/gate-control-plane.md`](../docs/gates/gate-control-plane.md)。自动增量规划由 changed path 直接匹配每个 Gate
的 Trigger；TargetPreset 只是人工选择的 Gate 分组，不参与自动规划。

## 生命周期与 Git 边界

- Session 的启动、恢复和结束由客户端负责；仓库配置不绑定平台事件矩阵。
- Agent 在当前 checkout 和当前分支中工作，不因仓库侧运行状态缺失而创建额外 worktree 或阻断写入。
- commit 是完成验证后的显式 Git 操作，只作用于当前分支和精确文件范围。
- 合并、发布及 primary 分支前进必须由用户后续明确选择；禁止 stash、reset、rebase、force 和未授权 push。
- 不读取或提交真实 session、密钥、token、缓存、运行数据或个人配置。

## OpenSpec 与策略

非平凡产品、agent、harness、gate、hook 或跨模块变更先创建或复用
`openspec/changes/<change-id>/`，再按 `tasks.md` 推进。OpenSpec 是规划和长期规格流程，不是每次文件
写入的状态令牌。普通定位和单文件小改只读取必要上下文。

策略约束来自 `AGENTS.md`、`.claude/CLAUDE.md`、`harness/agent-policy.manifest.yaml` 和共享 skills。平台配置只保留
入口、agent 发现和静态安全限制，不承担仓库状态协调。

## 原生 subagent 委派

工程任务直接使用当前 Agent 的原生 subagents；共享真源是
`harness/agent-policy.manifest.yaml` 的 `native_delegation` 与 `subagent_instance_protocol`。
不新增 CLI、调度器、队列、receipt、callback、watchdog、ack 或仓库任务状态机。

- main 拆分单一可验收目标，显式提供九项 handoff、唯一 Task id/agent_id 与当前 client/session_id；
  完整字段见共享 [subagent contract](../skills/authoring/feipi-openspec-orchestrate-change/references/subagent-contract.md)。
- 重要实现、复杂分析及独立验证使用 `gpt-6.1-sol`，轻量定位使用 `gpt-6-luna`。
  按宿主 API 选择角色和模型；模型覆盖要求 `fork_turns="none"` 时显式传入必要上下文，不固定所有角色模型。
- 直接调用原生 `spawn_agent`/`followup_task`，通过原生等待/完成事件接收结果，不维护另一套生命周期。
- 修改型并行任务必须使用互斥写范围；共享资源验证与集成串行，不回滚其他工作者的修改。
- 返回 Status、Changed files、Validation、Effect checks、Risks；状态为 PASS、FAIL 或 BLOCKED。
  main 仅聚合同一 client/session_id 的证据，处理 FAIL/BLOCKED，并独立运行 required checks。
- 保持当前环境权限，不因失败升级权限；原生能力不可用或模型受限时如实说明，由 main 接管或调整范围。

Qoder 工程派发已退役：旧 Qoder PASS 不能充当原生验收证据；旧 callback 到来仅识别为已退役，
不恢复或重新执行旧链。产品 Qoder session 的发现、解析、展示及导出仍受支持；通用安全保护不删除。
仅删除 tracked 工程入口，`/.qoder/` 个人配置和运行数据保持 ignored，不递归清理目录。

## 显式验证

维护者在提交或交接前显式运行：

```bash
python3 scripts/gates/cli.py run --mode incremental
```

若锁定依赖环境是当前变更的既定要求，可从仓库根使用 `UV_PROJECT_ENVIRONMENT="$PWD/.local/python/venv" uv run --project scripts --frozen --extra dev python ...` 入口。已经触发的
本次选中的检查必须成功；`BLOCKED` 表示检查完成并发现阻断问题，`FAIL` 表示 Gate 未能完成，二者均不得
描述为 PASS。`NOT_TRIGGERED` 仅表示自动增量规划没有选择该 Gate，不是执行结果。

完成报告应列出精确 changed files、验证命令与结果、当前分支 commit（如有）和剩余风险。仓库不会在
任务结束时改变 Git index、HEAD 或其他 checkout。
