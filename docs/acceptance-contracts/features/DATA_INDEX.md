# 数据索引模块 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | SQLite 索引器（查询接口、只读连接） |
| 关联源码 | `src/session_browser/index/indexer.py`、`queries.py`、`writers.py`（只读） |
| 关联测试 | `tests/index/test_sessions_filters.py` |
| 主要风险 | 查询过滤逻辑不正确；只读连接无法读取 Java 创建的 schema |

> **SI-110 变更说明**：Python full/incremental scan 写路径已退休，
> 由 Java scan 引擎接管（SI-050 ~ SI-090）。
> 原 DATA-INDEX-001 ~ DATA-INDEX-011 的 scan 验证
> 迁移到 Java 侧测试（`java/**/src/test/**`）。

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| DATA-INDEX-001 | P0 | data | manual: 全量扫描已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-002 | P0 | data | manual: 增量扫描已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-003 | P0 | data | manual: 全量/增量一致性已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-004 | P0 | data | manual: 新文件场景已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-005 | P0 | data | manual: 文件修改场景已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-006 | P0 | data | manual: 坏 JSON 隔离已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-007 | P1 | data | manual: 文件删除后索引一致性已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-008 | P1 | data | manual: Qoder canonical 去重已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-009 | P1 | data | manual: Qoder 增量更新已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-010 | P1 | data | manual: Qoder 定位器展开已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-011 | P1 | data | manual: Qoder 项目路径契约已迁移到 Java | — | — | manual | — | — |
| DATA-INDEX-012 | P1 | data | 会话筛选查询（agent/project/model/title_like） | 调用 `list_sessions` 带不同过滤参数 | 返回的 session 数量与过滤条件匹配，WHERE 子句正确组合 | pytest | — | `tests/index/test_sessions_filters.py` |
