# Agent Detail 迁移参考

## 定位

Agent Detail 不再作为目标页面扩展。本文件只保留原 Agent Detail 高保真稿和旧规约中的有效信息结构，作为 Dashboard 单 agent scope 的迁移参考。

目标实现以 `docs/page-ui-specs/pages/01_dashboard.md` 为准。单 agent 深度统计必须在 Dashboard 中展示，不再通过独立 Agent Detail 页面承载。

## 迁移映射

- 原 Agent selector 迁移为 Dashboard Page Head 中的 agent scope selector。
- 原 KPI 信息迁移为 Dashboard KPI 区，并按当前 agent scope 重算。
- 原 `Agent Activity Trend` 迁移为 Dashboard Trend 总览区的 `Session Trend`、`Token Trend`、`Prompt Activity Trend` 三张卡。
- 原 `Model Mix` 迁移为 Dashboard 单 agent scope 的 `Model Mix` 组件。
- 原 `Tool Distribution` 迁移为 Dashboard 单 agent scope 的 `Tool Distribution` 组件。
- 原 `Failure Signals` 迁移为 Dashboard 单 agent scope 的 `Failure Signals` 组件。
- 原 `Model Efficiency Detail` 迁移为 Dashboard 单 agent scope 的 `Model Efficiency Detail` 表。
- 原 `Sessions` 表迁移为 Dashboard 单 agent scope 的 `Agent Sessions` 表。

## 保留字段

Dashboard 单 agent scope 必须保留下列信息：

- `Model Mix`：Model、Sessions、Session Share、Tokens、Token Share、Cache Read Ratio、Failed/session。
- `Tool Distribution`：Tool、Calls、Call Share、Tokens、Token Share、Failed、Failure Rate。
- `Failure Signals`：Signal Type、Count、Severity、Rate、Representative Session、Last Seen。
- `Model Efficiency Detail`：Model、Sessions、Avg input、Avg output、Cache read、Tool calls/session、Failed/session、Notes。
- `Agent Sessions`：Title、Project、Model、Tokens、Rounds、Tools、Failed、Duration、Updated。

## 禁止项

- 不新增 Agent Detail 页面专属功能。
- 不把 Agent Detail 加回 Sidebar 主导航。
- 不在 Dashboard 中提供 Agent Detail 跳转按钮。
- 不让 Agent Detail 定义新的共享组件样式。
