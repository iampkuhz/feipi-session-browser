# 确定性质量门

仅当任务涉及质量门实现、Stop 门禁、验证失败诊断或 summary artifact 语义时读取本文件。

## 原则

- required gate 只能以自动化结果为准，不用 LLM 主观评分替代。
- summary 不允许出现 `score`、`rating`、`qualityScore` 等主观字段。
- required gate 失败、缺失或被跳过时，不得给 overall `PASS`。
- changed files 只用于选择 target；target 一旦选中，内部 gate 必须运行完整 baseline。
- 路径映射没有选中某个 target/gate 时，状态是 not triggered，不是 skipped。
- target/gate 被人工指定、路径映射选中、required baseline、full regression 或 release regression 要求运行后，测试框架报告的 skipped outcome 视为未验证完成；必须补齐 fixture/env、调整触发映射，或以 `FAIL`/`BLOCKED` 收口。
- full regression 和 release regression 必须证明完整选中集合是 `0 skipped`；任何 skipped tests 都不能作为 PASS 证据。
- Playwright gate 被选中时必须提供必要的 fixture URL，并且命令输出中出现 skipped tests 时不得 PASS。
- `noTestSkips` gate 运行 `scripts/quality/check_no_test_skips.py`，用于阻止新增 pytest / Playwright skip API；该 gate 失败时不得降级为 warning。

## 当前执行链

1. agent 入口调用 `scripts/harness/agent_stop_check.py`。
2. Stop 门禁合并 `tmp/agent_logs/current/changed-files.jsonl` 和 `git status --short --untracked-files=all`。
3. `scripts/claude_hooks/classify.py` 将路径映射到 quality target。
4. `scripts/quality/run_required_quality_gates.py` 运行需要的 target。
5. `scripts/quality/run_quality_gate.py` 写入 `tmp/quality/<change-id>/quality-gate-summary.<target>.json`。

## Trigger vs Skip

| 场景 | 语义 | 允许作为 PASS |
|---|---|---|
| changed-files 映射未命中某个 target/gate | not triggered | 是；因为该测试不在本次 required baseline 中 |
| target/gate 被映射选中但命令未运行 | missing / BLOCKED | 否 |
| target/gate 被映射选中且测试框架报告 skipped tests | skipped after trigger | 否 |
| selected / required gate 出现 skipped outcome | FAIL 或 BLOCKED | 否 |
| full regression / release regression 报告非 `0 skipped` | FAIL 或 BLOCKED | 否 |
| full regression / release regression 中测试缺少 fixture/env | BLOCKED 或 FAIL | 否 |
| `check_no_test_skips.py` 发现新增 skip API | FAIL | 否 |

不得用“跳过”描述 not triggered 的测试；也不得用 not triggered 掩盖已经确认需要运行的测试。

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
