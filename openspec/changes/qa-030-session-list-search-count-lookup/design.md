# Design: QA-030 Session List、Search、Count 与 Lookup 查询

## 1. 概述

迁移 Python `queries.py` 中 session list/search/count/get 四个查询到 Java。保持参数化 SQL、排序白名单、分页语义和空值处理。

## 2. 模块边界

### 2.1 允许修改的文件

| 文件 | 职责 |
|------|------|
| `java/index-sqlite/build.gradle.kts` | 添加 query-api 依赖 |
| `java/index-sqlite/src/main/java/.../SessionQueryRepository.java` | 会话只读查询仓库 |
| `java/index-sqlite/src/main/java/.../SessionResultSetMapper.java` | ResultSet 到 SessionRow 的行映射 |
| `java/index-sqlite/src/main/java/.../SessionListAggregate.java` | 过滤后聚合总量 record |
| `java/index-sqlite/src/test/java/.../SessionQueryRepositoryTest.java` | 单元测试 |
| `java/contract-tests/src/test/java/.../query/sessions/SessionQueryContractTest.java` | 契约测试 |
| `config/api-snapshots/java-public-api.txt` | API snapshot |

### 2.2 禁止修改

- `src/session_browser/**`
- `java/web/**`
- `java/scan-engine/**`

## 3. 类型设计

| 类型 | 可见性 | 说明 |
|------|--------|------|
| `SessionQueryRepository` | public | 四个查询方法，接收 `SessionListFilter` |
| `SessionResultSetMapper` | package-private | 行映射，避免列名泄漏 |
| `SessionListAggregate` | public record | 聚合结果，非负不变量 |

## 4. 查询方法

| 方法 | Python 对应 | SQL 结构 |
|------|------------|----------|
| `getSession(key)` | `get_session` | `SELECT ... WHERE session_key = ?` |
| `listSessions(filter)` | `list_sessions` | `SELECT ... WHERE ... ORDER BY ... LIMIT ? OFFSET ?` |
| `countSessions(filter)` | `count_sessions` | `SELECT COUNT(*) WHERE ...` |
| `listAggregate(filter)` | `get_sessions_list_aggregate` | `SELECT COUNT(*), COUNT(DISTINCT project_key), COALESCE(SUM(total_tokens), 0) WHERE ...` |

## 5. 校验放置

| 数据/条件 | 校验位置 | 下游行为 |
|-----------|----------|----------|
| 过滤值格式 | `SessionListFilter` 子过滤器 factory | repository 信任绑定值 |
| 排序字段合法性 | `SessionSortField` 枚举 | repository 信任列名 |
| 分页范围 | `PageRequest` factory | repository 信任 offset/limit |
| SQL 拼接 | repository | 只使用参数绑定 + 枚举列名 |

## 6. WHERE 子句构建

`buildFilterClauses` 方法统一构建 WHERE 子句，list/count/aggregate 三个查询共享：

1. agent 过滤 — `agent = ?`
2. 项目过滤 — `project_key = ?`
3. 模型过滤 — `model = ?`
4. 标题搜索 — `(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))`
5. 失败状态 — `failed_tool_count > 0` 或 `= 0`

## 7. 不变量

- 所有 SQL 使用参数化绑定
- 排序字段来自枚举白名单
- 读事务短生命周期
- 无 N+1 查询
- 查询只读，不修改数据库
