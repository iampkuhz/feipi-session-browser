# 设计：remove-stale-harness-gates

## 当前状态

仓库有多处文档和配置把以下脚本列为默认完成门禁：

- `python3 scripts/harness/check_no_unfinished_markers.py`
- `python3 scripts/harness/validate_task_files.py`

它们的脚本实现仍是全仓或旧目录扫描，并未限定到当前 change，因此会因为历史文件和生成报告失败。

## 提议的方法

1. 从默认质量门列表移除这两个命令。
2. 从 `create_active_change.py` 的 `REQUIRED_GATES` 移除，避免新 active change 继续继承过期门禁。
3. 从 `scripts/quality/doctor.py` 移除聚合执行，避免 doctor 失败。
4. 在 `harness/quality/gates.md` 中保留“可选诊断”说明，明确脚本仍可手动运行。

### 关键决策

1. 保留脚本文件。它们仍可用于专项清理或未来重构，不需要在本次变更中删除。
2. 只移除“强制运行”身份。这样降低误伤范围，同时保持已有工具可发现。
3. 不清理历史 TODO 或旧 `tasks/README.md`。那些是独立治理工作，不属于本次门禁调整。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 未完成标记不再默认拦截 | 中 | 低 | 保留脚本为可选诊断；OpenSpec tasks 仍要求显式完成状态 |
| 旧式 tasks 文件格式不再默认检查 | 低 | 低 | 当前主流程使用 OpenSpec `tasks.md`，默认检查不再依赖顶层 `tasks/` |

## 回滚

恢复本次修改的门禁引用即可重新强制运行两个脚本。

## 验证

- [ ] `rg` 确认强制门禁列表不再引用这两个脚本。
- [ ] 保留的 harness/OpenSpec 验证通过。
- [ ] `python3 scripts/quality/doctor.py` 不再运行这两个脚本。
