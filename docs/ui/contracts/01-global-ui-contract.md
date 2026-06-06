# 01 全局 UI 契约

## 页面功能标准 v3

- 当前页面功能标准见 `docs/ui/contracts/03-page-contracts.md`。
- 与旧版 HIFI/contract 条款冲突时，以页面功能标准 v3 为准。
- Sidebar 主导航只包含 Dashboard、Sessions、Projects；不提供独立 Agents 列表导航入口。
- Agent 列表信息归入 Dashboard，单个 agent 深度信息归入 Agent Detail。
- Session Detail 只保留 Trace / Payload 两个主 tab。
- 页面保持高密度桌面 UI；宽屏多余空间优先分配给主内容列、标题列、图表和明细表。
- 不允许出现 Dense / Comfortable / Columns / Export / Keyboard shortcuts 这类布局或工具按钮。
- 不允许删除已有核心页面、核心表格字段、搜索、过滤、排序、分页、行跳转、行展开能力。
- 所有不可用数据必须显示来源或不可用原因，不允许静默隐藏。

## 通用视觉规则

- 默认 light mode。
- 主内容区居中，宽屏不偏左。
- 左侧 sidebar 固定宽度，当前页面高亮明确。
- 页面术语用英文；中文只用于说明文档或内部注释。
- 信息密度高，但不能拥挤。
- 技术工具感：path/session id/model/token 等用 mono。
- 图标优先 emoji；同类组件图标尺寸一致。
- button/card 内图标与文字同一行时必须垂直居中。

## Token 展示规则

全部 token 数值使用缩写，精确到小数点后 1 位：

- `1700000` -> `1.7M`
- `20000` -> `20.0K`
- `950` -> `950`

禁止出现长整数 token：`1700000`、`1,700,000`。

## 表格规则

- th 与 td 同列对齐一致。
- 文本不能紧贴单元格边缘，必须有 padding。
- 可排序列和不可排序列要视觉区分。
- 表头不可全部显示可排序态。
- 有翻页的表格按页面功能标准 v3 使用当前产品风格：`Prev`、页码输入、总页数/总记录数、若干页码按钮、page size、`Next`。
- 当前首页不渲染或禁用 prev；当前尾页不渲染或禁用 next。

## Metric grid 规则

- 同一 metric grid 中所有 card 等宽。
- 不允许某个 card 因数字长而撑宽。
- 长数字必须缩写。

## 按钮/图标规则

- 每个 button 必须有 `data-action` 或 `href`。
- 每个 icon 必须在 `docs/ui/contracts/icon-behavior.md` 中说明含义。
- 可点击 icon 必须有 hover/focus/active 状态。
- 不可点击 icon 必须作为 decorative 或带 `aria-hidden="true"`。
