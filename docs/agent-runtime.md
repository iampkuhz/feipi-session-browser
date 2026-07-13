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
- `begin-change` 在 mutation 前保存 repo/worktree/client/session/run、base/target、初始 dirty
  snapshot、allowed/forbidden paths 和 activation evidence。Launcher 在 Agent 前调用；
  SessionStart 幂等调用；mutation guard 二次确认。Codex App host lifecycle 尚无真实证明，
  必须显示 `START_NOT_ENFORCED`，不能进入强归因自动收口。
- late dirty 默认拒绝；只有显式 `adopt-current` 携带 base、exact manifest 与用户确认时，
  才能在同一 run 保存审计并恢复，不得复制到 recovery worktree。
- subagent 继承父 run/worktree/lease，以独立 `agentId` 保存 evidence，不创建第二个 writer。
- Registry 与 lock 位于系统临时 Runtime root，目录/文件保持私有权限；回收必须验证 holder、
  epoch、进程身份与 Git 状态。

## Stop 与受控收口

Stop 从 Git range、working-tree diff、untracked files 与 run evidence 计算 changed files，
按 manifest 声明的七阶段执行。Gate 阶段只调用统一 service；运行期间出现 skipped、证据
不可验证、身份/锁冲突或环境缺失时不得生成 PASS。

默认安全收口由 `scripts/harness/complete_change.py` 完成：cheap preflight → exact stage →
pre-commit 稳定 → `candidateTree` → 一次 required Stop/Gate → worktree commit → commit
attestation → integration。attestation 只检查 tree、parent、exact paths、clean、result ref 和
内容型 receipt，commit 后重 Gate进程数为 0。

完成状态唯一为 `WORKING / STAGED / VALIDATED_CANDIDATE / COMMITTED / INTEGRATED /
BLOCKED_RETRYABLE / HANDOFF_REQUIRED`，并持久化 `oldHead`、`exactFilesHash`、
`candidateTree`、`validationReceipt`、`commitSha`、`resultRef`、`targetHeadObserved`。
detached checkout 可提交并创建 `refs/heads/codex/result/<run-id>`；primary dirty/前进只影响
integration。能力故障在同一 run retry；冲突保留 commit/ref。禁止 stash、reset、force、
auto-push 或删除 provider checkout。

## 维护入口

- Runtime 模块入口：`scripts/agent_runtime/README.md`
- 公开命令索引：`scripts/README.md`
- Runtime 机器契约：`harness/agent-runtime.manifest.yaml`
- 公共入口 registry：`harness/manifest.yaml`
- Gate 行为与修改流程：`scripts/gates/README.md`

常用只读诊断为 `python3 scripts/harness/sessionctl.py status|doctor --run-id <run-id>`；受控收口
使用 `python3 scripts/harness/complete_change.py --run-id <run-id> --message <message> --file <path>`。
正常 Stop/SessionEnd 或 launcher 退出时如存在 task-owned changes 但没有 attested `commitSha`，
必须返回 `COMMIT_REQUIRED`，不能返回 PASS。真实 Codex App lifecycle 未执行时必须标记
`START_NOT_ENFORCED`，不得用 repository fixture parity 替代平台 E2E 证据。
