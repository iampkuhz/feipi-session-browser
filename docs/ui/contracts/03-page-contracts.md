# 03 页面功能要求

本文件是 `docs/ui/` 的主入口。页面实现、测试和质量门应对齐本文件及同目录下的细分要求。

## 页面范围

- Dashboard：全局 session、agent、model、token 和失败工具概览。
- Sessions：session 检索、过滤、排序、分页和行跳转。
- Session Detail：单个 session 的 trace、payload 和归因解释。
- Projects：项目列表和项目级 session 概览。
- Project Detail：单个 project 的 session、agent 和 token 明细。
- Agent Detail：单个 agent 的深度统计和 session 列表。
- Glossary：术语解释和分类说明。

## Dashboard

- 展示 Projects、Sessions、Total Tokens、Failed Tools 四个核心指标。
- 展示 Session Trend 和 Token Trend。
- 图表支持按当前时间范围切换。
- Agent 汇总表展示 agent、session 数、token、失败工具和效率信息。
- Model Efficiency 表展示 model、provider、调用量和 token 表现。
- Dashboard 不展示独立 hero 区域。

## Sessions

- 支持关键词搜索。
- 支持 agent、project、date、token、status 等过滤。
- 支持排序、分页、page size 和行跳转。
- Session 标题、项目、agent、model、时间、token、失败状态必须可见。
- Active filters 可见，可逐项移除。
- 搜索或过滤后必须保留当前查询状态。

## Session Detail

- 只包含 Trace 和 Payload 两个主 tab。
- Trace 展示 round、user input、LLM call、tool call、subagent 和异常信号。
- Payload 展示 request、response、tool result 和 attribution。
- Round header 和非按钮区域点击可展开或收起。
- 全局只保留一个 Expand all / Collapse all 控制。
- Payload modal 必须可复制、可关闭、可滚动。

## Projects

- 展示项目名称、路径、session 数、agent、token、最近活动时间。
- 支持搜索、排序、分页和行跳转。
- 项目路径必须可读，过长时截断并提供 tooltip。
- tokenbar 与 Sessions 页面使用同一语义。

## Project Detail

- 展示项目概览指标。
- 展示该项目下 session 列表。
- 支持与 Sessions 页面一致的搜索、过滤、排序和分页。

## Agent Detail

- 展示单个 agent 的 session、token、model、tool 和失败情况。
- 支持 agent 切换。
- 展示该 agent 相关 session 列表。
- 不提供独立 Agents 列表页作为主导航入口。

## Glossary

- 展示术语、分类、说明和示例。
- 支持按分类查看。
- 术语解释必须服务页面理解。
