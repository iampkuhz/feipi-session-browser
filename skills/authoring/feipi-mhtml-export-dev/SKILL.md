---
name: feipi-mhtml-export-dev
disable-model-invocation: true
description: 用于 Session Detail 离线 HTML/MHTML 导出功能研发；普通页面 UI 或 parser 改造不要使用。
---

# MHTML / 离线 HTML 导出开发

本 skill 为 session detail 页面的自包含 HTML/MHTML 导出、内联资源、离线交互保真和 current-session tab 行为提供最小上下文执行规则。解决导出文件依赖外部网络、离线打开后交互失效、敏感字段泄露等问题。

## 何时使用

- 新增或修改 MHTML / 自包含 HTML 导出功能。
- 内联 CSS/JS 资源到导出文件。
- 处理离线打开后 tabs、modal、collapse 等交互保真。
- 修改 current-session tab 在导出文档中的行为。
- 处理导出文件中的敏感字段脱敏策略。
- 新增导出相关的 fixture-based 测试。

## 不要何时使用

- 纯 session detail 页面 UI 修改（不涉及导出）→ 使用 `feipi-session-detail-ui-dev`。
- 纯后端 parser 修改 → 使用 `feipi-session-ingestion-dev`。
- 纯 Java/Gradle 功能开发 → 使用 `feipi-java-feature-dev`。
- 纯 OpenSpec 编排 → 使用 `feipi-openspec-orchestrate-change`。
- 纯质量门诊断（非导出专项）→ 使用 `feipi-quality-gate-diagnosis`。

## 输入最小化

只读取以下必要片段：

1. 导出入口按钮和后端接口 — 定位触发生成 MHTML 的代码路径。
2. 目标 Jinja 模板和静态资源 — 只读与导出直接相关的模板和 CSS/JS。
3. 已有 fixture 或 mock 数据 — 用于验证导出效果，不读取真实 session。
4. `references/export-contract.md` — 导出对象、包含/不包含内容、交互保真要求。
5. `references/offline-resource-contract.md` — CSS/JS 内联规则、外链禁止策略。
6. `references/security-contract.md` — 敏感字段脱敏和导出确认规则。

不要全仓库扫描模板或静态资源。不要预读无关页面或真实 session 数据。

## 执行步骤

1. 定位导出入口按钮和后端接口：使用 `rg` 定位导出按钮（如 "Export HTML" 或 "Download MHTML"），找到对应的事件绑定和后端生成接口。
2. 定位 session detail 页面所需 CSS/JS/assets：确认导出文件需要内联哪些样式表、脚本和静态资源，列出完整清单。
3. 明确导出范围：当前 session detail 页面，不含外部跳转：导出文档只包含当前页面的内容，不内联导航到其他路由的链接目标页面。
4. 生成前展开/收集 round、sr、result、request、response 等信息：在生成导出文件前，确保所有需要展示的折叠区域（round 详情、tool execution result、request/response payload 等）已被展开或数据已收集完毕。
5. 资源内联，禁止依赖公网：所有 CSS/JS/图片/字体必须内联到导出文件中，不允许任何外部网络请求（包括 CDN、Google Fonts 等）。
6. 敏感字段遵循 UI 当前脱敏状态或显式导出策略：导出文件中的 API key、token、密钥等敏感信息必须按照 UI 当前的脱敏状态处理，或有明确的导出策略说明。
7. 离线文件打开后 tabs/modal/collapse 等关键交互可用：导出文档在离线打开时，tabs 切换、modal 弹窗、collapse 展开、trace 展开和 attribution 展开等关键交互必须可用。
8. 导出文件大小和性能有上限说明：对导出文件的大小设定上限（如 50MB），并在 UI 或文档中说明超限时的行为和降级策略。
9. 增加 fixture-based 测试：使用已有 fixture 或 mock 数据编写导出功能的测试用例，验证内联完整性、交互保真和脱敏正确性。
10. 跑 UI 与导出相关 gate：运行导出相关的静态检查和集成测试，确保不破坏已有 UI gate。

## 文件边界

- 导出功能入口：`src/session_browser/web/mhtml.py` 或等效后端导出模块。
- Jinja 模板：`java/web/src/main/resources/templates/` 下导出相关模板。
- 静态资源内联：`java/web/src/main/resources/static/` 下需要内联的 CSS/JS。
- 导出测试：`tests/backend/test_mhtml_export.py` 或等效测试文件。（历史 Python 路径，当前验证使用 `java/` 对应模块测试与 `./scripts/session-browser.sh test`，不作为现行文件入口。）
- UI 导出按钮：session detail 模板中的导出触发元素。
- 导出 gate：`scripts/gates/checks/` 下导出相关检查脚本。

不要跨边界修改后端 parser 或 Java 产品代码。不要在导出文件中引入外部网络依赖。

## 验证门禁

以下门禁不是每次都全部运行，但触发时 required gate 不能 skipped：

- `./java/gradlew -p java :java:web:test --tests '*WebStaticResourceContractTest'` — session detail 静态检查。
- `python3 scripts/gates/cli.py run --mode incremental --gate browserBehaviorTests` — 真实浏览器交互检查。
- fixture-based 导出测试 — 验证内联完整性和交互保真。
- `python3 scripts/gates/cli.py run --mode incremental --gate agentConfigurationPolicy` — agent parity gate。

选择策略：

- 只改导出后端 → 至少运行 fixture-based 导出测试。
- 改导出模板/内联 → 追加 `webResourceContracts`。
- 改导出交互 → 追加 `browserBehaviorTests`。
- 收口前 → 运行全部 UI 与导出相关 gate。

## 输出格式

使用 `templates/report.md` 模板。变更摘要必须包含：

- 改动的导出功能、模板、内联资源文件列表。
- 内联资源完整性说明。
- 离线交互保真风险评估。
- 敏感字段脱敏状态。
- 门禁运行结果。
- 导出文件大小和性能影响。
- 后续风险或 TODO。
