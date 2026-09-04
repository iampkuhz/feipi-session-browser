# Visual Gates 参考

本文件列出 session detail UI 开发相关的视觉质量门。修改 UI 后必须根据变更范围选择对应的 gate 运行。

## Gate 列表

| Gate 脚本 | 用途 | 触发条件 |
|---|---|---|
| `webResourceContracts` | Session detail 页面静态结构检查 | 改模板时必跑 |
| `webResourceContracts` | Session detail shell CSS 一致性检查 | 改 shell/layout CSS 时必跑 |
| `session-detail.spec.js` + `session-detail-migrated-gates.spec.js` | Session detail 交互 gate（Node Playwright） | 改 JS handler 时必跑 |
| `session-detail-layout.spec.js` | Session detail 布局 gate（Node Playwright） | 改布局或 shell 时必跑 |
| `browserBehaviorTests` | 真实浏览器交互与 handler 行为 | 改 JS 或模板按钮时必跑 |
| `webStaticRules` | 顶层 catalog Gate；内部 Java `css-ownership` rule 校验 ownership 并写出隔离 artifact | 改 CSS 时必跑 |
| `currentVersionPolicy` | Legacy CSS 检查 | 改 CSS 时必跑 |
| `webStaticRules` | 内部 Java `layout-inline-style` rule | 改模板时必跑 |
| `webStaticRules` | 内部 Java `raw-innerhtml` rule | 改 JS 时必跑 |

## 选择策略

- **只改模板 HTML**：`webResourceContracts` + `webStaticRules`（看 `layout-inline-style` RecipeStep）。
- **只改 CSS**：`webStaticRules`（看 `css-ownership` RecipeStep）+ `currentVersionPolicy` + `webResourceContracts`（如涉及 shell）。
- **只改 JS**：`browserBehaviorTests` + `webStaticRules`（看 `raw-innerhtml` RecipeStep）。
- **改布局或 shell**：Node Playwright 布局 gate + `webResourceContracts` + `webStaticRules`。
- **收口前**：运行静态 gate 与 `npm --prefix tests/playwright test --`。

## Baseline 文件与显式维护

- `config/web-quality-baselines.json` 的 `rules.layout-inline-style.entries` — 行内样式基线。
- `config/web-quality-baselines.json` 的 `rules.raw-innerhtml.entries` — innerHTML 基线。

修改 baseline 前必须确认变更是有意为之，不是为了绕过 gate。完成审阅后，才可显式执行唯一 Gradle task：

```bash
./gradlew :java:tests:quality-gates:runJavaQualityGates \
  -PfeipiJavaQualityRules=layout-inline-style \
  -PfeipiJavaQualityBaselineUpdateRules=layout-inline-style

./gradlew :java:tests:quality-gates:runJavaQualityGates \
  -PfeipiJavaQualityRules=raw-innerhtml \
  -PfeipiJavaQualityBaselineUpdateRules=raw-innerhtml
```

CSS ownership 没有可维护 baseline；运行 catalog 顶层 Gate `webStaticRules` 时，内部使用 Java
`css-ownership` rule 并保留隔离 artifact。单 rule 命令只用于 RecipeStep 诊断：

```bash
./gradlew :java:tests:quality-gates:runJavaQualityGates -PfeipiJavaQualityRules=css-ownership
```
