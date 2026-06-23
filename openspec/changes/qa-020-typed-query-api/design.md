# Design: QA-020 Typed Query API、Filter、Sort 与 Pagination 契约

## 1. 概述

本 design 建立 S4 stage 的 Java typed query API 端口层。实现最小 query ports 和 typed request/result，不提前创建 Web view model。

## 2. 模块边界

新增 `java/query-api` 模块，包 `com.feipi.session.browser.query.api`。

### 2.1 允许修改的文件

| 文件 | 职责 |
|------|------|
| `java/query-api/build.gradle.kts` | 模块构建配置 |
| `settings.gradle.kts` | 注册新模块 |
| `java/contract-tests/build.gradle.kts` | 添加 query-api 测试依赖 |
| `java/query-api/src/main/java/com/feipi/session/browser/query/api/*` | query API 类型 |
| `java/query-api/src/test/java/com/feipi/session/browser/query/api/*` | 单元测试 |
| `config/api-snapshots/java-public-api.txt` | API snapshot |

### 2.2 禁止修改

- `src/session_browser/**`
- `java/web/**`
- `java/scan-engine/**`

## 3. 类型设计

### 3.1 分页

| 类型 | 说明 | 校验位置 |
|------|------|----------|
| `PageRequest` | offset/cursor 分页请求，limit ∈ [1, 500]，offset ≥ 0 | factory 方法 |
| `PageResult<T>` | 分页结果，items 防御性拷贝，totalCount ≥ -1 | record compact constructor |

### 3.2 排序

| 类型 | 说明 |
|------|------|
| `SortOrder` | ASC/DESC 枚举，支持字符串解析 |
| `SessionSortField` | 会话排序列枚举，防 SQL 注入 |
| `ProjectSortField` | 项目排序维度枚举，防 SQL 注入 |
| `Sort` | 排序规范值对象，支持 session/project 两种上下文 |

### 3.3 过滤器

| 类型 | 说明 | 校验规则 |
|------|------|----------|
| `AgentFilter` | agent 标识过滤 | 非 null，trim 后无前后空白 |
| `ProjectFilter` | 项目键过滤 | 非 null，trim 后无前后空白 |
| `ModelFilter` | 模型名称过滤 | 非 null，trim 后无前后空白 |
| `AnomalyType` | 异常类型枚举 | 与 Python anomalies.py 对应 |
| `AnomalyFilter` | 异常类型过滤 | null 表示不过滤 |
| `TitleFilter` | 标题关键字过滤 | null/空表示不过滤，自动 trim |
| `FailureStatus` | 失败状态过滤 | ALL/FAILED_ONLY/SUCCESS_ONLY |

### 3.4 复合过滤器

| 类型 | 默认排序 | 默认分页 |
|------|----------|----------|
| `SessionListFilter` | ended_at DESC | offset=0, limit=50 |
| `ProjectListFilter` | last_active DESC | offset=0, limit=50 |
| `DashboardFilter` | — | offset=0, limit=50 |

## 4. 校验放置

| 数据/条件 | 校验位置 | 下游行为 |
|-----------|----------|----------|
| limit 范围 [1, 500] | `PageRequest` factory | repository 信任 |
| offset ≥ 0 | `PageRequest` factory | repository 信任 |
| sort field 合法性 | 枚举 `fromString()` | repository 信任列名 |
| agent 非空/无空白 | `AgentFilter.of()` | repository 信任绑定值 |
| project key 格式 | `ProjectFilter.of()` | repository 信任绑定值 |
| model 格式 | `ModelFilter.of()` | repository 信任绑定值 |

## 5. 不变量

- 所有过滤器不可变，通过 `with*` 方法创建新实例
- PageResult.items 防御性拷贝，不可变
- 排序字段通过枚举限定，无法注入非法 SQL
- 无 Optional 参数，无 Map DTO
- 无 Web/JDBC 依赖泄漏
