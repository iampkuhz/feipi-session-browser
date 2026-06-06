# Hook 强制执行

本文件描述强制执行 OpenSpec 工作流的 hook 架构。

## 概览

Hook 配置在 `.claude/settings.json` 中，在特定生命周期点执行。它们是主要执行机制——没有 hook，工作流仅依赖 agent 提示的合规性。

## Hook 类型

### SessionStart / SubagentStart

在新会话或子 agent 会话开始时执行。

- 入口：`.claude/hooks/session-start.sh`
- 行为：创建 per-session 日志目录，记录会话启动事件，不注入重型上下文。
- 输出：`tmp/agent_logs/<session>/hook-events.jsonl`

### PreToolUse

在工具（Write、Edit、MultiEdit、Bash）运行**之前**执行。

- **Bash 守卫**：入口 `.claude/hooks/pre-bash.sh`
  - hard block 少数危险命令（`rm -rf /`、`git reset --hard` 等）。
  - 允许 pytest、rg、git diff、git status、python3 scripts/*、bash scripts/*。
- **Write 守卫**：入口 `.claude/hooks/pre-write.sh`
  - 仓库内编辑默认允许，敏感路径（`~/.ssh`、`~/.aws`）阻止。

### PostToolUse

在工具完成**之后**执行。

- **Write 记录器**：入口 `.claude/hooks/post-write.sh`
  - 记录编辑的文件路径、工具名、时间戳和 change_id。
  - 输出到 `tmp/agent_logs/<session>/changed-files.jsonl` 和 `tmp/agent_logs/<session>/task-evidence/<change-id>.jsonl`。

### Stop / SubagentStop

在 agent 会话即将结束时执行。

- 入口：`.claude/hooks/stop.sh`
- 行为：区分只读会话与有写操作会话，执行完整质量门禁校验。
- 读取当前 session 的 `changed-files.jsonl`，找出需要 quality gate 的变更。
- 验证对应 summary 是否存在、status 是否 PASS、finishedAt 是否晚于变更记录。
- 失败时 exit 2，并给出可执行命令。

### ConfigChange

当 Claude Code 配置变更时执行。

- 入口：`.claude/hooks/config-change.sh`
- 行为：记录配置变更到 `tmp/agent_logs/<session>/config-change-log.jsonl`。

## 运行态日志目录

所有日志写入 `tmp/agent_logs/MMDD_<session-id>/`。每个 session 有独立目录，多个 agent 实例同时运行时互不干扰。

## OpenSpec change 激活

`scripts/openspec/create_active_change.py` 负责创建并激活 change。重复运行同一个 `change_id` 时，不覆盖已存在的 proposal/design/tasks/spec 文件；运行不同 `change_id` 时，必须更新 `tmp/active_change.json` 指向新的 active change。

## Hook 测试保护策略

`tests/hooks/` 目录为**受保护目录**，包含所有 Hook 场景的校验脚本和单测。

**规则：任何对 `tests/hooks/` 下文件的修改，必须逐文件经用户确认后方可执行。**

原因：Hook 测试是 Claude Code 运行时安全/质量门的验证层，误改可能导致：
- 危险命令拦截失效
