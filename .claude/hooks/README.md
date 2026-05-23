# Claude Hook Runtime

## 01. 入口

每种 hook 类型有独立的 shell 脚本入口，位于 `.claude/hooks/`：

| 脚本 | Hook 类型 | 说明 |
|---|---|---|
| `session-start.sh` | SessionStart | 初始化会话上下文 |
| `subagent-start.sh` | SubagentStart | 子 agent 启动记录 |
| `pre-bash.sh` | PreToolUse (Bash) | Bash 命令策略检查 |
| `pre-write.sh` | PreToolUse (Write/Edit/...) | 写路径策略检查 |
| `post-write.sh` | PostToolUse (Write/Edit/...) | 写后记录 |
| `tool-failure.sh` | PostToolUseFailure | 失败记录 |
| `stop.sh` | Stop | 停止校验（区分只读/有写会话） |
| `subagent-stop.sh` | SubagentStop | 子 agent 停止（委托 stop.sh） |
| `config-change.sh` | ConfigChange | 配置变更记录 |

`settings.json` 的 `hooks` 字段直接指向对应脚本。

## 02. Stop 钩子策略

`stop.sh` 区分两种会话：

- **只读会话**（`changed-files.jsonl` 为空或不存在）：跳过质量门禁校验，仅做敏感文件快速检查，写入 `readOnly: true` 的 summary。
- **有写操作会话**：执行完整校验链：
  1. OpenSpec 变更完整性（`stop_validate_change.py`）
  2. UI 质量门禁（`stop_quality_gate.py`）
  3. task-ledger 表头格式检查
  4. 写入 `readOnly: false` 的 summary

## 03. 业务逻辑位置

非 Stop hook 的 Python 策略逻辑位于：

```text
scripts/claude_hooks/
```

Stop hook 直接调用独立校验脚本：

```text
scripts/agent_hooks/stop_validate_change.py
scripts/hooks/stop_quality_gate.py
```

不再把复杂逻辑散落在 `.claude/hooks/*.sh` 的 shell 脚本中。

## 04. 权限原则

- 仓库内读写默认允许。
- Hook 不做白名单式正常开发限制。
- hard block 只用于少数危险命令和敏感数据泄露场景。
- deterministic quality gate 由显式命令生成 artifact。

## 05. 运行态目录

默认写入：

```text
tmp/agent_log/
```

`.agent/` 只作为 legacy 只读兼容路径。
