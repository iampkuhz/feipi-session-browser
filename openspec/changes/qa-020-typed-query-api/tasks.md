# Tasks: QA-020 Typed Query API、Filter、Sort 与 Pagination 契约

## QA-020

**类型**: IMPLEMENT
**状态**: completed

### 完成内容

1. 新增 `java/query-api` 模块，包含以下类型：
   - `SortOrder` — 排序方向枚举
   - `SessionSortField` — 会话排序列枚举
   - `ProjectSortField` — 项目排序维度枚举
   - `Sort` — 排序规范值对象
   - `PageRequest` — 分页请求（offset/cursor）
   - `PageResult<T>` — 分页结果
   - `AgentFilter` — agent 过滤器
   - `ProjectFilter` — 项目过滤器
   - `ModelFilter` — 模型过滤器
   - `AnomalyType` — 异常类型枚举
   - `AnomalyFilter` — 异常过滤器
   - `TitleFilter` — 标题关键字过滤器
   - `FailureStatus` — 失败状态过滤器
   - `SessionListFilter` — 会话列表复合过滤器
   - `ProjectListFilter` — 项目列表复合过滤器
   - `DashboardFilter` — Dashboard 过滤器
   - `QueryApiMarker` — 模块标记接口

2. 全面测试覆盖（~80 个测试用例）
3. 所有校验在 API factory 完成
4. 无 Optional 参数，无 Map DTO
5. API snapshot 更新
6. `./gradlew check` 全部通过
