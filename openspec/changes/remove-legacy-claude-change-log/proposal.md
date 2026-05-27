# 提案：移除旧版 `.claude/change-log.jsonl`

## 背景

当前 hook 运行态已经使用 `tmp/agent_logs/current/changed-files.jsonl`、`hook-events.jsonl` 和 `task-evidence/<change-id>.jsonl` 记录可校验 evidence。`.claude/change-log.jsonl` 是早期兼容日志，内容粒度不足，且位于项目配置目录下，容易被误认为长期规格或校验依据。

## 目标

- 删除 `.claude/change-log.jsonl`。
- 删除仍会写入该文件的 legacy hook 脚本。
- 删除针对 legacy 脚本的测试绑定，保留当前 `scripts.claude_hooks` 测试作为 hook 输入、分类和 evidence 的校验来源。

## 非目标

- 不改变当前 `.claude/settings.json` 中实际绑定的 hook 入口。
- 不改变 `tmp/agent_logs/current/changed-files.jsonl`、`hook-events.jsonl`、`task-evidence/` 的运行态 evidence 机制。
