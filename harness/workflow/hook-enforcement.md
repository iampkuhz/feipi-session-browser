# Hook 强制执行

本文件描述强制执行 OpenSpec 工作流的 hook 架构。

## 概览

Hook 配置在 `.claude/settings.json` 中，在特定生命周期点执行。它们是主要执行机制——没有 hook，工作流仅依赖 agent 提示的合规性。

## Hook 类型

### PreToolUse

在工具（Write、Edit、MultiEdit、Bash）运行**之前**执行。

- **Write|Edit|MultiEdit 守卫**（`guard_active_openspec_change.py`）：
  - 检查目标文件是否在受保护根目录下。
  - 受保护根目录：`CLAUDE.md`、`AGENTS.md`、`openspec/`、`.claude/`、`scripts/`、`harness/`、`src/`。
  - 如果是受保护的，需要 `.agent/active_change.json` 中存在有效 `change_id` 且匹配的 `openspec/changes/<change-id>/` 目录。
  - 匹配的变更目录还必须包含 `proposal.md`、`design.md`、`tasks.md`，避免空 change 目录放行产品或 harness 编辑。
  - Exit 0 = 允许，Exit 1 = 阻止。
  - 创建例外：写入 `openspec/changes/` 或 `.agent/active_change.json` 始终允许。

- **Bash 守卫**（`pre_tool_guard.sh`）：
  - 通用 Bash 预执行检查。

### PostToolUse

在工具完成**之后**执行。

- **Write|Edit|MultiEdit 记录器**（`log_change_evidence.py`）：
  - 记录编辑的文件路径、工具名、时间戳和 change_id。
  - 追加到 `.agent/task-evidence/<change-id>.jsonl`。
  - 如果没有活跃变更，记录到 `unknown.jsonl`。
  - 始终 exit 0（非阻塞）。

### Stop / SubagentStop

在 agent 会话即将结束时执行。

- **Stop 检查**（`stop_check.sh`）：
  - 警告 git status 中的本地文件。
  - 调用 `stop_validate_change.py` 检查变更完整性。

- **Stop 验证**（`stop_validate_change.py`）：
  - 检查受保护根目录中未提交的变更。
  - 如果存在变更，验证：
    1. `.agent/active_change.json` 存在且含 `change_id`。
    2. `openspec/changes/<change-id>/` 存在。
    3. 所需文件存在：`proposal.md`、`design.md`、`tasks.md`。
    4. `.agent/task-evidence/<change-id>.jsonl` 中有证据条目。
  - 如果不完整，以 exit 2 阻止，并输出“继续修复而不是停止”的动作列表。
  - 紧急绕过：`FEIPI_SKIP_STOP_HOOK=1`。

### OpenSpec change 激活

`scripts/openspec/create_active_change.py` 负责创建并激活 change。重复运行同一个 `change_id` 时，不覆盖已存在的 proposal/design/tasks/spec 文件；运行不同 `change_id` 时，必须更新 `.agent/active_change.json` 指向新的 active change。

这保证子 agent 和 hook 不会继续沿用旧任务的 active sentinel。

### SessionStart / SubagentStart

在新会话或子 agent 会话开始时执行。

- **上下文注入器**（`inject_session_context.py`）：
  - 向 stdout 打印简洁的上下文。
  - 包含：仓库根路径、活跃变更状态、证据路径、受保护根目录。
  - 如果没有活跃变更，警告受保护编辑将被阻止，直到 `/change` 创建一个。
  - 自测验证了有/无活跃变更的场景。

## 接线

所有 hook 在 `.claude/settings.json` 的 `hooks` 键下配置：

```json
{
  "hooks": {
    "SessionStart": [{ "command": "python3 scripts/agent_hooks/inject_session_context.py" }],
    "SubagentStart": [{ "command": "python3 scripts/agent_hooks/inject_session_context.py" }],
    "PreToolUse": [
      { "matcher": "Write|Edit|MultiEdit", "command": "python3 scripts/agent_hooks/guard_active_openspec_change.py" },
      { "matcher": "Bash", "command": ".claude/hooks/pre_tool_guard.sh" }
    ],
    "PostToolUse": [
      { "matcher": "Write|Edit|MultiEdit", "command": "python3 scripts/agent_hooks/log_change_evidence.py" }
    ],
    "Stop": [{ "command": ".claude/hooks/stop_check.sh" }],
    "SubagentStop": [{ "command": "python3 scripts/agent_hooks/stop_validate_change.py" }]
  }
}
```

## 自测

每个 hook 脚本支持 `--self-test` 模式，在临时 git 仓库中运行确定性的 pass/fail 检查：

```bash
python3 scripts/agent_hooks/guard_active_openspec_change.py --self-test   # 8/8
python3 scripts/agent_hooks/stop_validate_change.py --self-test           # 8/8
python3 scripts/agent_hooks/inject_session_context.py --self-test         # 10/10
python3 scripts/agent_hooks/log_change_evidence.py --self-test            # 3/3
```

## 失败模式

| 场景 | Hook | 结果 |
|----------|------|--------|
| 受保护编辑，无活跃变更 | PreToolUse 守卫 | 阻止（exit 1） |
| 会话启动，无活跃变更 | SessionStart 注入 | 警告（exit 0，上下文显示 NONE） |
| Stop 时受保护变更存在，变更不完整 | Stop 验证 | 阻止（exit 2），输出修复步骤 |
| Stop，紧急绕过 | Stop 验证 | 允许（FEIPI_SKIP_STOP_HOOK=1） |
| PostToolUse，无活跃变更 | 证据记录器 | 记录到 unknown.jsonl（exit 0） |
