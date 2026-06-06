# Agents 列表页遗留约束

## 定位

当前代码仍存在 `/agents` 列表页和 Sidebar 入口；目标结构不提供独立 Agents 列表页。本文件只记录迁移期间的约束，避免后续 UI 优化继续扩展该页面。

## 页面布局

- 路由：`/agents`；模板：`agents.html`。
- 如果页面仍存在，页面结构必须保持简单：Page Head、KPI、All Agents 表、Agent / Model Efficiency 表。
- 不新增图表区、不新增页面专属复杂工具条。

## 控件和候选项

- All Agents 表行点击进入 Dashboard 的对应 agent scope。
- Agent / Model Efficiency 表可排序，但不新增过滤器。
- 不新增 `/agents` 页面独有搜索。

## 文字内容

- 页面标题固定为 `Agents`。
- 表格标题固定为 `All Agents` 和 `Agent/Model Efficiency`。
- 空态说明没有 agent 数据，并提供运行 scan 和返回 Dashboard 两个入口。

## 数据指标与口径

- KPI 可展示 Active Agents、Sessions、Projects、Total Tokens。
- All Agents 表列固定为 Agent、Provider、Sessions、Projects、Tokens、Tool Calls、Failed、Last active。
- Agent / Model Efficiency 表列固定为 Agent、Model、Sessions、Avg Duration、P95 Duration、Input-side、Avg Tools、Tools/R、Cache R、Failed/Session、Last active。
- Token cell、badge、排序、空态复用共享组件语义。

## 目标收敛

- All Agents 和 Agent / Model Efficiency 信息迁移到 Dashboard。
- 单个 agent 深度统计迁移到 Dashboard single agent scope。
- Sidebar 不再展示 Agents 主导航。
- 404 状态页不再把 Agents 作为核心返回入口。

## 禁止项

- 不新增 `/agents` 页面独有功能。
- 不以 `/agents` 为后续 UI 优化入口。
- 不让 legacy 页面定义新的共享组件样式。
