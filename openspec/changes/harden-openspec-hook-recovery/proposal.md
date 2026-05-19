# 提案：harden-openspec-hook-recovery

## 问题

当前 OpenSpec hook 链路会在 Stop 阶段发现变更不完整，但失败结果以非阻塞 warning 暴露，LLM 不一定会收到可继续执行的修复任务。另一个问题是 `create_active_change.py` 在 `.agent/active_change.json` 已存在时不会切换到新 change，导致后续 PreToolUse、PostToolUse、Stop 都继续引用旧 change。

这会造成两个具体故障：

- 新任务已经创建了 `openspec/changes/<new-change>/`，但 active sentinel 仍指向旧 change。
- 受保护文件编辑被允许，证据被记录到旧 change 或错误 change，Stop 阶段才反复报错。

## 范围

**包含：**

- 让 `create_active_change.py` 在请求新 change 时更新 active sentinel。
- 让受保护编辑前置检查验证 active change 的必需文件。
- 让 Stop 检查使用阻塞退出码，并输出可执行的修复步骤。
- 更新 hook 工作流文档。

**不包含（非目标）：**

- 不修改产品 UI、Session 列表页或已有半成品 Sessions 变更。
- 不改变 OpenSpec 归档流程。
- 不提交 `.agent/active_change.json` 或本地 evidence 文件。

## 用户影响

Agent 在创建新 OpenSpec change 后会真正切换到该 change，子 agent 不会继续沿用旧上下文。Stop 阶段遇到不完整状态时，会以阻塞结果和明确动作提示促使 LLM 继续修复，而不是只留下不易执行的 stderr 噪音。

## 受影响的组件

- `.claude/hooks/stop_check.sh`
- `scripts/openspec/create_active_change.py`
- `scripts/agent_hooks/guard_active_openspec_change.py`
- `scripts/agent_hooks/stop_validate_change.py`
- `harness/workflow/hook-enforcement.md`
- `harness/workflow/subagent-execution.md`

## 验证策略

1. 运行相关 hook 自测。
2. 运行 harness/OpenSpec 结构质量门。
3. 检查 `git status --short`，确认 Sessions UI 半成品未被暂存。
