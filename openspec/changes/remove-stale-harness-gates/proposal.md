# 提案：remove-stale-harness-gates

## 问题

`check_no_unfinished_markers.py` 和 `validate_task_files.py` 目前被列为默认完成门禁，但它们的检查范围已经和当前仓库形态不匹配：

- `check_no_unfinished_markers.py` 全仓扫描 `TODO/FIXME/TBD/PLACEHOLDER/STUB`，会命中脚本自身、历史报告和仓库级 TODO 文档。
- `validate_task_files.py` 扫描顶层 `tasks/` 目录，要求旧式任务模板章节；当前主流程已经转向 OpenSpec change 的 `tasks.md`。

这两个脚本作为专项诊断仍有价值，但不应阻断每个 change 的完成。

## 范围

**包含：**

- 从默认质量门、active change 默认 `required_gates`、doctor 聚合和启动说明中移除这两个强制门禁。
- 在质量门文档中保留它们的可选诊断定位。

**不包含（非目标）：**

- 不删除脚本文件。
- 不清理历史 TODO、报告产物或顶层 `tasks/README.md`。
- 不修改产品 UI 或 Sessions 列表半成品。

## 用户影响

默认验证将只覆盖当前仍有效的结构和 OpenSpec 布局检查，避免与当前任务无关的历史残留阻塞完成。需要专项清理时，仍可手动运行这两个脚本。

## 受影响的组件

- `AGENTS.md`
- `CLAUDE.md`
- `.claude/commands/openspec-validate.md`
- `.claude/skills/change/SKILL.md`
- `.claude/skills/change/reference/workflow.md`
- `scripts/openspec/create_active_change.py`
- `scripts/quality/doctor.py`
- `harness/quality/gates.md`
- `harness/quality/gates.yaml`
- `harness/context/repo-context.md`

## 验证策略

1. 确认强制门禁列表不再引用这两个脚本。
2. 运行保留的 harness/OpenSpec 验证。
3. 运行 `scripts/quality/doctor.py`，确认不再因这两个脚本失败。
