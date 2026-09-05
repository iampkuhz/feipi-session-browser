# diagnose-ui-gate — UI 质量门禁诊断

你正在诊断一个失败的确定性 UI 质量门禁。

## 规则

- 除非用户明确要求修复，否则**不要修改文件**。
- **不要**用主观判断替代确定性门禁。
- **不要**仅凭截图做判断；先读取 JSON 指标数据。
- 这是按需诊断命令，**不是** Stop hook 门禁。

## 输入

- 可选参数：明确的 run id。
- 如无参数，读取 `tmp/quality/runs/latest.json` 指向的 immutable run。
- 读取 `tmp/quality/runs/<run-id>/summary.json`、`plan.json` 和 `logs/`。

## 步骤

1. **读取质量门禁摘要** `tmp/quality/runs/<run-id>/summary.json`。
   - 确认哪些顶层门禁失败了（`webStaticRules`、`webResourceContracts`、`browserVisualTests`）。
   - 读取 `gateResults` 的状态、reason、RecipeStep 和日志路径。

2. **读取具体门禁结果 JSON**。
   - `webStaticRules`：展开 Java `static-resource-contract`、`template-contract`、`css-ownership` 等内部 rule 输出。
   - `webResourceContracts`：读取 `:java:web:test` 中资源契约测试的输出。
   - `browserVisualTests`：读取 `session-detail-layout-result.json` 获取计算指标。

3. **将失败代码映射到根因**：
   - `MISSING_PHASE1_HIDE_LEFT_OVERRIDE` → CSS 特异性级联冲突。
   - `MISSING_PHASE1_MAIN_GRID_COLUMN` → `.main` 缺少 `grid-column: 1 / -1`。
   - `HERO_MAIN_STILL_TWO_COLUMN` → hero 布局仍为双列。
   - `HERO_TITLE_UNSAFE_ANYWHERE_WRAP` → 标题使用 `overflow-wrap: anywhere`。
   - `SHELL_ZERO_COLUMN` → `body.hide-left` 覆盖了 `phase1-shell`，`.main` 落入 0px 列。
   - `MAIN_WIDTH_TOO_SMALL` → 计算宽度低于 1200px 阈值。
   - `TITLE_OVERLAPS_KPIS` → 标题与 KPI 的 DOM 顺序或 CSS 定位问题。
   - `HORIZONTAL_SCROLL` → 内容宽于视口。

4. **检查相关源码文件**：
   - CSS：`java/web/src/main/resources/static/css/`
   - 模板：`java/web/src/main/resources/templates/`
   - 关注 `nextInspection` 中提到的选择器。

5. **提出最小修复方案**：
   - 指出需要的精确 CSS 规则或模板改动。
   - 说明为什么这是最小改动（不要重构）。
   - 说明哪些是确定性判断，哪些是 LLM 推断。

6. **提供精确验证命令**：
   - `python3 scripts/gates/cli.py run --mode full --target web-interface`
   - 或具体门禁：`./java/gradlew -p java :java:web:test --tests '*WebStaticResourceContractTest'`

## 输出格式

```
观察到的失败项：
- [门禁名]: [失败代码] - [信息]

可能的根因：
- [解释]

需检查的文件：
- [文件路径] — [要看什么]

最小修复方案：
1. [具体改动]
2. [具体改动]

验证命令：
python3 scripts/gates/cli.py run --mode full --target web-interface

确定性 vs 推断：[说明哪些是确定性的，哪些是 LLM 推断的]
```
