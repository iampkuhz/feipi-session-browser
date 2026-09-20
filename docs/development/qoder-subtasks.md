# Qoder CLI 子任务使用指南

## 概述

`scripts/harness/qoder_task.py` 提供 Qoder CLI 子任务的显式委派入口。主线程（如 Codex）仅负责交代任务和复核结果，不 busy wait。

**重要说明**：
- Codex 子任务完成后通过 `codex queue` 向精确父会话排入复核消息；需要可用的 Codex CLI 与本地服务
- 主会话收到完成消息后读取结果并独立复核，无需循环查询；回调故障时可人工读取结果
- 权限不足时任务会 BLOCKED，脚本按用户明确授权默认使用 `bypass_permissions`；仍可能受 OS 权限限制
- **这些是提示约束而非 OS 沙箱**：脚本通过 prompt 指导 Qoder 行为，但不提供真正的隔离
- **不要发送密钥、真实 session 数据或个人配置**：任务 JSON 会被记录到 tmp/qoder-tasks/
- **本机 qodercli 1.1.44 的环境问题（如 agent 配置加载提示、Bash 拒绝）不会被此脚本修复**

## 默认实现归属

当 Codex 担任主调度时，以下修改类型默认派发给 Qoder 实现：

- **默认范围**：功能实现、修复、重构、测试、脚本、配置、文档。
- **例外（Codex 自行处理）**：极小修改、设计决策、Qoder 不可用、权限不足、两轮返工仍不收敛。Codex 接管时须说明理由。
- **任务粒度**：单一可验收目标，实现与关联测试一起交付；跨模块先定边界再拆分；只读查询按同一主题批处理。
- **返工上限**：最多 2 轮返工；两轮后仍不收敛由 Codex 接管。
- **可见派发**：派发前公开 task id、目标/来源、读写与禁止范围、上下文、验收条件、权限模式、失败策略和版本变化；派发后记录 run id 与结果路径。
- **单任务调度**：Qoder 同时最多运行 1 个任务，其余任务由主调度排队；确认前一个已结束才启动下一个，运行状态不明时不补开。即使短时间可容纳两个任务，也不默认使用重叠运行，不通过另开 session 绕过限制。
- **并行约束**：只允许 Codex 与单个 Qoder 做独立工作，避开写写、读写、接口变更和运行输出冲突；集成验证串行。没有独立工作时结束 Codex 回合，不循环查询；已绑定 Codex 父会话的任务由完成回调请求接续。
- **身份与归属**：保留各 client/session 来源；Codex 独立复核和产出验收证据；Qoder 不得递归委派给自身。
- **当前能力边界**：提供 Codex 完成回调；无自动重发、无取消、无 OS 沙箱；`start`/`resume` 通过当前用户的 `qodercli` 进程快照做跨 checkout 预检查，发现占用返回含 PID 的 `BUSY`，检查失败则拒绝启动。跨任务调度层仍是“无锁、无自动队列”；新增 per-run 锁仅保护消费/恢复状态，进程预检仍接受检查到启动之间的极小并发窗口。不因失败自动扩大权限、不降低 Gate。

详细共享规则见 `harness/agent-policy.manifest.yaml` 的 `qoder_delegation` 段。

### 用户可见任务卡（首次派发与返工均适用）

- **派发前**：在用户可见的进度消息中展示任务标题、task id、目标、范围、权限和验收；不得仅放在命令参数、工具输出或内部推理中。
- **派发后**：从本次 run 的 `task.json` 读取真实身份，展示 Qoder session id、run id 和结果目录；`resume` 须注明“复用 session，新建 run”及返工轮次。
- **最终回复**：只要本回合执行过 `start` / `resume`，必须保留下面的格式化详情，不得只写“已派发，等待回调”。这是 Markdown 展示约定，不是 Codex 原生任务卡或展开工具记录的替代名称。
- **结果复核回复**：展示所复核 run 的同类详情，并分别说明运行、回调和验收状态；`finished / exit 0`、`queued` 均不能替代验收 PASS。
- **准确性**：标题/身份来自本次持久化记录，不凭历史猜测；尚未生成的字段写“未生成”，无法确认的状态写“未知”。结果目录使用绝对路径 Markdown 链接；不复制原始日志、完整 prompt 或个人配置。
- **派发失败**：如 `BUSY` 或命令失败，明确写“未派发”，不得沿用上一 run 冒充新任务。不要为补任务卡重新派发或轮询已有任务。

最终回复模板（字段替换为已核实的真实值）：

#### Qoder 任务详情

