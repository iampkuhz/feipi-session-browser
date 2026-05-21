# 06 Validation Contract

## 每个任务至少运行

```bash
python scripts/qa/ui/check_ui_contracts.py
python -m pytest
```

## 如果涉及 JS

```bash
node --check src/session_browser/web/static/js/<file>.js
```

## 如果涉及核心 UI 页面

Playwright 截图验收：

```text
1440x900
1280x800
1180x800
```

## 静态检查必须覆盖

- 禁止 vN/patch CSS 引用。
- 禁止 inline style/script/onclick。
- 按钮必须有 data-action 或 href。
- 图标必须有说明文档条目。
- Token 缩写规则。
- Pagination 只显示 prev/input/next。
- metric grid card 等宽。
- 表头/单元格对齐一致。
- card/button 内图文垂直居中。

## QA Coverage Status

> 本章节为 T014 安装时追加的交叉验证记录，对照现有 QA 基础设施。
> 最后更新：2026-05-21

### 1. check_ui_contracts.py 已覆盖的规则

| 合同规则 | 检查方式 | 状态 |
|---|---|---|
| 禁止 vN/patch CSS 引用 | `FORBIDDEN_NAME_PATTERNS` 匹配 `v\d+.(css\|js\|html)`、`patch|fix|overlay.(css\|js)`；`FORBIDDEN_TEXT_PATTERNS` 匹配 `session-browser-v\d+\.css`、`dashboard-v\d+\.css`、`session_browser_ui_v\d+\.js` | 已覆盖 |
| 禁止 inline style/script/onclick | `FORBIDDEN_TEXT_PATTERNS` 匹配 `onclick=`、`style=`、`<script`（非外部 src） | 已覆盖 |
| 按钮必须有 data-action 或 href | 正则扫描 `<button>` 标签，检查 `data-action`/`type="submit"`；宏定义内的按钮跳过 | 已覆盖（部分：仅检查 button 标签，未检查 a.btn） |

### 2. check_dom_contracts.py 已覆盖的规则

| 合同规则 | 检查方式 | 状态 |
|---|---|---|
| Pagination 只显示 prev/input/next | 检查 `ui_primitives.html` 中是否存在 `prev` 和 `next` 文本 | 已覆盖（仅存在性检查，不验证 "仅 prev/input/next" 模式） |
| Token 缩写规则 | 检查 Python 代码中是否存在 `format_compact_token` 或 `format_number` | 已覆盖（仅检查过滤器是否存在，不验证实际输出） |

### 3. pytest (test_ui_contract_static.py) 已覆盖的规则

| 合同规则 | 检查方式 | 状态 |
|---|---|---|
| 禁止 inline onclick | 遍历所有 .html 模板，断言 `onclick=` 不存在 | 已覆盖 |
| 禁止 vN/patch CSS 引用 | 遍历所有 .html 模板，断言不包含 `session-browser-v`、`dashboard-v`、`-patch.css`、`-fix.css`、`-overlay.css` | 已覆盖 |

### 4. 尚无 QA 脚本覆盖的规则（需后续补充）

| 合同规则 | 缺口说明 | 建议实现方式 |
|---|---|---|
| 图标必须有说明文档条目 | 无脚本验证图标与 `docs/ui/contracts/05-icon-behavior-detailed.md` 的一致性 | 新建 `scripts/qa/ui/check_icon_docs.py`：扫描生产模板中的 Unicode 符号和 icon class，与图标文档交叉比对 |
| metric grid card 等宽 | 无脚本验证 CSS 中 `grid-template-columns` 等宽规则 | 可在 `check_ui_contracts.py` 中增加 CSS 规则检查，或在 Playwright 中测量 DOM |
| 表头/单元格对齐一致 | 无脚本验证 DataTable 表头与数据单元格的 alignment/padding 一致性 | 需 Playwright 截图比对或 DOM 计算检查 |
| card/button 内图文垂直居中 | 无脚本验证 `align-items: center` 等 CSS 规则 | 可在 `check_ui_contracts.py` 中检查 CSS 文件，或 Playwright 中检查 computed style |
| JS 语法检查 (`node --check`) | 合同要求但未集成到自动化流程 | 可在 CI 脚本或 `harness/doctor.sh` 中添加 `node --check` 循环 |

### 5. Playwright viewport 配置对比

| 合同要求 | 当前实现 (ui-contract.spec.ts) | 差距 |
|---|---|---|
| 1440x900 | 截图命名为 `${name}-1440.png`，但未显式设置 viewport（依赖 Playwright 默认值） | 可能不匹配 1440x900；需确认 playwright.config.ts 默认 viewport |
| 1280x800 | 无对应截图测试 | **缺失** |
| 1180x800 | 无对应截图测试 | **缺失** |

**结论**：当前 `ui-contract.spec.ts` 仅覆盖 1 个 viewport（且未显式设置尺寸），合同要求 3 个 viewport 截图验收。需在 Playwright 配置或 spec 中补充 `viewportSize` 设置和多尺寸截图。
