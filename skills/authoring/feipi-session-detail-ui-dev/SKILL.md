---
name: feipi-session-detail-ui-dev
disable-model-invocation: true
description: 用于 Session Detail UI、Jinja 模板、CSS、前端交互和视觉质量门相关开发；后端 parser 或 OpenSpec 编排不要使用。
---

# Session Detail UI 开发

本 skill 为 session detail 页面、Jinja 模板、CSS ownership、前端 JS 交互和视觉质量门相关开发提供最小上下文执行规则。解决 UI 改造时上下文过长、CSS ownership 模糊、按钮失效、视觉回归漏测等问题。

## 何时使用

- 修改 session detail 页面的 Jinja / HTML 模板。
- 新增或修改 session detail 相关 CSS（布局、样式、ownership）。
- 修改前端 JS action handler（按钮点击、展开折叠、交互事件）。
- 处理 session detail shell、layout、interaction 相关变更。
- 修复视觉回归或布局错乱问题。
- 新增或修改 UI 质量门（static check、Playwright gate）。

## 不要何时使用

- 纯后端 parser 修改 → 使用 `feipi-session-ingestion-dev`。
- 纯 Java/Gradle 功能开发 → 使用 `feipi-java-feature-dev`。
- 纯 OpenSpec 编排 → 使用 `feipi-openspec-orchestrate-change`。
- 纯质量门诊断（非 UI 专项）→ 使用 `feipi-quality-gate-diagnosis`。
- MHTML 导出相关 → 使用 `feipi-mhtml-export-dev`。

## 输入最小化

只读取以下必要片段：

1. 目标 Jinja 模板文件 — 只读与当前变更直接相关的模板和 macro。
2. 对应 CSS 文件 — 只读与当前页面相关的 ownership 区域。
3. 对应 JS 文件 — 只读与当前 action handler 相关的事件绑定。
4. `references/ui-boundaries.md` — 模板、CSS、JS 边界定义。
5. `references/visual-gates.md` — 需要运行的 UI gate 列表。

不要全仓库扫描模板或 CSS。不要预读无关页面的模板。

## 执行步骤

1. 定位具体页面路径和模板：使用 `rg` 定位目标页面名称，确定对应的 Jinja 模板文件。
2. 查找对应 CSS ownership 和 JS action handler：确认哪些 CSS 文件管理该页面样式，哪些 JS 文件绑定交互事件。
3. 确认是否涉及 session detail shell、layout、interaction：判断变更范围是否超出单个组件，影响整体 shell 或 layout。
4. 先用 fixture 页面复现，不读取真实 session：使用已有 fixture 或 mock 数据验证 UI 变更效果。
5. 修改模板时优先使用已有 macro 和 class：不重新发明已有组件，复用现有 macro。
6. CSS 使用当前组件命名且每个规则必须有明确 ownership。
7. 修改 JS 时同步交互测试：确保 `browserBehaviorTests` 用真实浏览器行为覆盖新增或修改的 handler。
8. 跑静态 UI gate 和必要 Playwright gate：至少运行 `webResourceContracts`，涉及布局时追加 layout gate。
9. 输出截图/布局风险和未覆盖交互：报告视觉风险和交互覆盖盲区。

## 文件边界

- Jinja 模板：`java/web/src/main/resources/templates/` 下 session detail 相关模板。
- CSS 文件：`java/web/src/main/resources/static/css/` 下 session detail 相关样式。
- JS 文件：`java/web/src/main/resources/static/js/` 下 session detail 相关交互脚本。
- UI 质量门：`java/web/src/test/java/com/feipi/session/browser/web/page/`、
  `java/tests/playwright/session-detail*.spec.js`。
- Web 源码政策：catalog 顶层 Gate `webStaticRules`；内部继续用 Java `css-ownership`、
  `layout-inline-style`、`raw-innerhtml` 等 rule ID 分诊断。
- P4 Web gate baseline：`java/tests/quality-gates/config/web-quality-baselines.json` 中的 `rules.raw-innerhtml.entries` 与
  `rules.layout-inline-style.entries`；CSS ownership Java rule 继续写出按运行隔离的 artifact，artifact
  不是可维护 baseline。

不要跨边界修改后端 parser 或 Java 产品代码。不要在模板中直接嵌入 inline style。

## 验证门禁

以下门禁不是每次都全部运行，但触发时 required gate 不能 skipped：

- `./java/gradlew -p java :java:web:test --tests '*WebStaticResourceContractTest'` — session detail 静态检查与 shell CSS 一致性。
- `npm --prefix java/tests/playwright test -- session-detail.spec.js session-detail-behavior-contracts.spec.js` — 交互 gate。
- `npm --prefix java/tests/playwright test -- session-detail-layout.spec.js` — 布局 gate。
- `python3 scripts/gates/cli.py run --mode incremental --gate browserBehaviorTests` — 浏览器交互 Gate。
- `python3 scripts/gates/cli.py run --gate webStaticRules --mode incremental` — 顶层 Web 源码政策 Gate；报告内部
  Java rule IDs 用于定位 CSS ownership、inline style 与 raw innerHTML。
- `python3 scripts/gates/cli.py run --mode incremental --gate currentVersionPolicy` — 稳定内部标识检查。
- `./java/gradlew -p java :java:tests:quality-gates:runJavaQualityGates -PfeipiJavaQualityRules=layout-inline-style` — inline style 检查。
- `./java/gradlew -p java :java:tests:quality-gates:runJavaQualityGates -PfeipiJavaQualityRules=raw-innerhtml` — raw innerHTML 检查。

选择策略：

- 只改模板 → 至少运行 `webResourceContracts` + catalog Gate `webStaticRules`。
- 改 CSS → 追加 `webResourceContracts` + `currentVersionPolicy`。
- 改 JS → 运行 `browserBehaviorTests`，不再维护第二套正则式 handler 扫描。
- 改布局或 shell → 追加 Node Playwright 布局 gate + catalog Gate `webStaticRules`，按
  `layout-inline-style` 内部 rule 定位。
- 收口前 → 运行全部 UI gate。

## 输出格式

使用 `templates/report.md` 模板。变更摘要必须包含：

- 改动的模板、CSS、JS 文件列表。
- CSS ownership 变化（如有）。
- 视觉回归风险评估。
- 门禁运行结果。
- 未覆盖的交互或截图风险。
- 后续风险或 TODO。
