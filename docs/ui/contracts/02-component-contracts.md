# 02 组件要求

## Page Head

- 每个主页面必须有 Page Head。
- Page Head 包含页面标题、简短副标题和必要的右侧操作。
- Page Head 不展示使用说明或快捷键说明。

## Card

- Card 只用于承载独立信息组、重复项、modal 或工具面板。
- 页面 section 不应包在额外大卡片中。
- Card 内部标题、操作和内容区域必须有稳定间距。

## Button

- 命令按钮必须有 `data-action` 或 `href`。
- 图标按钮必须有 `aria-label` 或等价可访问名称。
- 主操作、次操作、危险操作必须有明确视觉区分。
- 禁止用纯文本胶囊替代可识别图标按钮。

## Badge

- Agent、Model、Provider、Status、Severity 使用 badge。
- 多个 agent 或 model 必须展示为多个独立 badge。
- Badge 文案不得合并成长字符串。

## Data Table

- 表头排序按钮覆盖整个表头单元格。
- hover 区域必须和可点击区域一致。
- 主列吸收宽屏空间；短字段列保持固定宽度。
- 行点击、展开、复制、跳转等行为必须可见且稳定。

## Token Cell

- Token cell 包含总量和 tokenbar。
- tokenbar segment 颜色语义跨页面一致。
- tooltip 行包含分类、数量、占比。
- tooltip 数值右对齐。

## Chart

- 图表必须有标题、口径、legend、tooltip。
- tooltip 必须给出精确数值。
- 图表颜色语义必须与 agent/token 分类一致。
- 无数据时显示明确空态，不渲染空白图。

## Modal 和 Drawer

- Modal 必须支持关闭按钮、Esc 关闭和遮罩关闭。
- Payload、request、response、attribution 使用 modal 或 drawer 展示。
- 弹层内容必须可滚动，不能撑破视口。
