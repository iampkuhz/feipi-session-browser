# UI 边界定义

本文件定义 session detail UI 开发的模板、CSS、JS 边界，帮助开发者快速定位修改范围和约束。

## 模板边界

- Session detail 页面使用 Jinja2 模板引擎。
- 模板文件位于 `src/templates/` 目录下。
- 复用已有 macro，不重新发明组件。
- 修改 macro 前必须搜索所有调用点，确认不会影响其他页面。
- 模板中不直接嵌入 `<style>` 或 inline style。
- 模板中不嵌入处理 `innerHTML` 的脚本；静态 JS 变更不得新增 raw `innerHTML`，并必须通过 catalog Gate
  `webStaticRules` 的 Java `raw-innerhtml` rule 校验。

## CSS ownership

- CSS 文件按功能区域划分 ownership，每个规则必须有明确的 owner。
- 使用 catalog Gate `webStaticRules`（内部 Java `css-ownership` rule）校验 ownership 合规性；完整报告继续
  写入按运行隔离的 artifact。
- 新增 CSS 规则必须放到对应 owner 的文件中，不新增无 owner 的全局样式。
- CSS 类名使用项目已有的命名约定，不新发明一套命名体系。
- 不使用全局 id selector（`#some-id`），优先使用 class selector。

## JS action handler

- JS 交互事件通过 action handler 模式管理。
- 使用 `browserBehaviorTests` 的真实浏览器交互校验 handler，不再维护正则式旁路检查。
- 删除模板中的按钮时必须同步删除对应的 JS handler。
- 新增 JS handler 时必须确保有对应的模板元素触发它。
- 不在 JS 中直接操作 DOM 样式，通过 CSS class 切换实现。

## Session Detail Shell

- Session detail shell 是页面的外层容器，控制整体布局结构。
- Shell 变更影响所有子组件的布局，必须运行 `npm --prefix java/tests/playwright test -- session-detail-layout.spec.js`。
- Shell CSS 由 `webResourceContracts` 守护，不允许随意修改 shell 类名。
- Layout 变更应优先消除 inline style；只有经审阅确认保留时，才显式更新
  `java/tests/quality-gates/config/web-quality-baselines.json` 的 `rules.layout-inline-style.entries`。

## CSS 当前命名与 ownership

- 样式类使用当前组件语义和 BEM 命名。
- `webStaticRules` 中的 `css-ownership` 检查 selector 归属。
- `currentVersionPolicy` 检查内部标识是否稳定且无版本后缀。
- 全局样式必须有明确 owner，组件样式放在对应 ownership 区域。

## 无真实 session 原则

- 所有 UI 测试和 fixture 必须使用 mock 数据或合成的 fixture 页面。
- 不读取、不输出、不复制真实 `~/.claude`、`~/.codex`、`~/.qoder` session 文件。
- Fixture 页面应覆盖典型的 session detail 场景：多轮对话、工具调用、长文本、空状态。
- 截图和视觉回归测试只使用 fixture 数据。

## 常见反模式

1. **单独文本框式散乱 CSS**：每个样式规则散落在不同文件中，没有统一 ownership，导致样式冲突和覆盖。
2. **新增全局 id selector**：使用 `#some-id` 选择器绕过 class 体系，破坏 CSS ownership 模型。
3. **使用 inline style 绕过 gate**：在模板中直接写 `style="..."` 绕过 CSS ownership 检查，被 catalog Gate `webStaticRules` 的 `layout-inline-style` rule 拦截。
4. **删除按钮但不删 JS handler**：模板中移除了按钮元素，但对应的 JS 事件绑定仍然存在，导致 `browserBehaviorTests` 报错或运行时错误。
5. **修改 macro 不检查所有调用点**：只修改了 macro 定义，没有搜索和验证所有使用该 macro 的页面，导致其他页面渲染异常。
6. **为了截图通过隐藏内容**：使用 `display: none` 或 `visibility: hidden` 隐藏有问题的元素来通过视觉回归测试，掩盖了真实的 UI 问题。
7. **使用真实 session 做 fixture**：将真实用户的 session 数据复制到仓库中做 UI 测试，违反隐私原则。
8. **把 skipped Playwright 当 PASS**：Playwright gate 被 skip 后在报告中标记为 PASS，实际未验证交互正确性。
