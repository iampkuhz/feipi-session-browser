# Qoder CLI 子任务使用指南

## 概述

`scripts/harness/qoder_task.py` 提供 Qoder CLI 子任务的显式委派入口。主线程（如 Codex）仅负责交代任务和复核结果，不 busy wait。

**重要说明**：
- 脚本无法主动唤醒已经结束的 Codex 回合
- 调用者应在下一回合按需读取结果，而非循环查询状态
- 权限不足时任务会 BLOCKED，脚本不默认绕过权限
- **这些是提示约束而非 OS 沙箱**：脚本通过 prompt 指导 Qoder 行为，但不提供真正的隔离
- **不要发送密钥、真实 session 数据或个人配置**：任务 JSON 会被记录到 tmp/qoder-tasks/
- **本机 qodercli 1.1.44 的环境问题（如 agent 配置加载提示、Bash 拒绝）不会被此脚本修复**

## 命令

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

可选字段：`agent_id`（自动生成）、`session_id`（自动生成 UUID）、`parent_client`、`parent_session_id`、`permission_mode`（枚举：`default`/`accept_edits`/`dont_ask`）。**`client` 强制为 `qoder`，不可覆盖**。

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

启动后立即返回唯一 run_id（UUID 格式）。Worker 进程在后台阻塞等待 qodercli 退出，原子写入完成记录。

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

## 输出目录

所有任务文件存储在 `tmp/qoder-tasks/<run_id>/`（已被 .gitignore 忽略）：

- `task.json` — 任务输入（含完整 handoff 和身份）
- `completion.json` — 完成记录（原子写入，权限 0600）
- `stdout.log` — qodercli 标准输出
- `stderr.log` — qodercli 标准错误
- `worker.pid` — Worker 进程 PID

目录权限 0700，文件权限 0600。

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
- `permission_mode` 仅接受 `default`/`accept_edits`/`dont_ask`，拒绝 `bypass_permissions` 等危险标志
- 退出 0 仅说明进程结束，不自动等价于质量验收 PASS
- 默认不绕过权限，不传自动提交/重试参数
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
