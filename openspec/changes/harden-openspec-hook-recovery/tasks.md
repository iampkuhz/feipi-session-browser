# 任务：harden-openspec-hook-recovery

从上到下遍历任务。不要跳过或重排。对每个任务：完成工作、标记完成（`- [x]`），并添加简短验证说明。

## 任务 1：修复 active change 切换

- [x] 修改 `scripts/openspec/create_active_change.py`，确保请求新 change 时更新 `.agent/active_change.json`。

  **验证：** 运行脚本创建本 change，并用临时 change smoke test 确认输出包含 `Updated active change`。

## 任务 2：前置阻止不完整 change

- [x] 修改 `scripts/agent_hooks/guard_active_openspec_change.py`，受保护编辑前验证 active change 必需文件。

  **验证：** `python3 scripts/agent_hooks/guard_active_openspec_change.py --self-test` 通过。

## 任务 3：Stop 阶段输出可修复阻塞

- [x] 修改 `scripts/agent_hooks/stop_validate_change.py` 与 `.claude/hooks/stop_check.sh`，阻塞状态返回 exit 2 并输出继续修复步骤。

  **验证：** `python3 scripts/agent_hooks/stop_validate_change.py --self-test` 通过。

## 任务 4：同步文档

- [x] 更新 hook/subagent 工作流文档，说明 active change 切换、前置完整性检查和阻塞语义。

  **验证：** 待最终质量门统一验证。

## 任务 5：提交范围确认

- [x] 只暂存本次 hook/OpenSpec 相关文件，不暂存既有 Sessions UI 半成品。

  **验证：** 暂存前后使用 `git diff --cached --stat` 检查提交范围。
