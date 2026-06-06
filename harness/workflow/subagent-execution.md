# 子 Agent 执行

本文档描述子 agent 在 OpenSpec 流程中的操作方式。

## 子 Agent 模型

本仓库的子 agent 定义在 `.claude/agents/` 下。每个 agent 包含：
- `name`：唯一标识符。
- `description`：何时使用。
- `tools`：允许的 Claude Code 工具。
- `model`：`inherit` 表示使用与主会话相同的模型。

## 默认 Agent

三个 agent 构成 OpenSpec 工作流核心：

### openspec-planner

- **用途**：设计 OpenSpec 变更（proposal、design、tasks、spec 增量）。
- **范围**：`openspec/changes/`、`tmp/active_change.json`、`openspec/specs/`。
- **禁止**：产品源文件、CLAUDE.md、AGENTS.md、代码实现。
- **活跃变更**：通过 `/change` 或 `create_active_change.py` 创建和记录活跃变更。
- 再次创建不同 change 时，`create_active_change.py` 必须切换 `tmp/active_change.json`，避免子 agent 继承旧 change。

### implementer

- **用途**：从变更的 `tasks.md` 中精确执行一个任务。
- **预检**：必须验证 `tmp/active_change.json` 存在且有效。
- **范围**：仅分配任务所需的文件。
- **证据**：由 PostToolUse hook 自动记录到 `tmp/task-evidence/<change-id>.jsonl`。
- **禁止**：扩大范围、跳过验证、修改 OpenSpec 产物。

### qa-verifier

- **用途**：会话停止前的最终验证门禁。
- **检查**：活跃变更完整性、证据条目、diff 范围、验证门禁、生成的产物。
- **输出**：PASS / FAIL / BLOCKED 及结构化原因。
- **工具**：只读分析（Read、Grep、Glob、LS、Bash）。

## Specialty Agent


## 上下文继承

每个子 agent 接收由 `inject_session_context.py` 注入的会话上下文：
- 仓库根路径。
- 活跃变更 ID 和状态。
- 证据路径和条目数。
- 受保护根目录和工作流默认值。

这确保子 agent 无法在缺乏当前 OpenSpec 状态知识的情况下操作。

## 守卫强制执行

`guard_active_openspec_change.py` PreToolUse hook 在每次对受保护根目录执行 Write/Edit/MultiEdit 之前运行。如果不存在活跃变更，或 active change 缺少 `proposal.md`、`design.md`、`tasks.md`，编辑将被阻止。这同样适用于子 agent。

## 证据追踪

`log_change_evidence.py` PostToolUse hook 记录每次受保护文件编辑。证据写入 `tmp/task-evidence/<change-id>.jsonl`。qa-verifier 读取此文件以确认所有编辑都有据可查。

## Stop 验证

子 agent 完成时，`stop_validate_change.py` 检查：
- 如果存在受保护变更，活跃变更必须基础完整。
- 所需文件（proposal.md、design.md、tasks.md）必须存在。
- 必须有证据条目。
- 如果不完整，阻止 stop（exit 2），并输出下一步修复动作，要求 agent 继续修复而不是自然结束。

紧急绕过：`FEIPI_SKIP_STOP_HOOK=1`。
