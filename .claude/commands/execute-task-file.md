# /execute-task-file

仅执行一个任务文件。

Arguments: `$ARGUMENTS`

规则：

- 读取任务文件。
- 读取链接的 OpenSpec 变更。
- 仅在任务指定的范围内实现。
- 运行任务文件中指定的验证命令。
- 用完成证据更新任务文件。
- 完成后停止。
