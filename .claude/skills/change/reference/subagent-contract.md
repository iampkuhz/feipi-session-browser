# 子 Agent 契约 — 活跃变更继承

本文档定义子 agent 如何继承并在活跃 OpenSpec 变更内工作。

## 子 Agent 如何继承活跃变更

当父 agent（`change` 技能驱动者）将工作委派给子 agent 时，子 agent 必须读取 `.agent/active_change.json` 来确定当前活跃变更上下文。

```json
{
  "change_id": "<change-id>",
  "change_path": "openspec/changes/<change-id>/",
  "started_at": "<ISO 8601 timestamp>",
  "source_request": "<原始用户请求或提示词文件路径>",
  "protected_roots": ["openspec/", "harness/", ".claude/", "CLAUDE.md"],
  "required_gates": ["scripts/openspec/validate_layout.py", ...]
}
```

`change_id` 字段是将子 agent 工作关联回父变更的关键。`change_path` 字段告诉子 agent 在哪里查找任务和规格。完整字段规范见 `.agent/SCHEMA.md`。

## 子 Agent 必须做什么

### 1. 读取活跃变更

在开始任何工作前，子 agent 必须：

```
Read .agent/active_change.json
```

如果文件不存在，子 agent 不得继续实现编辑。应报告错误："未找到活跃的 OpenSpec 变更。请先运行 `/change` 创建一个，再委派工作。"

### 2. 在变更范围内工作

子 agent 必须：

- 仅修改 `.agent/active_change.json` 中标识的活跃变更相关的文件。
- 在任何提交、验证说明或报告中引用变更 ID。
- 不扩大范围，不超出父变更描述的内容。
- 不创建新的变更目录。父变更拥有范围主权。

### 3. 更新任务状态

如果子 agent 被分配了 `openspec/changes/<change-id>/tasks.md` 中的具体任务，它必须：

- 完成后标记任务复选框（`- [x]`）。
- 在任务下方添加简短验证说明。
- 报告证据（命令输出、文件计数等）——而非仅"完成"。

### 4. 遵守 Hook 强制

子 agent 在与父 agent 相同的 hook 约束下运行：

- **PreToolUse (Write|Edit|MultiEdit)：** `scripts/hooks/guard_openspec_change.py` 检查活跃变更目录。子 agent 的工作是有效的，因为父 agent 已创建变更目录。`.agent/active_change.json` 是子 agent 的上下文锚点，但 hook 检查 `openspec/changes/` 下的目录。
- **PostToolUse (Write|Edit|MultiEdit)：** `.claude/hooks/post_tool_guard.sh` 运行语法检查。
- **PreToolUse (Bash)：** `.claude/hooks/pre_tool_guard.sh` 阻止破坏性命令。
- **Stop：** `.claude/hooks/stop_check.sh` 警告未提交文件。

### 5. 不得修改活跃变更注册

子 agent 不得：

- 修改 `.agent/active_change.json`（由父 agent 管理）。
- 在 `openspec/changes/` 下创建新的变更目录。
- 移动或归档变更（这是父级操作）。

## 委派模式

父 agent 应按以下模式委派：

1. 确保 `.agent/active_change.json` 存在且最新。
2. 从 `openspec/changes/<change-id>/tasks.md` 中给子 agent 分配具体任务。
3. 清晰传达范围边界。
4. 子 agent 完成后，验证工作和任务复选框。
5. 继续下一个任务或阶段。

## 子 Agent 提示词示例

> 你正在活跃变更上工作：`<change-id>`。
> 读取 `.agent/active_change.json` 获取上下文。
> 完成 `openspec/changes/<change-id>/tasks.md` 中的以下任务：
>
> - 任务：<任务描述>
> - 范围：<具体文件/函数>
> - 超出范围：<明确排除的内容>
>
> 完成后，标记任务复选框并添加验证说明。

## 验证证据

子 agent 必须提供具体证据，而非空口声明：

- 运行相关验证命令并展示输出。
- 展示文件 diff 或关键变更行。
- 报告测试结果的 pass/fail 计数。
