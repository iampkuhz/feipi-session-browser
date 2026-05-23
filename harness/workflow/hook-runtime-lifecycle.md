# Hook Runtime Lifecycle

## 01. SessionStart

- 入口：`.claude/hooks/claude-hook.sh session-start`
- 行为：记录 hook event，不注入重型上下文。
- 输出：`tmp/agent_log/hook-events.jsonl`

## 02. PreToolUse Bash

- 入口：`.claude/hooks/claude-hook.sh pre-bash`
- 行为：只 hard block 极少数危险命令。
- 允许：pytest、rg、git diff、git status、python3 scripts/*、bash scripts/*。
- 输出：`tmp/agent_log/hook-events.jsonl`

## 03. PreToolUse Write/Edit/MultiEdit/NotebookEdit

- 入口：`.claude/hooks/claude-hook.sh pre-write`
- 行为：仓库内默认允许；敏感目录写入阻止；生成物路径警告。
- 不因为没有 active change 拦截普通编辑。

## 04. PostToolUse Write/Edit/MultiEdit/NotebookEdit

- 入口：`.claude/hooks/claude-hook.sh post-write`
- 行为：写入 evidence。
- 输出：
  - `tmp/agent_log/changed-files.jsonl`
  - `tmp/agent_log/task-evidence/<change-id>.jsonl`
  - `tmp/agent_log/hook-events.jsonl`

## 05. Stop / SubagentStop

- 入口：`.claude/hooks/claude-hook.sh stop`
- 行为：只检查 deterministic quality artifact。
- 不执行重型测试。
- 失败时 exit 2。

## 06. ConfigChange

- 入口：`.claude/hooks/claude-hook.sh config-change`
- 行为：记录配置变更到 `tmp/agent_log/config-change-log.jsonl`。
