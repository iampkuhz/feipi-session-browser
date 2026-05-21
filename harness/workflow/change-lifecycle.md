# 变更生命周期

本文件描述 feipi-session-browser 仓库的 OpenSpec 变更完整生命周期。

## 概览

所有非平凡变更遵循以下流程：

```
/CHANGE -> 提案 -> 设计 -> 任务文件 -> 串行实现 -> 验证 -> 归档
```

单一入口为 `/change <需求描述或提示词文件路径>`。不要直接读取 `prompts/` 启动工作；始终通过 `/change` 路由。

## 1. 启动变更

运行 `/change <需求路径>`，它会：
- 在 `openspec/changes/<change-id>/` 下创建 `proposal.md`、`design.md`、`tasks.md`。
- 写入 `tmp/active_change.json` 记录活跃变更。
- 更新 `.claude/skills/change/` 下的变更技能引用。

## 2. 提案

openspec-planner agent 编写 `proposal.md`：
- 一段话总结变更内容及原因。
- 范围边界和非目标。
- 验证方式。

## 3. 设计

openspec-planner 编写 `design.md`：
- 技术方法和约束。
- 权衡和备选方案。
- 实现边界（哪些文件、哪些子系统）。

## 4. 任务文件

openspec-planner 将变更分解为 `tasks.md`：
- 每个任务可独立验证。
- 每个任务引用一个验证命令。
- 任务按串行排序（变更内无并行执行）。

## 5. 实现

implementer agent 逐个执行任务：
- **预检**：读取 `tmp/active_change.json`，验证活跃变更存在。
- **范围**：仅实现分配的任务，不多做。
- **验证**：实现后运行任务的验证命令。
- **证据**：受保护根目录下的所有文件编辑自动记录到 `tmp/task-evidence/<change-id>.jsonl`。

## 6. 验证

qa-verifier agent 检查：
- 活跃变更完整性（proposal、design、tasks）。
- 证据条目与编辑文件匹配。
- `git diff --stat` 范围与任务匹配。
- 所有验证命令通过。
- 产品测试通过。
- diff 中无生成的产物。

输出：PASS / FAIL / BLOCKED 及原因。

## 7. 归档

验证通过后：
- 将最终行为合并到 `openspec/specs/`。
- 将 `openspec/changes/<change-id>/` 移至 `openspec/changes/archive/`。
- 清除 `tmp/active_change.json`。

## 本地变更

`openspec/changes/` 下的 OpenSpec 变更是分支本地的。在合并到 `openspec/specs/` 并归档之前，不会提交到仓库。`.gitignore` 确保变更产物不会意外泄漏到提交中。

## Hook 强制执行

生命周期由 `.claude/settings.json` 中配置的 Claude Code hooks 强制执行：

| Hook | 脚本 | 用途 |
|------|------|------|
| SessionStart/SubagentStart | `inject_session_context.py` | 注入活跃变更状态 |
| PreToolUse (Write/Edit/MultiEdit) | `guard_active_openspec_change.py` | 无活跃变更时阻止受保护文件编辑 |
| PostToolUse (Write/Edit/MultiEdit) | `log_change_evidence.py` | 自动将文件编辑记录到证据 |
| Stop/SubagentStop | `stop_validate_change.py` | 变更未完成时阻止 stop |

详见 `harness/workflow/hook-enforcement.md`。
