# 07 页面数据要求

## 数据展示

- 页面必须展示数据来源能支持的核心字段。
- 不可用数据必须展示原因。
- 不允许静默隐藏缺失字段。
- 数字展示使用统一格式。
- 时间展示必须可比较，列表中保持同一格式。

## Session 数据

- Session 列表展示标题、project、agent、model、时间、token、状态。
- Session Detail 展示 round、LLM call、tool call、payload 和 attribution。
- trace 与 payload 必须能互相定位。

## Token 数据

- Token 分类包括 fresh、read、write、out。
- Token 总量和分段占比必须一致。
- tokenbar tooltip 必须展示各分类数量和占比。
- 缺失 token 时展示不可用原因。

## Agent 和 Model 数据

- Agent 名称、provider、model、session 数、token 和失败工具必须可区分。
- Model Efficiency 展示调用量、token 和效率指标。
- 多 agent 数据不能合并成不可拆分字符串。

## Project 数据

- Project 列表展示项目名称、路径、session 数、agent、token、最近活动。
- Project Detail 展示项目内 session 明细。
- 项目路径过长时截断并提供完整 tooltip。

## 空态

- 无数据页面展示明确空态和可执行下一步。
- 过滤无结果展示当前过滤条件和清除入口。
- 图表无数据不渲染空白坐标区。
