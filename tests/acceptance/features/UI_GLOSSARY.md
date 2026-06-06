# Glossary 页面 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 术语表页面（术语筛选卡、术语列表） |
| 关联源码 | `src/session_browser/web/templates/glossary.html` |
| 关联测试 | `tests/pages/test_glossary_page.py`、`tests/playwright/ui-contract.spec.ts` |
| 主要风险 | 术语表无 E2E 交互测试（筛选/搜索）；仅有 pytest 模板静态检查 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| UI-GLOSSARY-001 | P0 | visual | 术语表页模板（筛选卡 + 术语表） | 访问 `/glossary`，检查 DOM | `.page-head` 可见，`.metric-grid` 存在，`.filter-card` 可见，`.card.section` 和 `.data-table` 存在 | pytest | snapshot 更新条件：当术语表布局变更时需更新快照 | `tests/pages/test_glossary_page.py` |
| UI-GLOSSARY-002 | P0 | visual | 术语表页多视口截图 | 各视口访问 `/glossary` 截图 | 截图通过视觉回归，maxDiffPixelRatio <= 0.05 | Playwright | snapshot 更新条件：当 UI 布局/设计令牌/颜色变更时需更新快照 | `tests/playwright/ui-contract.spec.ts` |
| UI-GLOSSARY-003 | P2 | interaction | 术语筛选/搜索（空白待补充） | 待补充 E2E 测试 | 筛选后术语表内容变化，搜索后过滤 | Playwright | — | 待补充 |
