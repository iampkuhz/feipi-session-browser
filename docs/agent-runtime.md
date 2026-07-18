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

`scripts/harness/change.py` 是唯一公开 Change lifecycle CLI；业务 owner 只有
`scripts/agent_runtime/change/controller.py`。平台 Stop 不经过额外 wrapper，dispatcher 规范化
payload 后直接进入 `hook_entry.py`，再由 controller 处理 candidate、Gate、commit 与 integration。
旧 Completion/Stop 入口和 `sessionctl` 的 completion 命令已下线，不提供静默 alias。

Codex 配置只声明 `SessionStart`、`UserPromptSubmit`、`PreToolUse`、`PostToolUse` 与 `Stop`。
每个事件只有一个 matcher group：`pre-tool`/`post-tool` 在同一 Runtime 进程中按 tool name 顺序
复用 Bash 或写入 handler，未知工具只观察 lifecycle/evidence/lease。Claude、Qoder 的 legacy event
label 继续调用相同 handler，不形成第二条平台链路。

## Session、Change、Attempt

- Session 绑定 client、repo/common-dir、physical worktree、target branch 与 primary checkout，可顺序
  包含多个 Change。
- 每个用户 turn 对应单调递增的 `changeEpoch`。`SessionStart` 只建立 run；`UserPromptSubmit` 建立
  Change，缺失时首个 `PreToolUse` 可幂等 fallback。同 turn 的 Pre/Post Tool 复用当前 Change。
  `INTEGRATED` 或带 `NO_CHANGES` terminal Stop receipt 且 checkout clean 后，下一 turn 会在同一
  Session 创建新 Change；`REPAIR_REQUIRED` 继续原 Change。
- 每个 candidate/environment/plan/command 完整指纹只允许一个 Attempt。PASS、FAIL、BLOCKED、
  timeout 和 crash 都先登记后启动重 Gate child，实际执行次数不会只统计成功结果。
- Change 状态为 `WORKING → PREPARED → VALIDATING → REPAIR_REQUIRED|VALIDATED → COMMITTED →
  COMMITTED_HANDOFF|INTEGRATED`。`TERMINAL_BLOCKED` 只用于身份、归因、损坏或安全不变量。
- 状态写入必须同时校验 state、stateVersion、candidateTree 和 attemptId；bounded lock 内先追加
  audit/journal，再原子发布 snapshot。commit/ref 证据只能单调增加。
- read-only turn 的 Stop 将 `NO_CHANGES` receipt 单调写入当前 Change；重复 Stop 不运行 Gate、不提交、
  不集成，下一 turn 的新 Change 不继承 candidate、Attempt、receipt、commit 或 integration 证据。

## Start、归因与 writer

受控 launcher 在启动 agent 前调用 `ensure-session`；三平台 SessionStart/Prompt/PreTool 进入同一
入口；Stop 也会幂等自愈 clean checkout 的缺失 Start。primary checkout、身份不成立或 late dirty
无法归因时在 mutation 前 fail closed。只有显式 `change.py adopt-current` 携带 base、NUL-safe
exact manifest 与用户确认，并通过 allowed/forbidden path 校验，才可接管 pre-existing dirty 内容。

Registry 与 Change store 都位于 ignored、owner-private runtime root。锁等待默认 2 秒，活 owner
返回 `BUSY_RETRYABLE`，dead owner 回收要验证 PID start identity 与 epoch。subagent 继承父
run/worktree/lease，不创建第二个 writer。

dispatcher 自身保持标准库可启动，只选择 Python `>=3.12,<3.13` 且 runtime dependency ready 的
解释器。显式 `SESSION_BROWSER_PYTHON` 不可用时不 fallback；worktree `.local/python/venv` 优先于系统 Python。
未就绪时返回 `BLOCKED_PROJECT_PYTHON_NOT_READY` 与官方入口
`./scripts/session-browser.sh deps --dev`，Hook 内不安装依赖。
最早期 `ENTERED/PYTHON_NOT_READY/DISPATCHED/FAILED` trace 只保存摘要，位于系统临时目录的
`feipi-agent-runtime/<repo-key>/hook-bootstrap/`，原子、有界且不记录 prompt、命令、token 或环境正文。

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

`status --compact`、`ensure-session`、`on-stop`、`resume` 和 launcher 收口在返回 terminal PASS 前
都重新读取 worktree HEAD、index/working/untracked、result ref/candidate tree、primary target HEAD
以及当前 Session 的 active Change。若历史 `INTEGRATED` 后出现可归因的新 mutation，历史 Change
保持不变，同一 Session 自动建立以上一 commit 为 base 的新 epoch；当前状态不得复述旧 PASS。
HEAD/ref/tree 或 integration 真相失配时 fail closed。只读 reconciliation 不运行 Gate，下一次
`on-stop` 必须为新 epoch 形成独立 Attempt 和 receipt。

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
python3 scripts/harness/change.py --repo-root <checkout> adopt-current --run-id <run-id> ...
python3 scripts/harness/change.py --repo-root <checkout> abort --run-id <run-id>
```

`scripts/harness/sessionctl.py` 只管理 legacy run identity/Registry，例如 bootstrap、set-change、writer
lease、list/status/doctor/cleanup；`begin-change`、`adopt-current`、`completion-status`、`stop`、
`finalize`、`handoff` 不再属于其公开命令面。Codex App 的仓库内 fixture 只证明本地 dispatcher
contract；真实 host Hook capability 在没有主机证据时仍是 `UNVERIFIED`。

当前 Session 的有界只读查询使用：

```bash
uv run --frozen python scripts/harness/sessionctl.py \
  --repo-root . current --client codex --session-id "$CODEX_THREAD_ID" --json
```

它只按 `client + sessionId + checkoutRoot` 返回唯一 run 摘要，不展开历史 `auditEvents`，也不获取
Registry 写锁、bootstrap、lease 或修改 Change；零匹配、多匹配、未 attested 使用不同错误码和退出码。

Stop/handoff 前唯一 required Gate 入口仍是 `python3 scripts/gates/cli.py --tier required`；正常
平台 Stop 直接调用 controller，不依赖模型记住该命令。
