# Proposal: QA-030 Session List、Search、Count 与 Lookup 查询

## 动机

Python 端 `queries.py` 实现了 session list、search、count 和 lookup 四个核心查询，使用 untyped kwargs 和字符串拼接。需要迁移到 Java，保持参数化 SQL、排序白名单、分页语义和空值处理。

## 方案

在 `java/index-sqlite` 模块新增会话只读查询仓库：

1. **`SessionQueryRepository`** — 四个查询方法：`getSession`、`listSessions`、`countSessions`、`listAggregate`
2. **`SessionResultSetMapper`** — 显式列到 `SessionRow` 的行映射器
3. **`SessionListAggregate`** — 过滤后聚合总量 record

所有 SQL 使用参数化绑定（`?`），排序字段通过 `SessionSortField` 枚举白名单限定，无 SQL 注入风险。

## 影响

- 新增 3 个 production 类型（`SessionQueryRepository`、`SessionResultSetMapper`、`SessionListAggregate`）
- 新增 `java/index-sqlite` 对 `java/query-api` 的依赖
- 新增 ~30 个单元测试 + ~15 个契约测试
- 无 Python 代码修改

## 风险

- 查询行为与 Python 差异：通过契约测试覆盖关键场景
- 性能回归：使用相同的 SQL 结构，无 N+1 风险
