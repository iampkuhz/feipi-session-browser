# UI 门禁诊断边界

## 概览

质量门禁系统分为两层：

| 层级 | 类型 | 触发方式 | 示例 |
|---|---|---|---|
| **确定性门禁** | 自动化脚本 | Stop hook、质量运行器 | 静态 CSS 检查、模板契约 pytest、浏览器布局门禁 |
| **按需 LLM 诊断** | 手动触发 | 用户调用 `/diagnose-ui-gate` | 根因分析、修复建议 |

## 确定性门禁

这些自动运行并可阻塞 stop hook：

- `scripts/quality/check_session_detail_static.py` — 静态 CSS/模板文本检查
- `scripts/quality/run_session_detail_layout_gate.py` — Playwright 计算布局指标
- `tests/test_session_detail_layout_contract.py` — 模板结构 pytest
- `scripts/quality/run_quality_gate.py` — 统一运行器，编排所有门禁

**属性：**
- 无需 LLM 推断。
- 输出为结构化 JSON。
- 结果写入 `.agent/quality/<change-id>/`。
- Stop hook 读取这些产物以执行门禁。

## 按需 LLM 诊断

由 `/diagnose-ui-gate` 命令触发。

**属性：**
- 仅手动触发——stop hook 永远不会调用。
- 读取确定性门禁输出的 JSON，然后使用 LLM 推理来解读失败。
- 可建议修复，但除非用户明确要求，否则不修改文件。
- 不能覆盖或伪造确定性门禁结果。

**允许推断：**
- 复杂 CSS cascade 根因。
- 失败截图与布局意图的差异。
- 多种修复方案之间的权衡。
- 哪些文件最可能需要处理。

**不允许伪造：**
- `quality-gate-summary.json` PASS 状态。
- 浏览器计算指标。
- 截图产物。
- Stop hook 证据。

## 禁止

- Stop hook 不得调用 LLM 诊断命令。
- Stop hook 不得启动子 agent、调用 Claude、Codex 或 Qoder。
- Stop hook 不得直接运行浏览器测试。
- LLM 诊断不得用主观判断替代确定性门禁。

## 诊断命令

位置：`.claude/commands/diagnose-ui-gate.md`

用法：
```
/diagnose-ui-gate           # 使用当前活跃变更
/diagnose-ui-gate fix-xyz   # 指定变更 ID
```
