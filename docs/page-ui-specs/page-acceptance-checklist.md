# 页面验收清单

## 通用

- [ ] Sidebar 目标主导航为 Dashboard、Sessions、Projects；当前页高亮。
- [ ] Topbar 面包屑清晰；Footer 保持只读本地语义。
- [ ] Page Head、Card、Table、Badge、Token Cell、Pagination、Tooltip、Modal 复用共享 contract。
- [ ] 页面文件按布局、控件、文案、数据口径、交互、状态和禁止项逐项对齐。
- [ ] 文本不重叠；长路径、session id、model、token 使用截断并提供 tooltip。
- [ ] 搜索、过滤、排序、分页状态可见且不丢失上下文。
- [ ] 无数据、过滤无结果、错误、404 都有明确原因和下一步。
- [ ] 无 Dense、Comfortable、Columns、Export、Keyboard shortcuts。
- [ ] 无全局搜索入口；搜索只存在于需要检索当前列表的页面内。

## Dashboard

- [ ] 有 agent scope selector，并影响 KPI、trend、token 分析和 scope 分支区。
- [ ] KPI 固定为 Projects、Sessions、Total Tokens、Prompt Activity、Cache Read Ratio、Failed Tools，每张卡有一级值和二级指标。
- [ ] Day 显示最近 30 天，x 轴 `MM-DD`；Week 显示最近 20 个 ISO week；Month 显示最近 12 个月。
- [ ] Trend 总览区固定为 Session Trend、Token Trend、Prompt Activity Trend 三张同级卡，图表和摘要表同时可见。
- [ ] Token 分析区固定为 Token Trend by Composition 和 Cache Health；Cache Health 只画 Cache Read Ratio 折线，Fresh spike 使用异常标记。
- [ ] All agents scope 展示 Agent Contribution Comparison、All Agents、Agent / Model Efficiency。
- [ ] 单 agent scope 展示 Model Mix、Tool Distribution、Failure Signals、Model Efficiency Detail、Agent Sessions。
- [ ] 不展示 Hot Sessions & Signals，不展示全局搜索，不展示独立 Agents 导航入口，不提供 Agent Detail 跳转入口。

## Sessions

- [ ] 搜索覆盖标题、project、agent、model、session id。
- [ ] 过滤覆盖 agent、model、project、status、failure。
- [ ] 表格列完整：Title、Project、Agent、Model、Tokens、Rounds、Tools、Subagents、Duration、Updated。
- [ ] Tokens cell 为数字 + tokenbar + tooltip。
- [ ] 行跳转、排序、分页和 active filters 均可用。

## Session Detail

- [ ] 目标主 tab 只有 Trace、Payload。
- [ ] Hero 覆盖基础 KPI、Token Timeline + Cache Health、Tool Cost & ROI、Bug Mining、Context Budget。
- [ ] Trace 无 sidecar；round 全宽；全局只有一个 Expand all / Collapse all。
- [ ] Round 非按钮区域可 toggle；LLM/subagent call 有 request/response attribution 和 payload 入口。
- [ ] Payload 左侧选择 call，右侧展示 attribution 与 raw request/response。

## Projects

- [ ] 表格列完整：Project、Agents、Sessions、Tokens、Tools、Failed、Last Active。
- [ ] 多 agent 显示多个独立 badge。
- [ ] 搜索、排序、分页、行跳转和 token cell 可用。

## Project Detail

- [ ] 顶部展示项目名、返回入口、路径摘要和完整路径。
- [ ] KPI 覆盖 sessions、agents、tokens、cache reuse、failed tools、active period。
- [ ] 有 Project Token Trend、Agent Mix、Tool Hotspots。
- [ ] 项目内 sessions 表复用 Sessions contract。

## Agent Detail 迁移

- [ ] Agent Detail 不作为目标页面扩展。
- [ ] 原 Agent Detail 的 Model Mix、Tool Distribution、Failure Signals、Model Efficiency Detail、Sessions 信息并入 Dashboard 单 agent scope。
- [ ] Dashboard 的 agent 行点击切换 scope，不跳转到 Agent Detail。

## Token Glossary 和状态页

- [ ] Glossary 覆盖 token 组成、派生指标、provider 映射和 badge reference。
- [ ] Glossary 搜索无结果状态可见。
- [ ] 404、Error、空态使用统一状态组件，并提供可执行入口。
