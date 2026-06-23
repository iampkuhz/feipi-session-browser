# SI-030 Design: SQLite Connection、PRAGMA、事务与单 Writer 基础设施

## 1. 目标

建立连接工厂、read/write transaction、busy/retry 和单写者队列：
- 统一 PRAGMA 配置（WAL、synchronous、busy_timeout、foreign_keys）
- 写入通过有界队列串行化，解析线程不得直接 commit
- 批量事务大小可配置且有上限
- 读事务短生命周期，避免 WAL checkpoint starvation
- 取消和 shutdown 清空/回滚语义明确

## 2. 架构

### 2.1 类型定义

| 类型 | 职责 | 消费者 |
|------|------|--------|
| `PragmaConfig` record | PRAGMA 配置：journal_mode、synchronous、busy_timeout、foreign_keys | ConnectionFactory, IndexConnection |
| `ConnectionFactory` | 创建并配置 JDBC 连接，统一应用 PRAGMA | IndexConnection |
| `WriteTransaction` | 显式写事务：commit/rollback，try-with-resources 支持 | WriteQueue, SI-040+ |
| `ReadTransaction` | 短生命周期只读事务，REPEATABLE READ | IndexConnection |
| `WriteBatch` | 批量写入辅助，累积 SQL 在单事务中执行 | WriteQueue |
| `WriteQueue` | 有界队列 + 单 writer 线程，保证写入串行化 | IndexConnection |
| `IndexConnection` | 连接入口：管理 writer 连接、WriteQueue 和读连接工厂 | SI-040+ |

### 2.2 写入模型

```
调用线程                    WriteQueue                    Writer 线程
    |                          |                              |
    |-- submit(op) ----------->|                              |
    |                          |-- enqueue(op) ------------->|
    |                          |                              |-- op.execute(writerConn)
    |                          |                              |-- commit
    |<-- future.complete() ----|<-----------------------------|
```

- 所有写操作通过 WriteQueue.submit() 提交
- WriteQueue 内部单线程串行执行
- 队列有界（默认 64），满时阻塞
- 批量事务通过 WriteBatch 控制大小（默认 5000 条）

### 2.3 读取模型

```
调用线程                              读连接
    |                                   |
    |-- readTransaction() ------------->|
    |                                   |-- 独立连接，PRAGMA 配置
    |                                   |-- autoCommit=false (REPEATABLE READ)
    |-- 查询操作 ----------------------->|
    |<-- ReadTransaction.close() -------|
    |                                   |-- 恢复 autoCommit，关闭连接
```

- 每次 readTransaction() 创建独立连接
- WAL 模式允许并发读写
- 读连接短生命周期，避免 WAL checkpoint starvation

### 2.4 关闭语义

| 操作 | 行为 |
|------|------|
| WriteQueue.shutdown() | 不再接受新任务，等待已排队任务完成 |
| WriteQueue.cancelPending() | 立即取消所有待处理任务 |
| IndexConnection.close() | 先 shutdown WriteQueue，再关闭 writer 连接 |

## 3. 校验放置

| 校验 | 位置 | 理由 |
|------|------|------|
| PRAGMA 参数 | PragmaConfig compact constructor | 连接配置边界 |
| PRAGMA 应用 | PragmaConfig.apply + ConnectionFactory.create | 连接创建边界 |
| PRAGMA 验证 | PragmaConfig.verify | 连接配置后验证 |
| 事务边界 | WriteTransaction/ReadTransaction | 事务管理边界 |
| 批量上限 | WriteBatch.checkCapacity | 写入批次边界 |
| 队列状态 | WriteQueue.submit | 队列入口 |

## 4. 测试覆盖

| 场景 | 测试 | 文件 |
|------|------|------|
| PRAGMA 默认值/自定义/应用/验证 | PragmaConfigTest | index-sqlite |
| 连接创建/PRAGMA/资源管理 | ConnectionFactoryTest | index-sqlite |
| 事务 commit/rollback/自动回滚 | WriteTransactionTest | index-sqlite |
| 只读事务生命周期 | ReadTransactionTest | index-sqlite |
| 批量写入/上限/事务原子性 | WriteBatchTest | index-sqlite |
| 单 writer/并发提交/取消/关闭 | WriteQueueTest | index-sqlite |
| 并发读写/单 writer 保证/关闭 | IndexConnectionTest | index-sqlite |
| PRAGMA 契约/集成/单 writer | SqliteRuntimeContractTest | contract-tests |

## 5. Acceptance criteria

- 并发 reader + 单 writer 通过 ✓
- 两个 writer 不会隐式并发 ✓
- BUSY、cancel、crash 有确定测试 ✓
- 连接/statement 全部关闭 ✓
