# Subagent 执行规约

仅当任务需要委派、并行探索、独立验证、迁移分析、UI 评审或大量日志隔离时读取本文件。

## 触发策略

- 主 agent 应主动寻找可委派边界：长任务、并行探索、独立 QA、日志/大输出隔离、OpenSpec 规划、UI 评审、迁移分析。
- 简单单文件小改、无明确 scope、强串行推理、或多个 agent 会写同一文件时，不委派。
- 工具层不允许委派时，主 agent 按本规约自行执行，并在结果中保留范围和验证证据。

## Handoff 字段

委派前必须给子 agent 最小上下文：

| 字段 | 要求 |
|---|---|
| `Goal` | 本次子任务目标 |
| `Task id` | 对应 OpenSpec task 或本轮任务编号 |
| `Task source` | `tasks.md`、用户请求或明确文件片段 |
| `Allowed files/directories` | 可读写范围；只读任务写明只读 |
| `Forbidden files/directories` | 禁止触碰范围 |
| `Required context files` | 必读的最少文件 |
| `Expected output` | 固定输出结构和判断标准 |
| `Validation command` | 子任务应运行或建议运行的验证 |
| `Failure policy` | 失败、阻断、未知时如何返回 |

## 角色边界

| Agent | 适用任务 | 写权限边界 |
|---|---|---|
| `openspec-planner` | OpenSpec proposal、tasks、spec 评审 | 仅 OpenSpec 范围 |
| `repo-mapper` | 只读结构映射和影响面分析 | 不写文件 |
| `implementer` | 明确 task 的有界实现 | 只写 handoff 指定范围 |
| `qa-verifier` | 验证、回归风险、质量门证据 | 不写文件 |
| `ui-architect` | UI 布局、交互、视觉契约分析 | 默认不写文件 |
| `migration-planner` | 迁移方案、历史材料合并 | 不写文件 |
| `mhtml-export-specialist` | HTML/MHTML 导出与离线交互 | 只写导出相关范围 |

## 输出契约

子 agent 必须返回 `PASS`、`FAIL` 或 `BLOCKED`，并列出：

- 读取或修改的文件；
- 关键结论；
- 已运行或建议运行的验证命令；
- 剩余风险；
- 若阻断，给出下一步可执行动作。