| 字段 | 内容 |
|---|---|
| 任务 | 中文标题 · `task_id` |
| 派发方式 | 首次派发 / 返工第 N 轮（复用 session，新建 run） |
| Qoder session | `session_id` |
| 本次 run | `run_id` |
| 父任务 | `parent_client` · `parent_session_id` |
| 目标与范围 | 一句话目标；精确写范围摘要 |
| 验收 | 本轮需要证明的行为与检查；未运行项明确待复核 |
| 权限 | 实际 `permission_mode` |
| 状态 | 运行：已派发/已结束/未知；回调：未确认/queued/failed；验收：待复核/PASS/FAIL/BLOCKED |
| 结果 | [结果目录](绝对结果目录路径) |

## 命令

### 轻量预检查与任务命名

- 同机同用户的标准 `qodercli` 进程共享检查范围，不受 checkout、worktree 或 `QODER_TASK_DIR` 影响；GUI Qoder 不算 CLI 任务。
- 仅读取 PID/程序名，不读取其他任务的 prompt 或命令参数。不查询历史状态、不写共享运行登记、不自动停止进程。
- `BUSY` 时由调用方稍后重试，不自动排队。进程退出后即可通过下一次检查；极端同时启动不保证互斥。改名 CLI 或解释器包装可能无法识别；所有正常委派仍应走脚本入口。
- 建议 `title: "修复会话详情摘要与完整输入输出"`，`task_id: "fix-session-detail-summary-and-payload"`。`title` 是可选非空中文展示名，写入 prompt 和完成记录；`task_id` 保持 ASCII 稳定标识，日期/轮次不必堆叠；执行实例由 `run_id` UUID 区分。
- 不修改正在运行任务的 ID 或标题；新任务采用可读命名。

### start — 启动子任务

```bash
python scripts/harness/qoder_task.py start --task task.json
```

输入 JSON 必须包含完整九项 handoff：

| 字段 | 说明 |
|------|------|
| goal | 任务目标 |
| task_id | 唯一任务标识 |
| task_source | 任务来源 |
| allowed_files | 允许写入的路径 |
| forbidden_files | 禁止写入的路径 |
| required_context | 需要读取的上下文文件 |
| expected_output | 期望输出 |
| validation_command | 验证命令 |
| failure_policy | 失败策略 |

可选字段：`agent_id`（自动生成）、`session_id`（自动生成 UUID）、`parent_client`、`parent_session_id`、`permission_mode`（枚举：`default`/`accept_edits`/`dont_ask`/`bypass_permissions`）。**`client` 强制为 `qoder`，不可覆盖**。

**示例 task.json**（只读总结 AGENTS.md，不修改脚本；parent_session_id 使用占位符）：
```json
{
  "goal": "只读总结 AGENTS.md 的首要护栏、任务分流、受保护路径、验证原则、提交与集成、上下文治理六节，输出精简中文索引",
  "task_id": "agents_summary_001",
  "task_source": "Codex 复核请求",
  "allowed_files": "docs/development/agents-summary.md",
  "forbidden_files": "scripts/*, openspec/*, .claude/*, .codex/*, .qoder/*",
  "required_context": "AGENTS.md, .qoder/AGENTS.md",
  "expected_output": "docs/development/agents-summary.md 含六节中文索引",
  "validation_command": "test -f docs/development/agents-summary.md",
  "failure_policy": "report BLOCKED",
  "agent_id": "agent_summary_001",
  "client": "qoder",
  "parent_client": "codex",
  "parent_session_id": "00000000-0000-4000-8000-000000000001"
}
```

启动后立即返回唯一 run_id（UUID 格式）。Worker 进程在后台阻塞等待 qodercli 退出，先原子写入完成记录，再向已绑定 Codex 父会话排入复核消息。

### status — 查询状态

```bash
python scripts/harness/qoder_task.py status <run_id>
```

输出 JSON：
- 运行中：`{"run_id": "...", "status": "running", "pid": 12345}`
- 已完成：`{"run_id": "...", "status": "finished"}` 或 `{"status": "failed"}`
- 未知：非零退出（run_id 不存在）
- Worker 死亡且无完成记录：`{"status": "unknown"}`

### result — 获取结果

```bash
python scripts/harness/qoder_task.py result <run_id>
```

输出完成记录 JSON，包含：
- `status`: `finished`（exit 0）或 `failed`（非零）
- `exit_code`: CLI 退出码
- `session_id`: Qoder session UUID
- `task_id`, `agent_id`, `client`, `parent_client`, `parent_session_id`
- `task_file`, `stdout_log`, `stderr_log`: 报告/日志路径
- `stdout_tail`: stdout.log 最后 4000 字节（有限结果正文，避免读取长日志）

