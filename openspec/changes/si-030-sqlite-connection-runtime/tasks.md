# SI-030 Tasks

## SI-030 [IMPLEMENT] SQLite Connection、PRAGMA、事务与单 Writer 基础设施

状态：完成

### 产物

- `java/index-sqlite/` 新增类型：
  - `PragmaConfig.java` — PRAGMA 配置 record
  - `ConnectionFactory.java` — 连接工厂
  - `WriteTransaction.java` — 显式写事务
  - `ReadTransaction.java` — 短生命周期只读事务
  - `WriteBatch.java` — 批量写入辅助
  - `WriteQueue.java` — 有界队列 + 单 writer 线程
  - `IndexConnection.java` — 连接入口
- `java/index-sqlite/src/test/` — 7 个测试类，全面覆盖
- `java/contract-tests/**/sqlite/SqliteRuntimeContractTest.java` — 运行时契约测试
- OpenSpec change: `si-030-sqlite-connection-runtime`
