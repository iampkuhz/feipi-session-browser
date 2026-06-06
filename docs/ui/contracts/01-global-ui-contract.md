# 01 全局 UI 要求

## 页面基线

- 页面面向桌面端高密度使用场景。
- 主内容区必须为扫描、比较和重复操作优化。
- 页面应保持信息完整，不用营销式 hero 或装饰卡片占用首屏。
- 宽屏空间优先分配给主内容列、标题列、图表和明细表。
- 页面不能因为视觉留白减少核心字段、操作或反馈。

## 导航

- Sidebar 主导航包含 Dashboard、Sessions、Projects。
- Agent 汇总信息在 Dashboard 呈现。
- Agent Detail 通过 Dashboard 行跳转或详情选择器进入。
- 当前页面必须有明确高亮状态。
- 顶栏展示当前页面位置和必要操作，不承载说明文案。

## 信息密度

- 页面标题、指标、筛选、表格和图表之间保持紧凑间距。
- 表格和列表优先展示可操作信息。
- 长路径、session id、model、token 数值使用 mono 或 tabular number。
- 文本不得重叠；空间不足时使用截断、tooltip 或横向滚动。

## Token 展示

- Token 数值必须缩写显示，保留一位小数。
- 示例：`1700000` 显示为 `1.7M`，`20000` 显示为 `20.0K`。
- Token cell 固定为数值加 tokenbar。
- tokenbar hover 显示分类、数量和占比。

## 表格

- 表格列宽必须稳定。
- 文本列左对齐，数值列使用 tabular number。
- 可排序列必须有可见排序入口和当前排序状态。
- 分页表格必须包含上一页、下一页、页码、总数和 page size。
- 表格不能压缩到字段重叠。

## 禁止项

- 不维护 Dense、Comfortable、Columns、Export、Keyboard shortcuts 这类布局工具按钮。
- 不维护同一组件的多套同义 class 或视觉风格。
- 不用隐藏样式、别名样式或补丁样式承载当前页面。
