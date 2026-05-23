# Hook Runtime Lifecycle

## 01. SessionStart

- 入口：`.claude/hooks/session-start.sh`
- 行为：创建 per-session 日志目录，记录 hook event，不注入重型上下文。
- 输出：`tmp/agent_logs/<session>/hook-events.jsonl`

## 02. PreToolUse Bash

- 入口：`.claude/hooks/pre-bash.sh`
- 行为：只 hard block 极少数危险命令。
- 允许：pytest、rg、git diff、git status、python3 scripts/*、bash scripts/*。
- 输出：`tmp/agent_logs/<session>/hook-events.jsonl`

## 03. PreToolUse Write/Edit/MultiEdit/NotebookEdit

- 入口：`.claude/hooks/pre-write.sh`
- 行为：仓库内默认允许；敏感目录写入阻止；生成物路径警告。
- 不因为没有 active change 拦截普通编辑。

## 04. PostToolUse Write/Edit/MultiEdit/NotebookEdit

- 入口：`.claude/hooks/post-write.sh`
- 行为：写入 evidence。
- 输出：
  - `tmp/agent_logs/<session>/changed-files.jsonl`
  - `tmp/agent_logs/<session>/task-evidence/<change-id>.jsonl`
  - `tmp/agent_logs/<session>/hook-events.jsonl`

## 05. Stop / SubagentStop

- 入口：`.claude/hooks/stop.sh`
- 行为：区分只读会话与有写操作会话，执行完整质量门禁校验。
- 不执行重型测试。
- 失败时 exit 2。

## 06. ConfigChange

- 入口：`.claude/hooks/config-change.sh`
- 行为：记录配置变更到 `tmp/agent_logs/<session>/config-change-log.jsonl`。

## 07. Hook 测试保护策略

`tests/hooks/` 目录为**受保护目录**，包含所有 Hook 场景的校验脚本和单测。

**规则：任何对 `tests/hooks/` 下文件的修改，必须逐文件经用户确认后方可执行。**

原因：Hook 测试是 Claude Code 运行时安全/质量门的验证层，误改可能导致：
- 危险命令拦截失效
