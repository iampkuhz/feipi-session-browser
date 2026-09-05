# 最小 Agent 运行契约

Claude Code、Codex 与 Qoder 使用客户端已经选择的 checkout。仓库不为普通读取、编辑或提交维护
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
