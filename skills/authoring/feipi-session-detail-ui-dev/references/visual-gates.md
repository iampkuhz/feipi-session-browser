# Visual Gates 参考

本文件列出 session detail UI 开发相关的视觉质量门。修改 UI 后必须根据变更范围选择对应的 gate 运行。

## Gate 列表

| Gate 脚本 | 用途 | 触发条件 |
|---|---|---|
| `web.session-detail-static` | Session detail 页面静态结构检查 | 改模板时必跑 |
| `web.session-detail-static` | Session detail shell CSS 一致性检查 | 改 shell/layout CSS 时必跑 |
| `session-detail.spec.js` + `session-detail-migrated-gates.spec.js` | Session detail 交互 gate（Node Playwright） | 改 JS handler 时必跑 |
| `session-detail-layout.spec.js` | Session detail 布局 gate（Node Playwright） | 改布局或 shell 时必跑 |
| `web.js-action-handlers` | JS action handler 完整性检查 | 改 JS 或模板按钮时必跑 |
| `web.css-ownership` | CSS ownership 校验 | 改 CSS 时必跑 |
| `repository.repo-slimming` | Legacy CSS 检查 | 改 CSS 时必跑 |
| `web.layout-inline-style` | Inline style 检查 | 改模板时必跑 |
| `web.raw-innerhtml` | Raw innerHTML 检查 | 改 JS 或模板时必跑 |

## 选择策略

- **只改模板 HTML**：`web.session-detail-static` + `web.layout-inline-style` + `web.raw-innerhtml`。
- **只改 CSS**：`web.css-ownership` + `repository.repo-slimming` + `web.session-detail-static`（如涉及 shell）。
- **只改 JS**：`web.js-action-handlers` + `web.raw-innerhtml` + Node Playwright 交互 gate。
- **改布局或 shell**：Node Playwright 布局 gate + `web.session-detail-static` + `web.layout-inline-style`。
- **收口前**：运行静态 gate 与 `npx playwright test --config=playwright.config.js`。

## Baseline 文件

- `scripts/checks/layout_inline_style_baseline.json` — 行内样式基线数据。
- `scripts/checks/innerhtml_baseline.json` — innerHTML 基线数据。

修改 baseline 前必须确认变更是有意为之，不是为了绕过 gate。
