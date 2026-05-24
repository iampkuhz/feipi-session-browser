# 01 全局 UI 契约

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
- 有翻页的表格：只显示 `prev`、页码输入框、`next`。
- 当前首页不渲染 prev；当前尾页不渲染 next。

## Metric grid 规则

- 同一 metric grid 中所有 card 等宽。
- 不允许某个 card 因数字长而撑宽。
- 长数字必须缩写。

## 按钮/图标规则

- 每个 button 必须有 `data-action` 或 `href`。
- 每个 icon 必须在 `docs/ui/contracts/icon-behavior.md` 中说明含义。
- 可点击 icon 必须有 hover/focus/active 状态。
- 不可点击 icon 必须作为 decorative 或带 `aria-hidden="true"`。
