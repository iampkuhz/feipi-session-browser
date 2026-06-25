# Handoff Schema — 父 agent 到子 agent 的最小交接协议

本文档定义父 agent 调用子 agent 时必须传递的最小字段集，以及子 agent 必须返回的输出结构。

## 设计原则

1. **最小信息量**：只传递当前任务执行所必需的上下文。
2. **不传完整聊天历史**：禁止将父 agent 的完整对话记录、无关任务日志或整篇 spec 塞入 handoff。只粘贴与本 task 直接相关的字段、路径和命令输出摘要。
3. **可独立重试**：每个子任务携带足够信息，使其可以在无父 agent 上下文的情况下独立重跑。

## 输入 Schema（父 agent -> 子 agent）

```yaml
# ---- 必填字段 ----
task_id: "Pxx-Tyy"                    # 当前任务的唯一标识
run_id: "java-first-migration-20260625"  # 所属变更批次
objective: "一句话说明本任务目标"        # 明确、可验证的目标描述
allowed_scope:
  read:                                # 允许读取的文件/目录 pattern
    - path/pattern
  write:                               # 允许修改的文件/目录 pattern
    - path/pattern
forbidden_scope:                       # 禁止触碰的路径 pattern
  - path/pattern
expected_output:                       # 期望产物列表
  - "文件修改清单"
  - "validation report"

# ---- 推荐字段 ----
why_now: "为什么当前阶段必须做"          # 简短说明任务在整体流程中的位置
repo_state:
  branch: "main_java"                  # 当前分支
  git_status_summary: |                # git status --short 摘要
    <摘要内容>
required_context:                      # 已定位的文件片段或命令输出摘要
  - "不超过必要范围"                     # 禁止粘贴完整聊天历史
validation_cmds:                       # 验证命令列表
  - "cmd 1"
  - "cmd 2"
stop_conditions:                       # 遇到以下情况立即停止
  - "遇到用户改动冲突"
  - "遇到 required quality gate failure 且无法修复"
  - "需要产品/架构决策"
failure_policy:                        # 失败处理策略
  - "不扩大范围"
  - "验证失败可在 allowed scope 内修复一次"
  - "无法确认时返回 BLOCKED"

# ---- 可选字段 ----
change_id: "..."                       # OpenSpec change 标识（如果适用）
rate_limit_policy: "RATE-LIMIT-RETRY-POLICY.md"  # 重试策略引用
```

### 字段规则

| 字段 | 必填 | 缺失处理 |
|---|:---:|---|
| `task_id` | 是 | 缺失则子 agent 返回 `BLOCKED` |
| `run_id` | 是 | 缺失则子 agent 返回 `BLOCKED` |
| `objective` | 是 | 缺失则子 agent 返回 `BLOCKED` |
| `allowed_scope` | 是 | 缺失则子 agent 返回 `BLOCKED` |
| `forbidden_scope` | 推荐 | 缺失时子 agent 仍需避开明显敏感路径 |
| `expected_output` | 是 | 缺失则子 agent 返回 `BLOCKED` |
| `why_now` | 推荐 | 缺失时子 agent 继续执行 |
| `repo_state` | 推荐 | 缺失时子 agent 自行获取 |
| `required_context` | 可选 | 缺失时不要主动读取大型规则文件或无关目录 |
| `validation_cmds` | 可选 | 缺失时运行最小相关 deterministic check |
| `stop_conditions` | 推荐 | 缺失时使用默认停止条件 |
| `failure_policy` | 推荐 | 缺失时采用默认策略 |
| `change_id` | 可选 | 缺失时按普通 scoped task 执行 |
| `rate_limit_policy` | 可选 | 缺失时参考 `java-first-migration-state.md` 重试策略 |

### 禁止传递的内容

- 父 agent 的完整聊天历史或对话记录。
- 与本 task 无关的 spec、design note 或任务日志。
- 真实 session 大文件全文。
- 密钥、token、`.claude/settings.local.json`、`.mcp.json`。

## 输出 Schema（子 agent -> 父 agent）

子 agent 完成任务后，必须在最终回复中返回以下结构：

```yaml
# ---- 必填 ----
status: "PASS | FAIL | BLOCKED | BLOCKED_RETRYABLE"
changed_files:                         # 本次修改的文件列表（绝对路径）
  - "/absolute/path/to/file1"
  - "/absolute/path/to/file2"
validation:                            # 每条验证命令的执行结果
  - cmd: "bash scripts/harness/doctor.sh"
    result: "PASS | FAIL | NOT_RUN"
    note: ""                           # 可选，补充说明

# ---- 条件必填 ----
blockers:                              # status 为 BLOCKED 或 BLOCKED_RETRYABLE 时必填
  - "具体阻塞原因"
notes:                                 # 推荐始终提供
  - "需要后续关注的事项"
  - "发现的潜在风险"
```

### 输出字段规则

| 字段 | 必填 | 说明 |
|---|:---:|---|
| `status` | 是 | 四选一：`PASS`、`FAIL`、`BLOCKED`、`BLOCKED_RETRYABLE` |
| `changed_files` | 是 | 空列表用 `[]`；必须是绝对路径 |
| `validation` | 是 | 至少包含一条记录；未运行的命令标记为 `NOT_RUN` |
| `blockers` | 条件 | `status` 为 `BLOCKED` / `BLOCKED_RETRYABLE` 时必须填写 |
| `notes` | 推荐 | 建议始终提供，记录风险和后续事项 |

### Status 语义

- **PASS**：任务完成，validation 全部通过。
- **FAIL**：任务完成但 validation 失败，且已在 allowed scope 内修复一次仍不通过。
- **BLOCKED**：任务无法继续，需要人工介入（非临时性原因）。
- **BLOCKED_RETRYABLE**：任务因临时性原因（429 rate limit、基础设施故障）无法继续，可重试。