若尚未完成，返回 `{"status": "not_ready"}`。

**注意**：退出 0 仅说明进程结束，不自动等价于质量验收 PASS。主线程须独立复核报告。

### resume — 恢复会话

```bash
python scripts/harness/qoder_task.py resume <run_id> --followup followup.json
```

使用已保存的精确 Qoder session id 启动新 run，通过 `--resume` 参数恢复。**不使用 `--continue`**。

**`--followup` 必填**，提供后续任务 JSON，覆盖原任务字段（但 session_id 始终来自记录，client 强制为 qoder，agent_id 自动生成新值）。

启动后立即返回新 run_id（UUID 格式），worker 后台执行。与 `start` 一样是非阻塞的。

入口返回不表示 Qoder 已成功启动。worker 在实际创建 Qoder 子进程后记录真实 PID，并异步提交 `previous_run_id`/`next_run_id` 替代链，旧 run 才标记 `superseded`。启动失败时释放该 run 的恢复占位，旧结果保持不变；启动尚未确认时不得再次派发。

### ack — 显式消费确认

```bash
python scripts/harness/qoder_task.py ack <run_id> --parent-session-id <UUID>
```

显式确认已读取并处理某 run 的完成通知。需要精确身份核对：

- 保存的 `parent_session_id` 必须匹配提供的 UUID
- 当前 `CODEX_THREAD_ID` 环境变量也必须匹配
- 仅接受终态（`finished`/`failed`/`unknown` 异常），运行中不可 ack
- ack 幂等：同身份重复 ack 返回已消费记录
- **ack 不代表验收 PASS**，仅证明父会话已认领消费

`status`/`result` 始终只读，不隐式 ack。

## 输出目录

所有任务文件存储在 `tmp/qoder-tasks/<run_id>/`（已被 .gitignore 忽略）：

- `task.json` — 任务输入（含完整 handoff 和身份）
- `completion.json` — 完成记录（原子写入，权限 0600）
- `callback.json` — 独立回调状态；失败不覆盖 Qoder 原始结果
- `callback.claim` — 共享回调认领（worker 与 watchdog 共用）
- `lifecycle.json` — 生命周期状态（acknowledged/superseded/exhausted/unknown）
- `ack.json` — 显式消费确认记录
- `started.json` — Qoder 子进程启动确认（真实 child PID、run/session）
- `resume.reservation` — 防止同一旧 run 并发恢复；不构成全局任务锁
- `lifecycle.lock` — 本 run 生命周期原子更新锁
- `watchdog.status.json` / `watchdog.log` — 兜底状态和错误诊断
- `watchdog.claim` — watchdog 唯一实例认领
- `stdout.log` — qodercli 标准输出
- `stderr.log` — qodercli 标准错误
- `worker.pid` — Worker 进程 PID

目录权限 0700，文件权限 0600。

## 生命周期与兜底

每次 `start` / `resume` 后，在**最终回复**展示完整任务卡并结束回合，不能只留在 commentary 或工具输出中。禁止主线程用 `sleep`、`ps`、`status/result` 循环或反复等待工具维持 LLM 回合；5/10 分钟检查只由后台 watchdog 执行。仓库规则不能强制关闭客户端回合，需要主调度遵守。

### 每 run 独立 watchdog

绑定 Codex 父会话的成功启动 run 自动建立后台 watchdog：

- **不调用 LLM**，不占用第二个 Qoder
- 首次 300 秒（5 分钟）后检查，之后每 600 秒（10 分钟）检查
- 最多存活 24 小时，到期记录 `exhausted` 并退出，不自动重启
- 运行中且无变化时静默，不反复提醒
- 收到 `acknowledged` 或 `superseded` 后停止
- 只在 completion 存在且从未尝试通知时补发首次通知（与 worker 共享 callback.claim）
- worker 死亡无 completion 时记录 `unknown`，至多一次异常通知，不伪造结果

**注意**：watchdog 被杀或宿主重启后不保证唤醒，不建立自动复活服务。

### 显式消费（ack）

父会话收到回调后应显式 ack：

1. 读取 run 的 lifecycle，已 `acknowledged` 或 `superseded` 立即结束，不重复业务验收
2. 核对身份（parent_session_id + CODEX_THREAD_ID）
3. 显式 ack 成功后独立验收

**ack 仅证明已处理，不等于验收 PASS。**

### 返工替代链

`resume` 创建的新 worker 确认实际 Qoder 子进程成功启动后：

- 新 run 记录 `previous_run_id`
- 旧 run 标记 `superseded` 并记录 `next_run_id`
- 旧 run 的 watchdog 停止
- 旧 completion 仍可读取

