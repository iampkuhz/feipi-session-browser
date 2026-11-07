---
name: feipi-session-detail-ui-dev
disable-model-invocation: true
description: 用于 Session Detail UI、Pebble 模板、CSS、前端交互和视觉质量门相关开发；后端 parser 或 OpenSpec 编排不要使用。
---

# Session Detail UI 开发

只定位目标模板、CSS ownership 或相邻 JS handler；纯样式不预读 JS/无关模板。需要跨层约束才读 [UI 边界](references/ui-boundaries.md)。用合成 fixture，不读取真实 session。

- 复用现有 macro/class，样式归组件所有，不写 inline style。
- 开发反馈：布局用 `npm --prefix java/tests/playwright test -- session-detail-layout.spec.js`；交互用相邻 spec；资源结构用 `./java/gradlew -p java :java:web:test --tests '*WebStaticResourceContractTest'`。选能证明本次效果的一项，不固定叠加。局部浏览器用例不替代整套。
- 提交或交接按 `AGENTS.md`。最终 Gate 保留 `webStaticRules`、资源契约及浏览器完整发现，不额外重复相同套件。
- 仅在失败定位或审核 baseline 时读 [视觉规则](references/visual-gates.md)。报告实际视觉/交互效果与未覆盖风险。
