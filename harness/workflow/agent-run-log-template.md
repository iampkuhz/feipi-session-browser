# Agent Run Log 模板

本文档定义子任务执行日志的写入规范、格式和不提交规则。

## 不提交规则

**Agent run log 是运行时产物，绝不提交到 git。**

- 日志文件统一写入 `tmp/agent_state/<run_id>/` 目录下。
- 路径格式：`tmp/agent_state/<run_id>/<task_id>.log.md`。
- `tmp/` 目录已在 `.gitignore` 中排除，确保不会被意外提交。
- 如果 `tmp/agent_state/<run_id>/` 不存在，子 agent 应自行创建。

## 日志路径约定

```
tmp/
  agent_state/
    <run_id>/                  # 例如 java-first-migration-20260625
      state.json               # 全局任务状态（见 java-first-migration-state.md）
      P01-T01.log.md           # 子任务日志
      P01-T02.log.md
      ...
  agent_logs/                  # 历史兼容路径（已有约定）
  quality/                     # 质量门产物
```

## 日志模板

每个 `<task_id>.log.md` 文件必须包含以下段落：

```markdown
# Agent Run Log: <task_id>

## Run Metadata

- run_id: <run_id>
- task_id: <task_id>
- parent_agent: <父 agent 标识>
- child_agent: <子 agent 标识>
- started: <ISO-8601 开始时间>
- completed: <ISO-8601 完成时间，未完成时留空>
- llm_concurrency: 1

## Handoff

粘贴本次最小 handoff（参见 handoff-schema.md 输入 Schema）。

## Timeline

| 时间 (ISO-8601) | 事件 | 说明 |
|---|---|---|
| 2026-06-25T10:00:00+08:00 | STARTED | 子 agent 开始执行 |
| 2026-06-25T10:01:00+08:00 | FILE_READ | 读取 harness/workflow/... |
| 2026-06-25T10:02:00+08:00 | FILE_WRITE | 写入 harness/workflow/... |
| 2026-06-25T10:03:00+08:00 | VALIDATION | 运行 doctor.sh: PASS |
| 2026-06-25T10:04:00+08:00 | COMPLETED | status=PASS |

## Rate Limit / Retry

| 次数 | 时间 (ISO-8601) | 错误类型 | 错误信息 | 等待时长 (秒) | 重试结果 |
|---:|---|---|---|---:|---|
| 1 | 2026-06-25T10:05:00+08:00 | 429 | rate limit exceeded | 30 | PASS |
| 2 | 2026-06-25T10:07:00+08:00 | 503 | service unavailable | 60 | FAIL |

如果没有发生 rate limit 或重试，保留表头并标注"无"。

## Completion

```yaml
status: PASS | FAIL | BLOCKED | BLOCKED_RETRYABLE
changed_files:
  - /absolute/path/to/file1
validation:
  - cmd: "bash scripts/harness/doctor.sh"
    result: PASS
blockers: []
notes:
  - "后续需要关注的事项"
```
```

## Rate Limit / Retry 记录格式说明

- **次数**：从 1 开始递增，每次重试加 1。
- **时间**：重试发生的 ISO-8601 时间戳。
- **错误类型**：HTTP 状态码或错误类别（如 `429`、`503`、`timeout`、`infra_error`）。
- **错误信息**：简短的错误描述。
- **等待时长**：本次重试前的等待秒数，遵循指数退避策略（30/60/120 秒）。
- **重试结果**：`PASS` 表示重试成功，`FAIL` 表示重试仍然失败。

### 退避策略（引用自 java-first-migration-state.md）

| 重试次数 | 等待时长 |
|---:|---:|
| 1 | 30 秒 |
| 2 | 60 秒 |
| 3 | 120 秒 |

- 最多重试 3 次。
- 超过 3 次：标记为 `BLOCKED`，停止后续实现型任务。
- 不得 busy wait，不得并行重试。
