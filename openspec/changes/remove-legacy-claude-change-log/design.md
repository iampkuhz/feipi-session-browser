# 设计：移除旧版 `.claude/change-log.jsonl`

## 判断

`.claude/change-log.jsonl` 不再是当前校验链路的一部分：

- `PostToolUse` 实际入口是 `.claude/hooks/post-write.sh`。
- `post-write.sh` 调用 `python3 -m scripts.claude_hooks.main post-write`。
- 当前 evidence 由 `scripts/claude_hooks/evidence.py` 写入 `tmp/agent_logs/current/changed-files.jsonl` 和 `tmp/agent_logs/current/task-evidence/<change-id>.jsonl`。
- Stop/quality gate 读取的是 `tmp/agent_logs/current/changed-files.jsonl` 及 quality artifact，不读取 `.claude/change-log.jsonl`。

## 变更

- 删除 `.claude/change-log.jsonl`，避免把运行态日志留在项目配置目录。
- 删除 `scripts/hooks/log_file_change.py` 与 `scripts/agent_hooks/log_file_change.py`，它们只保留旧兼容写入逻辑，且未被当前 `.claude/settings.json` 绑定。
- 删除 `tests/backend/test_log_file_change.py`，避免继续为已移除脚本保留契约绑定。
- 更新历史 OpenSpec change 中的过时描述，指向当前 `tmp/agent_logs/current/*` evidence。

## 风险

如果外部手工流程仍直接调用 `scripts/hooks/log_file_change.py` 或 `scripts/agent_hooks/log_file_change.py`，该调用会失败。当前仓库 hook 配置未绑定这两个入口，仓库内校验链路应使用 `scripts.claude_hooks` 模块。
