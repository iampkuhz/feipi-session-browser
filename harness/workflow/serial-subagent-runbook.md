# 串行子 Agent 运行手册

使用子 agent 处理有边界的工作，而非无控并行。

推荐顺序：

1. `repo-mapper` 检查当前状态。
2. `openspec-planner` 创建或评审变更计划。
3. `task-slicer` 创建任务文件。
4. `implementer` 逐个执行任务。
5. `qa-verifier` 验证每个已完成的任务。

主 agent 不应 busy-wait。应委派有边界的任务，仅在完成报告返回后继续。
