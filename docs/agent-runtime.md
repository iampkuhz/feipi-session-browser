# Agent Runtime 生命周期

本文是 Claude Code、Codex 与 Qoder 在本仓库中的人类 Runtime 说明。机器契约见
`harness/agent-runtime.manifest.yaml`；Gate 清单仍只以 `config/gates.yaml` 为真相。

## 唯一生产链路

```text
平台 settings/config --client/--event
→ scripts/harness/hook_dispatch.py
→ scripts/agent_runtime/hook_entry.py
→ scripts/agent_runtime/change/controller.py
→ scripts.gates.cli.run_service
```

`scripts/harness/change.py` 是 canonical CLI。`scripts/harness/complete_change.py`、
`scripts/harness/stop_entry.py`、`scripts/agent_runtime/stop/pipeline.py` 和
`scripts/agent_runtime/session/finalize.py` 只保留参数或 payload 兼容，不拥有 candidate、Gate、
commit 或 integration 业务。

## Session、Change、Attempt

- Session 绑定 client、repo/common-dir、physical worktree、target branch 与 primary checkout，可顺序
  包含多个 Change。
- 每个用户任务对应单调递增的 `changeEpoch`。`INTEGRATED` 且 checkout clean 后，下一次 Prompt/
  PreTool 或显式 `next-change` 会在同一 Session 创建新 Change；`REPAIR_REQUIRED` 继续原 Change。
- 每个 candidate/environment/plan/command 完整指纹只允许一个 Attempt。PASS、FAIL、BLOCKED、
  timeout 和 crash 都先登记后启动重 Gate child，实际执行次数不会只统计成功结果。
- Change 状态为 `WORKING → PREPARED → VALIDATING → REPAIR_REQUIRED|VALIDATED → COMMITTED →
  COMMITTED_HANDOFF|INTEGRATED`。`TERMINAL_BLOCKED` 只用于身份、归因、损坏或安全不变量。
- 状态写入必须同时校验 state、stateVersion、candidateTree 和 attemptId；bounded lock 内先追加
  audit/journal，再原子发布 snapshot。commit/ref 证据只能单调增加。

## Start、归因与 writer

受控 launcher 在启动 agent 前调用 `ensure-session`；三平台 SessionStart/Prompt/PreTool 进入同一
入口；Stop 也会幂等自愈 clean checkout 的缺失 Start。primary checkout、身份不成立或 late dirty
无法归因时在 mutation 前 fail closed。只有显式 `adopt-current` 携带 base、exact manifest 与用户
确认，才可接管 pre-existing dirty 内容。

Registry 与 Change store 都位于 ignored、owner-private runtime root。锁等待默认 2 秒，活 owner
返回 `BUSY_RETRYABLE`，dead owner 回收要验证 PID start identity 与 epoch。subagent 继承父
run/worktree/lease，不创建第二个 writer。

## Candidate、Gate 与 fixture

controller 从 staged、unstaged、untracked 的 NUL-safe Git 集合自动生成 exact manifest，在任何
index mutation 前校验 allowed/forbidden scope。staged deletion、unstaged deletion、同路径
staged+unstaged 与 untracked 都由同一 exact-stage 路径处理；调用方不再手拼 `--file`。

可能修改文件的 formatter/pre-commit 最多运行两轮：只修改归属路径时自动 restage；第二轮仍不
稳定或触及范围外路径则 `REPAIR_REQUIRED`。稳定 tree 绑定 Attempt 完整指纹。相同 PASS receipt
直接复用；相同 FAIL/BLOCKED 在 1 秒内返回缓存根因且重 Gate child 为 0。

所有 controller child 经过 `change/runtime.py`：显式 timeout、新 process group、超时回收进程树、
run-scoped log、有界 tail，以及移除 `CODEX_*`、`CLAUDE_*`、`QODER_*` 的净化环境。cheap
preflight 不启动 fixture、不构建 distribution。需要浏览器 fixture 时由 controller supervisor
管理单一 identity endpoint、PID/start/group/log，并在 15 秒内 ready 或结构化失败。

## Commit 与 ff-only integration

Gate PASS 后，同一 writer lease 内先持久化 commit intent，再执行正常 `git commit`。controller
校验 parent、candidate tree、exact paths、clean checkout、PASS Attempt 和 durable
`refs/heads/codex/result/<change-id>`。若进程在 commit/ref/primary ff 后崩溃，resume 从 Git 与
journal 恢复同一事实，不重复 commit 或 Gate。

自动 integration 仅在 primary clean、位于目标 branch、primary HEAD 等于 attested parent、source
commit/tree/ref/receipt 仍匹配时执行一次 `git merge --ff-only`。否则保留 commit/ref 并返回
`COMMITTED_HANDOFF`；禁止 rebase、cherry-pick、integration worktree、stash、reset、force 或
自动 push。

## 机器协议与维护入口

默认 stdout 是不超过 4 KiB 的单个 JSON 对象，只包含 status/state/code、Session/Change/Attempt、
candidate/commit/integration、首个独立根因、dependent count、metrics 和 artifact path。完整
Git/Gate/environment 事实只写 run-scoped artifact。失败、BLOCKED、未运行或 skipped 均不得称
PASS。

```bash
python3 scripts/harness/change.py --repo-root <checkout> ensure-session --run-id <run-id>
python3 scripts/harness/change.py --repo-root <checkout> status --run-id <run-id> --compact
python3 scripts/harness/change.py --repo-root <checkout> on-stop --run-id <run-id> --message '<message>'
python3 scripts/harness/change.py --repo-root <checkout> resume --run-id <run-id> --message '<message>'
python3 scripts/harness/change.py --repo-root <checkout> next-change --run-id <run-id> --task-key <key>
```

Stop/handoff 前唯一 required Gate 入口仍是 `python3 scripts/gates/cli.py --tier required`；正常
平台 Stop 直接调用 controller，不依赖模型记住该命令。
