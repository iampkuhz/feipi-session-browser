# SI-030 Proposal: SQLite Connection、PRAGMA、事务与单 Writer 基础设施

## Summary

实现 SQLite 连接管理基础设施：统一 PRAGMA 配置、显式事务控制、单 writer 队列和短生命周期只读事务。
写入通过有界队列串行化，读取通过独立连接并行执行。

## Changes

- `java/index-sqlite/` — 新增连接运行时类型：
  - `PragmaConfig` — PRAGMA 配置 record（journal_mode, synchronous, busy_timeout, foreign_keys）
  - `ConnectionFactory` — 连接工厂，创建并配置 JDBC 连接
  - `WriteTransaction` — 显式写事务，支持 commit/rollback
  - `ReadTransaction` — 短生命周期只读事务，避免 WAL checkpoint starvation
  - `WriteBatch` — 批量写入辅助，事务大小可配置
  - `WriteQueue` — 有界队列 + 单 writer 线程，保证写入串行化
  - `IndexConnection` — 连接入口，组合 writer 连接和读连接工厂
- `java/index-sqlite/**/test/` — 全面测试覆盖
- `java/contract-tests/**/sqlite/` — 运行时契约测试

## Scope

- 允许修改: java/index-sqlite/**, java/contract-tests/**/sqlite/**, java/test-support/**/sqlite/**
- 禁止触碰: src/session_browser/**, java/web/**

## Risk

低风险。新类型无现有消费者；与 SI-020 schema/migration 层协同工作。
