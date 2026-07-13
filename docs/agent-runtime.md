# Agent Runtime 生命周期

本文是 Claude Code、Codex 与 Qoder 在本仓库中的唯一人类 Runtime 说明。事件 binding、
状态、存储字段与 Stop 阶段以 `harness/agent-runtime.manifest.yaml` 为机器真相；Gate 清单以
`config/gates.yaml` 为真相，本文不复制矩阵或状态表。

## 生产链路

```text
平台 settings/config --client/--event
→ scripts/harness/hook_dispatch.py
→ scripts/agent_runtime/hook_entry.py
→ scripts/agent_runtime/session/* 与 events/*
→ Stop: scripts/harness/stop_entry.py
→ scripts/agent_runtime/stop/pipeline.py
→ scripts.gates.cli.run_service
```

共享 dispatcher 只校验可信 Git root、选择项目 Python、保留 stdin/CWD/退出码并转发；
策略、evidence、Session 状态和 Gate 业务不在平台配置或 dispatcher 中实现。
`scripts/harness/sessionctl.py` 只是稳定 CLI adapter，Registry、lease、lifecycle 与 finalize
业务位于 `scripts/agent_runtime/session/`。

## Checkout、身份与写租约

- Runtime 采用客户端或 pre-launch launcher 已选的 checkout，不创建、切换或删除
  provider-owned worktree。
- checkout 身份只来自 Git top-level、common-dir、worktree inventory 与 canonical realpath；
  branch 名、目录名、客户端名或 detached 提示不能替代 Git 事实。
- 新 Claude/Codex linked run 必须来自 primary 当前 named branch 的精确已提交 `HEAD`；
  `origin/HEAD`、remote default、tracking branch 与硬编码 `main` 都不是替代来源。
- bootstrap 只登记 run。第一次 mutating tool 获取按 `worktreeId` 隔离的 writer lease；同一
  checkout 最多一个 writer，只读 run 可并行。
- subagent 继承父 run/worktree/lease，以独立 `agentId` 保存 evidence，不创建第二个 writer。
- Registry 与 lock 位于系统临时 Runtime root，目录/文件保持私有权限；回收必须验证 holder、
  epoch、进程身份与 Git 状态。

## Stop 与受控收口

Stop 从 Git range、working-tree diff、untracked files 与 run evidence 计算 changed files，
按 manifest 声明的七阶段执行。Gate 阶段只调用统一 service；运行期间出现 skipped、证据
不可验证、身份/锁冲突或环境缺失时不得生成 PASS。

默认安全收口由 `scripts/harness/complete_change.py` 完成：第一次 Stop PASS 后只提交显式文件，
commit 改变 HEAD 后重新 Stop，第二次 PASS 才执行本地 finalize。initial/primary dirty、额外
文件、detached、冲突或 Gate 失败时保留 branch/worktree 并 handoff；禁止 stash、reset、force、
auto-push 或删除 provider checkout。

## 维护入口

- Runtime 模块入口：`scripts/agent_runtime/README.md`
- 公开命令索引：`scripts/README.md`
- Runtime 机器契约：`harness/agent-runtime.manifest.yaml`
- 公共入口 registry：`harness/manifest.yaml`
- Gate 行为与修改流程：`scripts/gates/README.md`

常用只读诊断为 `python3 scripts/harness/sessionctl.py status|doctor --run-id <run-id>`；受控收口
使用 `python3 scripts/harness/complete_change.py --run-id <run-id> --message <message> --file <path>`。
真实客户端生命周期未执行时必须继续按 manifest 标记 `UNVERIFIED`，不得用 repository fixture
parity 替代平台 E2E 证据。
