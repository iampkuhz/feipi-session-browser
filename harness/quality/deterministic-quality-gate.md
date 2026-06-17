# 确定性质量门

仅当任务涉及质量门实现、Stop 门禁、验证失败诊断或 summary artifact 语义时读取本文件。

## 原则

- required gate 只能以自动化结果为准，不用 LLM 主观评分替代。
- summary 不允许出现 `score`、`rating`、`qualityScore` 等主观字段。
- required gate 失败、缺失或被跳过时，不得给 overall `PASS`。
- changed files 只用于选择 target；target 一旦选中，内部 gate 必须运行完整 baseline。

## 当前执行链

1. agent 入口调用 `scripts/harness/agent_stop_check.py`。
2. Stop 门禁合并 `tmp/agent_logs/current/changed-files.jsonl` 和 `git status --short --untracked-files=all`。
3. `scripts/claude_hooks/classify.py` 将路径映射到 quality target。
4. `scripts/quality/run_required_quality_gates.py` 运行需要的 target。
5. `scripts/quality/run_quality_gate.py` 写入 `tmp/quality/<change-id>/quality-gate-summary.<target>.json`。

## Summary 语义

| 字段 | 要求 |
|---|---|
| `status` | `PASS`、`FAIL` 或 `BLOCKED` |
| `target` | quality target 名称 |
| `changeId` | 本次变更 ID；未知时可为 `unknown` |
| `requiredGates` | 每个 required gate 的状态 |
| `blockingFailures` | 阻断项列表 |
| `warnings` | 非阻断告警 |
| `artifacts` | 结构化证据路径 |
| `gateDetails` | 各 gate 命令、耗时和输出摘要 |

## 失败处理

- gate 失败先看结构化 summary 和详细日志，不猜测通过。
- 若是环境阻断，状态保持 `BLOCKED`，输出可复现命令。
- 若发现 target 选择遗漏，先修 `scripts/claude_hooks/classify.py` 或 `scripts/quality/quality_targets.py`。
