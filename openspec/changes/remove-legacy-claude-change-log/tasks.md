# 任务：remove-legacy-claude-change-log

从上到下执行任务；完成后标记为 `- [x]` 并记录验证。

## 任务 1：确认当前 hook evidence 链路

- [x] 确认 `.claude/settings.json` 的 `PostToolUse` 入口经 `.claude/hooks/post-write.sh` 调用 `scripts.claude_hooks.main post-write`，当前 evidence 写入 `tmp/agent_logs/current/changed-files.jsonl` 与 `task-evidence/`。

  **验证：** 已用 `rg`、`sed` 检查 hook 配置和 `scripts/claude_hooks/evidence.py`。

## 任务 2：移除旧版日志和兼容脚本

- [x] 删除 `.claude/change-log.jsonl`、`scripts/hooks/log_file_change.py`、`scripts/agent_hooks/log_file_change.py`。

  **验证：** 待运行 `rg "change-log\\.jsonl|log_file_change\\.py"` 确认无过时绑定。

## 任务 3：同步测试和文档引用

- [x] 删除 legacy 脚本测试绑定，并将历史 OpenSpec 描述改为当前 evidence 路径。

  **验证：** 待运行相关 hook 测试和 harness/OpenSpec 校验。

## 任务 4：提交

- [x] 暂存本次相关文件并提交 git，避免纳入其他未提交改动。

  **验证：** 已运行相关 hook 测试、harness/OpenSpec 校验和 `bash scripts/harness/doctor.sh`；提交前检查 `git diff --cached --name-only`。
