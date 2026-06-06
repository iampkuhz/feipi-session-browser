# Project Detail 页面规约

## 定位

Project Detail 展示单个项目的 session、agent、token、tool 和失败热点，并提供项目内 session 明细。

## 页面布局

- 路由：`/projects/<project_key>`；模板：`project.html`。
- Page Head 左侧显示项目名，左侧前置 Back to Projects。
- Page Head 下方显示项目路径摘要，完整路径可 hover 查看。
- KPI 区固定为 6 张卡片。
- 分析区包含 Project Token Trend、Agent Mix、Tool Hotspots。
- 下方是项目内 Sessions 表格，复用 Sessions 页面表格结构。

## 控件和候选项

- 时间粒度候选项固定为 `Day`、`Week`、`Month`，只作用于 Project Token Trend。
- Agent Mix 中 agent badge 可点击进入 Dashboard，并带上对应 agent scope 参数。
- Tool Hotspots 支持按 calls、tokens、failure rate 排序。
- 项目内 Sessions 表可搜索 title 和 session id。
- 项目内 Sessions 表可排序列固定为 Tokens、Rounds、Tools、Failed、Duration、Updated。

## 文字内容

- 返回按钮文案固定为 `Back to Projects`。
- KPI label 固定为 Sessions、Agents、Input-side Tokens、Output Tokens、Cache Reuse、Failed Tools。
- 分析卡标题固定为 `Project Token Trend`、`Agent Mix`、`Tool Hotspots`。
- 项目内表格标题固定为 `Sessions`。

## 数据指标与口径

- Sessions：当前 project 下 session 总数。
- Agents：当前 project 下出现过的 agent 数，按 agent key 去重。
- Input-side Tokens：Fresh + Cache Read + Cache Write。
- Output Tokens：模型可见输出 token。
- Cache Reuse：Cache Read / Input-side Tokens。
- Failed Tools：当前 project failed tool result 数。
- Active Period：first seen 到 last active；不作为 KPI 固定卡时放在 Page Head 副信息区。
- Project Token Trend 按当前 project 聚合 token，tooltip 显示四类 token 和总量。
- Agent Mix 展示 agent、sessions、tokens、failed tools 占比。
- Tool Hotspots 展示 tool name、calls、tokens、failed、failure rate。
- 项目内 Sessions 表列固定为 Title、Agent、Model、Tokens、Rounds、Tools、Failed、Duration、Updated。

## 交互逻辑

- 切换 Day/Week/Month 重算 Project Token Trend，不影响项目内 Sessions 表。
- 点击 agent badge 进入 Dashboard 的对应 agent scope。
- 点击 session 行进入 Session Detail。
- 点击复制 session id 不触发行跳转。
- Hover 图表点显示精确数值和百分比。
- Hover 长路径、长 model、长 session id 显示完整值。

## 状态

- project 不存在：展示错误状态和 Back to Projects。
- project 加载失败：展示错误状态和 Back to Projects。
- project 内无 sessions：展示空态和 View all sessions。
- 图表无数据：显示图表卡片内空态，不渲染空白坐标。

## 禁止项

- 不在项目页重新发明一套 Sessions 表格样式。
- 不静默隐藏路径、agent、model、失败、token 缺失原因。
- 不把跨项目数据混入当前 project 指标。
