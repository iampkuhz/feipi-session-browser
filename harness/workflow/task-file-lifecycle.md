# 任务文件生命周期

任务文件位于：

```text
tasks/changes/<change-id>/<NN>-<short-name>.md
```

任务文件满足以下条件才可执行：

- 目标（Goal）
- 范围（Scope）
- 需检查的文件
- 可能变动的文件
- 所需变更
- 验证命令
- 验收标准
- 手动 QA 检查清单

任务应足够小，以便在一次 Claude Code 运行中完成并验证。
