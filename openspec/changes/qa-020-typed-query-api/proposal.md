# Proposal: QA-020 Typed Query API、Filter、Sort 与 Pagination 契约

## 动机

Python 端使用 untyped dict/kwargs 传递查询参数，存在以下问题：
- SQL 注入风险：排序字段和过滤值直接拼接
- 参数校验分散：各层重复校验同一条件
- 缺乏编译期安全：无法在编译时发现参数错误

## 方案

新增 `java/query-api` 模块，建立 typed query API 端口层：

1. **分页**：`PageRequest`/`PageResult<T>` 支持 offset 和 cursor 两种分页模式
2. **排序**：`Sort` 值对象 + `SessionSortField`/`ProjectSortField` 枚举，编译期限定合法列
3. **过滤**：`AgentFilter`/`ProjectFilter`/`ModelFilter`/`AnomalyFilter`/`TitleFilter`/`FailureStatus` 单一维度过滤器
4. **复合**：`SessionListFilter`/`ProjectListFilter`/`DashboardFilter` 组合过滤器，不可变 + `with*` 方法链

## 影响

- 新增 1 个 Gradle 模块
- 新增 16 个 public 类型（含 package-info 和 marker）
- 新增 ~80 个测试用例
- 无 production 代码修改（仅 query ports）

## 风险

- 无当前消费者的 speculative 类型：本 task 创建的过滤器类型将在 QA-030 中被 repository 层消费，属于已确认的消费者
- API 冻结后修改成本高：通过 QA-010 契约审计已覆盖排序字段和过滤维度