启动失败时旧 run 不变，不吞旧结果。

### 能力边界

- 已入队的旧 `codex queue` 消息无法撤回，仍可能唤醒父会话
- 消费/替代前置检查阻止重复业务验收，但不保证 0 次迟到唤醒
- watchdog 不建立全局队列或 OS 常驻服务

## 环境变量

| 变量 | 说明 |
|------|------|
| `QODER_TASK_CLI` | 覆盖 qodercli 路径（测试用） |
| `QODER_TASK_DIR` | 覆盖任务目录路径（须在本仓库内，测试用） |
| `FEIPI_AGENT_CLIENT` | Worker 环境变量：客户端标识 |
| `FEIPI_SESSION_ID` | Worker 环境变量：session UUID |
| `FEIPI_AGENT_ID` | Worker 环境变量：agent 标识 |
| `FEIPI_PARENT_CLIENT` | Worker 环境变量：父客户端（可选） |
| `FEIPI_PARENT_SESSION_ID` | Worker 环境变量：父 session（可选） |

**`QODER_SESSION_ID` 冲突说明**：Qoder CLI 会把环境变量 `QODER_SESSION_ID` 解释为 `--session-id`，与 `--resume` 组合时触发错误（"session-id can only be used with --continue or --resume when --fork-session is also specified"）。因此仓库身份统一使用 `FEIPI_*` 变量；start/resume 在构造 child env 时显式 `pop("QODER_SESSION_ID", None)`，避免父进程残留的该变量污染子 CLI 的 argv 解析。

## 安全约束

- 无 `shell=True`、无 `eval`
- Run ID 使用 UUID，严格正则校验，防路径穿越
- 拒绝任务文件、任务目录及读取文件的任何祖先为符号链接
- `permission_mode` 仅接受 `default`/`accept_edits`/`dont_ask`/`bypass_permissions`；缺省为用户授权的 `bypass_permissions`，拒绝其他未知值
- 退出 0 仅说明进程结束，不自动等价于质量验收 PASS
- 默认传 `--permission-mode bypass_permissions`，不叠加 `--dangerously-skip-permissions`，不传自动提交/重试参数
- 缺少 CLI 或非法输入时明确非零退出，不创建假的成功任务

## 身份与归属

- 脚本记录独立 `client=qoder` 身份
- 保留 `parent_client`/`parent_session_id` 关联
- Qoder 声明不得自动视为 Codex 验收 PASS
- 主线程须独立复核报告
- 所有身份字段写入 completion.json 和环境变量

## 本机 CLI

本机命令为 `qodercli`（非 GUI `qoder`）。帮助确认：
- `--resume <saved UUID>` 用于恢复会话
- `--session-id` 仅用于新会话
- 不使用 `--continue`

## 用户授权的默认权限

当前用户已明确授权默认 `bypass_permissions`：跳过 Qoder 工具权限审批，包括文件编辑与脚本执行，但不会授予 OS 管理员权限，也不是目录沙箱。任务范围、禁止 Git mutation 和真实数据访问等约束仍须遵守。

新任务省略 `permission_mode` 时使用并记录该默认值；显式 `default`、`accept_edits` 或 `dont_ask` 优先。`resume` 保留原任务已记录模式，升级旧任务须在 followup JSON 中明确设置 `"permission_mode": "bypass_permissions"`。无需临时 Bash 授权 wrapper。权限设置与完成回调相互独立。

## Codex 完成回调

`parent_client: "codex"` 启用回调。新任务必须有精确的 `parent_session_id` UUID；省略时可从当前 `CODEX_THREAD_ID` 补全并写入任务记录。不能用任务名称、`--last` 或历史目录猜测。恢复任务保留原绑定，不因调用环境切换而改绑父会话。

worker 在成功、非零退出或执行异常后先保存 `completion.json`，再执行参数数组形式的 `codex queue --thread <UUID> --message <通知>`。只通知 run id、结果位置及复核要求，不把原始日志、prompt 或响应复制到父会话。收到通知后主线程必须核对身份并独立验收；exit 0 不代表 PASS。

回调状态与任务状态分离：`queued` 只表示 CLI 已接受消息，不证明主会话已经消费；`failed` 表示发送失败；`unknown` 表示发送结果不确定。调用有超时、同一 run 不自动重复发送，避免重复执行。超时或回执中断不得伪造成功。CLI/本地服务不可用、worker 被强制结束等情况不能保证接续。

验收必须覆盖真实 Qoder 退出后，原 Codex 会话无需用户输入自动读取结果；桌面通知、结果文件生成、模拟测试或单纯 queued 均不能替代此项。旧的已完成任务不会被批量补发。
