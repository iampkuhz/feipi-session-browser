# Java-First 迁移 — 状态管理与重试策略

本文档定义本次长任务的状态文件约定与 429/BLOCKED_RETRYABLE 重试策略。

## 状态文件位置

| 文件 | 可提交 | 用途 |
|---|---|---|
| `tmp/agent_state/java-first-migration/state.json` | 否 | 运行时任务状态表 |
| `tmp/agent_state/java-first-migration/<task-id>.log.md` | 否 | 单任务执行日志 |
| `tmp/agent_logs/` | 否 | Agent 日志（已有约定） |
| `tmp/quality/` | 否 | 质量门产物（已有约定） |

运行时状态不提交。长期可提交的规则只落入 `harness/`、`skills/`、`openspec/`、`scripts/`。

## state.json 结构

```json
{
  "migration_id": "java-first-migration",
  "created": "2026-06-25",
  "branch": "main_java",
  "tasks": {
    "<task-id>": {
      "status": "PENDING | IN_PROGRESS | PASS | FAIL | BLOCKED | BLOCKED_RETRYABLE",
      "started": "ISO-8601",
      "completed": "ISO-8601 | null",
      "description": "...",
      "changed_files": [],
      "validation_passed": false,
      "retry_count": 0
    }
  },
  "phase_status": {
    "P00": "NOT_STARTED | IN_PROGRESS | DONE",
    "P01": "...",
    "..."
  }
}
```

## 重试策略

触发条件：子任务返回 `BLOCKED_RETRYABLE`（典型场景：429 rate limit、临时性基础设施故障）。

### 流程

1. 父 agent 收到 `BLOCKED_RETRYABLE` 后，记录当前重试次数。
2. 使用一次性 `sleep` 等待，时长按指数退避：
   - 第 1 次：30 秒
   - 第 2 次：60 秒
   - 第 3 次：120 秒
3. 等待后重试同一任务。
4. 重试成功：更新 `state.json`，继续下一任务。
5. 重试失败：继续退避，最多重试 3 次。
6. 超过 3 次重试：将任务标记为 `BLOCKED`，停止后续实现型任务。

### 硬约束

- **不得 busy wait**：禁止 1 秒级轮询、反复查询状态、空转循环。
- **不得并行重试**：同一时刻只能有一个 LLM agent 在运行。
- **不得跳过失败任务**：`BLOCKED` 任务必须人工介入后才能继续。
