# Project Detail 页面规约

## 定位

Project Detail 展示单个项目的 session、agent、token、tool 和失败热点，并提供项目内 session 明细。

## 页面布局

- 路由：`/projects/<project_key>`；模板：`project.html`。
- Page Head 左侧显示项目名，左侧前置 `Back to Projects`。
- Page Head 下方显示项目路径摘要，完整路径通过 hover tooltip 展示。
- KPI 区固定为 5 张卡片：`Sessions`、`Agents`、`Total Tokens`、`Cache Read Ratio`、`Failed Tools`。
- 分析区包含 `Project Token Trend`、`Agent Mix`、`Tool Hotspots`。
- 下方是项目内 `Sessions` 表格，复用 Sessions 页面压缩列结构。

## 控件和候选项

- 时间粒度候选项固定为 `Day`、`Week`、`Month`，只作用于 `Project Token Trend`。
- Agent Mix 中 agent badge 点击进入 Dashboard，并带上对应 agent scope 参数。
- Tool Hotspots 按 calls 降序展示。
- 项目内 Sessions 表搜索范围固定为 title 和 session id。
- 项目内 Sessions 表可排序列固定为 `Tokens`、`Workload`、`Failure`、`Updated`。

## 文字内容

- 返回按钮文案固定为 `Back to Projects`。
- KPI label 固定为 `Sessions`、`Agents`、`Total Tokens`、`Cache Read Ratio`、`Failed Tools`。
- 分析卡标题固定为 `Project Token Trend`、`Agent Mix`、`Tool Hotspots`。
- 项目内表格标题固定为 `Sessions`。

## 数据指标与口径

### KPI 区

1. `Sessions`
   - 一级值：当前 project 下 session 总数。
   - 二级指标固定为 `Today`、`7d Avg`、`Median Duration`。
2. `Agents`
   - 一级值：当前 project 下出现过的 agent key 去重数。
   - 二级指标固定为 `Claude Code`、`Qoder`、`Codex`。
   - 每个二级指标展示该 agent 在当前 project 下的 session 数。
3. `Total Tokens`
   - 一级值：当前 project 下 `Fresh + Cache Read + Cache Write + Output`。
   - 二级指标固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
4. `Cache Read Ratio`
   - 一级值：`Cache Read / Input-side Tokens`。
   - 二级指标固定为 `Eligible Sessions`、`Low-read Sessions`。
5. `Failed Tools`
   - 一级值：当前 project failed tool result 数。
   - 二级指标固定为 `Failure Rate`、`Affected Sessions`、`Repeated Failure Sessions`。
- `Active Period` 放在 Page Head 副信息区，格式固定为 `Active: <first seen> to <last active>`。

### Project Token Trend

- 图表类型固定为堆叠面积图。
- x 轴显示当前时间粒度的 range point。
- y 轴显示 total tokens。
- 堆叠层顺序固定为 Fresh、Cache Read、Cache Write、Output。
- 不渲染配套明细表；数值细节通过 hover tooltip 展示。
- tooltip 固定展示 Range point、Fresh、Cache Read、Cache Write、Output、Total Tokens、Cache Read Ratio。

### Agent Mix

- 图表类型固定为 100% 横向堆叠柱状图。
- 分段固定为 Claude Code、Qoder、Codex。
- 该卡不渲染配套表格。
- tooltip 固定展示 Agent、Sessions、Session Share、Tokens、Token Share、Failed Tools。

### Tool Hotspots

- 图表类型固定为横向柱状图。
- y 轴显示 tool name；x 轴显示 calls。
- 柱子排序固定为 calls 降序。
- 每个柱子右侧显示 failure rate。
- 不渲染配套表格。
- tooltip 固定展示 Tool、Calls、Tokens、Failed、Failure Rate。

### 项目内 Sessions 表

- 表格列固定为 `Session`、`Agent / Model`、`Tokens`、`Workload`、`Failure`、`Updated`。
- `Session`：session title、短 session id、git branch。
- `Agent / Model`：agent badge 和 model mono 文本。
- `Tokens`：统一 token cell。
- `Workload`：rounds、tools、subagents、duration 合并展示。
- `Failure`：failed tool result 数量。
- `Updated`：last event time。

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
