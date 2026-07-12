# Agent Runtime

本目录是 Claude Code、Codex、Qoder 的共享 Runtime 实现。平台目录只保留 shell wrapper 和配置；
事件语义、身份、Registry、writer lease、evidence 与 Stop 都在这里收敛。

机器可读的 Hook surface、Stop 阶段、状态机和存储契约以
`harness/agent-runtime.manifest.yaml` 为准。本页解释阅读与维护顺序，不复制平台 Hook 矩阵。

## 事件链

```text
.claude/.codex/.qoder Hook wrapper
  -> hook_entry.py
  -> context.py + events/adapter.py
  -> identity.py + paths.py
  -> registry.py
  -> events/policy/* 或 events/evidence.py
```

- `events/adapter.py` 只把平台 surface、字段别名和 bootstrap 事件规范为统一请求。
- `hook_entry.py` 是共享事件 dispatcher；它编排 adapter、Registry、策略和 evidence，
  但不执行 Stop 或 Gate executor。
- SessionStart/CwdChanged/UserPromptSubmit/PreToolUse 中被 manifest 声明的事件负责幂等
  bootstrap 或 checkout 重确认；PreWrite/PreBash 负责写授权和 mutation 前证据；
  PostWrite/PostBash/ToolFailure 补齐结果证据；SessionEnd 精确释放当前 run 的 lease。
- Stop wrapper 不经过普通事件策略分支，而是调用公开的 `scripts/harness/stop_entry.py`，
  再进入 `stop/pipeline.py`。

新增平台字段或事件只改 adapter 与对应 contract；不得在三套 wrapper 中复制业务规则。

## Identity、Registry 与 Writer Lease

- `context.py` 读取原始 payload；`identity.py` 解析 `client/sessionId/runId/agentId`；
  `paths.py` 只依据可信身份生成 run-scoped 路径。
- checkout 身份只来自 Git top-level、common-dir、worktree inventory 与 canonical realpath。
  branch 名、目录名、客户端名和 detached 提示不能替代 Git 事实。
- Registry 的位置、权限、原子写和状态转换由 `harness/agent-runtime.manifest.yaml` 定义；
  人工查询通过 `python3 scripts/harness/sessionctl.py status --run-id <run-id>`。
- bootstrap 不预占 writer lease。第一次写操作才获取按 `worktreeId` 隔离的 lease；同一 checkout
  最多一个 writer，只读 run 可以并行。
- subagent 继承父 run/worktree/lease，并用独立 `agentId` 保存 evidence；不得创建第二个主 writer。
- lease heartbeat、epoch、fencing token、stale reclaim 和释放都由 Registry service 处理；
  wrapper 不得自行删除 lock 或 runtime 文件。

## Stop 唯一七阶段

`stop/model.py` 定义 typed `StopContext`，`stop/pipeline.py` 按以下固定顺序推进：

1. **identity**：证明 run、session 与 checkout，初始化 run-scoped 路径。
2. **lock**：获取当前 run 的 Stop lock，并审计受控 stale-owner reclaim。
3. **evidence**：收集 Git、changed-files 与 OpenSpec 证据，计算 required target。
4. **reentry-recovery**：匹配同一身份和 fingerprint 的持久失败及 circuit 状态。
5. **gate**：只调用 `scripts.gates.cli.run_service(..., tier='required')`；不选择 Gate、
   不解析命令、不自行循环 subprocess。
6. **report**：直接消费 typed Gate result，写并校验 runtime report。
7. **finalize**：无条件更新 recovery/Registry、释放 lock、写 Stop summary。

Stop 的公开 wrapper 是 `scripts/harness/stop_entry.py`。人工 required Gate 验证使用
`python3 scripts/gates/cli.py --tier required`，不要直接调用 `stop/pipeline.py`。

## 状态与收口语义

不同层的状态不得互相冒充：

| 状态 | 含义 |
|---|---|
| `PASS` | 本层所有已触发 required 验证完成且证据可校验；运行期间出现 skipped 不得标为 `PASS` |
| `FAIL` / `FAILED` | 已触发检查实际执行并失败；Gate service 使用 `FAIL`，runtime Gate record 使用 `FAILED` |
| `BLOCKED` | 因身份、锁、环境、命令、证据或恢复状态无法完成或证明验证 |

相同失败超过 continuation 上限时 circuit 进入 `OPEN`，Hook 与 CLI 都返回非零
`BLOCKED`（控制台标记 `HANDOFF_BLOCKED`）。熔断只终止自动重入，不能生成 PASS receipt；
Registry、runtime report 与 Stop summary 均保持 `BLOCKED`。
| `HANDOFF_REQUIRED` | Gate/Stop 证据可能已存在，但自动 commit/finalize 无法安全完成；保留 branch/worktree 交给维护者 |

Gate runtime record 另有 `EXECUTED`、`REUSED`、`NOT_TRIGGERED`、`FAILED`、`BLOCKED`。
`NOT_TRIGGERED` 表示规划未选择该 Gate，不等于 `SKIPPED`，也不能作为该 Gate 的执行 `PASS` 证据。
Registry 全部状态与合法转换只从 `harness/agent-runtime.manifest.yaml` 读取；文档不维护副本。

受控收口使用：

```bash
python3 scripts/harness/complete_change.py \
  --run-id <run-id> \
  --message '<commit-message>' \
  --file <exact-path>
```

该命令固定执行 Stop、精确 stage/commit、二次 Stop 和 `sessionctl finalize`。任一步无法安全完成
时返回 `HANDOFF_REQUIRED` 或 `BLOCKED`，不得 stash、reset、force、自动 push 或删除 provider checkout。
