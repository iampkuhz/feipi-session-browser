# diagnose-ui-gate — UI 质量门禁诊断

你正在诊断一个失败的确定性 UI 质量门禁。

## 规则

- 除非用户明确要求修复，否则**不要修改文件**。
- **不要**用主观判断替代确定性门禁。
- **不要**仅凭截图做判断；先读取 JSON 指标数据。
- 这是按需诊断命令，**不是** Stop hook 门禁。

## 输入

- 可选参数：变更 ID（change id）。
- 如无参数，读取 `ACTIVE_CHANGE_ID` 环境变量或 `tmp/active-change` 文件。
- 读取 `tmp/quality/<change-id>/quality-gate-summary.json`。
- 读取 `blockingFailures` / `artifacts` 中引用的每个失败门禁产物。

## 步骤

1. **读取质量门禁摘要** `tmp/quality/<change-id>/quality-gate-summary.json`。
   - 确认哪些门禁失败了（staticCssContract、templateContract、browserLayout、pytest）。
   - 读取 `blockingFailures` 获取失败代码和信息。

2. **读取具体门禁结果 JSON**。
   - `staticCssContract`：读取 `check_session_detail_static.py` 的输出。
   - `browserLayout`：读取 `session-detail-layout-result.json` 获取计算指标。

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
   - CSS：`src/session_browser/web/static/style.css`
   - 模板：`src/session_browser/web/templates/base.html`、`session.html`
   - 关注 `nextInspection` 中提到的选择器。

5. **提出最小修复方案**：
   - 指出需要的精确 CSS 规则或模板改动。
   - 说明为什么这是最小改动（不要重构）。
   - 说明哪些是确定性判断，哪些是 LLM 推断。

6. **提供精确验证命令**：
   - `python3 scripts/quality/run_quality_gate.py --target session-detail`
   - 或具体门禁：`python3 scripts/quality/check_session_detail_static.py`

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
python3 scripts/quality/run_quality_gate.py --target session-detail

确定性 vs 推断：[说明哪些是确定性的，哪些是 LLM 推断的]
```
