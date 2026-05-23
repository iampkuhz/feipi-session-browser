# Hook 强制执行

本文件描述强制执行 OpenSpec 工作流的 hook 架构。

> **注**：旧 hook 入口（`scripts/agent_hooks/`、`.claude/hooks/pre_tool_guard.sh` 等）
> 已迁移至 `.claude/hooks/claude-hook.sh` + `scripts/claude_hooks/`。
> 本文档保留架构说明，实际路径以 `harness/workflow/hook-runtime-lifecycle.md` 为准。

## 概览

Hook 配置在 `.claude/settings.json` 中，在特定生命周期点执行。它们是主要执行机制——没有 hook，工作流仅依赖 agent 提示的合规性。

## Hook 类型

### SessionStart / SubagentStart

在新会话或子 agent 会话开始时执行。

- 入口：`.claude/hooks/claude-hook.sh session-start`
- 行为：记录会话启动事件，不注入重型上下文。
- 输出：`tmp/agent_log/hook-events.jsonl`

### PreToolUse

在工具（Write、Edit、MultiEdit、Bash）运行**之前**执行。

- **Bash 守卫**：入口 `.claude/hooks/claude-hook.sh pre-bash`
  - hard block 少数危险命令（`rm -rf /`、`git reset --hard` 等）。
  - 允许 pytest、rg、git diff、git status、python3 scripts/*、bash scripts/*。
- **Write 守卫**：入口 `.claude/hooks/claude-hook.sh pre-write`
  - 仓库内编辑默认允许，敏感路径（`~/.ssh`、`~/.aws`）阻止。

### PostToolUse

在工具完成**之后**执行。

- **Write 记录器**：入口 `.claude/hooks/claude-hook.sh post-write`
  - 记录编辑的文件路径、工具名、时间戳和 change_id。
  - 输出到 `tmp/agent_log/changed-files.jsonl` 和 `tmp/agent_log/task-evidence/<change-id>.jsonl`。

### Stop / SubagentStop

在 agent 会话即将结束时执行。

- 入口：`.claude/hooks/claude-hook.sh stop`
- 行为：只检查 deterministic quality artifact，不跑重型测试。
- 读取 `tmp/agent_log/changed-files.jsonl`，找出需要 quality gate 的变更。
- 验证对应 summary 是否存在、status 是否 PASS、finishedAt 是否晚于变更记录。
- 失败时 exit 2，并给出可执行命令。

### ConfigChange

当 Claude Code 配置变更时执行。

- 入口：`.claude/hooks/claude-hook.sh config-change`
- 行为：记录配置变更到 `tmp/agent_log/config-change-log.jsonl`。

## OpenSpec change 激活

`scripts/openspec/create_active_change.py` 负责创建并激活 change。重复运行同一个 `change_id` 时，不覆盖已存在的 proposal/design/tasks/spec 文件；运行不同 `change_id` 时，必须更新 `tmp/active_change.json` 指向新的 active change。

这保证子 agent 和 hook 不会继续沿用旧任务的 active sentinel。

## 接线

所有 hook 通过统一入口 `.claude/hooks/claude-hook.sh` 分发：

```json
{
  "hooks": {
    "SessionStart": [{ "command": ".claude/hooks/claude-hook.sh session-start" }],
    "SubagentStart": [{ "command": ".claude/hooks/claude-hook.sh subagent-start" }],
    "PreToolUse": [
      { "matcher": "Bash", "command": ".claude/hooks/claude-hook.sh pre-bash" },
      { "matcher": "Write|Edit|MultiEdit|NotebookEdit", "command": ".claude/hooks/claude-hook.sh pre-write" }
    ],
    "PostToolUse": [
      { "matcher": "Write|Edit|MultiEdit|NotebookEdit", "command": ".claude/hooks/claude-hook.sh post-write" }
    ],
    "Stop": [{ "command": ".claude/hooks/claude-hook.sh stop" }],
    "SubagentStop": [{ "command": ".claude/hooks/claude-hook.sh subagent-stop" }],
    "ConfigChange": [{ "command": ".claude/hooks/claude-hook.sh config-change" }]
  }
}
```

## 质量门禁

需要 deterministic quality gate 的变更，必须显式运行：

```bash
python3 scripts/quality/run_quality_gate.py --target <target> --change-id <change-id>
```

Stop hook 只验证 summary artifact，不跑重型测试。
