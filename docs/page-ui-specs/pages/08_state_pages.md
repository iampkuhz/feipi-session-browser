# 状态页规约

## 定位

404、Error、页面级空态和过滤无结果状态使用统一状态组件，给出明确原因和下一步操作。

## 页面布局

- 404 模板：`404.html`；Error 模板：`error.html`。
- 状态页加载 `states.css`，复用统一 `state-panel` 组件和共享 empty/error state 组件。
- 状态页内容居中于主内容区，不覆盖 Sidebar、Topbar、Footer。
- Error details 使用 details/summary，原始错误放可滚动 pre。

## 控件和候选项

- 404 页面操作入口固定为 Dashboard、Projects、Sessions。
- Error 页面操作入口固定为 Dashboard。
- 页面级空态固定提供一个主操作和一个次操作。
- 过滤无结果状态固定提供 `Clear current filter` 和 `Clear all filters` 两个操作。

## 文字内容

- 404 标题固定为 `Page Not Found`。
- Error 标题固定为 `Something Went Wrong`。
- 空态标题必须说明当前页面没有哪类数据，例如 `No sessions indexed yet`。
- 过滤无结果标题必须说明当前条件无匹配，例如 `No sessions match your current filters`。
- 错误详情标题固定为 `Error details`。

## 数据与安全

- 404 返回 status 404。
- Error 返回 status 500。
- Error details 只展示必要错误摘要；不得泄露密钥、token、真实 session 原文、个人敏感路径。
- 状态页必须有合适的 `role` 和 `aria-live`。

## 交互逻辑

- 点击 Dashboard 返回 `/dashboard`。
- 点击 Projects 返回 `/projects`。
- 点击 Sessions 返回 `/sessions`。
- 展开 Error details 只影响当前状态面板，不改变 URL。
- `Clear current filter` 只清除当前触发无结果的过滤条件。
- `Clear all filters` 清除当前页面全部搜索和过滤条件。

## 状态

- 404 不显示 Error details。
- Error 没有 error body 时隐藏 details。
- 空态操作不可用时必须说明原因，不显示无效按钮。

## 禁止项

- 不使用营销式 hero。
- 不展示不可执行按钮。
- 不把 Agents 作为核心返回入口。
