# 跨页面交互 验收用例

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 跨页面交互（侧边栏切换、分页、AJAX 部分渲染、复制操作、Profile 模态框、Timeline 交互） |
| 关联源码 | `java/web/src/main/resources/templates/base.html`（侧边栏）、各页面 JS |
| 关联测试 | `java/web/src/test/java/com/feipi/session/browser/web/` |
| 主要风险 | 侧边栏切换后布局不一致；AJAX 渲染与全页渲染结果不一致 |

## 验收用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| UI-INTERACTION-001 | P0 | interaction | 侧边栏切换（展开/折叠） | 点击侧边栏切换按钮 | body class 切换，sidebar 宽度变化，main 宽度相应调整 | Playwright | — | `java/tests/playwright/shell-states.spec.js` |
| UI-INTERACTION-002 | P0 | interaction | 会话列表筛选/排序/分页 | 在列表页执行交互 | URL 和 JSON rows DOM 状态同步，单次 next 只前进一页 | Playwright | — | `java/tests/playwright/sessions-list.spec.js` |
| UI-INTERACTION-003 | P0 | interaction | Sessions AJAX 部分渲染 | 发送 AJAX 请求到 sessions 端点 | 返回 HTML 片段正确渲染，无全页刷新 | pytest | — | `java/web/src/test/java/com/feipi/session/browser/web/api/SessionApiHandlerTest.java` |
| UI-INTERACTION-004 | P0 | interaction | 分页 hasNext 逻辑 | 检查分页 hasNext 计算 | 当前页 < 总页时 hasNext=True，否则 False | pytest | — | 待补充 |
| UI-INTERACTION-005 | P1 | interaction | 复制操作契约 | 点击 diagnostics copy action | 剪贴板写入当前 data-copy 值且交互无错误 | Playwright | — | `java/tests/playwright/session-detail.spec.js` |
| UI-INTERACTION-006 | P1 | interaction | Payload 模态框打开 | 点击 payload action | 模态框可见、内容可访问并可关闭 | Playwright | — | `java/tests/playwright/session-detail.spec.js` |
| UI-INTERACTION-007 | P1 | interaction | Timeline 可扩展性 | 操作展开/折叠控制 | 展开后显示详情，折叠后隐藏且 aria 状态同步 | Playwright | — | `java/tests/playwright/session-detail.spec.js` |
| UI-INTERACTION-008 | P1 | visual | Timeline 预览 | 检查 Timeline 预览渲染 | 预览行显示摘要信息，状态图标正确 | pytest | — | `java/web/src/test/java/com/feipi/session/browser/web/page/SessionDetailPageTest.java` |
| UI-INTERACTION-010 | P1 | interaction | 查询状态管理 | 验证筛选/排序/分页状态同步 | query params 与当前状态一致 | pytest | — | 待补充 |
| UI-INTERACTION-011 | P2 | interaction | 键盘快捷键（空白待补充） | 待补充 E2E 测试 | 快捷键触发预期操作 | Playwright | — | 待补充 |
| UI-INTERACTION-012 | P2 | interaction | 跨页面导航流（空白待补充） | 待补充 E2E 测试 | 从列表页点击行跳转到详情页，URL 正确 | Playwright | — | 待补充 |
