# Shell 状态要求

## 基础结构

- 页面根结构使用统一 app shell。
- Sidebar、Topbar、Main panel、Content 区域必须稳定。
- 页面内容通过 block 注入，不改变 shell 结构。

## Sidebar

- Sidebar 固定展示主导航。
- 当前页面高亮。
- 导航项文本和图标垂直居中。
- 不在 Sidebar 中维护低频工具入口。

## Topbar

- Topbar 展示当前位置和必要页面操作。
- Topbar 不展示长说明文案。
- 面包屑应帮助定位当前页面层级。

## 主内容

- 主内容区负责页面业务信息。
- 宽屏下主内容不偏左。
- 页面内容不应被 Sidebar 或 Topbar 遮挡。
- 页面内滚动区域必须明确。

## 状态页

- 404、错误页、空态页使用统一状态组件。
- 状态页必须给出可执行操作。
- 状态页不使用营销式 hero。
