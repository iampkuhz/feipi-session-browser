# Session Runtime 生命周期

本仓库只采用客户端已经选择的 Git checkout。Codex App/CLI、Claude Code CLI、Qoder
CLI 与 Qoder 客户端通过薄 Hook adapter 调用同一个 Session service；Runtime 不创建、切换或
删除客户端拥有的 worktree。

## 唯一流程

```text
客户端启动并确定 checkout
→ Hook bootstrap/adopt
→ 首次 mutation 获取 checkout writer lease
→ Stop validate
→ 精确 commit
→ commit 后重新 Stop validate
→ finalize/integrate 或 handoff
→ SessionEnd release
```

`scripts/harness/sessionctl.py` 是 Registry、bootstrap、writer lease、Stop、finalize、handoff
与 cleanup 的唯一业务入口。`scripts/claude_hooks/adapter.py` 只规范化平台 payload；
`.claude/hooks/`、`.codex/hooks/`、`.qoder/hooks/` 只转发 stdin、client/event 与退出码。

## Checkout 与身份

- checkout 事实只来自 Git top-level、common-dir、worktree inventory 与 canonical realpath。
- `repoKey` 来自 Git common-dir；`worktreeId` 来自 `repoKey + checkoutRoot realpath`。
- `primary-checkout` 与 `linked-worktree` 都可直接采用；branch 名、detached 状态、目录名和
  客户端名称不参与写授权。
- SessionStart 是常规 bootstrap；Codex/Qoder PreToolUse、Qoder UserPromptSubmit 是幂等兜底；
  Claude/Qoder CwdChanged 只重确认当前 checkout。

## Registry 与 Writer Lease

Registry 位于当前用户系统临时目录的 `feipi-agent-runtime/<repo-key>/`，目录权限为 `0700`，
文件权限为 `0600`。bootstrap 只登记 `BOOTSTRAPPED` run，不提前占用 writer lease。

只读 Session 可并行；第一次 Write/Edit/MultiEdit/apply_patch 或 mutating Bash 获取按
`worktreeId` 隔离的 lease。主 checkout writer 为 `LOCAL_WRITER`，linked worktree writer 为
`ISOLATED_WRITER`；同 checkout 的后续 writer 在 mutation 处进入 `READ_ONLY_CONFLICT`，但仍可
读取。lease 使用 epoch、fencing token、heartbeat 和 checkout mutation lock；正常 SessionEnd
精确释放，异常 lease 只能按 holder、epoch、进程身份和 Git 状态受控回收。

subagent 继承主 Session 的 run/worktree/lease，不创建第二份 primary writer lease。启动前的
dirty snapshot 只作为 baseline，无法区分归因时必须 handoff。

## Stop、收口与清理

Stop 的 changed-files 真相来自 `baseCommit...HEAD`、working tree diff 与 untracked files；Stop
只验证并写 run-scoped evidence，不宣称已集成。finalize 只能执行安全集成，否则输出 handoff。

用户没有明确要求保留未提交状态时，named linked-worktree 使用 `complete_change.py` 自动收口：
第一次 Stop PASS 后只提交显式文件清单；commit 改变 HEAD/fingerprint 后重新 Stop；第二次 PASS
才调用 finalize。initial/primary dirty、额外 diff、预存 staged、detached、冲突或任一门禁失败时保留
临时分支并 handoff，不询问是否强制合并。

cleanup/release 只处理指定 run 的 lease、Registry/evidence；客户端拥有的 checkout 始终保留。
Runtime 不自动 push，不 force，不广域删除运行数据。

常用只读诊断与收口命令：

```bash
python3 scripts/harness/sessionctl.py status --run-id <run-id>
python3 scripts/harness/sessionctl.py doctor --run-id <run-id>
python3 scripts/harness/sessionctl.py handoff --run-id <run-id>
python3 scripts/harness/complete_change.py --run-id <run-id> --message '<message>' --file <path>
python3 scripts/harness/sessionctl.py finalize --run-id <run-id>
python3 scripts/harness/sessionctl.py cleanup --run-id <run-id>
```

机器可读真相是 `harness/agent-runtime.manifest.yaml`；完整 required quality gate 入口是
`python3 scripts/quality/run_required_quality_gates.py`。
