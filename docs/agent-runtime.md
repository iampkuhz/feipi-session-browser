# Session Runtime 生命周期

本仓库采用客户端或 pre-launch launcher 已经选择的 Git checkout。Codex App/CLI、Claude Code
CLI 与 Qoder 客户端通过薄 Hook adapter 调用同一个 Session service；Runtime 不创建、切换或
删除客户端拥有的 worktree。Claude/Codex 新 linked run 还必须通过 exact primary `HEAD` 起点
校验。

维护入口先读 `scripts/README.md`；事件、身份、writer lease 与 Stop 的模块阅读顺序见
`scripts/agent_runtime/README.md`。本页只维护 Session/worktree 生命周期，不复制 Gate 清单。

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
与 cleanup 的唯一业务入口。`scripts/agent_runtime/events/adapter.py` 只规范化平台 payload；
`.claude/hooks/`、`.codex/hooks/`、`.qoder/hooks/` 只转发 stdin、client/event 与退出码。

## Checkout 与身份

- checkout 事实只来自 Git top-level、common-dir、worktree inventory 与 canonical realpath。
- `repoKey` 来自 Git common-dir；`worktreeId` 来自 `repoKey + checkoutRoot realpath`。
- `primary-checkout` 与 `linked-worktree` 都可直接采用；branch 名、detached 状态、目录名和
  客户端名称不参与写授权。
- SessionStart 是常规 bootstrap；Codex/Qoder PreToolUse、Qoder UserPromptSubmit 是幂等兜底；
  Claude/Qoder CwdChanged 只重确认当前 checkout。

## Worktree 起点

新 Claude/Codex linked worktree 的合法起点是 primary checkout 当前 named branch 的已提交精确
`HEAD`。`origin/HEAD`、远端默认分支、tracking branch 与硬编码 `main` 都不能替代它；primary
detached 或 snapshot 期间 branch/HEAD 改变时必须 BLOCK。primary 的 staged、unstaged 与
untracked 内容不自动复制。

- Claude Code CLI：repository `.claude/settings.json` 固定
  `worktree.baseRef: "head"`，直接在 primary 当前分支运行 `claude --worktree`。
- Codex CLI：当前 CLI 没有原生 managed-worktree 选项。使用：
  `python3 scripts/harness/launch_codex_worktree.py --client codex-cli --name <task> -- <codex-args>`。
  launcher 从一次稳定 snapshot 的精确 SHA 创建仓库外 worktree，再执行 `codex -C <path>`。
- Codex App：原生 Worktree 任务必须在创建界面将 starting branch 选择为 primary 当前分支；仓库
  无法预选该 UI 字段。也可使用
  `python3 scripts/harness/launch_codex_worktree.py --client codex-app --name <task>` 创建精确 checkout
  并在 App 中作为 workspace 打开。

新 Claude/Codex linked run 在 bootstrap 时保存 `worktreeBase.expectedHead/actualHead`。不一致返回
`WORKTREE_BASE_MISMATCH`，要求重新创建任务；hook 不 rebase、reset、切分支或删除 provider
checkout。已登记 run 的 resume 使用 Registry 保存的 `baseCommit`，不会因 primary 后续前进而
误阻断。真实客户端未执行的端到端状态仍为 `UNVERIFIED`。

## Registry 与 Writer Lease

Registry 位于当前用户系统临时目录的 `feipi-agent-runtime/<repo-key>/`，目录权限为 `0700`，
文件权限为 `0600`。bootstrap 只登记 `BOOTSTRAPPED` run，不提前占用 writer lease。

只读 Session 可并行；第一次 Write/Edit/MultiEdit/apply_patch 或 mutating Bash 获取按
`worktreeId` 隔离的 lease。主 checkout writer 为 `LOCAL_WRITER`，linked worktree writer 为
`ISOLATED_WRITER`；同 checkout 的后续 writer 在 mutation 处进入 `READ_ONLY_CONFLICT`，但仍可
读取。lease 使用 epoch、fencing token、heartbeat 和 checkout mutation lock；正常 SessionEnd
精确释放，异常 lease 只能按 holder、epoch、进程身份和 Git 状态受控回收。

subagent 继承主 Session 的 run/worktree/lease，不创建第二份 primary writer lease。启动前的
dirty snapshot 记录路径的 `exists`、`size` 与 `sha256`，不保存文件内容。Stop 只排除当前状态
与 baseline 完全一致的路径；同一路径再次修改后必须进入 changed-files。旧记录没有内容状态时
保守沿用路径排除，不能把无法证明的修改静默归因当前 run。

## Stop、收口与清理

`scripts/harness/stop_entry.py` 仅为公开 wrapper；`scripts/agent_runtime/stop/pipeline.py` 是 identity → lock → evidence → reentry-recovery → gate → report → finalize 的唯一 dispatcher。Gate 阶段只调用 `scripts.gates.cli.run_service`。

Stop 的 changed-files 真相来自 `baseCommit...HEAD`、working tree diff 与 untracked files；Stop
只验证并写 run-scoped evidence，不宣称已集成。finalize 只能执行安全集成，否则输出 handoff。
相同失败触发 circuit `OPEN` 时，Hook/CLI 均以非零 `BLOCKED` 终止；Registry、runtime report、
Stop summary 和 validation receipt 都不得写成 `PASS`。

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

机器可读状态与 Hook surface 真相是 `harness/agent-runtime.manifest.yaml`；Gate catalog、
状态与修改流程见 `scripts/gates/README.md`。Stop/handoff 前唯一 required Gate 命令是：

```bash
python3 scripts/gates/cli.py --tier required
```
